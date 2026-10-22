"""
Estágio do Pipeline: Classificação Taxonômica de Aves (BirdClassifyStage).
Lê os recortes de aves previamente salvos em disco (na raiz do IRIS),
consulta o provedor taxonômico (API iNaturalist com prior geográfico ou BioCLIP local),
consolida espécies (votação ponderada para vídeos) e persiste todas as informações
no banco de dados SQLite e no relatório CSV de conferência (relatorio_aves.csv).
Arquivos originais e organizados PERMANECEM INTACTOS nesta etapa.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import cv2
from PIL import Image
from rich.console import Console
from rich.live import Live

from src.core.config import config
from src.core.logger import log_event
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from src.core.ui import ProgressTracker, PipelineUI

from .detector import safe_imread
from .classifier import BirdClassifier
from .video_processor import VideoBirdProcessor
from .reporter import export_bird_review_csv, render_bird_summary_table

console = Console()


class BirdClassifyStage(PipelineStage):
    """Estágio atômico de classificação taxonômica de aves via iNaturalist / BioCLIP."""

    def run(self, project: Project, **kwargs) -> bool:
        init_central_db()

        if not project.has_items():
            console.print("[yellow]Nenhum arquivo no projeto para identificar aves.[/yellow]")
            return True

        module_cfg = config.get("modules.bird_id", {})
        if not module_cfg.get("enabled", True):
            console.print("[dim]Identificação de aves desabilitada no config. Pulando.[/dim]")
            return True

        classifier_type = module_cfg.get("classifier_type", "inaturalist")
        min_species_conf = float(module_cfg.get("min_species_confidence", 0.70))
        video_min_crops = int(module_cfg.get("video_min_confident_crops", 2))

        inat_cfg = module_cfg.get("inaturalist", {})
        default_lat = inat_cfg.get("default_lat", None)
        default_lng = inat_cfg.get("default_lng", None)
        default_acc = inat_cfg.get("positional_accuracy_meters", 25000)
        use_exif_gps = bool(inat_cfg.get("use_exif_gps", True))
        inat_creds = inat_cfg.get("credentials_file", "secrets/inaturalist.json")
        inat_url = inat_cfg.get("api_url", None)
        inat_delay = float(inat_cfg.get("request_delay_seconds", 1.0))

        # 1. Recupera identificações/detecções já registradas no banco do projeto
        existing_records = project.list_bird_identifications()
        records_with_crops = [r for r in existing_records if r.get("crop_saved_path")]

        # Se não houver recortes registrados no banco, tenta localizar por fallback nos itens do projeto
        if not records_with_crops:
            dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
            iris_crops_folder = module_cfg.get("iris_crops_folder", "10_Aves/Recortes")
            crops_dest_dir = dest_root / iris_crops_folder / project.name
            
            # Varre se os recortes já existem na pasta física do IRIS
            for item in project.get_items():
                p = Path(item.organized_path or item.staging_path or item.original_path)
                is_vid = bool(item.meta_is_video or p.suffix.lower() in [".mp4", ".mov", ".m4v"])
                if is_vid:
                    vid_crops = sorted(crops_dest_dir.glob(f"crop_{p.stem}_f*.jpg"))
                    if vid_crops:
                        records_with_crops.append({
                            "item_path": str(p),
                            "is_video": True,
                            "crop_saved_path": str(vid_crops[0].resolve()),
                            "metadata_json": {
                                "detection_status": "detected",
                                "video_crops": [{"crop_path": str(vc.resolve())} for vc in vid_crops]
                            }
                        })
                else:
                    candidate_crop = crops_dest_dir / f"crop_{p.stem}.jpg"
                    if candidate_crop.exists():
                        records_with_crops.append({
                            "item_path": str(p),
                            "is_video": False,
                            "crop_saved_path": str(candidate_crop.resolve()),
                            "metadata_json": {"detection_status": "detected"}
                        })

        if not records_with_crops:
            console.print("[yellow]⚠ Nenhum recorte de ave registrado no banco ou encontrado em disco.[/yellow]")
            console.print("[dim]Dica: Execute a etapa anterior de Detecção (bird_detect) para gerar os recortes das aves primeiro.[/dim]")
            return True

        console.print(f"[bold cyan]Iniciando classificação taxonômica de {len(records_with_crops)} recorte(s) (Provedor: {classifier_type})...[/bold cyan]")

        # Inicializa o classificador e o processador de vídeo
        try:
            classifier = BirdClassifier(
                classifier_type=classifier_type,
                inat_credentials_path=inat_creds,
                inat_api_url=inat_url,
                inat_request_delay=inat_delay
            )
            video_proc = VideoBirdProcessor(classifier=classifier)
        except Exception as e:
            console.print(f"[bold red]Erro ao inicializar classificador ({classifier_type}): {e}[/bold red]")
            return False

        # Mapeamento rápido de ProjectItem por item_path para resolução de GPS/EXIF
        items_by_path = {}
        for it in project.get_items():
            for p_str in [it.organized_path, it.staging_path, it.original_path]:
                if p_str:
                    items_by_path[p_str] = it
                    items_by_path[str(Path(p_str).resolve())] = it

        classified_records: List[Dict[str, Any]] = []
        total_files = len(records_with_crops)
        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")

        with Live(
            PipelineUI.generate_renderable(tracker, "ETAPA: CLASSIFICAÇÃO TAXONÔMICA DE AVES", start_str, total_files, 0.0, "Carregando...", "Iniciando"),
            console=console,
            refresh_per_second=4
        ) as live:
            for rec in records_with_crops:
                item_path_str = rec.get("item_path", "")
                p_item = items_by_path.get(item_path_str)
                file_name = Path(item_path_str).name if item_path_str else "Recorte"
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: CLASSIFICAÇÃO TAXONÔMICA DE AVES", start_str, total_files, 0.0, file_name, "Classificando..."))

                # Resolução de Geo-Prior (EXIF ou Padrão)
                exif_lat = getattr(p_item, "meta_latitude", None) if (p_item and use_exif_gps) else None
                exif_lng = getattr(p_item, "meta_longitude", None) if (p_item and use_exif_gps) else None
                item_lat = exif_lat if exif_lat is not None else default_lat
                item_lng = exif_lng if exif_lng is not None else default_lng
                item_acc = getattr(p_item, "meta_gps_accuracy", None) or default_acc if p_item else default_acc
                observed_on = getattr(p_item, "meta_datetime_original", None) if p_item else None

                is_video = rec.get("is_video", False)
                crop_saved_path = rec.get("crop_saved_path", "")
                meta_json = rec.get("metadata_json", {})

                try:
                    if is_video:
                        # Extrai a lista de recortes salvos na Etapa 1
                        video_crops = meta_json.get("video_crops", [])
                        if not video_crops and crop_saved_path:
                            video_crops = [{"crop_path": crop_saved_path}]

                        res = video_proc.classify_video_crops(
                            saved_crops=video_crops,
                            classifier=classifier,
                            duration_sec=meta_json.get("duration_sec", 0.0),
                            lat=item_lat,
                            lng=item_lng,
                            accuracy=item_acc,
                            observed_on=observed_on,
                            min_confident_crops=video_min_crops
                        )

                        if res:
                            conf = res["confidence"]
                            is_confident = res.get("is_confident_detection", True)
                            needs_review = (conf < min_species_conf) or (not is_confident)

                            merged_meta = dict(meta_json)
                            merged_meta.update({
                                "evaluated_crops": res.get("evaluated_crops", len(video_crops)),
                                "species_crops_count": res.get("species_crops_count", 0),
                                "min_confident_crops": video_min_crops,
                                "vote_distribution": res.get("vote_distribution", {}),
                                "geo_lat": item_lat,
                                "geo_lng": item_lng,
                                "provider": classifier_type,
                                "detection_status": "classified"
                            })

                            updated_rec = {
                                "item_path": item_path_str,
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
                                "crop_saved_path": crop_saved_path,
                                "metadata_json": merged_meta
                            }
                            project.add_bird_identification(updated_rec)
                            classified_records.append(updated_rec)
                    else:
                        if crop_saved_path and Path(crop_saved_path).exists():
                            crop_bgr = safe_imread(crop_saved_path)
                            if crop_bgr is not None:
                                crop_pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
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

                                    merged_meta = dict(meta_json)
                                    merged_meta.update({
                                        "geo_lat": item_lat,
                                        "geo_lng": item_lng,
                                        "provider": classifier_type,
                                        "detection_status": "classified"
                                    })

                                    updated_rec = {
                                        "item_path": item_path_str,
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
                                        "crop_saved_path": crop_saved_path,
                                        "metadata_json": merged_meta
                                    }
                                    project.add_bird_identification(updated_rec)
                                    classified_records.append(updated_rec)
                except Exception as e:
                    log_event(f"Erro ao classificar recorte de {file_name}: {e}", level="error")
                    console.print(f"[yellow]Aviso ao classificar recorte de {file_name}: {e}[/yellow]")

                tracker.update(1)
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA: CLASSIFICAÇÃO TAXONÔMICA DE AVES", start_str, total_files, 0.0, file_name, "Progresso"))

            live.update(PipelineUI.generate_renderable(tracker, "ETAPA: CLASSIFICAÇÃO TAXONÔMICA DE AVES", start_str, total_files, 0.0, "Concluído", "Finalizando"))

        if classified_records:
            # Exportar relatório CSV de conferência
            try:
                csv_path = project.project_dir / "relatorio_aves.csv"
                export_bird_review_csv(classified_records, csv_path)
            except Exception as e:
                console.print(f"[yellow]Aviso ao exportar relatório CSV de aves: {e}[/yellow]")

            # Renderiza resumo no console
            try:
                render_bird_summary_table(classified_records, console)
                console.print(f"[bold green]OK: Classificação taxonômica concluída com sucesso![/bold green]")
                console.print(f"[dim]Relatório de conferência gerado em:[/dim] {csv_path}")
            except Exception as e:
                console.print(f"[yellow]Aviso ao renderizar tabela de aves: {e}[/yellow]")

        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdClassifyStage(stage_id, name)
