import os
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from rich.console import Console
from rich.live import Live
from datetime import datetime
from typing import Optional, List, Tuple

from src.core.pipeline import PipelineStage
from src.core.project import Project, ProjectItem
from src.core.ui import ProgressTracker, PipelineUI
from src.core.config import config
from src.core.geo import GeoService, GEO_WRITABLE_EXTS, build_exiftool_geo_args
from src.core.metadata import read_gps_batch, VIDEO_EXTENSIONS, RAW_EXTENSIONS
from src.modules.ingestion.strategies.base import compute_file_hash

console = Console()

class SanitizationStage(PipelineStage):
    """
    Etapa unificada de Sanitização de Metadados EXIF e Injeção de Geotag (GPS/IPTC/XMP).
    Executa após o Organize de forma seletiva:
    - Atua exclusivamente sobre arquivos destinados a álbuns e nuvem (2_AlbunsDatas),
      incluindo fotos avulsas, rajadas e cópias das amostras de timelapse.
    - PRESERVA integralmente em formato bit-perfect os frames brutos de timelapses
      (4_Timelapses, 4_Timelapses_LongaExposicao) e astrofotografia (5_Astrofotografia),
      evitando regravações físicas desnecessárias e recálculo de hash em massa.
    - Remove blocos obsoletos/duplicados de JPEGs (MPF, MakerNotes, Preview, trailers).
    - Injeta tags GPS e IPTC/XMP (Cidade, Estado, País) para fotos sem GPS nativo.
    - NUNCA regrava arquivos RAW nem vídeos (as coordenadas vão exclusivamente para o nome).
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

        # Coleta de itens: prioriza itens organizados
        organized_items = [it for it in project.get_items(status="organized")]
        copied_items = [it for it in project.get_items(status="copied")]

        if not organized_items and not copied_items:
            console.print("[yellow]Nenhum arquivo no projeto para sanitizar.[/yellow]")
            return True

        using_organized = len(organized_items) > 0
        active_items = organized_items if using_organized else copied_items

        # Seleção cirúrgica de alvos: (Path, Optional[ProjectItem])
        targets: List[Tuple[Path, Optional[ProjectItem]]] = []
        seen_paths = set()
        count_skipped_bulk = 0

        for it in active_items:
            p_str = it.organized_path if using_organized and it.organized_path else it.staging_path
            if not p_str:
                continue
            p = Path(p_str)
            if not p.exists():
                continue

            p_norm = str(p.resolve()).replace("\\", "/")
            rel_dest_norm = (it.relative_dest_dir or "").replace("\\", "/")

            # Pula explicitamente frames brutos de timelapses e astrofotografia
            if "4_Timelapses" in p_norm or "4_Timelapses" in rel_dest_norm or it.category in ("timelapse", "timelapse_long_exposure"):
                count_skipped_bulk += 1
                # Se for timelapse, verifica se possui amostras copiadas para álbuns (2_AlbunsDatas)
                if it.extra_organized_paths_json:
                    try:
                        extra_paths = json.loads(it.extra_organized_paths_json)
                        for ep_str in extra_paths:
                            ep = Path(ep_str)
                            ep_norm = str(ep.resolve()).replace("\\", "/")
                            if ep.exists() and "2_AlbunsDatas" in ep_norm and ep_norm not in seen_paths:
                                seen_paths.add(ep_norm)
                                targets.append((ep, it))
                    except Exception:
                        pass
                continue

            if "5_Astrofotografia" in p_norm or "5_Astrofotografia" in rel_dest_norm or it.category == "astro_lua":
                count_skipped_bulk += 1
                continue

            # Se estiver no modo organizado, restringe a 2_AlbunsDatas ou avulsas/rajadas
            if using_organized:
                is_album = ("2_AlbunsDatas" in p_norm) or ("2_AlbunsDatas" in rel_dest_norm) or (it.category in ("avulsa", "rajada"))
                if not is_album:
                    continue

            if p_norm not in seen_paths:
                seen_paths.add(p_norm)
                targets.append((p, it))

            # Também inclui cópias extras caso existam
            if it.extra_organized_paths_json:
                try:
                    extra_paths = json.loads(it.extra_organized_paths_json)
                    for ep_str in extra_paths:
                        ep = Path(ep_str)
                        ep_norm = str(ep.resolve()).replace("\\", "/")
                        if ep.exists() and "2_AlbunsDatas" in ep_norm and ep_norm not in seen_paths:
                            seen_paths.add(ep_norm)
                            targets.append((ep, it))
                except Exception:
                    pass

        if not targets:
            if count_skipped_bulk > 0:
                console.print(f"[green]✔ Todos os {count_skipped_bulk} frames de timelapses/astrofotografia foram preservados em formato original (bit-perfect).[/green]")
                console.print("[cyan]Nenhum arquivo de álbum (2_AlbunsDatas) pendente de sanitização. Etapa concluída.[/cyan]")
            else:
                console.print("[yellow]Nenhum arquivo elegível para sanitização de álbuns.[/yellow]")
            return True

        total_files = len(targets)
        console.print(f"[cyan]Iniciando sanitização e verificação de geolocalização em {total_files} arquivo(s) de álbum...[/cyan]")
        if count_skipped_bulk > 0:
            console.print(f"[dim]• Frames brutos de timelapse/astro preservados sem alteração:[/dim] [green]{count_skipped_bulk}[/green]")
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
        stage_title = "ETAPA: SANITIZAÇÃO DE METADADOS E GEOTAG (ÁLBUNS)"

        with Live(
            PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Preparando...", "Inicializando"),
            console=console,
            refresh_per_second=4
        ) as live:
            for i in range(0, total_files, batch_size):
                chunk_targets = targets[i:i + batch_size]
                chunk_paths = [p for p, _ in chunk_targets]

                # 1. Leitura rápida somente-leitura de GPS nativo
                gps_map = read_gps_batch(chunk_paths)

                # Separação dos grupos para gravação única
                # Grupo A: JPEGs com GPS nativo -> apenas sanitização (sem GPS)
                # Grupo B: Formatos graváveis sem GPS nativo -> sanitização (se JPEG) + injeção de GPS
                items_sanitize_only_jpeg: List[Tuple[Path, Optional[ProjectItem]]] = []
                items_write_geo_jpeg: List[Tuple[Path, Optional[ProjectItem]]] = []
                items_write_geo_other: List[Tuple[Path, Optional[ProjectItem]]] = []

                for p, it in chunk_targets:
                    p_res_str = str(p.resolve())
                    ext = p.suffix.lower()
                    is_video = ext in VIDEO_EXTENSIONS
                    is_raw = ext in RAW_EXTENSIONS

                    native_lat, native_lng, native_acc = gps_map.get(p_res_str, (None, None, None))

                    if native_lat is not None and native_lng is not None:
                        # Possui GPS nativo da câmera/celular
                        if it:
                            it.meta_latitude = native_lat
                            it.meta_longitude = native_lng
                            it.meta_gps_accuracy = native_acc
                            it.geo_source = "native"
                            it.geo_written = False
                        count_native_gps += 1

                        if ext in [".jpg", ".jpeg"]:
                            items_sanitize_only_jpeg.append((p, it))
                    else:
                        # Não possui GPS nativo
                        if loc and tag_media:
                            if it:
                                it.meta_latitude = loc.lat
                                it.meta_longitude = loc.lng
                                it.meta_gps_accuracy = loc.accuracy_m
                                it.geo_source = "preset"

                            if is_video or is_raw or ext not in GEO_WRITABLE_EXTS:
                                # Regra estrita: NUNCA regravar RAW nem Vídeo
                                if it:
                                    it.geo_written = False
                                count_geo_named_only += 1
                            else:
                                if ext in [".jpg", ".jpeg"]:
                                    items_write_geo_jpeg.append((p, it))
                                else:
                                    items_write_geo_other.append((p, it))
                                if it:
                                    it.geo_written = True
                                count_geo_written += 1
                        else:
                            if ext in [".jpg", ".jpeg"]:
                                items_sanitize_only_jpeg.append((p, it))

                cur_name = chunk_targets[-1][0].name if chunk_targets else ""
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, f"Lote {i // batch_size + 1}", "Processando..."))

                # Execução 1: JPEGs com GPS nativo (apenas limpeza de APP2/MakerNotes)
                if items_sanitize_only_jpeg:
                    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                        f.write("-MPF:all=\n")
                        f.write("-trailer:all=\n")
                        f.write("-MakerNotes:all=\n")
                        f.write("-PreviewImage=\n")
                        f.write("-overwrite_original\n")
                        f.write("-P\n")
                        f.write("-charset\nUTF8\n")
                        f.write("-charset\nfilename=UTF8\n")
                        for p, _ in items_sanitize_only_jpeg:
                            f.write(f"{p.resolve()}\n")
                        argfile_a = f.name
                    try:
                        cmd_a = [
                            exiftool_bin,
                            "-charset", "UTF8",
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
                    geo_args = build_exiftool_geo_args(loc, is_video=False, ext=".jpg")
                    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                        f.write("-MPF:all=\n")
                        f.write("-trailer:all=\n")
                        f.write("-MakerNotes:all=\n")
                        f.write("-PreviewImage=\n")
                        f.write("-overwrite_original\n")
                        f.write("-P\n")
                        for arg in geo_args:
                            f.write(f"{arg}\n")
                        for p, _ in items_write_geo_jpeg:
                            f.write(f"{p.resolve()}\n")
                        argfile_b = f.name
                    try:
                        cmd_b = [
                            exiftool_bin,
                            "-charset", "UTF8",
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
                    geo_args = build_exiftool_geo_args(loc, is_video=False, ext=".png")
                    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                        f.write("-overwrite_original\n")
                        f.write("-P\n")
                        for arg in geo_args:
                            f.write(f"{arg}\n")
                        for p, _ in items_write_geo_other:
                            f.write(f"{p.resolve()}\n")
                        argfile_c = f.name
                    try:
                        cmd_c = [
                            exiftool_bin,
                            "-charset", "UTF8",
                            "-@",
                            argfile_c,
                        ]
                        subprocess.run(cmd_c, capture_output=True, text=True, encoding="utf-8", errors="replace")
                    finally:
                        try:
                            os.unlink(argfile_c)
                        except OSError:
                            pass

                # Atualiza tamanhos, hashes e metadados no SQLite para os alvos processados
                modified_physical_paths = {p.resolve() for p, _ in (items_sanitize_only_jpeg + items_write_geo_jpeg + items_write_geo_other)}
                seen_saved_ids = set()

                with project.transaction():
                    for p, it in chunk_targets:
                        if it is not None:
                            # Atualiza tamanho e hash apenas se o arquivo 'p' foi modificado fisicamente e é a rota principal do item
                            target_str = it.organized_path or it.staging_path or ""
                            if target_str and Path(target_str).resolve() == p.resolve() and p.resolve() in modified_physical_paths:
                                if p.exists():
                                    it.file_size_bytes = p.stat().st_size
                                    it.file_hash = compute_file_hash(p)
                            item_key = it.original_path or getattr(it, "id", None)
                            if item_key not in seen_saved_ids:
                                seen_saved_ids.add(item_key)
                                project.save_item(it)

                tracker.update(len(chunk_targets))
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, cur_name, "Progresso"))

            live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, 0.0, "Concluído", "Finalizando"))

        console.print("[bold green]Sanitização e processamento de geolocalização concluídos![/bold green]")
        if count_skipped_bulk > 0:
            console.print(f"  [dim]• Frames brutos de timelapses/astro preservados (bit-perfect):[/dim] [green]{count_skipped_bulk}[/green]")
        console.print(f"  [dim]• Mídias de álbum com GPS nativo preservado:[/dim] [cyan]{count_native_gps}[/cyan]")
        console.print(f"  [dim]• Fotos de álbum com metadados GPS/IPTC injetados via ExifTool:[/dim] [cyan]{count_geo_written}[/cyan]")
        console.print(f"  [dim]• RAWs/Vídeos preservados intactos (GPS apenas no nome):[/dim] [cyan]{count_geo_named_only}[/cyan]")
        console.print(f"  [dim]• JPEGs de álbum sanitizados (MPF/MakerNotes):[/dim] [cyan]{count_sanitized_jpeg}[/cyan]")

        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return SanitizationStage(stage_id, name)
