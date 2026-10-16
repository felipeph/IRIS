import os
import json
import shutil
from pathlib import Path
from dataclasses import asdict
from rich.console import Console

from src.core.pipeline import PipelineStage
from src.core.project import Project, ProjectItem
from src.core.config import config
from src.core.metadata import extract_metadata_batch
from src.core.classifier import classify_media_batch
from src.core.ui import ProgressTracker, PipelineUI
from rich.live import Live
from datetime import datetime

console = Console()

class PlanningStage(PipelineStage):
    def run(self, project: Project) -> bool:
        if not project.items:
            console.print("[yellow]Nenhum arquivo no projeto para planejar.[/yellow]")
            return True

        console.print("[bold cyan]Iniciando extração de metadados e planejamento...[/bold cyan]")
        
        # Pre-flight check
        if not shutil.which("exiftool"):
            console.print("[bold red]ERRO: exiftool não encontrado no PATH![/bold red]")
            console.print("Por favor, instale o exiftool para continuar.")
            return False
            
        if not shutil.which("ffprobe"):
            console.print("[bold red]ERRO: ffprobe não encontrado no PATH![/bold red]")
            console.print("Por favor, instale o ffmpeg/ffprobe para continuar.")
            return False

        # Obter todos os itens aptos a planejar
        all_planning_items = [item for item in project.items if item.status == "copied" and item.verified]
        
        if not all_planning_items:
            console.print("[yellow]Nenhum arquivo copiado/verificado encontrado na staging para planejar.[/yellow]")
            return True

        # 1. Identificar quais precisam de extração de metadados
        items_to_extract = [item for item in all_planning_items if item.meta_is_video is None]
        
        if items_to_extract:
            console.print(f"[cyan]Extraindo metadados de {len(items_to_extract)} arquivos pendentes...[/cyan]")
            file_paths = [Path(item.staging_path) for item in items_to_extract]
            total_files = len(file_paths)
            tracker = ProgressTracker(total_files, mode="items")
            start_str = datetime.now().strftime("%H:%M:%S")

            batch_size = 500
            with Live(PipelineUI.generate_renderable(tracker, "ETAPA 3: EXTRAÇÃO DE METADADOS", start_str, total_files, 0.0, "Preparando...", "Inicializando"), console=console, refresh_per_second=4) as live:
                for i in range(0, total_files, batch_size):
                    chunk_paths = file_paths[i:i+batch_size]
                    chunk_items = items_to_extract[i:i+batch_size]
                    
                    last_current = [0]
                    def progress_cb(current, total, current_file=""):
                        units_added = current - last_current[0]
                        if units_added > 0:
                            tracker.update(units_added)
                            last_current[0] = current
                        live.update(PipelineUI.generate_renderable(tracker, "ETAPA 3: EXTRAÇÃO DE METADADOS", start_str, total_files, 0.0, current_file, "Extraindo..."))
                    
                    # Extrai metadados do lote
                    chunk_metadatas = extract_metadata_batch(chunk_paths, progress_callback=progress_cb)
                    
                    # Salva no banco progressivamente em transação única por lote
                    meta_lookup = {str(m.file_path.resolve()): m for m in chunk_metadatas}
                    with project.transaction():
                        for item in chunk_items:
                            path_key = str(Path(item.staging_path).resolve())
                            if path_key in meta_lookup:
                                m = meta_lookup[path_key]
                                item.meta_is_video = m.is_video
                                item.meta_date_str = m.date_str
                                item.meta_time_str = m.time_str
                                item.meta_timestamp = m.timestamp.isoformat() if m.timestamp else ""
                                item.meta_camera_model = m.camera_model
                                item.meta_camera_make = m.camera_make
                                item.meta_focal_length_equiv = m.focal_length_equiv
                                item.meta_focal_str = m.focal_str
                                item.meta_aperture_str = m.aperture_str
                                item.meta_shutter_str = m.shutter_str
                                item.meta_iso_str = m.iso_str
                                item.meta_resolution_str = m.resolution_str
                                item.meta_fps_str = m.fps_str
                                item.meta_duration_str = m.duration_str
                                item.meta_original_stem = m.original_stem
                                item.meta_extension = m.extension
                                item.meta_is_raw = m.is_raw
                                item.meta_width = m.width
                                item.meta_height = m.height
                                project.save_item(item)
                    
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA 3: EXTRAÇÃO DE METADADOS", start_str, total_files, 0.0, "Concluído", "Finalizando"))

        # 2. Reconstruir a lista completa de MediaMetadata a partir do Banco
        from src.core.metadata import MediaMetadata
        
        console.print("[cyan]Carregando metadados do banco para classificação...[/cyan]")
        all_metadatas = []
        for item in all_planning_items:
            if item.meta_is_video is not None:
                try:
                    ts = datetime.fromisoformat(item.meta_timestamp) if item.meta_timestamp else None
                    meta = MediaMetadata(
                        file_path=Path(item.staging_path),
                        is_video=item.meta_is_video,
                        date_str=item.meta_date_str,
                        time_str=item.meta_time_str,
                        timestamp=ts,
                        camera_model=item.meta_camera_model,
                        camera_make=item.meta_camera_make,
                        focal_length_equiv=item.meta_focal_length_equiv,
                        focal_str=item.meta_focal_str,
                        aperture_str=item.meta_aperture_str,
                        shutter_str=item.meta_shutter_str,
                        iso_str=item.meta_iso_str,
                        resolution_str=item.meta_resolution_str,
                        fps_str=item.meta_fps_str,
                        duration_str=item.meta_duration_str,
                        original_stem=item.meta_original_stem,
                        extension=item.meta_extension,
                        is_raw=item.meta_is_raw,
                        width=item.meta_width,
                        height=item.meta_height
                    )
                    all_metadatas.append(meta)
                except Exception as e:
                    console.print(f"[red]Erro ao ler metadados do item {item.staging_path}: {e}[/red]")
        
        if not all_metadatas:
            console.print("[red]Nenhum metadado válido para classificar.[/red]")
            return False

        item_lookup = {str(Path(item.staging_path).resolve()): item for item in all_planning_items}

        class_config = config.get("classification", {})
        name_config = config.get("naming", {})

        classified_items = classify_media_batch(all_metadatas, class_config, name_config)
        
        with project.transaction():
            for c_item in classified_items:
                path_key = str(c_item.metadata.file_path.resolve())
                p_item = item_lookup.get(path_key)
                if p_item:
                    p_item.category = c_item.category
                    p_item.target_filename = c_item.target_filename
                    p_item.relative_dest_dir = str(c_item.relative_dest_dir)
                    p_item.extra_dest_dirs_json = json.dumps([str(p) for p in c_item.extra_dest_dirs])
                    project.save_item(p_item)
        
        console.print("[bold green]Planejamento concluído![/bold green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return PlanningStage(stage_id, name)
