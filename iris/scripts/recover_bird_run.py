"""
Script de Recuperação e Reconciliação: Identificação de Aves (IRIS Bird ID).
Recupera execuções da Etapa 6 reutilizando os recortes salvos em 'recortes_aves/'
ou registros já gravados, popula o banco local e central, gera o relatório CSV
e atualiza o status do projeto.
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
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import cv2
from PIL import Image
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn, TimeRemainingColumn

from src.core.config import config
from src.core.project import get_project, init_central_db
from src.modules.bird_id.classifier import BirdClassifier
from src.modules.bird_id.detector import safe_imread
from src.modules.bird_id.reporter import export_bird_review_csv, render_bird_summary_table

console = Console()


def recover_bird_project(project_name: str = "2026-10-21_21-55_BirdDetect"):
    console.print(f"[bold cyan]Iniciando recuperação de identificações para o projeto: {project_name}[/bold cyan]")
    
    # 1. Garante esquema central atualizado
    init_central_db(force=True)
    
    proj = get_project(project_name)
    if not proj:
        console.print(f"[bold red]Projeto '{project_name}' não encontrado![/bold red]")
        return False

    # Verifica se os registros já estão gravados no banco do projeto
    existing_records = proj.list_bird_identifications()
    if existing_records:
        console.print(f"[bold green]OK: Encontradas {len(existing_records)} identificações já gravadas no banco de dados.[/bold green]")
        records_to_save = existing_records
    else:
        crops_dir = proj.project_dir / "recortes_aves"
        if not crops_dir.exists():
            console.print(f"[bold red]Diretório de recortes '{crops_dir}' não encontrado![/bold red]")
            return False

        items = proj.get_items()
        if not items:
            console.print("[yellow]Nenhum arquivo encontrado no projeto.[/yellow]")
            return False

        console.print(f"Total de itens no projeto: [bold]{len(items)}[/bold]")
        console.print(f"Buscando recortes em: [dim]{crops_dir}[/dim]")

        # Inicializa classificador BioCLIP
        console.print("[dim]Carregando modelo BioCLIP e catálogo taxonômico...[/dim]")
        classifier = BirdClassifier()

        module_cfg = config.get("modules.bird_id", {})
        min_species_conf = float(module_cfg.get("min_species_confidence", 0.75))

        records_to_save = []
        
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
            task = progress.add_task("[cyan]Classificando recortes...", total=len(items))

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
                        preds = classifier.classify_crop(crop_pil, top_k=3, use_tta=True)
                        top1 = preds[0]
                        conf = top1["confidence"]
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
                                "recovered": True
                            }
                        }

                        # Persiste dual-write (local + central)
                        try:
                            proj.add_bird_identification(rec)
                        except Exception as e:
                            console.print(f"[yellow]Aviso ao persistir registro: {e}[/yellow]")

                        records_to_save.append(rec)

                progress.advance(task)

        console.print(f"[bold green]OK: Total de identificações gravadas no banco:[/bold green] {len(records_to_save)}")

    # 3. Exportar relatório CSV
    csv_path = proj.project_dir / "relatorio_aves.csv"
    try:
        export_bird_review_csv(records_to_save, csv_path)
        console.print(f"[bold green]OK: Relatório CSV gerado com sucesso em:[/bold green] {csv_path}")
    except Exception as e:
        console.print(f"[yellow]Aviso ao exportar CSV: {e}[/yellow]")

    # 4. Renderizar resumo visual no terminal
    try:
        render_bird_summary_table(records_to_save, console)
    except Exception as e:
        console.print(f"[yellow]Aviso ao renderizar tabela: {e}[/yellow]")

    # 5. Atualizar estágio do projeto
    proj.current_stage_id = "bird_id"
    proj.save_metadata()
    console.print("[bold green]OK: Projeto atualizado com status da Etapa 6 (bird_id) concluída com sucesso![/bold green]")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Recuperador de Identificações de Aves")
    parser.add_argument("--project", default="2026-10-21_21-55_BirdDetect", help="Nome do projeto")
    args = parser.parse_args()

    recover_bird_project(args.project)
