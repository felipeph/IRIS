import re
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt

from src.core.pipeline import PipelineStage
from src.core.project import Project, ProjectItem
from src.core.config import config
from src.modules.video_edit.namer import generate_edited_video_name, resolve_edited_output_path
from src.modules.video_edit.session import group_videos_into_sessions, parse_item_datetime, parse_duration_seconds
from src.modules.video_edit.renderer import render_edited_video, get_video_stream_info
from src.modules.timelapse.notifier import send_windows_toast, send_ntfy_notification

console = Console()

def parse_speed_arg(speed_input: Any, default: float = 1.0) -> float:
    """Converte entradas como '2x', '0.5x', 2, 2.0 em float."""
    if speed_input is None:
        return default
    if isinstance(speed_input, (int, float)):
        return float(speed_input)
    s_str = str(speed_input).strip().lower().replace("x", "")
    try:
        return float(s_str)
    except ValueError:
        return default

class VideoEditStage(PipelineStage):
    """
    Etapa 6: Edição e Upscale de Vídeos 4K UHD para 7_Video_Editado_4K.
    Identifica arquivos categorizados como 'video', aplica seleção interativa,
    suporta processamento individual ou junção de sessão, trimming configurável,
    controle de velocidade (--speed=Nx), teto de 60 FPS, Lanczos 4K e deband 16-bit.
    """

    def run(self, project: Project, **kwargs) -> bool:
        dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
        ve_config = dict(config.get("modules.video_edit", {}))

        # Sobrescrita de parâmetros via kwargs / CLI
        if "speed" in kwargs and kwargs["speed"] is not None:
            ve_config["speed"] = parse_speed_arg(kwargs["speed"])
        else:
            ve_config["speed"] = parse_speed_arg(ve_config.get("speed", 1.0))

        if "mode" in kwargs and kwargs["mode"]:
            ve_config["mode"] = str(kwargs["mode"]).lower()
        if "strip_audio" in kwargs and kwargs["strip_audio"] is not None:
            ve_config["strip_audio"] = bool(kwargs["strip_audio"])
        if "trim_seconds" in kwargs and kwargs["trim_seconds"] is not None:
            ve_config["trim_seconds"] = float(kwargs["trim_seconds"])
        if "trim_enabled" in kwargs and kwargs["trim_enabled"] is not None:
            ve_config["trim_enabled"] = bool(kwargs["trim_enabled"])
        if "target_fps" in kwargs and kwargs["target_fps"] is not None:
            ve_config["target_fps"] = int(kwargs["target_fps"])
        if "render_profile" in kwargs and kwargs["render_profile"]:
            ve_config["render_profile"] = str(kwargs["render_profile"]).lower().strip()
        else:
            ve_config["render_profile"] = str(ve_config.get("render_profile", "fast")).lower().strip()

        # 1. Buscar vídeos do projeto
        all_items = project.items
        video_items = [it for it in all_items if it.category == "video"]

        if not video_items:
            console.print(f"[cyan]Nenhum arquivo de vídeo identificado no projeto '{project.name}'. Etapa concluída.[/cyan]")
            return True

        # 2. Agrupar vídeos em sessões de trabalho
        mode = ve_config.get("mode", "individual")
        session_interval = float(ve_config.get("session_interval_minutes", 10.0))
        sessions = group_videos_into_sessions(video_items, mode=mode, session_interval_minutes=session_interval)

        total_sessions = len(sessions)
        speed_factor = ve_config.get("speed", 1.0)
        target_fps = ve_config.get("target_fps", 60)
        speed_label = f"{speed_factor}x"
        render_profile = ve_config.get("render_profile", "fast")

        console.print(f"\n[bold cyan]=== Etapa 6: Edição e Upscale de Vídeos 4K ({len(video_items)} clipe(s) em {total_sessions} lote(s) | Modo: {mode.upper()} | Perfil: {render_profile.upper()} | Velocidade: {speed_label} | FPS Alvo: {target_fps}) ===[/bold cyan]")

        # 3. Exibir Tabela Rich com resumo dos itens e status
        summary_table = Table(title="Vídeos Detectados para Edição e Upscale 4K", show_header=True, header_style="bold magenta")
        summary_table.add_column("ID", justify="center", style="cyan", width=5)
        summary_table.add_column("Nome Original / Clipes", style="white")
        summary_table.add_column("Câmera", style="magenta")
        summary_table.add_column("Resolução Orig.", justify="center", style="yellow")
        summary_table.add_column("FPS Orig.", justify="center", style="cyan")
        summary_table.add_column("Duração Orig.", justify="right", style="green")
        summary_table.add_column("Status Render", style="bold")

        existing_records = project.get_edited_videos()
        existing_paths = {r.get("output_video_path") for r in existing_records}

        session_preview_data = []

        for idx, s_items in enumerate(sessions, 1):
            first_it = s_items[0]
            first_dt = parse_item_datetime(first_it)
            last_it = s_items[-1]
            last_dt = parse_item_datetime(last_it) if len(s_items) > 1 else None
            cam = first_it.meta_camera_model or first_it.meta_camera_make or "Camera"

            # Resoluções e durações
            w = first_it.meta_width or 1920
            h = first_it.meta_height or 1080
            fps_val = 30.0
            if first_it.meta_fps_str:
                try:
                    fps_val = float(first_it.meta_fps_str.replace("fps", ""))
                except Exception:
                    pass

            tot_dur = sum(parse_duration_seconds(it) for it in s_items)
            dur_min, dur_sec = divmod(int(round(tot_dur)), 60)
            dur_str = f"{dur_min:02d}:{dur_sec:02d}"

            # Nome provisório para checagem
            expected_name = generate_edited_video_name(
                first_dt=first_dt,
                last_dt=last_dt,
                camera_model=cam,
                orig_w=w,
                orig_h=h,
                target_w=ve_config.get("target_width", 3840),
                target_h=ve_config.get("target_height", 2160),
                orig_fps=fps_val,
                target_fps=target_fps,
                speed=speed_factor,
                trim_sec=ve_config.get("trim_seconds", 2.0) if ve_config.get("trim_enabled", True) else 0.0,
                audio_stripped=bool(ve_config.get("strip_audio", False)),
                duration_sec=tot_dur / speed_factor if speed_factor > 0 else tot_dur,
                clip_count=len(s_items)
            )
            out_cand = resolve_edited_output_path(dest_root, first_dt, expected_name)
            is_done = str(out_cand.resolve()) in existing_paths and out_cand.exists()
            status_desc = "[green]✔ Já Renderizado[/green]" if is_done else "[yellow]Pendente[/yellow]"

            if len(s_items) == 1:
                display_name = Path(first_it.staging_path).name
            else:
                display_name = f"{len(s_items)} clipes fundidos ({Path(first_it.staging_path).name} ...)"

            summary_table.add_row(
                str(idx),
                display_name,
                cam,
                f"{w}x{h}",
                f"{fps_val:.0f} fps",
                dur_str,
                status_desc
            )
            session_preview_data.append({
                "index": idx,
                "items": s_items,
                "first_dt": first_dt,
                "last_dt": last_dt,
                "camera": cam,
                "orig_w": w,
                "orig_h": h,
                "orig_fps": fps_val,
                "duration": tot_dur,
                "output_cand": out_cand,
                "is_done": is_done
            })

        console.print(summary_table)

        # 4. Seletor Interativo com Confirmação e Desmarcação
        interactive = kwargs.get("interactive", True)
        selected_indices = set(range(1, total_sessions + 1))

        if interactive:
            console.print("\n[dim]Pressione [ENTER] para processar todos os vídeos ou informe os IDs que deseja desmarcar.[/dim]")
            ans = Prompt.ask("Deseja continuar com todos os vídeos? [ENTER = Sim, ou digite 'desmarcar 1,3' ou '0' para cancelar]", default="S").strip().upper()

            if ans in ["0", "CANCELAR", "SAIR", "N"]:
                console.print("[yellow]Operação de edição de vídeo cancelada pelo usuário.[/yellow]")
                return False
            elif ans.startswith("DESMARCAR"):
                # Extrai números de desmarcação
                to_remove = [int(n) for n in re.findall(r'\d+', ans)]
                for r in to_remove:
                    selected_indices.discard(r)
                console.print(f"[cyan]Vídeos selecionados após desmarcação: {sorted(list(selected_indices))}[/cyan]")
            elif ans not in ["S", "SIM", ""]:
                # Pode ter digitado apenas os índices a remover
                to_remove = [int(n) for n in re.findall(r'\d+', ans)]
                if to_remove:
                    for r in to_remove:
                        selected_indices.discard(r)
                    console.print(f"[cyan]Vídeos selecionados após desmarcação: {sorted(list(selected_indices))}[/cyan]")

        if not selected_indices:
            console.print("[yellow]Nenhum vídeo selecionado para processamento. Etapa concluída.[/yellow]")
            return True

        force_render = kwargs.get("force_render", False) or kwargs.get("force_rerender", False)
        if not force_render and interactive:
            already_count = sum(1 for p in session_preview_data if p["index"] in selected_indices and p["is_done"])
            if already_count > 0:
                force_render = Confirm.ask(
                    f"\n[yellow]{already_count} vídeo(s) já existem renderizados no disco. Deseja re-renderizar e sobrescrever os vídeos?[/yellow]",
                    default=False
                )

        success_count = 0
        error_count = 0

        # 5. Renderização dos lotes selecionados
        active_sessions = [p for p in session_preview_data if p["index"] in selected_indices]
        total_active = len(active_sessions)

        for job_idx, sdata in enumerate(active_sessions, 1):
            out_path = sdata["output_cand"]
            s_items = sdata["items"]
            first_dt = sdata["first_dt"]
            last_dt = sdata["last_dt"]
            cam = sdata["camera"]
            orig_w = sdata["orig_w"]
            orig_h = sdata["orig_h"]
            fps_val = sdata["orig_fps"]
            tot_dur = sdata["duration"]

            console.print(f"\n[bold blue]-> Processando Vídeo [{job_idx}/{total_active}]: {out_path.name}[/bold blue]")

            if sdata["is_done"] and not force_render:
                console.print(f"[green]✔ Vídeo já renderizado previamente: {out_path.name}[/green]")
                success_count += 1
                continue

            # Resolve caminhos físicos reais dos arquivos de entrada
            clip_paths: List[Path] = []
            for it in s_items:
                candidate = Path(it.organized_path) if it.organized_path else Path(it.staging_path)
                if candidate.exists():
                    clip_paths.append(candidate)
                else:
                    console.print(f"[red]Aviso: Arquivo de vídeo de origem não encontrado: {candidate}[/red]")

            if not clip_paths:
                console.print(f"[red]Erro: Nenhum arquivo físico de vídeo encontrado para o lote.[/red]")
                error_count += 1
                continue

            # Renderiza com FFmpeg
            render_ok, encoder_used, err_msg, render_stats = render_edited_video(
                clip_paths=clip_paths,
                output_video_path=out_path,
                config=ve_config
            )

            if render_ok:
                final_dur = render_stats.get("final_duration_seconds", tot_dur / speed_factor)
                video_size_bytes = out_path.stat().st_size if out_path.exists() else 0

                # Compila metadados técnicos ricos para descrição do YouTube
                rich_meta = {
                    "camera_make": s_items[0].meta_camera_make or "Cam",
                    "camera_model": cam,
                    "orig_width": orig_w,
                    "orig_height": orig_h,
                    "orig_fps": fps_val,
                    "target_fps": target_fps,
                    "speed_factor": speed_factor,
                    "trim_seconds": render_stats.get("trim_seconds", 0.0),
                    "audio_stripped": render_stats.get("audio_stripped", False),
                    "clip_count": len(clip_paths),
                    "mode": mode,
                    "total_orig_duration_seconds": tot_dur,
                    "final_duration_seconds": final_dur,
                    "video_size_bytes": video_size_bytes,
                    "first_dt_iso": first_dt.isoformat() if first_dt else "",
                    "last_dt_iso": last_dt.isoformat() if last_dt else "",
                    "first_dt_formatted": first_dt.strftime("%d/%m/%Y às %H:%M:%S") if first_dt else "",
                    "last_dt_formatted": last_dt.strftime("%d/%m/%Y às %H:%M:%S") if last_dt else "",
                    "date_str": first_dt.strftime("%d/%m/%Y") if first_dt else "",
                    "encoder": encoder_used,
                    "render_profile": ve_config.get("render_profile", "fast"),
                    "deband_enabled": render_stats.get("deband_enabled", False),
                    "unsharp_enabled": render_stats.get("unsharp_enabled", False),
                    "render_stats": render_stats
                }

                # Salva no banco de dados SQLite local e central
                record = {
                    "project_name": project.name,
                    "source_video_paths": [str(p.resolve()) for p in clip_paths],
                    "output_video_path": str(out_path.resolve()),
                    "mode": mode,
                    "render_profile": ve_config.get("render_profile", "fast"),
                    "clip_count": len(clip_paths),
                    "speed_factor": speed_factor,
                    "orig_fps": fps_val,
                    "target_fps": float(target_fps),
                    "orig_resolution": f"{orig_w}x{orig_h}",
                    "target_resolution": f"{ve_config.get('target_width', 3840)}x{ve_config.get('target_height', 2160)}",
                    "trim_start_sec": render_stats.get("trim_seconds", 0.0),
                    "trim_end_sec": render_stats.get("trim_seconds", 0.0),
                    "audio_stripped": 1 if render_stats.get("audio_stripped", False) else 0,
                    "duration_seconds": final_dur,
                    "encoder": encoder_used,
                    "youtube_privacy": config.get("modules.youtube.privacy_status", "unlisted"),
                    "status": "rendered",
                    "metadata_json": rich_meta
                }
                project.save_edited_video(record)

                # Notificações Windows / NTFY
                topic = config.get("modules.timelapse.ntfy_topic", "timelapse-studio-2026")
                enable_toast = config.get("modules.timelapse.windows_toast", True)

                profile_tag = ve_config.get("render_profile", "fast").upper()
                if enable_toast:
                    send_windows_toast(
                        "IRIS - Vídeo 4K Renderizado!",
                        f"Vídeo: {out_path.name}\nPerfil: {profile_tag} | Encoder: {encoder_used} | Speed: {speed_label}"
                    )
                if topic:
                    send_ntfy_notification(
                        topic=topic,
                        title="🎬 IRIS: Vídeo 4K Renderizado com Sucesso!",
                        message=f"📁 Projeto: {project.name}\n🎞️ Vídeo: {out_path.name}\n⚡ Perfil: {profile_tag} | Speed: {speed_label} | FPS: {target_fps}",
                        tags=["film_projector", "clapper", "sparkles"],
                        priority="default"
                    )

                console.print(f"[bold green]✔ Vídeo 4K gerado com sucesso: {out_path.name}[/bold green]")
                success_count += 1
            else:
                console.print(f"[bold red]✖ Falha na renderização de '{out_path.name}': {err_msg}[/bold red]")
                error_count += 1

            # Pausa suave de resfriamento entre vídeos para permitir que a GPU libere recursos
            if job_idx < total_active:
                time.sleep(1.0)

        if error_count > 0:
            console.print(f"[yellow]Etapa 6 finalizada com {error_count} erro(s) e {success_count} sucesso(s).[/yellow]")
            return False

        console.print(f"[bold green]Etapa 6 concluída com sucesso! ({success_count} vídeo(s) masterizado(s) em 4K).[/bold green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return VideoEditStage(stage_id, name)
