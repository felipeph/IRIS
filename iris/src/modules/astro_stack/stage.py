"""Etapa do Pipeline: Empilhamento Lunar (PSS -> 8_Astro_Stack)."""
import datetime
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.core.config import config
from src.core.logger import log_event
from src.core.ui import PipelineUI
from src.modules.astro_stack.runner import AstroStackRunner
from src.modules.astro_stack.namer import resolve_astro_stack_dir
from src.modules.timelapse.notifier import send_windows_toast, send_ntfy_notification

console = Console(legacy_windows=False)


class AstroStackStage(PipelineStage):
    """Etapa de Empilhamento Lunar: Localiza sessões em 5_Astrofotografia/Lua,
    executa o PlanetarySystemStacker em modo headless para gerar TIFFs 16-bit
    alinhados e centralizados em 8_Astro_Stack.
    """

    def run(self, project: Project, **kwargs) -> bool:
        console.print(Panel(
            "[bold cyan]🌕 ETAPA: EMPILHAMENTO LUNAR (PlanetarySystemStacker)[/bold cyan]\n"
            "[dim]Alinhamento Multiponto • Ranking Local • Stacking 16-bit Linear[/dim]",
            expand=False,
            border_style="cyan"
        ))

        dest_root = Path(config.get("general.destination_root", "C:/IRIS"))
        astro_config = config.get("modules.astro_stack", {})
        if not astro_config.get("enabled", True):
            console.print("[yellow]Módulo astro_stack desativado nas configurações. Pulando etapa.[/yellow]")
            return True

        # Mapeia sessões de astrofotografia no projeto
        sessions: Dict[str, List[Path]] = {}

        # 1. Busca por itens classificados no banco de dados do projeto
        for it in project.items:
            rel_dest = getattr(it, "relative_dest_dir", "") or ""
            if "5_Astrofotografia" in rel_dest or "astro_lua" in getattr(it, "category", ""):
                # Resolve caminho físico
                p = dest_root / rel_dest / it.target_filename if hasattr(it, "target_filename") and it.target_filename else dest_root / rel_dest / Path(it.original_path).name
                if p.exists() and p.is_file():
                    sessions.setdefault(rel_dest, []).append(p)

        # 2. Se nenhuma sessão mapeada pelos items, faz scan na pasta 5_Astrofotografia/Lua
        astro_root = dest_root / "5_Astrofotografia" / "Lua"
        if not sessions and astro_root.exists():
            extensions = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raw", ".tif", ".tiff", ".png", ".jpg"}
            for sess_dir in astro_root.rglob("sessao_*"):
                if sess_dir.is_dir():
                    raws = sorted(p for p in sess_dir.iterdir() if p.is_file() and p.suffix.lower() in extensions and not p.name.startswith("."))
                    if len(raws) >= 2:
                        rel_key = str(sess_dir.relative_to(dest_root)).replace("\\", "/")
                        sessions[rel_key] = raws

        # 3. Se nenhuma sessão encontrada, verifica se o source_path do projeto aponta diretamente para uma sessão ou raiz com fotos
        if not sessions and getattr(project, "source_path", None):
            src_p = Path(project.source_path)
            if src_p.exists() and src_p.is_dir():
                extensions = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raw", ".tif", ".tiff", ".png", ".jpg"}
                direct_raws = sorted(p for p in src_p.iterdir() if p.is_file() and p.suffix.lower() in extensions and not p.name.startswith("."))
                if len(direct_raws) >= 2:
                    parts = list(src_p.parts)
                    if "5_Astrofotografia" in parts:
                        idx = parts.index("5_Astrofotografia")
                        rel_key = "/".join(parts[idx:])
                    else:
                        rel_key = f"5_Astrofotografia/Lua/{src_p.name}"
                    sessions[rel_key] = direct_raws
                else:
                    for sess_dir in src_p.rglob("sessao_*"):
                        if sess_dir.is_dir():
                            raws = sorted(p for p in sess_dir.iterdir() if p.is_file() and p.suffix.lower() in extensions and not p.name.startswith("."))
                            if len(raws) >= 2:
                                parts = list(sess_dir.parts)
                                if "5_Astrofotografia" in parts:
                                    idx = parts.index("5_Astrofotografia")
                                    rel_key = "/".join(parts[idx:])
                                else:
                                    rel_key = f"5_Astrofotografia/Lua/{sess_dir.name}"
                                sessions[rel_key] = raws

        if not sessions:
            console.print("[dim]Nenhuma sessão de fotos lunares encontrada em '5_Astrofotografia/Lua' ou na origem. Prosseguindo.[/dim]")
            return True

        runner = AstroStackRunner()
        if not runner.is_available():
            console.print(
                "[red]ERRO: Ambiente virtual com dependências de astrofotografia não encontrado![/red]\n"
                "[yellow]Por favor, configure 'modules.astro_stack.venv_path' ou crie o ambiente .venv_astro.[/yellow]"
            )
            return False

        console.print(f"Encontradas [bold green]{len(sessions)}[/bold green] sessão(ões) lunar(es) para análise.")

        keep_percents = astro_config.get("keep_percents", [10, 25, 50])
        align_box_width = astro_config.get("align_box_width", 64)
        align_search_width = astro_config.get("align_search_width", 20)
        stab_mode = astro_config.get("stab_mode", "Surface")
        timeout = astro_config.get("timeout_seconds", 600)
        margin = astro_config.get("margin_pixels", 128)

        stacked_count = 0
        total_raws_processed = 0
        total_tiffs_generated = 0
        total_sessions = len(sessions)
        batch_t0 = time.time()

        for s_idx, (session_rel_dir, raw_files) in enumerate(sessions.items(), 1):
            session_name = Path(session_rel_dir).name
            console.print(f"\n[cyan][{s_idx}/{total_sessions}][/cyan] Sessão: [bold white]{session_rel_dir}[/bold white] ({len(raw_files)} frames)")

            # Verifica se já foi empilhado
            if project.is_astro_session_stacked(session_rel_dir) and not kwargs.get("force", False):
                console.print(f"  [dim]✔ Sessão já empilhada anteriormente. Pulando.[/dim]")
                continue

            session_input_dir = raw_files[0].parent
            session_output_dir = resolve_astro_stack_dir(session_rel_dir, dest_root)
            session_output_dir.mkdir(parents=True, exist_ok=True)

            t0 = time.time()
            start_str = datetime.datetime.now().strftime("%H:%M:%S")

            # Variáveis de estado para o painel vertical Rich
            current_phase_msg = "Iniciando análise dos frames da sessão..."
            current_item = ""
            progress_pct = 0.0
            crop_size = 0
            shared_gain = 1.0
            completed_stacks: Dict[str, str] = {}

            def make_renderable():
                now = time.time()
                elapsed = now - t0
                elapsed_str = str(datetime.timedelta(seconds=int(elapsed)))
                if progress_pct > 0:
                    total_est = elapsed / (progress_pct / 100.0)
                    remaining = max(0, total_est - elapsed)
                    eta_str = str(datetime.timedelta(seconds=int(remaining)))
                    end_dt = datetime.datetime.now() + datetime.timedelta(seconds=int(remaining))
                    previsao_str = end_dt.strftime("%H:%M:%S")
                else:
                    eta_str = "--:--:--"
                    previsao_str = "--:--:--"

                return PipelineUI.generate_astro_stack_renderable(
                    stage_title=f"🌕 EMPILHAMENTO LUNAR (PSS) [{s_idx}/{total_sessions}]",
                    start_str=start_str,
                    session_name=session_name,
                    total_photos=len(raw_files),
                    keep_percents=keep_percents,
                    current_phase_msg=current_phase_msg,
                    current_item=current_item,
                    progress_pct=progress_pct,
                    crop_size=crop_size,
                    shared_gain=shared_gain,
                    completed_stacks=completed_stacks,
                    elapsed_str=elapsed_str,
                    eta_str=eta_str,
                    previsao_fim_str=previsao_str,
                )

            try:
                with Live(make_renderable(), console=console, refresh_per_second=4) as live:
                    def on_progress(event_or_msg, pct_val):
                        nonlocal current_phase_msg, current_item, progress_pct, crop_size, shared_gain, completed_stacks
                        if isinstance(event_or_msg, dict):
                            current_phase_msg = event_or_msg.get("msg", current_phase_msg)
                            current_item = event_or_msg.get("item", current_item)
                            if "progress_pct" in event_or_msg:
                                progress_pct = float(event_or_msg["progress_pct"])
                            if "crop_size" in event_or_msg and event_or_msg["crop_size"]:
                                crop_size = int(event_or_msg["crop_size"])
                            if "gain" in event_or_msg and event_or_msg["gain"]:
                                shared_gain = float(event_or_msg["gain"])
                            if "completed_stacks" in event_or_msg:
                                completed_stacks.update(event_or_msg["completed_stacks"])
                            if event_or_msg.get("phase") == "kp_done" and "kp" in event_or_msg:
                                completed_stacks[str(event_or_msg["kp"])] = event_or_msg.get("filename", "")
                        else:
                            current_phase_msg = str(event_or_msg)
                            if pct_val is not None:
                                progress_pct = float(pct_val)
                        live.update(make_renderable())

                    report_data = runner.run_session(
                        input_dir=session_input_dir,
                        output_dir=session_output_dir,
                        keep_percents=keep_percents,
                        margin=margin,
                        align_box_width=align_box_width,
                        align_search_width=align_search_width,
                        stab_mode=stab_mode,
                        timeout=timeout,
                        progress_callback=on_progress,
                    )
                    progress_pct = 100.0
                    current_phase_msg = "[green]Empilhamento concluído com sucesso![/green]"
                    live.update(make_renderable())

                elapsed_sec = time.time() - t0
                report_data["elapsed_seconds"] = round(elapsed_sec, 2)

                # Registra no SQLite do projeto
                record_db = {
                    "session_dir": session_rel_dir,
                    "raw_count": len(raw_files),
                    "keep_percents": keep_percents,
                    "output_dir": str(session_output_dir),
                    "output_tiff_paths_json": report_data.get("output_tiff_paths", {}),
                    "crop_size": report_data.get("crop_size", 0),
                    "shared_gain": report_data.get("shared_gain", 1.0),
                    "status": "stacked",
                    "metadata_json": report_data,
                    "elapsed_seconds": round(elapsed_sec, 2),
                }
                project.add_astro_stack(record_db)
                stacked_count += 1
                total_raws_processed += len(raw_files)
                total_tiffs_generated += len(report_data.get("output_tiff_paths", {}))

                console.print(f"  [bold green]OK: Sessão empilhada em {session_output_dir}[/bold green]")
                for kp_val, out_p in report_data.get("output_tiff_paths", {}).items():
                    console.print(f"    • TIFF {kp_val}%: [green]{Path(out_p).name}[/green]")

            except Exception as e:
                console.print(f"  [bold red]ERRO ao empilhar sessão {session_rel_dir}: {e}[/bold red]")
                log_event(f"Falha no empilhamento da sessão {session_rel_dir}: {e}", "error")

        total_batch_elapsed = time.time() - batch_t0
        console.print(f"\n[bold green]Concluído! {stacked_count} nova(s) sessão(ões) empilhada(s) ({total_tiffs_generated} TIFFs gerados) em {total_batch_elapsed:.1f}s.[/bold green]")

        # Dispara notificação consolidada única ao término de todo o lote
        if stacked_count > 0:
            enable_toast = astro_config.get("windows_toast", True)
            if enable_toast:
                send_windows_toast(
                    "IRIS: Empilhamento Lunar Concluído",
                    f"{stacked_count} sessão(ões) empilhada(s) • {total_tiffs_generated} TIFFs gerados de {total_raws_processed} fotos em {total_batch_elapsed:.1f}s."
                )
            ntfy_topic = astro_config.get("ntfy_topic", config.get("modules.timelapse.ntfy_topic", "iris-alerts"))
            if ntfy_topic:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    title="Empilhamento Lunar Concluído",
                    message=f"{stacked_count} sessão(ões) • {total_tiffs_generated} TIFFs ({total_raws_processed} fotos) em {total_batch_elapsed:.1f}s.",
                    tags=["crescent_moon", "telescope"],
                )

        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return AstroStackStage(stage_id, name)
