"""
Estágio do Pipeline: Identificação de Espécies de Aves (BirdIdStage).
Processa fotos estáticas e vídeos de teleobjetiva/superzoom do projeto,
identifica espécies via YOLOv8 + BioCLIP com prior regional e gera relatórios de revisão.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
from PIL import Image
from rich.console import Console
from rich.live import Live

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from src.core.ui import ProgressTracker, PipelineUI

from .detector import BirdDetector, safe_imread, safe_imwrite, safe_read_image_or_raw
from .classifier import BirdClassifier
from .video_processor import VideoBirdProcessor
from .reporter import export_bird_review_csv, render_bird_summary_table
from .action import apply_bird_organization

console = Console()


class BirdIdStage(PipelineStage):
    """Estágio do IRIS responsável pela identificação taxonômica de espécies de aves."""

    def run(self, project: Project, **kwargs) -> bool:
        init_central_db()

        if not project.has_items():
            console.print("[yellow]Nenhum arquivo no projeto para identificar aves.[/yellow]")
            return True

        module_cfg = config.get("modules.bird_id", {})
        if not module_cfg.get("enabled", True):
            console.print("[dim]Etapa de identificação de aves desabilitada no config. Pulando.[/dim]")
            return True

        # Parâmetros
        classifier_type = module_cfg.get("classifier_type", "inaturalist")
        yolo_model = module_cfg.get("yolo_model", "yolov8s.pt")
        yolo_conf = float(module_cfg.get("yolo_confidence", 0.25))
        min_species_conf = float(module_cfg.get("min_species_confidence", 0.70))
        zoom_threshold_mm = float(module_cfg.get("zoom_threshold_mm", 300.0))
        video_sample_sec = module_cfg.get("video_sample_interval_seconds", None)
        video_target_frames = int(module_cfg.get("video_target_frames", 15))
        video_max_crops = int(module_cfg.get("video_max_crops", 5))
        video_min_crops = int(module_cfg.get("video_min_confident_crops", 2))
        save_crops = bool(module_cfg.get("save_crops", True))

        inat_cfg = module_cfg.get("inaturalist", {})
        default_lat = inat_cfg.get("default_lat", None)
        default_lng = inat_cfg.get("default_lng", None)
        default_acc = inat_cfg.get("positional_accuracy_meters", 25000)
        use_exif_gps = bool(inat_cfg.get("use_exif_gps", True))
        inat_creds = inat_cfg.get("credentials_file", "secrets/inaturalist.json")
        inat_url = inat_cfg.get("api_url", None)
        inat_delay = float(inat_cfg.get("request_delay_seconds", 1.0))

        # Selecionar itens elegíveis no projeto
        eligible_items = []
        raw_exts = {".cr2", ".cr3", ".arw", ".dng", ".nef", ".raw"}
        for item in project.get_items():
            file_path = Path(item.organized_path or item.staging_path or item.original_path)
            ext = file_path.suffix.lower()

            # Critério de elegibilidade:
            # 1. Teleobjetiva/Zoom acentuado (Superzoom Canon)
            focal = getattr(item, "meta_focal_length_equiv", None)
            is_telephoto = focal is not None and focal >= zoom_threshold_mm
            
            # 2. Vídeos ou Fotos (JPEG e RAW)
            if item.meta_is_video or ext in [".mp4", ".mov", ".m4v"]:
                eligible_items.append((item, file_path, True))
            elif ext in [".jpg", ".jpeg"] or ext in raw_exts:
                if focal is None or is_telephoto:
                    eligible_items.append((item, file_path, False))

        if not eligible_items:
            console.print("[dim]Nenhum arquivo com perfil de teleobjetiva/aves encontrado no projeto.[/dim]")
            return True

        console.print(f"[bold cyan]Iniciando identificação de aves em {len(eligible_items)} arquivo(s) (Provedor: {classifier_type})...[/bold cyan]")

        # Inicializa modelos (lazy loading)
        try:
            detector = BirdDetector(model_name=yolo_model, confidence=yolo_conf)
            classifier = BirdClassifier(
                classifier_type=classifier_type,
                inat_credentials_path=inat_creds,
                inat_api_url=inat_url,
                inat_request_delay=inat_delay
            )
            video_proc = VideoBirdProcessor(detector, classifier)
        except Exception as e:
            console.print(f"[bold red]Erro ao inicializar modelos de IA (YOLO/{classifier_type}): {e}[/bold red]")
            return False

        crops_dest_dir = project.project_dir / "recortes_aves"
        if save_crops:
            crops_dest_dir.mkdir(parents=True, exist_ok=True)

        records_to_save = []
        item_record_pairs = []
        total_files = len(eligible_items)
        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")

        with Live(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, "Carregando...", "Iniciando"), console=console, refresh_per_second=4) as live:
            for item, file_path, is_video in eligible_items:
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, file_path.name, "Processando..."))

                # Resolução de Geo-Prior (EXIF ou Padrão)
                exif_lat = getattr(item, "meta_latitude", None) if use_exif_gps else None
                exif_lng = getattr(item, "meta_longitude", None) if use_exif_gps else None
                item_lat = exif_lat if exif_lat is not None else default_lat
                item_lng = exif_lng if exif_lng is not None else default_lng
                item_acc = getattr(item, "meta_gps_accuracy", None) or default_acc
                observed_on = getattr(item, "meta_datetime_original", None)

                try:
                    if is_video:
                        res = video_proc.process_video(
                            file_path,
                            sample_interval_sec=float(video_sample_sec) if video_sample_sec else None,
                            target_frames=video_target_frames,
                            min_confident_crops=video_min_crops,
                            max_crops_to_classify=video_max_crops,
                            lat=item_lat,
                            lng=item_lng,
                            accuracy=item_acc,
                            observed_on=observed_on
                        )
                        if res:
                            crop_path_str = ""
                            if save_crops and res.get("best_crop_bgr") is not None:
                                crop_file = crops_dest_dir / f"crop_{file_path.stem}.jpg"
                                safe_imwrite(str(crop_file), res["best_crop_bgr"])
                                crop_path_str = str(crop_file)

                            conf = res["confidence"]
                            is_confident = res.get("is_confident_detection", True)
                            needs_review = (conf < min_species_conf) or (not is_confident)

                            record = {
                                "item_path": str(file_path),
                                "is_video": True,
                                "species_common": res["species_common"],
                                "species_common_en": res.get("species_common_en", ""),
                                "species_scientific": res["species_scientific"],
                                "family": res.get("family", ""),
                                "order": res.get("order", ""),
                                "confidence": conf,
                                "top2_common": res.get("top2_common", ""),
                                "top2_scientific": res.get("top2_scientific", ""),
                                "top2_confidence": res.get("top2_confidence", 0.0),
                                "top3_common": res.get("top3_common", ""),
                                "top3_scientific": res.get("top3_scientific", ""),
                                "top3_confidence": res.get("top3_confidence", 0.0),
                                "needs_review": needs_review,
                                "crop_saved_path": crop_path_str,
                                "metadata_json": {
                                    "evaluated_crops": res.get("evaluated_crops", 0),
                                    "species_crops_count": res.get("species_crops_count", 0),
                                    "min_confident_crops": video_min_crops,
                                    "vote_distribution": res.get("vote_distribution", {}),
                                    "geo_lat": item_lat,
                                    "geo_lng": item_lng,
                                    "provider": classifier_type
                                }
                            }
                            records_to_save.append(record)
                            item_record_pairs.append((item, record))
                    else:
                        crop_pil = None
                        crop_bgr = None
                        detected = False
                        yolo_c = 0.0

                        # Reutiliza recorte prévio se já existir no disco
                        orig_stem = getattr(item, "meta_original_stem", "") or file_path.stem
                        clean_stem = file_path.stem.split("_[")[0]
                        candidate_crops = [
                            crops_dest_dir / f"crop_{file_path.stem}.jpg",
                            crops_dest_dir / f"crop_{clean_stem}.jpg",
                            crops_dest_dir / f"crop_{orig_stem}.jpg"
                        ]
                        existing_crop = next((p for p in candidate_crops if p.exists()), None)
                        if existing_crop:
                            crop_bgr = safe_imread(str(existing_crop))
                            if crop_bgr is not None:
                                crop_pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
                                detected = True
                                yolo_c = 1.0

                        if crop_pil is None:
                            img_bgr = safe_read_image_or_raw(str(file_path))
                            if img_bgr is not None:
                                crop_pil, crop_bgr, detected, yolo_c, _ = detector.detect_and_crop(img_bgr)

                        # Decisão técnica: Se o YOLO detectou ave, consulta a classificação
                        if crop_pil is not None and detected:
                            preds = classifier.classify_crop(
                                crop_pil,
                                top_k=3,
                                use_tta=True,
                                lat=item_lat,
                                lng=item_lng,
                                accuracy=item_acc,
                                observed_on=observed_on
                            )
                            if preds:
                                top1 = preds[0]
                                conf = top1["confidence"]
                                needs_review = conf < min_species_conf

                                crop_path_str = ""
                                if save_crops and crop_bgr is not None:
                                    crop_file = existing_crop or (crops_dest_dir / f"crop_{file_path.stem}.jpg")
                                    if not crop_file.exists():
                                        safe_imwrite(str(crop_file), crop_bgr)
                                    crop_path_str = str(crop_file)

                                record = {
                                    "item_path": str(file_path),
                                    "is_video": False,
                                    "species_common": top1["common_name"],
                                    "species_common_en": top1.get("common_name_en", ""),
                                    "species_scientific": top1["scientific_name"],
                                    "family": top1.get("family", ""),
                                    "order": top1.get("order", ""),
                                    "confidence": conf,
                                    "top2_common": preds[1]["common_name"] if len(preds) > 1 else "",
                                    "top2_scientific": preds[1]["scientific_name"] if len(preds) > 1 else "",
                                    "top2_confidence": preds[1]["confidence"] if len(preds) > 1 else 0.0,
                                    "top3_common": preds[2]["common_name"] if len(preds) > 2 else "",
                                    "top3_scientific": preds[2]["scientific_name"] if len(preds) > 2 else "",
                                    "top3_confidence": preds[2]["confidence"] if len(preds) > 2 else 0.0,
                                    "needs_review": needs_review,
                                    "crop_saved_path": crop_path_str,
                                    "metadata_json": {
                                        "yolo_detected": detected,
                                        "yolo_conf": yolo_c,
                                        "geo_lat": item_lat,
                                        "geo_lng": item_lng,
                                        "provider": classifier_type
                                    }
                                }
                                records_to_save.append(record)
                                item_record_pairs.append((item, record))
                except Exception as e:
                    console.print(f"[yellow]Aviso ao processar {file_path.name}: {e}[/yellow]")

                tracker.update(1)
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, file_path.name, "Progresso"))

            live.update(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, "Concluído", "Finalizando"))

        # Executar ação unificada de alta certeza (Renomeação + Subpasta + EXIF)
        for item, rec in item_record_pairs:
            try:
                new_path = apply_bird_organization(item, project, rec, module_cfg)
                rec["item_path"] = str(new_path)
            except Exception as e:
                console.print(f"[yellow]Aviso na organização física da ave {rec.get('species_common')}: {e}[/yellow]")

        # Persistir no banco do projeto
        if records_to_save:
            for rec in records_to_save:
                try:
                    project.add_bird_identification(rec)
                except Exception as e:
                    console.print(f"[yellow]Aviso ao persistir identificação de ave ({rec.get('species_common')}): {e}[/yellow]")

            # Exportar relatório CSV
            try:
                csv_path = project.project_dir / "relatorio_aves.csv"
                export_bird_review_csv(records_to_save, csv_path)
            except Exception as e:
                console.print(f"[yellow]Aviso ao exportar relatório CSV de aves: {e}[/yellow]")

            # Renderiza resumo na saída do terminal
            try:
                render_bird_summary_table(records_to_save, console)
                console.print(f"[bold green]OK: Relatório de revisão gerado com sucesso em:[/bold green] {csv_path}")
            except Exception as e:
                console.print(f"[yellow]Aviso ao renderizar tabela de aves: {e}[/yellow]")

        console.print("[bold green]Identificação de aves concluída![/bold green]")
        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdIdStage(stage_id, name)
