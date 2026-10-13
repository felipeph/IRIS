"""CLI direta para empilhamento lunar avulso com PlanetarySystemStacker."""
import argparse
import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent
IRIS_DIR = MODULE_DIR.parents[2]
if str(IRIS_DIR) not in sys.path:
    sys.path.insert(0, str(IRIS_DIR))

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

import datetime
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.live import Live

from src.core.config import config
from src.core.ui import PipelineUI
from src.modules.astro_stack.runner import AstroStackRunner

console = Console(legacy_windows=False)


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

    runner = AstroStackRunner()
    if not runner.is_available():
        console.print("[red]Erro: Ambiente virtual do astro não encontrado.[/red]")
        sys.exit(1)

    extensions = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raw", ".tif", ".tiff", ".png", ".bmp", ".jpg", ".jpeg"}
    raw_files = [p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in extensions and not p.name.startswith(".")]

    t0 = time.time()
    start_str = datetime.datetime.now().strftime("%H:%M:%S")

    current_phase_msg = "Iniciando análise dos frames..."
    current_item = ""
    progress_pct = 0.0
    crop_size = args.crop_size or 0
    shared_gain = 1.0
    completed_stacks = {}

    def make_renderable():
        now = time.time()
        elapsed = now - t0
        elapsed_str = str(datetime.timedelta(seconds=int(elapsed)))
        if progress_pct > 0:
            total_est = elapsed / (progress_pct / 100.0)
            remaining = max(0, total_est - elapsed)
            eta_str = str(datetime.timedelta(seconds=int(remaining)))
            end_dt = datetime.datetime.now() + datetime.timedelta(seconds=int(remaining))
            previsao_str = end_dt.strftime("%H:%M:%S")
        else:
            eta_str = "--:--:--"
            previsao_str = "--:--:--"

        return PipelineUI.generate_astro_stack_renderable(
            stage_title="🌕 IRIS ASTRO - EMPILHAMENTO LUNAR (PSS)",
            start_str=start_str,
            session_name=input_dir.name,
            total_photos=len(raw_files),
            keep_percents=keep_percents,
            current_phase_msg=current_phase_msg,
            current_item=current_item,
            progress_pct=progress_pct,
            crop_size=crop_size,
            shared_gain=shared_gain,
            completed_stacks=completed_stacks,
            elapsed_str=elapsed_str,
            eta_str=eta_str,
            previsao_fim_str=previsao_str,
        )

    with Live(make_renderable(), console=console, refresh_per_second=4) as live:
        def cb(event_or_msg, pct_val):
            nonlocal current_phase_msg, current_item, progress_pct, crop_size, shared_gain, completed_stacks
            if isinstance(event_or_msg, dict):
                current_phase_msg = event_or_msg.get("msg", current_phase_msg)
                current_item = event_or_msg.get("item", current_item)
                if "progress_pct" in event_or_msg:
                    progress_pct = float(event_or_msg["progress_pct"])
                if "crop_size" in event_or_msg and event_or_msg["crop_size"]:
                    crop_size = int(event_or_msg["crop_size"])
                if "gain" in event_or_msg and event_or_msg["gain"]:
                    shared_gain = float(event_or_msg["gain"])
                if "completed_stacks" in event_or_msg:
                    completed_stacks.update(event_or_msg["completed_stacks"])
                if event_or_msg.get("phase") == "kp_done" and "kp" in event_or_msg:
                    completed_stacks[str(event_or_msg["kp"])] = event_or_msg.get("filename", "")
            else:
                current_phase_msg = str(event_or_msg)
                if pct_val is not None:
                    progress_pct = float(pct_val)
            live.update(make_renderable())

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
        progress_pct = 100.0
        current_phase_msg = "[green]Empilhamento concluído com sucesso![/green]"
        live.update(make_renderable())

    table = Table(title=f"Resultados do Empilhamento: {input_dir.name}")
    table.add_column("Keep %", style="cyan")
    table.add_column("Arquivo TIFF Gerado (16-bit)", style="green")

    for kp_val, out_p in report.get("output_tiff_paths", {}).items():
        table.add_row(f"{kp_val}%", Path(out_p).name)

    console.print(table)
    console.print(f"\n[dim]Diretório final: {output_dir}[/dim]\n")


if __name__ == "__main__":
    run_cli()
