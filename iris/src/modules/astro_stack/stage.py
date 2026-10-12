"""Etapa do Pipeline: Empilhamento Lunar (PSS -> 8_Astro_Stack)."""
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.core.config import config
from src.core.logger import log_event
from src.modules.astro_stack.runner import AstroStackRunner
from src.modules.astro_stack.namer import resolve_astro_stack_dir
from src.modules.timelapse.notifier import send_windows_toast, send_ntfy_notification

console = Console()


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

        runner = AstroStackRunner()
        if not runner.is_available():
            console.print(
                "[red]ERRO: Ambiente virtual com dependências de astrofotografia não encontrado![/red]\n"
                "[yellow]Por favor, configure 'modules.astro_stack.venv_path' ou crie o ambiente .venv_astro.[/yellow]"
            )
            return False

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

        if not sessions:
            console.print("[dim]Nenhuma sessão de fotos lunares encontrada em '5_Astrofotografia/Lua'. Prosseguindo.[/dim]")
            return True

        console.print(f"Encontradas [bold green]{len(sessions)}[/bold green] sessão(ões) lunar(es) para análise.")

        keep_percents = astro_config.get("keep_percents", [10, 25, 50])
        align_box_width = astro_config.get("align_box_width", 64)
        align_search_width = astro_config.get("align_search_width", 20)
        stab_mode = astro_config.get("stab_mode", "Surface")
        timeout = astro_config.get("timeout_seconds", 600)
        margin = astro_config.get("margin_pixels", 128)

        stacked_count = 0
        total_sessions = len(sessions)

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
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(f"[cyan]Empilhando com PSS...", total=100)

                    def on_progress(msg: str, pct: Optional[float]):
                        progress.update(task, description=f"[cyan]{msg}[/cyan]")

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
                    progress.update(task, completed=100, description="[green]Empilhamento concluído![/green]")

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

                console.print(f"  [bold green]OK: Sessão empilhada em {session_output_dir}[/bold green]")
                for kp_val, out_p in report_data.get("output_tiff_paths", {}).items():
                    console.print(f"    • TIFF {kp_val}%: [green]{Path(out_p).name}[/green]")

                # Dispara Notificações
                enable_toast = astro_config.get("windows_toast", True)
                if enable_toast:
                    send_windows_toast(
                        f"IRIS: Empilhamento Lunar Concluído",
                        f"Sessão {session_name} ({len(raw_files)} fotos) empilhada com sucesso em {elapsed_sec:.1f}s."
                    )
                ntfy_topic = astro_config.get("ntfy_topic", config.get("modules.timelapse.ntfy_topic", "iris-alerts"))
                if ntfy_topic:
                    send_ntfy_notification(
                        topic=ntfy_topic,
                        title=f"Lua Empilhada: {session_name}",
                        message=f"{len(raw_files)} fotos empilhadas ({keep_percents}%) em {elapsed_sec:.1f}s.",
                        tags=["crescent_moon", "telescope"],
                    )

            except Exception as e:
                console.print(f"  [bold red]ERRO ao empilhar sessão {session_rel_dir}: {e}[/bold red]")
                log_event(f"Falha no empilhamento da sessão {session_rel_dir}: {e}", "error")

        console.print(f"\n[bold green]Concluído! {stacked_count} nova(s) sessão(ões) empilhada(s).[/bold green]")
        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return AstroStackStage(stage_id, name)
