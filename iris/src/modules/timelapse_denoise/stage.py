import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm
from rich.table import Table

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project, ProjectItem
from src.core.ui import PipelineUI, ProgressTracker
from src.modules.timelapse_denoise.engine import process_sequence_denoise

console = Console()


def resolve_denoised_relative_dir(seq_rel: str, denoise_cfg: dict | None = None) -> Path:
    """
    Resolve o caminho relativo da pasta de saída do denoise mantendo a mesma
    hierarquia de câmera e datas, substituindo o primeiro segmento de diretório
    (ex: '4_Timelapses_LongaExposicao' ou '4_Timelapses') pela pasta raiz
    configurada (padrão: '4_Timelapses_LongaExposicao_Denoised').

    Exemplo:
        seq_rel: '4_Timelapses_LongaExposicao/GoPro/2026/11/03/timelapse_20-46-48'
        retorna: Path('4_Timelapses_LongaExposicao_Denoised/GoPro/2026/11/03/timelapse_20-46-48')
    """
    if denoise_cfg is None:
        denoise_cfg = config.get("modules.timelapse_denoise", {})
    root_folder = str(
        denoise_cfg.get("output_root_folder", "4_Timelapses_LongaExposicao_Denoised")
    ).strip() or "4_Timelapses_LongaExposicao_Denoised"

    parts = Path(seq_rel).parts
    if len(parts) > 1:
        return Path(root_folder, *parts[1:])
    return Path(root_folder, seq_rel)


