"""Interface CLI Autônoma para Astrofotografia Lunar do IRIS.

Permite processamento imediato de stacks TIFF do AutoStakkert! via linha de comando,
substituindo o fluxo manual no RegiStax com geração automática de múltiplos presets
(suave, equilibrado, enfático e mineral), realce 16-bit e proteção de limbo.
"""

import sys
import argparse
import time
from pathlib import Path
from typing import List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

from .postprocess import load_lunar_image, process_and_export_all_presets
from .wavelets import LunarWaveletEngine

console = Console()


def show_banner():
    banner = (
        "[bold cyan][LUA] IRIS ASTRO - MOTOR LUNAR AUTÔNOMO[/bold cyan]\n"
        "[dim]Wavelets À Trous B3-Spline • Limb Guard Anti-Halo • CLAHE 16-bit[/dim]"
    )
    console.print(Panel(banner, expand=False, border_style="cyan"))


def cmd_info(args):
    """Exibe informações técnicas e alcance dinâmico de um stack lunar."""
    show_banner()
    file_path = Path(args.file)
    if not file_path.exists():
        console.print(f"[red]Erro: Arquivo não encontrado:[/red] {file_path}")
        sys.exit(1)

    with console.status(f"[cyan]Analisando {file_path.name}...[/cyan]"):
        img_float, bit_depth = load_lunar_image(file_path)
        h, w = img_float.shape[:2]
        channels = 1 if img_float.ndim == 2 else img_float.shape[2]
        min_v = float(img_float.min())
        max_v = float(img_float.max())
        mean_v = float(img_float.mean())

    table = Table(title=f"Metadados Técnicos: {file_path.name}")
    table.add_column("Propriedade", style="cyan")
    table.add_column("Valor", style="green")

    table.add_row("Resolução", f"{w} x {h} ({w * h / 1e6:.1f} MP)")
    table.add_row("Canais de Cor", f"{channels} ({'Monocromático' if channels == 1 else 'RGB Colorido'})")
    table.add_row("Profundidade de Bits", f"{bit_depth}-bit")
    table.add_row("Tamanho do Arquivo", f"{file_path.stat().st_size / (1024 * 1024):.2f} MB")
    table.add_row("Brilho Mínimo / Máximo", f"{min_v:.4f} / {max_v:.4f}")
    table.add_row("Brilho Médio", f"{mean_v:.4f}")

    console.print(table)


def cmd_sharpen(args):
    """Executa o aprimoramento de wavelets e contraste sobre um stack TIFF."""
    show_banner()
    file_path = Path(args.file)
    if not file_path.exists():
        console.print(f"[red]Erro: Arquivo não encontrado:[/red] {file_path}")
        sys.exit(1)

    presets_arg = args.preset
    output_dir = Path(args.output_dir) if args.output_dir else None

    console.print(f"\n[bold white]Arquivo de Origem:[/bold white] [green]{file_path}[/green]")
    console.print(f"[bold white]Preset / Grupo:[/bold white] [cyan]{presets_arg}[/cyan]")
    console.print(f"[bold white]Proteção de Limbo (Limb Guard):[/bold white] {'[green]Ativado[/green]' if not args.no_limb_guard else '[yellow]Desativado[/yellow]'}")
    console.print(f"[bold white]Realce de Relevo Local (CLAHE 16-bit):[/bold white] {'[green]Ativado[/green]' if not args.no_clahe else '[yellow]Desativado[/yellow]'}")
    if args.clarity is not None:
        console.print(f"[bold white]Sobrescrita Clarity (Relevo):[/bold white] [magenta]{args.clarity:.2f}[/magenta]")
    if args.deconvolve:
        console.print(f"[bold white]Deconvolução Richardson-Lucy:[/bold white] [green]Forçada ativada[/green]")
    if args.contrast is not None:
        console.print(f"[bold white]Sobrescrita Contraste Curva S:[/bold white] [magenta]{args.contrast:.2f}[/magenta]")
    console.print("")

    t0 = time.time()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Processando variações de wavelets e relevo...", total=100)

        results = process_and_export_all_presets(
            input_path=file_path,
            output_dir=output_dir,
            presets=[presets_arg] if presets_arg not in ("all", "craters", "classic") else [presets_arg],
            enable_clahe=not args.no_clahe,
            use_limb_guard=not args.no_limb_guard,
            export_png=not args.no_png,
            export_tiff=not args.no_tiff,
            custom_gamma=args.gamma,
            custom_contrast=args.contrast,
            custom_clarity=args.clarity,
            custom_deconvolve=True if args.deconvolve else None,
        )
        progress.update(task, completed=100)

    total_time = time.time() - t0
    console.print(f"\n[bold green][OK] Processamento concluído em {total_time:.2f} segundos![/bold green]\n")

    table = Table(title="Arquivos Finais Gerados")
    table.add_column("Preset", style="magenta")
    table.add_column("Descrição", style="white")
    table.add_column("Arquivo TIFF (16-bit)", style="cyan")
    table.add_column("Arquivo PNG (8-bit)", style="green")

    for p_name, paths in results.items():
        desc = LunarWaveletEngine.PRESETS.get(p_name, {}).get("description", "")
        tif_str = paths.get("tiff").name if "tiff" in paths else "-"
        png_str = paths.get("png").name if "png" in paths else "-"
        table.add_row(p_name.capitalize(), desc, tif_str, png_str)

    console.print(table)
    dest_folder = next(iter(results.values())).get("png", next(iter(results.values())).get("tiff")).parent
    console.print(f"\n[dim]Diretório de saída: {dest_folder}[/dim]")


