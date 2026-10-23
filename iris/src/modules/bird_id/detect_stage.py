"""
Estágio do Pipeline: Detecção e Recorte de Aves (BirdDetectStage).
Utiliza YOLOv8s para escanear fotografias teleobjetivas, RAWs e vídeos,
extrai bounding boxes das aves e salva os recortes em alta resolução
exclusivamente na raiz do IRIS ({destination_root}/10_Aves/Recortes/{project_name}/),
registrando todos os caminhos e metadados no SQLite do projeto.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live

from src.core.config import config
from src.core.logger import log_event
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from src.core.ui import ProgressTracker, PipelineUI

import cv2
from .detector import BirdDetector, safe_imwrite, safe_read_image_or_raw
from .video_processor import VideoBirdProcessor, calculate_sharpness

console = Console()


class BirdDetectStage(PipelineStage):
    """Estágio atômico de detecção de aves via YOLOv8 e extração de recortes."""

    def run(self, project: Project, **kwargs) -> bool:
        init_central_db()

        if not project.has_items():
            console.print("[yellow]Nenhum arquivo no projeto para detecção de aves.[/yellow]")
            return True

        module_cfg = config.get("modules.bird_id", {})
        if not module_cfg.get("enabled", True):
            console.print("[dim]Detecção de aves desabilitada no config. Pulando.[/dim]")
            return True

        yolo_model = module_cfg.get("yolo_model", "yolov8s.pt")
        yolo_conf = float(module_cfg.get("yolo_confidence", 0.25))
        zoom_threshold_mm = float(module_cfg.get("zoom_threshold_mm", 300.0))
        video_sample_sec = module_cfg.get("video_sample_interval_seconds", None)
        video_target_frames = int(module_cfg.get("video_target_frames", 15))
        video_max_crops = int(module_cfg.get("video_max_crops", 5))

        iris_crops_folder = module_cfg.get("iris_crops_folder", "10_Aves/Recortes")
        dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
        crops_dest_dir = dest_root / iris_crops_folder / project.name
        crops_dest_dir.mkdir(parents=True, exist_ok=True)

        # Selecionar itens elegíveis no projeto
        eligible_items = []
        raw_exts = {".cr2", ".cr3", ".arw", ".dng", ".nef", ".raw"}
        for item in project.get_items():
            file_path = Path(item.organized_path or item.staging_path or item.original_path)
            ext = file_path.suffix.lower()

            focal = getattr(item, "meta_focal_length_equiv", None)
            is_telephoto = focal is not None and focal >= zoom_threshold_mm

            if item.meta_is_video or ext in [".mp4", ".mov", ".m4v"]:
                eligible_items.append((item, file_path, True))
            elif ext in [".jpg", ".jpeg"] or ext in raw_exts:
                if focal is None or is_telephoto:
                    eligible_items.append((item, file_path, False))

        if not eligible_items:
            console.print("[dim]Nenhum arquivo com perfil de teleobjetiva/aves encontrado no projeto.[/dim]")
            return True

        console.print(f"[bold cyan]Iniciando detecção de aves (YOLOv8) em {len(eligible_items)} arquivo(s)...[/bold cyan]")
        console.print(f"[dim]Recortes serão salvos exclusivamente na raiz do IRIS:[/dim] [cyan]{crops_dest_dir}[/cyan]")

        try:
            detector = BirdDetector(model_name=yolo_model, confidence=yolo_conf)
            video_proc = VideoBirdProcessor(detector=detector)
        except Exception as e:
            console.print(f"[bold red]Erro ao inicializar detector YOLO ({yolo_model}): {e}[/bold red]")
            return False

        detected_count = 0
        total_files = len(eligible_items)
        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")

        with Live(
            PipelineUI.generate_renderable(tracker, "ETAPA: DETECÇÃO E RECORTE DE AVES", start_str, total_files, 0.0, "Carregando...", "Iniciando"),
            console=console,
            refresh_per_second=4
        ) as live:
            for item, file_path, is_video in eligible_items:
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: DETECÇÃO E RECORTE DE AVES", start_str, total_files, 0.0, file_path.name, "Analisando..."))

                try:
                    if is_video:
                        # Extrai os N melhores recortes de vídeo ranqueados por nitidez
                        extraction = video_proc.extract_best_video_crops(
                            video_path=file_path,
                            output_dir=crops_dest_dir,
                            stem=file_path.stem,
                            sample_interval_sec=float(video_sample_sec) if video_sample_sec else None,
                            target_frames=video_target_frames,
                            max_crops_to_extract=video_max_crops
                        )

                        if extraction and extraction.get("saved_crops"):
                            best_path = extraction.get("best_crop_path", "")
                            clean_video_crops = [
                                {k: v for k, v in sc.items() if k not in ("pil_img", "bgr_img")}
                                for sc in extraction.get("saved_crops", [])
                            ]
                            record = {
                                "item_path": str(file_path),
                                "is_video": True,
                                "crop_saved_path": best_path,
                                "metadata_json": {
                                    "yolo_detected": True,
                                    "duration_sec": extraction.get("duration_sec", 0.0),
                                    "total_sampled_frames": extraction.get("total_sampled_frames", 0),
                                    "detected_bird_frames": extraction.get("detected_bird_frames", 0),
                                    "video_crops": clean_video_crops,
                                    "evaluated_crops": len(clean_video_crops),
                                    "max_crops_configured": video_max_crops,
                                    "best_crop_path": best_path,
                                    "detection_status": "detected"
                                }
                            }
                            project.save_bird_detection(record)
                            detected_count += 1
                    else:
                        crop_file = crops_dest_dir / f"crop_{file_path.stem}.jpg"
                        crop_path_str = ""
                        detected = False
                        yolo_c = 0.0
                        bbox = None
                        sharpness = None

                        if crop_file.exists():
                            detected = True
                            yolo_c = 1.0
                            crop_path_str = str(crop_file.resolve())
                        else:
                            img_bgr = safe_read_image_or_raw(str(file_path))
                            if img_bgr is not None:
                                _, crop_bgr, detected, yolo_c, bbox = detector.detect_and_crop(img_bgr)
                                if detected and crop_bgr is not None:
                                    safe_imwrite(str(crop_file), crop_bgr, quality=95)
                                    crop_path_str = str(crop_file.resolve())
                                    try:
                                        crop_gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
                                        sharpness = calculate_sharpness(crop_gray)
                                    except Exception:
                                        sharpness = 0.0

                        if detected and crop_path_str:
                            meta = {
                                "yolo_detected": True,
                                "yolo_conf": float(yolo_c),
                                "bbox": bbox,
                                "crop_saved_path": crop_path_str,
                                "detection_status": "detected"
                            }
                            if sharpness is not None:
                                meta["sharpness"] = float(sharpness)
                            record = {
                                "item_path": str(file_path),
                                "is_video": False,
                                "crop_saved_path": crop_path_str,
                                "metadata_json": meta
                            }
                            project.save_bird_detection(record)
                            detected_count += 1
                except Exception as e:
                    log_event(f"Erro ao detectar ave em {file_path.name}: {e}", level="error")
                    console.print(f"[yellow]Aviso ao detectar ave em {file_path.name}: {e}[/yellow]")

                tracker.update(1)
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: DETECÇÃO E RECORTE DE AVES", start_str, total_files, 0.0, file_path.name, "Progresso"))

            live.update(PipelineUI.generate_renderable(tracker, "ETAPA: DETECÇÃO E RECORTE DE AVES", start_str, total_files, 0.0, "Concluído", "Finalizando"))

        console.print(f"[bold green]OK: Detecção concluída![/bold green] Aves detectadas em [bold cyan]{detected_count}/{total_files}[/bold cyan] arquivo(s).")
        console.print(f"[dim]Recortes armazenados em:[/dim] [cyan]{crops_dest_dir}[/cyan]")
        console.print("[dim]Informações dos recortes persistidas no banco de dados do projeto. Pronto para a etapa de identificação.[/dim]")
        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdDetectStage(stage_id, name)
