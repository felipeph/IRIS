"""
Gerador de Relatórios e Tabela de Revisão Taxonômica de Aves (IRIS Bird ID).
"""

import csv
from pathlib import Path
from typing import List, Dict, Any

from rich.console import Console
from rich.table import Table


def export_bird_review_csv(records: List[Dict[str, Any]], output_csv_path: Path):
    """Exporta as identificações de aves para um arquivo CSV para conferência e revisão."""
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "item_path",
        "is_video",
        "species_common",
        "species_common_en",
        "species_scientific",
        "confidence",
        "needs_review",
        "top2_common",
        "top2_scientific",
        "top2_confidence",
        "top3_common",
        "top3_scientific",
        "top3_confidence",
        "crop_saved_path",
    ]

    with open(output_csv_path, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)


def render_bird_summary_table(records: List[Dict[str, Any]], console: Console):
    """Exibe tabela formatada com Rich no console."""
    if not records:
        return

    table = Table(title="[bold green]IRIS Bird ID - Resumo de Aves Identificadas[/bold green]", show_header=True, header_style="bold cyan")
    table.add_column("Tipo", style="dim", width=6)
    table.add_column("Arquivo / Clipe", style="white", min_width=25)
    table.add_column("Espécie Identificada (PT / EN)", style="bold green", min_width=24)
    table.add_column("Nome Científico", style="italic", min_width=20)
    table.add_column("Confiança", justify="right", width=10)
    table.add_column("Revisão?", justify="center", width=9)

    for r in records:
        tipo = "Vídeo" if r.get("is_video") else "Foto"
        fname = Path(r.get("item_path", "")).name
        comm = r.get("species_common", "Desconhecido")
        comm_en = r.get("species_common_en", "")
        display_comm = f"{comm} ({comm_en})" if comm_en else comm
        sci = r.get("species_scientific", "")
        conf = float(r.get("confidence", 0.0)) * 100
        needs_rev = r.get("needs_review", False)

        rev_badge = "[bold red]SIM[/bold red]" if needs_rev else "[green]Não[/green]"
        conf_str = f"{conf:.1f}%"
        if conf < 75.0:
            conf_str = f"[yellow]{conf_str}[/yellow]"

        table.add_row(tipo, fname, display_comm, sci, conf_str, rev_badge)

    console.print(table)