def cmd_batch(args):
    """Processa recursivamente todos os TIFFs em um diretório de sessão lunar."""
    show_banner()
    source_dir = Path(args.dir)
    if not source_dir.exists() or not source_dir.is_dir():
        console.print(f"[red]Erro: Diretório inválido:[/red] {source_dir}")
        sys.exit(1)

    tiff_files = [
        f for f in source_dir.rglob("*")
        if f.is_file() and f.suffix.lower() in (".tif", ".tiff") and not f.name.startswith(".") and "_processado_iris" not in str(f)
    ]

    if not tiff_files:
        console.print(f"[yellow]Nenhum arquivo TIFF de stack encontrado em:[/yellow] {source_dir}")
        sys.exit(0)

    console.print(f"Encontrados [bold green]{len(tiff_files)}[/bold green] arquivos TIFF para processamento em lote.")
    presets_arg = args.preset

    for idx, tiff in enumerate(tiff_files, 1):
        console.print(f"\n[cyan][{idx}/{len(tiff_files)}][/cyan] Processando: [bold]{tiff.name}[/bold]")
        process_and_export_all_presets(
            input_path=tiff,
            output_dir=None,
            presets=[presets_arg] if presets_arg not in ("all", "craters", "classic") else [presets_arg],
            enable_clahe=not args.no_clahe,
            use_limb_guard=not args.no_limb_guard,
            export_png=not args.no_png,
            export_tiff=not args.no_tiff,
            custom_gamma=args.gamma,
            custom_contrast=args.contrast,
            custom_clarity=args.clarity,
            custom_deconvolve=True if args.deconvolve else None,
        )

    console.print(f"\n[bold green][OK] Lote concluído com sucesso![/bold green]")


def main():
    parser = argparse.ArgumentParser(
        prog="iris-astro",
        description="Módulo de Astrofotografia Lunar e Wavelets Autônomos do IRIS.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    presets_choices = ["all", "craters", "classic"] + list(LunarWaveletEngine.PRESETS.keys())

    # Comando: sharpen
    parser_sharpen = subparsers.add_parser("sharpen", help="Processa e aprimora um arquivo TIFF empilhado")
    parser_sharpen.add_argument("file", help="Caminho do arquivo de imagem (TIFF/PNG)")
    parser_sharpen.add_argument(
        "--preset",
        choices=presets_choices,
        default="all",
        help="Preset ou grupo de wavelets a aplicar (default: all, opções: all, craters, classic ou preset específico)",
    )
    parser_sharpen.add_argument("--output-dir", help="Diretório personalizado de destino")
    parser_sharpen.add_argument("--no-clahe", action="store_true", help="Desativa o realce de relevo local (CLAHE)")
    parser_sharpen.add_argument("--no-limb-guard", action="store_true", help="Desativa a proteção de borda do limbo lunar")
    parser_sharpen.add_argument("--clarity", type=float, default=None, help="Sobrescreve intensidade de relevo 3D/Clarity (ex: 0.3 a 0.8)")
    parser_sharpen.add_argument("--contrast", type=float, default=None, help="Sobrescreve contraste da curva S (ex: 1.1 a 1.4)")
    parser_sharpen.add_argument("--deconvolve", action="store_true", help="Força aplicação de Deconvolução Richardson-Lucy contra seeing")
    parser_sharpen.add_argument("--gamma", type=float, default=1.0, help="Ajuste de curva gama (default: 1.0)")
    parser_sharpen.add_argument("--no-png", action="store_true", help="Não exporta PNG de visualização")
    parser_sharpen.add_argument("--no-tiff", action="store_true", help="Não exporta TIFF 16-bit")
    parser_sharpen.set_defaults(func=cmd_sharpen)

    # Comando: batch
    parser_batch = subparsers.add_parser("batch", help="Processa em lote todos os TIFFs de uma pasta")
    parser_batch.add_argument("dir", help="Caminho do diretório contendo os TIFFs")
    parser_batch.add_argument(
        "--preset",
        choices=presets_choices,
        default="all",
        help="Preset ou grupo de wavelets a aplicar (default: all, opções: all, craters, classic ou preset específico)",
    )
    parser_batch.add_argument("--no-clahe", action="store_true", help="Desativa o CLAHE")
    parser_batch.add_argument("--no-limb-guard", action="store_true", help="Desativa o Limb Guard")
    parser_batch.add_argument("--clarity", type=float, default=None, help="Sobrescreve intensidade de relevo 3D/Clarity")
    parser_batch.add_argument("--contrast", type=float, default=None, help="Sobrescreve contraste da curva S")
    parser_batch.add_argument("--deconvolve", action="store_true", help="Força aplicação de Deconvolução Richardson-Lucy")
    parser_batch.add_argument("--gamma", type=float, default=1.0, help="Ajuste de curva gama")
    parser_batch.add_argument("--no-png", action="store_true", help="Não exporta PNG")
    parser_batch.add_argument("--no-tiff", action="store_true", help="Não exporta TIFF")
    parser_batch.set_defaults(func=cmd_batch)

    # Comando: info
    parser_info = subparsers.add_parser("info", help="Exibe metadados técnicos e estatísticas de um arquivo")
    parser_info.add_argument("file", help="Caminho do arquivo de imagem")
    parser_info.set_defaults(func=cmd_info)

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
