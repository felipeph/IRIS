"""
Estágio do Pipeline: Injeção de Metadados de Aves (BirdTagStage).
Injeta metadados taxonômicos (IPTC, XMP e EXIF) via ExifTool nas fotos e vídeos de aves
organizados no disco:
- Palavras-chave taxonômicas (Keywords, Subject)
- Linhagem hierárquica (HierarchicalSubject)
- Título e legenda (Caption-Abstract, Description)
Opera de forma graciosa e não-destrutiva sem recodificar pixels.
Painel Rich Live padronizado com acompanhamento em tempo real.
"""

from datetime import datetime
import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Tuple
from rich.console import Console
from rich.live import Live

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from src.core.ui import ProgressTracker, PipelineUI
from .action import apply_bird_metadata

console = Console()


class BirdTagStage(PipelineStage):
    """Estágio atômico de injeção de metadados taxonômicos EXIF/IPTC/XMP em aves."""

    def run(self, project: Project, **kwargs) -> bool:
        init_central_db()

        if not project.has_items():
            console.print("[yellow]Nenhum arquivo no projeto para injetar metadados de aves.[/yellow]")
            return True

        module_cfg = config.get("modules.bird_id", {})
        if not module_cfg.get("enabled", True):
            console.print("[dim]Módulo de aves desabilitado no config. Pulando injeção de metadados.[/dim]")
            return True

        write_exif = bool(module_cfg.get("write_exif_tags", True))
        if not write_exif:
            console.print("[dim]Injeção de metadados EXIF/IPTC desabilitada em 'modules.bird_id.write_exif_tags'. Pulando.[/dim]")
            return True

        env_exif = os.getenv("IRIS_EXIFTOOL_PATH")
        exiftool_bin = env_exif if env_exif else shutil.which("exiftool")
        if not exiftool_bin:
            console.print("[yellow]Aviso: ExifTool não encontrado no sistema ou na variável IRIS_EXIFTOOL_PATH.[/yellow]")
            console.print("[dim]A injeção de metadados taxonômicos foi ignorada graciosamente. Instale o ExifTool para habilitá-la.[/dim]")
            return True

        min_confidence = float(module_cfg.get("min_species_confidence", 0.70))
        records = project.list_bird_identifications()
        if not records:
            console.print("[yellow]Nenhum registro de identificação de aves encontrado no banco do projeto.[/yellow]")
            return True

        # Indexar ProjectItems por caminhos
        items_by_path = {}
        for it in project.get_items():
            for p_str in [it.organized_path, it.staging_path, it.original_path]:
                if p_str:
                    items_by_path[p_str] = it
                    try:
                        items_by_path[str(Path(p_str).resolve())] = it
                    except Exception:
                        pass

        # Mapear arquivos físicos a serem tagueados: dict[Path, record]
        files_to_tag: Dict[Path, Dict[str, Any]] = {}
        burst_records: Dict[str, Dict[str, Any]] = {}

        for rec in records:
            conf = float(rec.get("confidence", 0.0))
            needs_review = bool(rec.get("needs_review", False))
            has_species = bool(rec.get("species_common") or rec.get("species_scientific"))

            if not has_species or conf < min_confidence or needs_review:
                continue

            item_path_str = rec.get("item_path", "")
            item = items_by_path.get(item_path_str)
            if not item:
                try:
                    item = items_by_path.get(str(Path(item_path_str).resolve()))
                except Exception:
                    item = None

            if item:
                p = Path(item.organized_path or item.staging_path or item.original_path)
                if p.exists():
                    files_to_tag[p] = rec
                b_id = getattr(item, "burst_id", "") or ""
                if b_id:
                    burst_records[b_id] = rec

        # Propagar metadados para fotos irmãs da mesma rajada que foram organizadas na pasta da espécie
        for b_id, rec in burst_records.items():
            siblings = project.get_items(burst_id=b_id)
            for sib in siblings:
                sib_p = Path(sib.organized_path or sib.staging_path or sib.original_path)
                if sib_p.exists() and sib_p not in files_to_tag:
                    files_to_tag[sib_p] = rec

        total_files = len(files_to_tag)
        if total_files == 0:
            console.print("[dim]Nenhum arquivo elegível de ave com alta certeza para injeção de metadados.[/dim]")
            return True

        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")
        stage_title = "ETAPA: INJEÇÃO DE METADADOS DE AVES (EXIF/IPTC)"

        success_count = 0
        error_count = 0

        with Live(
            PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Carregando...", "Iniciando"),
            console=console,
            refresh_per_second=4
        ) as live:
            for file_path, rec in files_to_tag.items():
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, file_path.name, "Injetando EXIF/IPTC..."))

                try:
                    ok = apply_bird_metadata(file_path, rec)
                    if ok:
                        success_count += 1
                    else:
                        error_count += 1
                except Exception:
                    error_count += 1
                finally:
                    tracker.update(1)

            live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Concluído", "Finalizando"))

        console.print(f"[bold green]OK: Injeção de metadados de aves concluída![/bold green]")
        console.print(f"  [green]• Arquivos com metadados EXIF/IPTC gravados com sucesso:[/green] [bold cyan]{success_count}[/bold cyan]")
        if error_count > 0:
            console.print(f"  [yellow]• Arquivos com falha ou gravação ignorada:[/yellow] {error_count}")

        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdTagStage(stage_id, name)