class TimelapseDenoiseStage(PipelineStage):
    """
    Etapa dedicada de Filtragem Espaço-Temporal Inteligente para Timelapses Noturnos
    (4_Timelapses_LongaExposicao).
    Remove hot pixels fixos de exposição longa, ruído temporal de leitura/ISO (filtro bilateral
    temporal guiado com proteção de estrelas) e manchas de crominância (YCrCb), salvando
    cada imagem limpa em pasta dedicada na raiz do IRIS (4_Timelapses_LongaExposicao_Denoised)
    preservando exatamente a estrutura hierárquica de câmera e datas, com metadados EXIF/GPS intactos.
    """

    def run(self, project: Project, **kwargs) -> bool:
        dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
        denoise_cfg = config.get("modules.timelapse_denoise", {})

        if not denoise_cfg.get("enabled", True):
            console.print("[yellow]Módulo timelapse_denoise está desativado nas configurações. Pulando etapa.[/yellow]")
            return True

        root_folder_name = (
            str(denoise_cfg.get("output_root_folder", "4_Timelapses_LongaExposicao_Denoised")).strip()
            or "4_Timelapses_LongaExposicao_Denoised"
        )
        legacy_subfolder = str(denoise_cfg.get("output_subfolder", "denoised")).strip() or "denoised"
        window_size = int(denoise_cfg.get("window_size", 7))
        sigma_range = float(denoise_cfg.get("sigma_range", 4.5))
        hot_pixel_threshold = int(denoise_cfg.get("hot_pixel_threshold", 8))
        chroma_denoise = bool(denoise_cfg.get("chroma_denoise", True))
        jpeg_quality = int(denoise_cfg.get("jpeg_quality", 96))
        apply_normal = bool(denoise_cfg.get("apply_to_normal_timelapse", False))

        tl_items = list(project.get_items(category="timelapse_long_exposure"))
        if apply_normal:
            tl_items.extend(project.get_items(category="timelapse"))

        if not tl_items:
            console.print(
                f"[cyan]Nenhuma sequência de timelapse noturno (longa exposição) encontrada no projeto '{project.name}'. Etapa concluída.[/cyan]"
            )
            return True

        groups: Dict[str, List[ProjectItem]] = defaultdict(list)
        for it in tl_items:
            default_key = (
                "4_Timelapses_LongaExposicao/Geral"
                if it.category == "timelapse_long_exposure"
                else "4_Timelapses/Geral"
            )
            key = it.relative_dest_dir or default_key
            groups[key].append(it)

        total_sequences = len(groups)
        console.print(
            f"\n[bold cyan]=== Redução de Ruído Espaço-Temporal de Timelapse ({total_sequences} sequência(s)) ===[/bold cyan]"
        )

        summary_table = Table(
            title="Sequências Elegíveis para Denoise Espaço-Temporal",
            show_header=True,
            header_style="bold magenta",
        )
        summary_table.add_column("Sequência", style="cyan")
        summary_table.add_column("Fotos", justify="right", style="green")
        summary_table.add_column("Destino Raiz", style="magenta")
        summary_table.add_column("Status Denoise", style="yellow")

        seq_status_map: Dict[str, bool] = {}
        for seq_rel, items in groups.items():
            out_rel = resolve_denoised_relative_dir(seq_rel, denoise_cfg)
            out_dir = dest_root / out_rel
            existing_jpgs = list(out_dir.glob("*.jpg")) if out_dir.exists() else []

            legacy_dir = (dest_root / Path(seq_rel)) / legacy_subfolder
            legacy_jpgs = list(legacy_dir.glob("*.jpg")) if legacy_dir.exists() else []

            is_done = (len(existing_jpgs) >= len(items) and len(items) > 0) or (
                len(legacy_jpgs) >= len(items) and len(items) > 0
            )
            seq_status_map[seq_rel] = is_done
            status_desc = (
                f"[green]Concluído ({len(existing_jpgs) or len(legacy_jpgs)} fotos)[/green]"
                if is_done
                else "[yellow]Pendente[/yellow]"
            )
            summary_table.add_row(seq_rel, str(len(items)), f"{out_rel}/", status_desc)

        console.print(summary_table)

        force_denoise = kwargs.get("force_denoise", False) or kwargs.get("force_render", False)
        if not force_denoise and kwargs.get("interactive", False):
            already_done = sum(1 for done in seq_status_map.values() if done)
            if already_done > 0:
                force_denoise = Confirm.ask(
                    f"\n[yellow]{already_done} sequência(s) já possuem frames limpos. Deseja reprocessar e sobrescrever?[/yellow]",
                    default=False,
                )

        success_count = 0
        error_count = 0

        for seq_idx, (seq_rel, items) in enumerate(groups.items(), 1):
            seq_dir = dest_root / Path(seq_rel)
            out_rel = resolve_denoised_relative_dir(seq_rel, denoise_cfg)
            out_dir = dest_root / out_rel
            console.print(f"\n[bold blue]-> Sequência [{seq_idx}/{total_sequences}]: {seq_rel}[/bold blue]")
            console.print(f"[cyan]   Pasta de Destino Denoise: {out_dir}[/cyan]")

            photo_paths: List[Path] = []
            for it in items:
                candidate = Path(it.organized_path) if it.organized_path else Path(it.staging_path)
                if candidate.exists():
                    photo_paths.append(candidate)

            if not photo_paths and seq_dir.exists():
                valid_exts = {".jpg", ".jpeg"}
                photo_paths = sorted(
                    [p for p in seq_dir.iterdir() if p.is_file() and p.suffix.lower() in valid_exts]
                )

            if not photo_paths:
                console.print(f"[red]Aviso: Nenhuma foto encontrada fisicamente para '{seq_rel}'.[/red]")
                error_count += 1
                continue

            photo_paths = sorted(photo_paths, key=lambda p: p.name)

            if seq_status_map.get(seq_rel, False) and not force_denoise:
                out_count = len(list(out_dir.glob("*.jpg"))) if out_dir.exists() else 0
                legacy_dir = seq_dir / legacy_subfolder
                leg_count = len(list(legacy_dir.glob("*.jpg"))) if legacy_dir.exists() else 0
                done_path = out_dir if out_count >= len(photo_paths) else legacy_dir
                done_count = out_count if out_count >= len(photo_paths) else leg_count
                console.print(
                    f"[green]✔ Frames já limpos em '{done_path}' ({done_count} arquivos).[/green]"
                )
                success_count += 1
                continue

            total_bytes = sum(p.stat().st_size for p in photo_paths if p.exists())
            total_gb = total_bytes / (1024 ** 3)
            tracker = ProgressTracker(total_units=float(len(photo_paths)), mode="items")
            start_str = datetime.now().strftime("%H:%M:%S")
            stage_title = f"DENOISE ESPAÇO-TEMPORAL [{seq_idx}/{total_sequences}] (W={window_size} | σ={sigma_range})"

            with Live(
                PipelineUI.generate_renderable(
                    tracker=tracker,
                    stage_title=stage_title,
                    start_str=start_str,
                    total_files=len(photo_paths),
                    total_gb=total_gb,
                    current_item_name=photo_paths[0].name,
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
                            status_msg=(
                                f"Filtrando (Bilateral W={window_size} + Chroma YCrCb | Hot Pixels suprimidos: {hp_cnt})..."
                            ),
                        )
                    )

                ok, stats = process_sequence_denoise(
                    photo_paths=photo_paths,
                    output_dir=out_dir,
                    window_size=window_size,
                    sigma_range=sigma_range,
                    hot_pixel_threshold=hot_pixel_threshold,
                    chroma_denoise=chroma_denoise,
                    jpeg_quality=jpeg_quality,
                    progress_callback=on_progress,
                )

            if ok:
                manifest_path = out_dir / "denoise_manifest.json"
                try:
                    manifest_data = {
                        **stats,
                        "project_name": project.name,
                        "sequence_rel": seq_rel,
                        "output_root_folder": root_folder_name,
                        "output_relative_dir": str(out_rel),
                        "completed_at": datetime.now().isoformat(),
                    }
                    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
                except Exception:
                    pass

                console.print(
                    f"[bold green]✔ Denoise concluído: {stats['processed_photos']} fotos salvas em '{out_dir}' "
                    f"({stats['avg_fps']} fotos/s | {stats['hot_pixels_detected']} hot pixels removidos).[/bold green]"
                )
                success_count += 1
            else:
                console.print(
                    f"[bold red]✖ Falha no denoise da sequência '{seq_rel}': {stats.get('error', 'Erro desconhecido')}[/bold red]"
                )
                error_count += 1

        if error_count > 0:
            console.print(
                f"[yellow]Etapa de denoise finalizada com {error_count} erro(s) e {success_count} sucesso(s).[/yellow]"
            )
            return False

        console.print(
            f"[bold green]Etapa de Denoise Espaço-Temporal concluída com sucesso ({success_count} sequência(s))![/bold green]"
        )
        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return TimelapseDenoiseStage(stage_id, name)
