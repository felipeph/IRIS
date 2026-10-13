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

MODULE_DIR = Path(__file__).resolve().parent
IRIS_DIR = MODULE_DIR.parents[2]
if str(IRIS_DIR) not in sys.path:
    sys.path.insert(0, str(IRIS_DIR))

try:
    from .postprocess import load_lunar_image, process_and_export_all_presets
    from .wavelets import LunarWaveletEngine
except (ImportError, ValueError):
    from src.modules.astro.postprocess import load_lunar_image, process_and_export_all_presets
    from src.modules.astro.wavelets import LunarWaveletEngine

# Garante suporte completo a UTF-8 no console do Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        if sys.stdin and hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console(legacy_windows=False)


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
            presets=[presets_arg],
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
            presets=[presets_arg],
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


def cmd_stack(args):
    """Executa o empilhamento lunar via PlanetarySystemStacker (PSS)."""
    from src.core.config import config
    from src.modules.astro_stack.runner import AstroStackRunner
    from src.modules.astro_stack.namer import resolve_astro_stack_dir

    show_banner()
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        console.print(f"[red]Erro: Diretório não encontrado:[/red] {input_dir}")
        sys.exit(1)

    dest_root = Path(config.get("general.destination_root", "C:/IRIS"))
    output_dir = Path(args.output_dir).resolve() if args.output_dir else resolve_astro_stack_dir(input_dir, dest_root)
    output_dir.mkdir(parents=True, exist_ok=True)

    keep_percents = [int(p.strip()) for p in args.percents.split(",") if p.strip()]

    console.print(f"\n[bold white]Origem (Fotos/RAWs):[/bold white] [green]{input_dir}[/green]")
    console.print(f"[bold white]Destino (Stacks 16-bit):[/bold white] [cyan]{output_dir}[/cyan]")
    console.print(f"[bold white]Percentuais (Keep %):[/bold white] [magenta]{keep_percents}%[/magenta]\n")

    runner = AstroStackRunner()
    if not runner.is_available():
        console.print("[red]Erro: Ambiente virtual do astro não encontrado.[/red]")
        sys.exit(1)

    t0 = time.time()
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Executando alinhamento e empilhamento PSS...", total=100)

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
        progress.update(task, completed=100, description="[green]Empilhamento concluído![/green]")

    total_time = time.time() - t0
    console.print(f"\n[bold green][OK] Empilhamento concluído em {total_time:.2f} segundos![/bold green]\n")

    table = Table(title=f"Arquivos TIFF Gerados: {input_dir.name}")
    table.add_column("Keep %", style="cyan")
    table.add_column("Arquivo TIFF Gerado (16-bit)", style="green")

    for kp_val, out_p in report.get("output_tiff_paths", {}).items():
        table.add_row(f"{kp_val}%", Path(out_p).name)

    console.print(table)
    console.print(f"\n[dim]Diretório de saída: {output_dir}[/dim]\n")


def cmd_pipeline(args):
    """Executa o pipeline lunar completo: Empilhamento PSS -> Aprimoramento Wavelets."""
    from src.core.config import config
    from src.modules.astro_stack.runner import AstroStackRunner
    from src.modules.astro_stack.namer import resolve_astro_stack_dir
    from src.modules.astro_sharpen.namer import resolve_astro_sharpen_dir

    show_banner()
    input_dir = Path(args.input_dir).resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        console.print(f"[red]Erro: Diretório não encontrado:[/red] {input_dir}")
        sys.exit(1)

    dest_root = Path(config.get("general.destination_root", "C:/IRIS"))
    stack_dir = Path(args.output_stack_dir).resolve() if args.output_stack_dir else resolve_astro_stack_dir(input_dir, dest_root)
    stack_dir.mkdir(parents=True, exist_ok=True)
    sharpen_dir = Path(args.output_sharpen_dir).resolve() if args.output_sharpen_dir else resolve_astro_sharpen_dir(stack_dir, dest_root)
    sharpen_dir.mkdir(parents=True, exist_ok=True)

    keep_percents = [int(p.strip()) for p in args.percents.split(",") if p.strip()]

    console.print(Panel(
        f"[bold cyan]🌕 PIPELINE LUNAR COMPLETO (PSS -> WAVELETS)[/bold cyan]\n"
        f"[dim]Origem:[/dim] {input_dir}\n"
        f"[dim]Destino Stacks:[/dim] {stack_dir}\n"
        f"[dim]Destino Finais:[/dim] {sharpen_dir}\n"
        f"[dim]Presets:[/dim] {args.preset}",
        expand=False,
        border_style="cyan"
    ))

    # Etapa 1: Stacking
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
        task = progress.add_task("[cyan]Etapa 1/2: Empilhando frames com PSS...", total=100)
        report = runner.run_session(
            input_dir=input_dir,
            output_dir=stack_dir,
            keep_percents=keep_percents,
            progress_callback=lambda msg, _: progress.update(task, description=f"[cyan]{msg}[/cyan]"),
        )
        progress.update(task, completed=100, description="[green]Stacking concluído![/green]")

    # Etapa 2: Sharpening
    console.print("\n[bold cyan]Etapa 2/2: Aplicando Wavelets e CLAHE nos Stacks...[/bold cyan]")
    all_sharpen_results = {}
    for kp_val, out_p in report.get("output_tiff_paths", {}).items():
        stack_p = Path(out_p)
        res = process_and_export_all_presets(
            input_path=stack_p,
            output_dir=sharpen_dir,
            presets=[args.preset],
            enable_clahe=not args.no_clahe,
            use_limb_guard=not args.no_limb_guard,
        )
        all_sharpen_results[f"Stack {kp_val}%"] = res

    console.print(f"\n[bold green][OK] Pipeline completo finalizado com sucesso![/bold green]\n")
    console.print(f"[dim]Stacks 16-bit: {stack_dir}[/dim]")
    console.print(f"[dim]Imagens Finais: {sharpen_dir}[/dim]\n")


