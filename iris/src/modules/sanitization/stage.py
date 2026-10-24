import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from rich.console import Console
from rich.live import Live
from datetime import datetime

from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.core.ui import ProgressTracker, PipelineUI
from src.core.config import config
from src.core.geo import GeoService, GEO_WRITABLE_EXTS, build_exiftool_geo_args
from src.core.metadata import read_gps_batch, VIDEO_EXTENSIONS, RAW_EXTENSIONS
from src.modules.ingestion.strategies.base import compute_file_hash

console = Console()

class SanitizationStage(PipelineStage):
    """
    Etapa unificada de Sanitização de Metadados EXIF e Injeção de Geotag (GPS/IPTC/XMP).
    Executa em lote com uma ÚNICA chamada do ExifTool por arquivo elegível:
    - Remove blocos obsoletos/duplicados de JPEGs (MPF, MakerNotes, Preview, trailers).
    - Injeta tags GPS e IPTC/XMP (Cidade, Estado por extenso, País, Sub-location) para fotos sem GPS nativo.
    - NUNCA regrava arquivos RAW nem vídeos (as coordenadas vão exclusivamente para o nome do arquivo).
    - Recalcula hash e tamanho uma única vez somente para os arquivos fisicamente modificados.
    """

    def run(self, project: Project) -> bool:
        if not project.has_items():
            console.print("[yellow]Nenhum arquivo no projeto para sanitizar.[/yellow]")
            return True

        # Pre-flight check
        env_exif = os.getenv("IRIS_EXIFTOOL_PATH")
        if env_exif and Path(env_exif).exists():
            exiftool_bin = env_exif
        else:
            exiftool_bin = shutil.which("exiftool")
        if not exiftool_bin:
            console.print("[bold red]ERRO: exiftool não encontrado no PATH![/bold red]")
            console.print("Por favor, instale o exiftool para continuar.")
            return False

        # Local de geolocalização do projeto
        loc = None
        if hasattr(project, "geo_location_id") and project.geo_location_id:
            loc = GeoService.get_location(project.geo_location_id)
        if not loc:
            loc = GeoService.get_default_location()

        tag_media = bool(config.get("geo.tag_media", True))

        all_copied_items = [
            item for item in project.get_items(status="copied")
            if item.staging_path and Path(item.staging_path).exists()
        ]

        if not all_copied_items:
            console.print("[yellow]Nenhum arquivo elegível em staging para sanitização.[/yellow]")
            return True

        total_files = len(all_copied_items)
        console.print(f"[cyan]Iniciando sanitização e verificação de geolocalização em {total_files} arquivos...[/cyan]")
        if loc:
            console.print(f"[dim]• Localização Ativa:[/dim] [green]{loc.label}[/green] ({loc.city}, {loc.state})")
        else:
            console.print("[yellow]• Nenhuma localização ativa configurada para o projeto.[/yellow]")

        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")

        count_native_gps = 0
        count_geo_written = 0
        count_geo_named_only = 0
        count_sanitized_jpeg = 0

        batch_size = 500
        stage_title = "ETAPA: SANITIZAÇÃO DE METADADOS E GEOTAG"

        with Live(
            PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Preparando...", "Inicializando"),
            console=console,
            refresh_per_second=4
        ) as live:
            for i in range(0, total_files, batch_size):
                chunk_items = all_copied_items[i:i + batch_size]
                chunk_paths = [Path(it.staging_path) for it in chunk_items]

                # 1. Leitura rápida somente-leitura de GPS nativo
                gps_map = read_gps_batch(chunk_paths)

                # Separação dos grupos para gravação única
                # Grupo A: JPEGs com GPS nativo -> apenas sanitização (sem GPS)
                # Grupo B: Formatos graváveis sem GPS nativo -> sanitização (se JPEG) + injeção de GPS
                items_sanitize_only_jpeg = []
                items_write_geo_jpeg = []
                items_write_geo_other = []

                for it in chunk_items:
                    p = Path(it.staging_path)
                    p_res_str = str(p.resolve())
                    ext = p.suffix.lower()
                    is_video = ext in VIDEO_EXTENSIONS
                    is_raw = ext in RAW_EXTENSIONS

                    native_lat, native_lng, native_acc = gps_map.get(p_res_str, (None, None, None))

                    if native_lat is not None and native_lng is not None:
                        # Possui GPS nativo da câmera/celular
                        it.meta_latitude = native_lat
                        it.meta_longitude = native_lng
                        it.meta_gps_accuracy = native_acc
                        it.geo_source = "native"
                        it.geo_written = False
                        count_native_gps += 1

                        if ext in [".jpg", ".jpeg"]:
                            items_sanitize_only_jpeg.append(it)
                    else:
                        # Não possui GPS nativo
                        if loc and tag_media:
                            it.meta_latitude = loc.lat
                            it.meta_longitude = loc.lng
                            it.meta_gps_accuracy = loc.accuracy_m
                            it.geo_source = "preset"

                            if is_video or is_raw or ext not in GEO_WRITABLE_EXTS:
                                # Regra estrita: NUNCA regravar RAW nem Vídeo
                                it.geo_written = False
                                count_geo_named_only += 1
                            else:
                                if ext in [".jpg", ".jpeg"]:
                                    items_write_geo_jpeg.append(it)
                                else:
                                    items_write_geo_other.append(it)
                                it.geo_written = True
                                count_geo_written += 1
                        else:
                            if ext in [".jpg", ".jpeg"]:
                                items_sanitize_only_jpeg.append(it)

                cur_name = Path(chunk_items[-1].staging_path).name if chunk_items else ""
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, f"Lote {i // batch_size + 1}", "Processando..."))

                # Execução 1: JPEGs com GPS nativo (apenas limpeza de APP2/MakerNotes)
                if items_sanitize_only_jpeg:
                    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                        for it in items_sanitize_only_jpeg:
                            f.write(f"{Path(it.staging_path).resolve()}\n")
                        argfile_a = f.name
                    try:
                        cmd_a = [
                            exiftool_bin,
                            "-MPF:all=",
                            "-trailer:all=",
                            "-MakerNotes:all=",
                            "-PreviewImage=",
                            "-overwrite_original",
                            "-P",
                            "-charset", "filename=utf8",
                            "-@",
                            argfile_a,
                        ]
                        subprocess.run(cmd_a, capture_output=True, text=True, encoding="utf-8", errors="replace")
                        count_sanitized_jpeg += len(items_sanitize_only_jpeg)
                    finally:
                        try:
                            os.unlink(argfile_a)
                        except OSError:
                            pass

                # Execução 2: JPEGs sem GPS (limpeza de APP2/MakerNotes + injeção de GPS/IPTC em UMA ÚNICA chamada)
                if items_write_geo_jpeg and loc:
                    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                        for it in items_write_geo_jpeg:
                            f.write(f"{Path(it.staging_path).resolve()}\n")
                        argfile_b = f.name
                    try:
                        geo_args = build_exiftool_geo_args(loc, is_video=False, ext=".jpg")
                        cmd_b = [
                            exiftool_bin,
                            "-MPF:all=",
                            "-trailer:all=",
                            "-MakerNotes:all=",
                            "-PreviewImage=",
                            *geo_args,
                            "-overwrite_original",
                            "-P",
                            "-@",
                            argfile_b,
                        ]
                        subprocess.run(cmd_b, capture_output=True, text=True, encoding="utf-8", errors="replace")
                        count_sanitized_jpeg += len(items_write_geo_jpeg)
                    finally:
                        try:
                            os.unlink(argfile_b)
                        except OSError:
                            pass

                # Execução 3: Outras imagens graváveis sem GPS (PNG/WEBP/HEIC/TIFF) -> apenas injeção de GPS/IPTC
                if items_write_geo_other and loc:
                    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                        for it in items_write_geo_other:
                            f.write(f"{Path(it.staging_path).resolve()}\n")
                        argfile_c = f.name
                    try:
                        geo_args = build_exiftool_geo_args(loc, is_video=False, ext=".png")
                        cmd_c = [
                            exiftool_bin,
                            *geo_args,
                            "-overwrite_original",
                            "-P",
                            "-@",
                            argfile_c,
                        ]
                        subprocess.run(cmd_c, capture_output=True, text=True, encoding="utf-8", errors="replace")
                    finally:
                        try:
                            os.unlink(argfile_c)
                        except OSError:
                            pass

                # Atualiza tamanhos, hashes e metadados no SQLite em transação única por lote
                modified_paths = {it.original_path for it in items_sanitize_only_jpeg} | \
                                 {it.original_path for it in items_write_geo_jpeg} | \
                                 {it.original_path for it in items_write_geo_other}

                with project.transaction():
                    for it in chunk_items:
                        p = Path(it.staging_path)
                        if p.exists() and it.original_path in modified_paths:
                            new_size = p.stat().st_size
                            it.file_size_bytes = new_size
                            it.file_hash = compute_file_hash(p)
                        project.save_item(it)

                tracker.update(len(chunk_items))
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, cur_name, "Progresso"))

            live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Concluído", "Finalizando"))

        console.print("[bold green]Sanitização e processamento de geolocalização concluídos![/bold green]")
        console.print(f"  [dim]• Mídias com GPS nativo preservado:[/dim] [cyan]{count_native_gps}[/cyan]")
        console.print(f"  [dim]• Fotos com metadados GPS/IPTC injetados via ExifTool:[/dim] [cyan]{count_geo_written}[/cyan]")
        console.print(f"  [dim]• RAWs/Vídeos preservados intactos (GPS apenas no nome):[/dim] [cyan]{count_geo_named_only}[/cyan]")
        console.print(f"  [dim]• JPEGs sanitizados (MPF/MakerNotes):[/dim] [cyan]{count_sanitized_jpeg}[/cyan]")

        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return SanitizationStage(stage_id, name)
