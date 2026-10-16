"""Etapa do Pipeline: Aprimoramento Wavelets e Contraste Lunar (9_Astro_Sharpening)."""
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
from src.modules.astro.postprocess import process_and_export_all_presets
from src.modules.astro.wavelets import LunarWaveletEngine
from src.modules.astro_sharpen.namer import resolve_astro_sharpen_dir
from src.modules.timelapse.notifier import send_windows_toast, send_ntfy_notification

console = Console(legacy_windows=False)


class AstroSharpenStage(PipelineStage):
    """Etapa de Aprimoramento Lunar: Lê os stacks TIFF 16-bit de 8_Astro_Stack,
    aplica a transformada Wavelet À Trous B3-Spline, Limb Guard, CLAHE 16-bit
    e curvas adaptativas do LunarWaveletEngine, salvando em 9_Astro_Sharpening.
    """

    def run(self, project: Project, **kwargs) -> bool:
        console.print(Panel(
            "[bold cyan]🌕 ETAPA: APRIMORAMENTO LUNAR (Wavelets & Micro-Relevo)[/bold cyan]\n"
            "[dim]Wavelets À Trous B3-Spline • Limb Guard Anti-Halo • CLAHE 16-bit[/dim]",
            expand=False,
            border_style="cyan"
        ))

        dest_root = Path(config.get("general.destination_root", "C:/IRIS"))
        sharpen_config = config.get("modules.astro_sharpen", {})
        if not sharpen_config.get("enabled", True):
            console.print("[yellow]Módulo astro_sharpen desativado nas configurações. Pulando etapa.[/yellow]")
            return True

        # Localiza arquivos TIFF em 8_Astro_Stack
        stacks_to_process: List[Path] = []

        # 1. Busca através dos registros no banco de dados do projeto
        db_stacks = project.get_astro_stacks()
        for s in db_stacks:
            tiffs_dict = s.get("output_tiff_paths_json", {})
            if isinstance(tiffs_dict, dict):
                for path_str in tiffs_dict.values():
                    p = Path(path_str)
                    if p.exists() and p not in stacks_to_process:
                        stacks_to_process.append(p)
            out_dir = s.get("output_dir")
            if out_dir:
                p_dir = Path(out_dir)
                if p_dir.exists():
                    for tiff_f in p_dir.glob("*.tif*"):
                        if "preview" not in tiff_f.name and tiff_f not in stacks_to_process:
                            stacks_to_process.append(tiff_f)

        # 2. Se nenhum registro no DB e o projeto não possui itens ingeridos (ex: projeto avulso direto em pasta),
        # verifica se o source_path possui arquivos TIFF
        if not stacks_to_process and not project.has_items() and getattr(project, "source_path", None):
            src_p = Path(project.source_path)
            if src_p.exists() and src_p.is_dir():
                for tiff_f in src_p.rglob("*.tif*"):
                    if tiff_f.is_file() and not tiff_f.name.startswith(".") and "preview" not in tiff_f.name.lower():
                        stacks_to_process.append(tiff_f)

        if not stacks_to_process:
            console.print(f"[cyan]Nenhum arquivo TIFF empilhado identificado no projeto '{project.name}'. Etapa concluída.[/cyan]")
            return True

        console.print(f"Encontrados [bold green]{len(stacks_to_process)}[/bold green] stack(s) TIFF para aprimoramento.")

        presets = sharpen_config.get("presets", ["registax_fiel", "registax_limb_guard", "registax_plus"])
        enable_clahe = sharpen_config.get("enable_clahe", True)
        use_limb_guard = sharpen_config.get("use_limb_guard", True)

        processed_count = 0
        total_presets_generated = 0
        total_stacks = len(stacks_to_process)
        batch_t0 = time.time()

        for idx, stack_file in enumerate(stacks_to_process, 1):
            console.print(f"\n[cyan][{idx}/{total_stacks}][/cyan] Processando: [bold white]{stack_file.name}[/bold white]")

            # Define pasta de destino na raiz 9_Astro_Sharpening
            output_dir = resolve_astro_sharpen_dir(stack_file, dest_root)
            output_dir.mkdir(parents=True, exist_ok=True)

            t0 = time.time()
            try:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TimeElapsedColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(f"[cyan]Aplicando wavelets e CLAHE...", total=100)

                    results = process_and_export_all_presets(
                        input_path=stack_file,
                        output_dir=output_dir,
                        presets=presets,
                        enable_clahe=enable_clahe,
                        use_limb_guard=use_limb_guard,
                        export_png=True,
                        export_tiff=True,
                    )
                    progress.update(task, completed=100, description="[green]Wavelets aplicados com sucesso![/green]")

                elapsed_sec = time.time() - t0
                processed_count += 1
                total_presets_generated += len(results)

                # Registra cada preset gerado no SQLite
                for p_name, paths in results.items():
                    tiff_p = str(paths.get("tiff", ""))
                    png_p = str(paths.get("png", ""))
                    project.add_astro_sharpen({
                        "source_stack_path": str(stack_file),
                        "preset": p_name,
                        "output_tiff_path": tiff_p,
                        "output_png_path": png_p,
                        "status": "sharpened",
                        "metadata_json": {
                            "preset": p_name,
                            "enable_clahe": enable_clahe,
                            "use_limb_guard": use_limb_guard,
                        },
                        "elapsed_seconds": round(elapsed_sec / max(1, len(results)), 2),
                    })

                console.print(f"  [bold green]OK: Wavelets finalizados em {output_dir}[/bold green]")
                for p_name, paths in results.items():
                    tif_name = paths.get("tiff").name if "tiff" in paths else "-"
                    png_name = paths.get("png").name if "png" in paths else "-"
                    console.print(f"    • Preset {p_name}: [green]{tif_name}[/green] / [cyan]{png_name}[/cyan]")

            except Exception as e:
                console.print(f"  [bold red]ERRO ao aprimorar {stack_file.name}: {e}[/bold red]")
                log_event(f"Falha no aprimoramento de {stack_file.name}: {e}", "error")

        total_batch_elapsed = time.time() - batch_t0
        console.print(f"\n[bold green]Concluído! {processed_count} stack(s) processado(s) ({total_presets_generated} imagens geradas) em {total_batch_elapsed:.1f}s.[/bold green]")

        # Dispara notificação consolidada única ao término de todo o lote
        if processed_count > 0:
            enable_toast = sharpen_config.get("windows_toast", True)
            if enable_toast:
                send_windows_toast(
                    "IRIS: Aprimoramento Lunar Concluído",
                    f"{processed_count} stack(s) aprimorado(s) • {total_presets_generated} variações de wavelets geradas em {total_batch_elapsed:.1f}s."
                )
            ntfy_topic = sharpen_config.get("ntfy_topic", config.get("modules.timelapse.ntfy_topic", "iris-alerts"))
            if ntfy_topic:
                send_ntfy_notification(
                    topic=ntfy_topic,
                    title="Aprimoramento Lunar Concluído",
                    message=f"{processed_count} stack(s) • {total_presets_generated} variações geradas em {total_batch_elapsed:.1f}s.",
                    tags=["sparkles", "moon"],
                )

        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return AstroSharpenStage(stage_id, name)
