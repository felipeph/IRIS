import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import List, Dict, Any

from rich.console import Console
from rich.table import Table

from src.core.pipeline import PipelineStage
from src.core.project import Project, ProjectItem
from src.core.config import config
from src.modules.timelapse.namer import generate_timelapse_video_name, resolve_produced_output_path
from src.modules.timelapse.sequence import prepare_numbered_sequence, clean_sequence_dir
from src.modules.timelapse.renderer import render_timelapse_video
from src.modules.timelapse.notifier import notify_timelapse_render_done

console = Console()

class TimelapseStage(PipelineStage):
    """
    Etapa 5: Renderização de Timelapse 4K UHD para 6_Produzidos.
    Identifica sequências de fotos categorizadas como 'timelapse',
    aplica filtros de corte inteligente Lanczos, aceleração por hardware
    e registra o resultado nos bancos de dados do IRIS.
    """

    def run(self, project: Project, **kwargs) -> bool:
        dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
        tl_config = config.get("modules.timelapse", {})
        
        # 1. Buscar itens de timelapse do projeto
        all_items = project.items
        tl_items = [it for it in all_items if it.category == "timelapse"]

        if not tl_items:
            console.print(f"[cyan]Nenhum arquivo de timelapse identificado no projeto '{project.name}'. Etapa concluída.[/cyan]")
            return True

        # 2. Agrupar itens por pasta de sequência organizada
        groups: Dict[str, List[ProjectItem]] = defaultdict(list)
        for it in tl_items:
            # Chave de agrupamento: relative_dest_dir (ex: 4_Timelapses/Canon/2026/08/17/timelapse_16-55-00)
            key = it.relative_dest_dir or "4_Timelapses/Geral"
            groups[key].append(it)

        total_sequences = len(groups)
        console.print(f"\n[bold cyan]=== Etapa 5: Renderização de Timelapse 4K ({total_sequences} sequência(s) encontrada(s)) ===[/bold cyan]")

        # Exibir tabela de sequências planejadas
        summary_table = Table(title="Sequências de Timelapse do Projeto", show_header=True, header_style="bold magenta")
        summary_table.add_column("Sequência", style="cyan")
        summary_table.add_column("Fotos", justify="right", style="green")
        summary_table.add_column("Status Render", style="yellow")

        for seq_rel, items in groups.items():
            seq_dir = dest_root / Path(seq_rel)
            existing_renders = [tl for tl in project.get_timelapses() if tl.get("sequence_dir") == str(seq_dir.resolve())]
            status_desc = "[green]Já Renderizado[/green]" if existing_renders else "[yellow]Pendente[/yellow]"
            summary_table.add_row(seq_rel, str(len(items)), status_desc)

        console.print(summary_table)

        success_count = 0
        error_count = 0

        for seq_idx, (seq_rel, items) in enumerate(groups.items(), 1):
            seq_dir = dest_root / Path(seq_rel)
            console.print(f"\n[bold blue]-> Processando Sequência [{seq_idx}/{total_sequences}]: {seq_rel}[/bold blue]")

            # Obter caminhos reais das fotos
            photo_paths: List[Path] = []
            for it in items:
                candidate = Path(it.organized_path) if it.organized_path else Path(it.staging_path)
                if candidate.exists():
                    photo_paths.append(candidate)

            # Fallback: Se a pasta física já foi organizada e possui fotos
            if not photo_paths and seq_dir.exists():
                valid_exts = {'.jpg', '.jpeg', '.png'}
                photo_paths = sorted([p for p in seq_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts])

            if not photo_paths:
                console.print(f"[red]Aviso: Nenhuma foto encontrada fisicamente para a sequência '{seq_rel}'.[/red]")
                error_count += 1
                continue

            # Extrair datas e metadados da sequência
            first_item = items[0]
            last_item = items[-1]

            first_dt = None
            last_dt = None
            if first_item.meta_timestamp:
                try:
                    first_dt = datetime.fromisoformat(first_item.meta_timestamp)
                except Exception:
                    pass
            if last_item.meta_timestamp:
                try:
                    last_dt = datetime.fromisoformat(last_item.meta_timestamp)
                except Exception:
                    pass

            if not first_dt:
                first_dt = datetime.fromtimestamp(photo_paths[0].stat().st_mtime)
            if not last_dt:
                last_dt = datetime.fromtimestamp(photo_paths[-1].stat().st_mtime)

            camera_model = first_item.meta_camera_model or first_item.meta_camera_make or "Camera"
            orig_w = first_item.meta_width or 0
            orig_h = first_item.meta_height or 0

            fps = tl_config.get("fps", 60)
            fpi = max(1, tl_config.get("frames_per_image", 1))
            target_h = tl_config.get("target_height", 2160)
            target_w = tl_config.get("target_width", 3840)
            crop_mode = tl_config.get("crop_mode", "center")

            video_name = generate_timelapse_video_name(
                first_dt=first_dt,
                last_dt=last_dt,
                camera_model=camera_model,
                orig_w=orig_w,
                orig_h=orig_h,
                total_photos=len(photo_paths),
                fps=fps,
                fpi=fpi,
                target_height=target_h,
                crop_mode=crop_mode,
                is_test=False
            )

            output_video_path = resolve_produced_output_path(dest_root, first_dt, video_name)

            # Verificar se já existe render concluído
            existing = [tl for tl in project.get_timelapses() if tl.get("output_video_path") == str(output_video_path.resolve())]
            if existing and output_video_path.exists():
                console.print(f"[green]✔ Vídeo já renderizado previamente: {output_video_path.name}[/green]")
                success_count += 1
                continue

            console.print(f"[cyan]Destino final 6_Produzidos: {output_video_path}[/cyan]")

            # 3. Preparar sequência numerada via hardlinks
            prep_ok, temp_seq_dir, sorted_photos = prepare_numbered_sequence(
                photo_paths=photo_paths,
                target_dir=seq_dir,
                is_test=False
            )

            if not prep_ok:
                console.print(f"[red]Erro ao criar sequência temporária de fotos em {seq_dir}.[/red]")
                error_count += 1
                continue

            # 4. Renderizar vídeo com FFmpeg
            render_ok, encoder_used, err_msg, render_stats = render_timelapse_video(
                sequence_dir=temp_seq_dir,
                output_video_path=output_video_path,
                photo_count=len(sorted_photos),
                config=tl_config
            )

            # Limpar sequência temporária
            if tl_config.get("auto_clean_sequence", True):
                clean_sequence_dir(temp_seq_dir)

            if render_ok:
                total_frames = len(sorted_photos) * fpi
                dur_sec = total_frames / fps if fps > 0 else 0.0
                real_sec = max(1.0, (last_dt - first_dt).total_seconds())
                speedup = max(1, int(round(real_sec / dur_sec))) if dur_sec > 0 else 1

                # Compilar metadados ricos da sequência e da produção
                total_orig_size_bytes = sum(it.file_size_bytes for it in items if it.file_size_bytes)
                orig_formats = sorted(list({it.meta_extension.upper().lstrip('.') for it in items if it.meta_extension}))
                video_size_bytes = output_video_path.stat().st_size if output_video_path.exists() else 0
                apertures = [it.meta_aperture_str for it in items if it.meta_aperture_str]
                shutters = [it.meta_shutter_str for it in items if it.meta_shutter_str]
                isos = [it.meta_iso_str for it in items if it.meta_iso_str]
                focals = [it.meta_focal_str for it in items if it.meta_focal_str]
                focal_equivs = [it.meta_focal_length_equiv for it in items if it.meta_focal_length_equiv is not None]

                rich_meta = {
                    "camera_make": first_item.meta_camera_make or "Cam",
                    "camera_model": camera_model,
                    "orig_width": orig_w,
                    "orig_height": orig_h,
                    "total_orig_size_bytes": total_orig_size_bytes,
                    "video_size_bytes": video_size_bytes,
                    "orig_formats": orig_formats,
                    "first_dt_iso": first_dt.isoformat() if first_dt else "",
                    "last_dt_iso": last_dt.isoformat() if last_dt else "",
                    "first_dt_formatted": first_dt.strftime("%d/%m/%Y às %H:%M:%S") if first_dt else "",
                    "last_dt_formatted": last_dt.strftime("%d/%m/%Y às %H:%M:%S") if last_dt else "",
                    "date_str": first_dt.strftime("%d/%m/%Y") if first_dt else "",
                    "real_duration_seconds": real_sec,
                    "avg_interval_seconds": round(real_sec / max(1, len(sorted_photos) - 1), 2) if len(sorted_photos) > 1 else 0.0,
                    "frames_per_image": fpi,
                    "fps": fps,
                    "speedup_factor": speedup,
                    "duration_seconds": dur_sec,
                    "encoder": encoder_used,
                    "crop_mode": crop_mode,
                    "target_width": target_w,
                    "target_height": target_h,
                    "apertures": apertures,
                    "shutters": shutters,
                    "isos": isos,
                    "focals": focals,
                    "focal_equiv_summary": f"{focal_equivs[0]:.0f}mm" if focal_equivs else "",
                    "render_stats": render_stats
                }

                # Salvar no banco do projeto e banco central
                record = {
                    "project_name": project.name,
                    "sequence_dir": str(seq_dir.resolve()),
                    "output_video_path": str(output_video_path.resolve()),
                    "photo_count": len(sorted_photos),
                    "fps": fps,
                    "frames_per_image": fpi,
                    "resolution": f"{target_w}x{target_h}",
                    "crop_mode": crop_mode,
                    "encoder": encoder_used,
                    "duration_seconds": dur_sec,
                    "speedup_factor": speedup,
                    "youtube_privacy": config.get("modules.youtube.privacy_status", "unlisted"),
                    "status": "rendered",
                    "metadata_json": rich_meta
                }
                project.save_timelapse(record)

                # Notificar
                topic = tl_config.get("ntfy_topic", "timelapse-studio-2026")
                enable_toast = tl_config.get("windows_toast", True)
                notify_timelapse_render_done(
                    project_name=project.name,
                    video_name=output_video_path.name,
                    details=f"Encoder: {encoder_used} | Duração: {dur_sec:.1f}s | Speedup: {speedup}x",
                    topic=topic,
                    enable_toast=enable_toast
                )

                console.print(f"[bold green]✔ Renderização concluída: {output_video_path.name}[/bold green]")
                success_count += 1
            else:
                console.print(f"[bold red]✖ Falha na renderização de '{video_name}': {err_msg}[/bold red]")
                error_count += 1

        if error_count > 0:
            console.print(f"[yellow]Etapa 5 finalizada com {error_count} erro(s) e {success_count} sucesso(s).[/yellow]")
            return False

        console.print(f"[bold green]Etapa 5 concluída com sucesso! ({success_count} timelapse(s) gerado(s)).[/bold green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return TimelapseStage(stage_id, name)