def main():
    parser = argparse.ArgumentParser(
        prog="iris-astro",
        description="Módulo de Astrofotografia Lunar e Wavelets Autônomos do IRIS.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Comandos disponíveis")

    presets_choices = ["all", "craters", "classic", "registax"] + list(LunarWaveletEngine.PRESETS.keys())

    # Comando: stack
    parser_stack = subparsers.add_parser("stack", help="Empilha fotos/RAWs lunares com o PlanetarySystemStacker (PSS)")
    parser_stack.add_argument("input_dir", type=Path, help="Pasta contendo as fotos/RAWs da Lua")
    parser_stack.add_argument("--output-dir", type=Path, default=None, help="Pasta de destino para os stacks TIFF")
    parser_stack.add_argument("--percents", type=str, default="10,25,50", help="Percentuais de frames por AP (ex: 10,25,50)")
    parser_stack.add_argument("--crop-size", type=int, default=None, help="Tamanho do recorte centrado (auto por padrão)")
    parser_stack.add_argument("--margin", type=int, default=128, help="Margem além do diâmetro lunar em pixels")
    parser_stack.add_argument("--align-box-width", type=int, default=64, help="Largura da caixa de alinhamento")
    parser_stack.add_argument("--stab-mode", type=str, default="Surface", choices=["Surface", "Planet"])
    parser_stack.set_defaults(func=cmd_stack)

    # Comando: pipeline
    parser_pipe = subparsers.add_parser("pipeline", help="Executa o fluxo completo: Stacking PSS -> Aprimoramento Wavelets")
    parser_pipe.add_argument("input_dir", type=Path, help="Pasta contendo as fotos/RAWs da Lua")
    parser_pipe.add_argument("--output-stack-dir", type=Path, default=None, help="Pasta de destino dos stacks (8_Astro_Stack)")
    parser_pipe.add_argument("--output-sharpen-dir", type=Path, default=None, help="Pasta de destino dos finais (9_Astro_Sharpening)")
    parser_pipe.add_argument("--percents", type=str, default="10,25,50", help="Percentuais de frames (ex: 10,25,50)")
    parser_pipe.add_argument("--preset", choices=presets_choices, default="registax", help="Preset ou grupo de wavelets")
    parser_pipe.add_argument("--no-clahe", action="store_true", help="Desativa o CLAHE")
    parser_pipe.add_argument("--no-limb-guard", action="store_true", help="Desativa o Limb Guard")
    parser_pipe.set_defaults(func=cmd_pipeline)

    # Comando: sharpen
    parser_sharpen = subparsers.add_parser("sharpen", help="Processa e aprimora um arquivo TIFF empilhado")
    parser_sharpen.add_argument("file", help="Caminho do arquivo de imagem (TIFF/PNG)")
    parser_sharpen.add_argument(
        "--preset",
        choices=presets_choices,
        default="all",
        help="Preset ou grupo de wavelets a aplicar (default: all, opções: all, craters, classic, registax ou preset específico)",
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
        help="Preset ou grupo de wavelets a aplicar (default: all, opções: all, craters, classic, registax ou preset específico)",
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

