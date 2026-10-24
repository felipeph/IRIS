#!/usr/bin/env python3
"""
Script de Reconciliação de Identificações de Aves via iNaturalist API (IRIS Bird ID).
Reclassifica os recortes já existentes de um projeto usando a API corrigida do iNaturalist v2,
popula o banco de dados local e central (iris_central.db), regera o 'relatorio_aves.csv'
e exibe o resumo visual no terminal com as porcentagens normalizadas.
"""

import sys
import argparse
from pathlib import Path

# Configura encoding UTF-8 seguro no console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
IRIS_ROOT = SCRIPT_DIR.parent
if str(IRIS_ROOT) not in sys.path:
    sys.path.insert(0, str(IRIS_ROOT))

import cv2
from PIL import Image
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn

from src.core.config import config
from src.core.project import get_project, init_central_db
from src.modules.bird_id.classifier import BirdClassifier
from src.modules.bird_id.detector import safe_imread
from src.modules.bird_id.reporter import export_bird_review_csv, render_bird_summary_table

console = Console()


def reconcile_project(project_name: str, apply_actions: bool = False):
    console.print(Panel.fit(
        f"[bold cyan]IRIS - Reconciliação de Aves (iNaturalist API v2)[/bold cyan]\n"
        f"Projeto: [bold yellow]{project_name}[/bold yellow]",
        border_style="cyan"
    ))

    # 1. Garante esquema central inicializado
    init_central_db(force=True)

    proj = get_project(project_name)
    if not proj:
        console.print(f"[bold red]❌ Projeto '{project_name}' não encontrado![/bold red]")
        return False

    items = proj.get_items()
    if not items:
        console.print("[yellow]Nenhum arquivo encontrado no projeto.[/yellow]")
        return False

    crops_dir = proj.project_dir / "recortes_aves"
    if not crops_dir.exists():
        console.print(f"[bold red]❌ Diretório de recortes '{crops_dir}' não encontrado![/bold red]")
        return False

    console.print(f"[cyan]Total de itens registrados no projeto:[/cyan] [bold]{len(items)}[/bold]")
    console.print(f"[cyan]Pasta de recortes verificada:[/cyan] [dim]{crops_dir}[/dim]\n")

    # Carrega configurações do módulo bird_id
    module_cfg = config.get("modules.bird_id", {})
    min_species_conf = float(module_cfg.get("min_species_confidence", 0.70))
    inat_cfg = module_cfg.get("inaturalist", {})
    from src.core.geo import GeoService
    project_loc = None
    if hasattr(project, "geo_location_id") and project.geo_location_id:
        project_loc = GeoService.get_location(project.geo_location_id)
    if not project_loc:
        project_loc = GeoService.get_default_location()

    if project_loc:
        default_lat = project_loc.lat
        default_lng = project_loc.lng
        default_acc = project_loc.accuracy_m
    else:
        default_lat = inat_cfg.get("default_lat", -19.92)
        default_lng = inat_cfg.get("default_lng", -43.94)
        default_acc = inat_cfg.get("positional_accuracy_meters", 25000)

    use_exif_gps = bool(inat_cfg.get("use_exif_gps", True))
    inat_creds = inat_cfg.get("credentials_file", "secrets/inaturalist.json")
    inat_url = inat_cfg.get("api_url", None)
    inat_delay = float(inat_cfg.get("request_delay_seconds", 1.0))

    console.print("[dim]Inicializando cliente iNaturalist com suporte completo a API v2...[/dim]")
    classifier = BirdClassifier(
        classifier_type="inaturalist",
        inat_credentials_path=inat_creds,
        inat_api_url=inat_url,
        inat_request_delay=inat_delay
    )

    records_to_save = []
    crops_classified = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Classificando recortes com iNaturalist...", total=len(items))

        for item in items:
            file_path = Path(item.organized_path or item.staging_path or item.original_path)
            stem = file_path.stem
            clean_stem = stem.split("_[")[0]
            orig_stem = getattr(item, "meta_original_stem", "") or stem

            candidates = [
                crops_dir / f"crop_{stem}.jpg",
                crops_dir / f"crop_{clean_stem}.jpg",
                crops_dir / f"crop_{orig_stem}.jpg"
            ]
            crop_file = next((c for c in candidates if c.exists()), None)

            if crop_file is not None:
                crop_bgr = safe_imread(str(crop_file))
                if crop_bgr is not None:
                    crop_pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))

                    # Resolução de Geo-Prior
                    exif_lat = getattr(item, "meta_latitude", None) if use_exif_gps else None
                    exif_lng = getattr(item, "meta_longitude", None) if use_exif_gps else None
                    item_lat = exif_lat if exif_lat is not None else default_lat
                    item_lng = exif_lng if exif_lng is not None else default_lng
                    item_acc = getattr(item, "meta_gps_accuracy", None) or default_acc
                    observed_on = getattr(item, "meta_datetime_original", None)

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
                        conf = top1["confidence"]  # Normalizado entre 0.0 e 1.0
                        needs_review = conf < min_species_conf

                        is_vid = bool(item.meta_is_video or file_path.suffix.lower() in [".mp4", ".mov", ".m4v"])

                        rec = {
                            "item_path": str(file_path),
                            "is_video": is_vid,
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
                            "crop_saved_path": str(crop_file),
                            "metadata_json": {
                                "yolo_detected": True,
                                "geo_lat": item_lat,
                                "geo_lng": item_lng,
                                "provider": "inaturalist",
                                "reconciled": True
                            }
                        }

                        # Persiste atômico (local + central)
                        try:
                            proj.add_bird_identification(rec)
                        except Exception as e:
                            console.print(f"[yellow]Aviso ao persistir no SQLite: {e}[/yellow]")

                        records_to_save.append(rec)
                        crops_classified += 1

            progress.advance(task)

    console.print(f"\n[bold green]✔ Total de itens reclassificados com sucesso:[/bold green] [bold]{crops_classified}[/bold]")

    # Exporta relatório CSV limpo
    csv_path = proj.project_dir / "relatorio_aves.csv"
    try:
        export_bird_review_csv(records_to_save, csv_path)
        console.print(f"[bold green]✔ Relatório CSV regenerado em:[/bold green] {csv_path}")
    except Exception as e:
        console.print(f"[bold red]Erro ao exportar CSV: {e}[/bold red]")

    # Renderiza tabela resumo no terminal
    try:
        render_bird_summary_table(records_to_save, console)
    except Exception as e:
        console.print(f"[yellow]Aviso ao renderizar tabela: {e}[/yellow]")

    console.print("\n[bold green]🎉 Reconciliação do projeto concluída com êxito![/bold green]")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconciliador de Identificações de Aves via iNaturalist")
    parser.add_argument("--project", default="2026-10-22_09-45_TESTE_INATURALIST - Copy", help="Nome do projeto a reconciliar")
    parser.add_argument("--apply-actions", action="store_true", help="Aplica organização física se alta certeza")
    args = parser.parse_args()

    success = reconcile_project(args.project, apply_actions=args.apply_actions)
    sys.exit(0 if success else 1)
