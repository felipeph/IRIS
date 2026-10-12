"""CLI direta para empilhamento lunar avulso com PlanetarySystemStacker."""
import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from src.core.config import config
from src.modules.astro_stack.runner import AstroStackRunner

console = Console()


def run_cli():
    parser = argparse.ArgumentParser(
        prog="iris-astro stack",
        description="Empilhamento Lunar Autônomo via PlanetarySystemStacker (PSS).",
    )
    parser.add_argument("input_dir", type=Path, help="Pasta contendo as fotos/RAWs da Lua")
    parser.add_argument("--output-dir", type=Path, default=None, help="Pasta de destino para os stacks TIFF")
    parser.add_argument("--percents", type=str, default="10,25,50", help="Percentuais de frames por AP (ex: 10,25,50)")
    parser.add_argument("--crop-size", type=int, default=None, help="Tamanho do recorte centrado (auto por padrão)")
    parser.add_argument("--margin", type=int, default=128, help="Margem além do diâmetro lunar em pixels")
    parser.add_argument("--align-box-width", type=int, default=64, help="Largura da caixa de alinhamento")
    parser.add_argument("--stab-mode", type=str, default="Surface", choices=["Surface", "Planet"])

    args = parser.parse_args(sys.argv[2:] if len(sys.argv) > 1 and sys.argv[1] == "stack" else sys.argv[1:])

    input_dir = args.input_dir.resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        console.print(f"[red]Erro: Diretório não encontrado: {input_dir}[/red]")
        sys.exit(1)

    dest_root = Path(config.get("general.destination_root", "C:/IRIS"))
    output_dir = args.output_dir.resolve() if args.output_dir else dest_root / "8_Astro_Stack" / "Manual" / input_dir.name
    output_dir.mkdir(parents=True, exist_ok=True)

    keep_percents = [int(p.strip()) for p in args.percents.split(",") if p.strip()]

    console.print(Panel(
        f"[bold cyan]🌕 IRIS ASTRO - EMPILHAMENTO LUNAR (PSS)[/bold cyan]\n"
        f"[dim]Origem:[/dim] {input_dir}\n"
        f"[dim]Destino:[/dim] {output_dir}\n"
        f"[dim]Percentuais:[/dim] {keep_percents}%",
        expand=False,
        border_style="cyan"
    ))

    runner = AstroStackRunner()
    if not runner.is_available():
        console.print("[red]Erro: Ambiente virtual do astro não encontrado.[/red]")
        sys.exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Executando PSS...", total=100)

        def cb(msg, _):
            progress.update(task, description=f"[cyan]{msg}[/cyan]")

        report = runner.run_session(
            input_dir=input_dir,
            output_dir=output_dir,
            keep_percents=keep_percents,
            crop_size=args.crop_size,
            margin=args.margin,
            align_box_width=args.align_box_width,
            stab_mode=args.stab_mode,
            progress_callback=cb,
        )
        progress.update(task, completed=100, description="[green]Concluído![/green]")

    table = Table(title=f"Resultados do Empilhamento: {input_dir.name}")
    table.add_column("Keep %", style="cyan")
    table.add_column("Arquivo TIFF Gerado (16-bit)", style="green")

    for kp_val, out_p in report.get("output_tiff_paths", {}).items():
        table.add_row(f"{kp_val}%", Path(out_p).name)

    console.print(table)
    console.print(f"\n[dim]Diretório final: {output_dir}[/dim]\n")


if __name__ == "__main__":
    run_cli()
