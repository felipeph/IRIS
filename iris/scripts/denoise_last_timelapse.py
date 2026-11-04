"""
Utilitário CLI para executar a Filtragem Espaço-Temporal Inteligente (TimelapseDenoiseStage)
diretamente sobre o último projeto executado (ex: 2026-11-04_10-03_DCIM) ou sobre uma pasta
de sequência específica, salvando os frames limpos na pasta dedicada na raiz do IRIS
(4_Timelapses_LongaExposicao_Denoised) preservando exatamente a estrutura hierárquica de pastas
e mantendo os JPEGs originais intactos com metadados EXIF/GPS preservados.

Uso:
  python iris/scripts/denoise_last_timelapse.py
  python iris/scripts/denoise_last_timelapse.py --project "2026-11-04_10-03_DCIM" --render
  python iris/scripts/denoise_last_timelapse.py --dir "C:\\IRIS\\4_Timelapses_LongaExposicao\\GoPro\\2026\\11\\03\\timelapse_20-46-48"
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

IRIS_DIR = Path(__file__).resolve().parents[1]
if str(IRIS_DIR) not in sys.path:
    sys.path.insert(0, str(IRIS_DIR))

from rich.console import Console
from rich.live import Live

from src.core.config import config
from src.core.project import get_project, list_open_projects
from src.core.ui import PipelineUI, ProgressTracker
from src.modules.timelapse_denoise.engine import process_sequence_denoise
from src.modules.timelapse_denoise.stage import TimelapseDenoiseStage
from src.modules.timelapse.stage import TimelapseStage

console = Console()


def denoise_directory(
    seq_dir: Path,
    out_dir: Path | None = None,
    subfolder: str | None = None,
    window_size: int = 7,
    sigma_range: float = 4.5,
    hot_pixel_threshold: int = 8,
    jpeg_quality: int = 96,
) -> bool:
    if not seq_dir.exists():
        console.print(f"[red]Pasta não encontrada: {seq_dir}[/red]")
        return False

    valid_exts = {".jpg", ".jpeg"}
    photos = sorted([p for p in seq_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts], key=lambda p: p.name)
    if not photos:
        console.print(f"[red]Nenhuma foto JPEG encontrada em: {seq_dir}[/red]")
        return False

    dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
    denoise_cfg = config.get("modules.timelapse_denoise", {})
    root_folder = str(
        denoise_cfg.get("output_root_folder", "4_Timelapses_LongaExposicao_Denoised")
    ).strip() or "4_Timelapses_LongaExposicao_Denoised"

    if out_dir is None:
        try:
            rel = seq_dir.resolve().relative_to(dest_root.resolve())
            parts = rel.parts
            if len(parts) > 1:
                out_dir = dest_root / root_folder / Path(*parts[1:])
            else:
                out_dir = dest_root / root_folder / rel
        except ValueError:
            # seq_dir não está dentro de dest_root, usa subfolder como fallback
            fallback_sub = subfolder or str(denoise_cfg.get("output_subfolder", "denoised")).strip() or "denoised"
            out_dir = seq_dir / fallback_sub

    total_gb = sum(p.stat().st_size for p in photos) / (1024 ** 3)
    tracker = ProgressTracker(total_units=float(len(photos)), mode="items")
    start_str = datetime.now().strftime("%H:%M:%S")
    stage_title = f"DENOISE ESPAÇO-TEMPORAL DIRETO (W={window_size} | σ={sigma_range})"

    with Live(
        PipelineUI.generate_renderable(
            tracker=tracker,
            stage_title=stage_title,
            start_str=start_str,
            total_files=len(photos),
            total_gb=total_gb,
            current_item_name=photos[0].name,
            status_msg="Calibrando mapa de Hot Pixels e iniciando janela temporal...",
        ),
        console=console,
        refresh_per_second=4,
    ) as live:

        def on_progress(done_cnt: int, tot_cnt: int, cur_name: str, hp_cnt: int):
            delta = max(0.0, float(done_cnt) - tracker.completed_units)
            tracker.update(delta)
            live.update(
                PipelineUI.generate_renderable(
                    tracker=tracker,
                    stage_title=stage_title,
                    start_str=start_str,
                    total_files=tot_cnt,
                    total_gb=total_gb,
                    current_item_name=cur_name,
                    status_msg=f"Filtrando (Bilateral W={window_size} + Chroma YCrCb | Hot Pixels: {hp_cnt})...",
                )
            )

        ok, stats = process_sequence_denoise(
            photo_paths=photos,
            output_dir=out_dir,
            window_size=window_size,
            sigma_range=sigma_range,
            hot_pixel_threshold=hot_pixel_threshold,
            chroma_denoise=True,
            jpeg_quality=jpeg_quality,
            progress_callback=on_progress,
        )

    if ok:
        console.print(
            f"[bold green]✔ Sucesso! {stats['processed_photos']} fotos limpas salvas em '{out_dir}' "
            f"({stats['avg_fps']} fotos/s | {stats['hot_pixels_detected']} hot pixels suprimidos).[/bold green]"
        )
        return True

    console.print(f"[bold red]✖ Erro durante o processamento: {stats.get('error')}[/bold red]")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa o Denoise Espaço-Temporal de Timelapse Noturno.")
    parser.add_argument("--project", type=str, default="", help="Nome do projeto (default: último projeto aberto)")
    parser.add_argument("--dir", type=str, default="", help="Caminho direto de uma pasta de sequência de fotos")
    parser.add_argument("--out-dir", type=str, default="", help="Caminho direto para salvar os frames limpos (opcional)")
    parser.add_argument("--subfolder", type=str, default="", help="Subpasta para salvar frames (fallback legado)")
    parser.add_argument("--window", type=int, default=int(config.get("modules.timelapse_denoise.window_size", 7)))
    parser.add_argument("--sigma", type=float, default=float(config.get("modules.timelapse_denoise.sigma_range", 4.5)))
    parser.add_argument("--force", action="store_true", help="Força reprocessamento mesmo que os frames limpos já existam")
    parser.add_argument("--render", action="store_true", help="Re-renderiza o vídeo Timelapse 4K UHD após limpar os frames")
    args = parser.parse_args()

    if args.dir:
        custom_out = Path(args.out_dir) if args.out_dir else None
        ok = denoise_directory(
            seq_dir=Path(args.dir),
            out_dir=custom_out,
            subfolder=args.subfolder if args.subfolder else None,
            window_size=args.window,
            sigma_range=args.sigma,
        )
        return 0 if ok else 1

    proj_name = args.project.strip()
    if not proj_name:
        projects = list_open_projects()
        if not projects:
            console.print("[red]Nenhum projeto encontrado no banco do IRIS.[/red]")
            return 1
        proj_name = projects[0]

    project = get_project(proj_name)
    if not project:
        console.print(f"[red]Projeto '{proj_name}' não encontrado.[/red]")
        return 1

    console.print(f"[bold cyan]Executando Denoise Espaço-Temporal para o projeto: {project.name}[/bold cyan]")
    stage = TimelapseDenoiseStage("timelapse_denoise", "Redução de Ruído de Timelapse Noturno")
    ok = stage.run(project, force_denoise=args.force, interactive=False)
    if not ok:
        return 1

    if args.render:
        console.print(f"\n[bold cyan]Iniciando re-renderização 4K UHD com os frames limpos...[/bold cyan]")
        tl_stage = TimelapseStage("timelapse", "Renderização de Timelapse 4K")
        tl_ok = tl_stage.run(project, force_render=True, interactive=False)
        return 0 if tl_ok else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
