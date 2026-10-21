"""
Estágio do Pipeline: Identificação de Espécies de Aves (BirdIdStage).
Processa fotos estáticas e vídeos de teleobjetiva/superzoom do projeto,
identifica espécies via YOLOv8 + BioCLIP com prior regional e gera relatórios de revisão.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.core.ui import ProgressTracker, PipelineUI

from .detector import BirdDetector, safe_imread, safe_imwrite
from .classifier import BirdClassifier
from .video_processor import VideoBirdProcessor
from .reporter import export_bird_review_csv, render_bird_summary_table

console = Console()


class BirdIdStage(PipelineStage):
    """Estágio do IRIS responsável pela identificação taxonômica de espécies de aves."""

    def run(self, project: Project, **kwargs) -> bool:
        if not project.has_items():
            console.print("[yellow]Nenhum arquivo no projeto para identificar aves.[/yellow]")
            return True

        module_cfg = config.get("modules.bird_id", {})
        if not module_cfg.get("enabled", True):
            console.print("[dim]Etapa de identificação de aves desabilitada no config. Pulando.[/dim]")
            return True

        # Parâmetros
        yolo_model = module_cfg.get("yolo_model", "yolov8s.pt")
        yolo_conf = float(module_cfg.get("yolo_confidence", 0.25))
        min_species_conf = float(module_cfg.get("min_species_confidence", 0.60))
        zoom_threshold_mm = float(module_cfg.get("zoom_threshold_mm", 300.0))
        video_sample_sec = float(module_cfg.get("video_sample_interval_seconds", 2.0))
        save_crops = bool(module_cfg.get("save_crops", True))

        # Selecionar itens elegíveis no projeto
        eligible_items = []
        for item in project.get_items():
            file_path = Path(item.organized_path or item.staging_path or item.original_path)
            ext = file_path.suffix.lower()

            # Critério de elegibilidade:
            # 1. Teleobjetiva/Zoom acentuado (Superzoom Canon)
            focal = getattr(item, "meta_focal_length_equiv", None)
            is_telephoto = focal is not None and focal >= zoom_threshold_mm
            
            # 2. Ou categoria marcada como ave / fotos e vídeos elegíveis se zoom não estiver disponível
            if item.meta_is_video or ext in [".mp4", ".mov", ".m4v"]:
                eligible_items.append((item, file_path, True))
            elif ext in [".jpg", ".jpeg"]:
                # Se tiver metadado de zoom, filtra por teleobjetiva; se não tiver, inclui
                if focal is None or is_telephoto:
                    eligible_items.append((item, file_path, False))

        if not eligible_items:
            console.print("[dim]Nenhum arquivo com perfil de teleobjetiva/aves encontrado no projeto.[/dim]")
            return True

        console.print(f"[bold cyan]Iniciando identificação de aves em {len(eligible_items)} arquivo(s)...[/bold cyan]")

        # Inicializa modelos (lazy loading)
        try:
            detector = BirdDetector(model_name=yolo_model, confidence=yolo_conf)
            classifier = BirdClassifier()
            video_proc = VideoBirdProcessor(detector, classifier)
        except Exception as e:
            console.print(f"[bold red]Erro ao inicializar modelos de IA (YOLO/BioCLIP): {e}[/bold red]")
            return False

        crops_dest_dir = project.project_dir / "recortes_aves"
        if save_crops:
            crops_dest_dir.mkdir(parents=True, exist_ok=True)

        records_to_save = []
        total_files = len(eligible_items)
        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")

        with Live(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, "Carregando...", "Iniciando"), console=console, refresh_per_second=4) as live:
            for item, file_path, is_video in eligible_items:
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, file_path.name, "Processando..."))

                try:
                    if is_video:
                        res = video_proc.process_video(file_path, sample_interval_sec=video_sample_sec)
                        if res:
                            crop_path_str = ""
                            if save_crops and res.get("best_crop_bgr") is not None:
                                crop_file = crops_dest_dir / f"crop_{file_path.stem}.jpg"
                                safe_imwrite(str(crop_file), res["best_crop_bgr"])
                                crop_path_str = str(crop_file)

                            conf = res["confidence"]
                            needs_review = conf < min_species_conf

                            record = {
                                "item_path": str(file_path),
                                "is_video": True,
                                "species_common": res["species_common"],
                                "species_scientific": res["species_scientific"],
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
                                    "vote_distribution": res.get("vote_distribution", {})
                                }
                            }
                            records_to_save.append(record)
                    else:
                        img_bgr = safe_imread(str(file_path))
                        if img_bgr is not None:
                            crop_pil, crop_bgr, detected, yolo_c, _ = detector.detect_and_crop(img_bgr)
                            # Se detectou ave ou fallback de foto estática
                            if detected or focal is not None:
                                preds = classifier.classify_crop(crop_pil, top_k=3, use_tta=True)
                                top1 = preds[0]
                                conf = top1["confidence"]
                                needs_review = conf < min_species_conf

                                crop_path_str = ""
                                if save_crops and crop_bgr is not None:
                                    crop_file = crops_dest_dir / f"crop_{file_path.stem}.jpg"
                                    safe_imwrite(str(crop_file), crop_bgr)
                                    crop_path_str = str(crop_file)

                                record = {
                                    "item_path": str(file_path),
                                    "is_video": False,
                                    "species_common": top1["common_name"],
                                    "species_scientific": top1["scientific_name"],
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
                                        "yolo_conf": yolo_c
                                    }
                                }
                                records_to_save.append(record)
                except Exception as e:
                    console.print(f"[yellow]Aviso ao processar {file_path.name}: {e}[/yellow]")

                tracker.update(1)
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, file_path.name, "Progresso"))

            live.update(PipelineUI.generate_renderable(tracker, "ETAPA: IDENTIFICAÇÃO DE AVES", start_str, total_files, 0.0, "Concluído", "Finalizando"))

        # Persistir no banco do projeto
        if records_to_save:
            for rec in records_to_save:
                project.add_bird_identification(rec)

            # Exportar relatório CSV
            csv_path = project.project_dir / "relatorio_aves.csv"
            export_bird_review_csv(records_to_save, csv_path)

            # Renderiza resumo na saída do terminal
            render_bird_summary_table(records_to_save, console)
            console.print(f"[bold green]✓ Relatório de revisão gerado com sucesso em:[/bold green] {csv_path}")

        console.print("[bold green]Identificação de aves concluída![/bold green]")
        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdIdStage(stage_id, name)
