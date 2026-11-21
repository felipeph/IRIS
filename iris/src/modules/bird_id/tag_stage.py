"""
Estágio do Pipeline: Injeção de Metadados de Aves (BirdTagStage).
Injeta metadados taxonômicos (IPTC, XMP e EXIF) via ExifTool exclusivamente nos formatos graváveis
(`GEO_WRITABLE_EXTS`: JPEG, PNG, WEBP, TIFF, HEIC) de aves organizados no disco:
- Palavras-chave taxonômicas (Keywords, Subject)
- Linhagem hierárquica (HierarchicalSubject)
- Título e legenda (Caption-Abstract, Description)
Arquivos RAW e vídeos NUNCA são regravados fisicamente pelo ExifTool (Zero Data Loss);
sua taxonomia permanece preservada no nome do arquivo, subpasta e SQLite.
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
from src.core.geo import GeoService, GEO_WRITABLE_EXTS
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from src.core.ui import ProgressTracker, PipelineUI
from src.modules.ingestion.strategies.base import compute_file_hash
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
        seen_non_writable: set[Path] = set()

        for rec in records:
            conf = float(rec.get("confidence", 0.0))
            needs_review = bool(rec.get("needs_review", False))
            has_species = bool(rec.get("species_common") or rec.get("species_scientific"))
            is_early_exit = bool(rec.get("metadata_json", {}).get("burst_early_exit", False))

            if not has_species or needs_review:
                continue

            if conf < min_confidence and not is_early_exit:
                continue

            item_path_str = rec.get("item_path", "")
            item = items_by_path.get(item_path_str)
            if not item:
                try:
                    item = items_by_path.get(str(Path(item_path_str).resolve()))
                except Exception:
                    item = None

            if item:
                cat = getattr(item, "category", "") or ""
                rel_dest = (getattr(item, "relative_dest_dir", "") or "").replace("\\", "/")
                p_norm = str(item.organized_path or item_path_str).replace("\\", "/")
                if cat in ("timelapse", "timelapse_long_exposure", "astro_lua") or any(f in rel_dest for f in ("4_Timelapses", "4_Timelapses_LongaExposicao", "5_Astrofotografia")) or any(f in p_norm for f in ("4_Timelapses", "4_Timelapses_LongaExposicao", "5_Astrofotografia")):
                    continue
                p = Path(item.organized_path or item.staging_path or item.original_path)
                if p.exists():
                    if p.suffix.lower() in GEO_WRITABLE_EXTS:
                        files_to_tag[p] = rec
                    else:
                        seen_non_writable.add(p.resolve())
                b_id = getattr(item, "burst_id", "") or ""
                if b_id:
                    burst_records[b_id] = rec

        # Propagar metadados para fotos irmãs da mesma rajada que foram organizadas na pasta da espécie
        for b_id, rec in burst_records.items():
            siblings = project.get_items(burst_id=b_id)
            for sib in siblings:
                cat_s = getattr(sib, "category", "") or ""
                rel_s = (getattr(sib, "relative_dest_dir", "") or "").replace("\\", "/")
                sib_p = Path(sib.organized_path or sib.staging_path or sib.original_path)
                p_s_norm = str(sib_p).replace("\\", "/")
                if cat_s in ("timelapse", "timelapse_long_exposure", "astro_lua") or any(f in rel_s for f in ("4_Timelapses", "4_Timelapses_LongaExposicao", "5_Astrofotografia")) or any(f in p_s_norm for f in ("4_Timelapses", "4_Timelapses_LongaExposicao", "5_Astrofotografia")):
                    continue
                if sib_p.exists() and sib_p not in files_to_tag:
                    if sib_p.suffix.lower() in GEO_WRITABLE_EXTS:
                        files_to_tag[sib_p] = rec
                    else:
                        seen_non_writable.add(sib_p.resolve())

        skipped_non_writable = len(seen_non_writable)
        total_files = len(files_to_tag)
        if total_files == 0:
            if skipped_non_writable > 0:
                console.print(
                    f"[green]✔ {skipped_non_writable} arquivo(s) RAW/vídeo de ave preservado(s) intacto(s) "
                    f"(Zero Data Loss — taxonomia mantida no nome, pasta e SQLite).[/green]"
                )
            else:
                console.print("[dim]Nenhum arquivo elegível de ave com alta certeza para injeção de metadados.[/dim]")
            return True

        # Obter tags da localização do projeto para incorporar palavras-chave geográficas
        project_loc = None
        if hasattr(project, "geo_location_id") and project.geo_location_id:
            project_loc = GeoService.get_location(project.geo_location_id)
        if not project_loc:
            project_loc = GeoService.get_default_location()

        extra_geo_tags = project_loc.get_tags() if project_loc else []

        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")
        stage_title = "ETAPA: INJEÇÃO DE METADADOS DE AVES (EXIF/IPTC)"

        success_count = 0
        error_count = 0
        modified_paths: List[Path] = []

        with Live(
            PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Carregando...", "Iniciando"),
            console=console,
            refresh_per_second=4
        ) as live:
            for file_path, rec in files_to_tag.items():
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, file_path.name, "Injetando EXIF/IPTC..."))

                try:
                    ok = apply_bird_metadata(file_path, rec, extra_keywords=extra_geo_tags)
                    if ok:
                        success_count += 1
                        modified_paths.append(file_path)
                    else:
                        error_count += 1
                except Exception:
                    error_count += 1
                finally:
                    tracker.update(1)

            live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Concluído", "Finalizando"))

        if modified_paths:
            seen_saved_keys = set()
            with project.transaction():
                for file_path in modified_paths:
                    if not file_path.exists():
                        continue
                    it = items_by_path.get(str(file_path))
                    if it is None:
                        try:
                            it = items_by_path.get(str(file_path.resolve()))
                        except Exception:
                            it = None
                    if it is None:
                        continue
                    if it.original_path in seen_saved_keys:
                        continue
                    seen_saved_keys.add(it.original_path)
                    it.file_size_bytes = file_path.stat().st_size
                    it.file_hash = compute_file_hash(file_path)
                    project.save_item(it)

        console.print(f"[bold green]OK: Injeção de metadados de aves concluída![/bold green]")
        console.print(f"  [green]• Arquivos com metadados EXIF/IPTC gravados com sucesso:[/green] [bold cyan]{success_count}[/bold cyan]")
        if skipped_non_writable > 0:
            console.print(f"  [dim]• Arquivos RAW/vídeo preservados intactos (Zero Data Loss):[/dim] [cyan]{skipped_non_writable}[/cyan]")
        if error_count > 0:
            console.print(f"  [yellow]• Arquivos com falha ou gravação ignorada:[/yellow] {error_count}")

        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdTagStage(stage_id, name)
