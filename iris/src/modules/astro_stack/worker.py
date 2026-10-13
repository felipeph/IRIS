"""Worker executado dentro do ambiente Python dedicado do astro para preparar, empilhar e finalizar sessões."""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

from concurrent.futures import ProcessPoolExecutor, as_completed

import cv2
import numpy as np
import tifffile

# Adiciona diretório do módulo ao sys.path para importar preprocessor e namer
MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from preprocessor import (
    read_mono,
    moon_bounds,
    centred_crop,
    calculate_sequence_gain,
    process_and_save_frame,
    process_single_frame,
    scale_single_frame,
)
from namer import build_stack_filename, build_preview_filename, build_report_filename



def parse_args():
    parser = argparse.ArgumentParser(description="Worker de empilhamento lunar PSS do IRIS.")
    parser.add_argument("--input-dir", type=Path, required=True, help="Diretório contendo os RAWs/fotos da sessão")
    parser.add_argument("--output-dir", type=Path, required=True, help="Diretório de destino (8_Astro_Stack/...)")
    parser.add_argument("--keep-percents", type=str, default="10,25,50", help="Lista de percentuais (ex: 10,25,50)")
    parser.add_argument("--crop-size", type=int, default=None, help="Tamanho do recorte quadrado (auto por padrão)")
    parser.add_argument("--margin", type=int, default=128, help="Margem total além do diâmetro lunar em pixels")
    parser.add_argument("--align-box-width", "--align_box_width", type=int, default=64, help="Largura da caixa dos pontos de alinhamento")
    parser.add_argument("--align-search-width", "--align_search_width", type=int, default=20, help="Largura de busca dos pontos de alinhamento")
    parser.add_argument("--stab-mode", type=str, default="Surface", choices=["Surface", "Planet"], help="Modo de estabilização")
    parser.add_argument("--vendor-dir", type=Path, default=None, help="Caminho para vendor/PlanetarySystemStacker")
    parser.add_argument("--workers", type=int, default=None, help="Número de workers paralelos para decodificação (auto)")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout do processo PSS em segundos")
    return parser.parse_args()


def main():
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    keep_percents = [int(p.strip()) for p in args.keep_percents.split(",") if p.strip()]
    if not keep_percents:
        keep_percents = [100]

    # Resolve caminhos do vendor e de run_pss.py
    vendor_dir = args.vendor_dir
    if not vendor_dir or not vendor_dir.exists():
        # Procura relativo ao projeto
        candidates = [
            MODULE_DIR.parents[2] / "vendor" / "PlanetarySystemStacker",
            Path("C:/code/IRIS/iris/vendor/PlanetarySystemStacker"),
            Path("C:/code/FOTOGRAFIA/pipp-core-test/pss"),
        ]
        for c in candidates:
            if (c / "run_pss.py").exists() or (c / "planetary_system_stacker").exists():
                vendor_dir = c
                break

    if not vendor_dir or not vendor_dir.exists():
        print(f"ERRO: vendor do PlanetarySystemStacker não encontrado.", file=sys.stderr)
        sys.exit(1)

    run_pss_script = vendor_dir / "run_pss.py"
    if not run_pss_script.exists():
        # Tenta procurar na raiz do vendor
        if (vendor_dir / "planetary_system_stacker").exists():
            run_pss_script = vendor_dir / "run_pss.py"

    if not run_pss_script.exists():
        print(f"ERRO: run_pss.py não encontrado em {vendor_dir}", file=sys.stderr)
        sys.exit(1)

    # Coleta arquivos de imagem
    extensions = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raw", ".tif", ".tiff", ".png", ".bmp", ".jpg", ".jpeg"}
    files = sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in extensions and not p.name.startswith("."))

    if len(files) < 2:
        print(f"ERRO: Mínimo de 2 imagens necessário para empilhamento. Encontradas: {len(files)}", file=sys.stderr)
        sys.exit(2)

    start_time = time.monotonic()
    run_id = f"run_{time.strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    prepared_dir = run_dir / "frames"
    prepared_dir.mkdir(parents=True, exist_ok=True)

    max_workers = args.workers if args.workers is not None and args.workers > 0 else min(os.cpu_count() or 4, 4)
    print(f"STATUS: Início da sessão. Encontrados {len(files)} arquivos. Workers paralelos: {max_workers}", flush=True)

    # 1. Determinação da geometria (crop_size) e ganho linear comum antecipado
    sample_peaks = []
    if args.crop_size is not None and args.crop_size > 0:
        crop_size = args.crop_size
        print(f"STATUS: Dimensão de corte pré-definida via argumento: {crop_size}x{crop_size}", flush=True)
        sample_count = min(5, len(files))
        sample_indices = np.linspace(0, len(files) - 1, sample_count, dtype=int).tolist()
        for s_idx in sample_indices:
            sf = files[s_idx]
            try:
                s_img = read_mono(sf, fast_demosaic=True)
                sample_peaks.append(float(np.max(s_img)))
            except Exception:
                pass
    else:
        # Amostragem representativa rápida de até 10 frames distribuídos
        sample_count = min(10, len(files))
        sample_indices = np.linspace(0, len(files) - 1, sample_count, dtype=int).tolist()
        sample_bounds = []
        for s_idx in sample_indices:
            sf = files[s_idx]
            try:
                s_img = read_mono(sf, fast_demosaic=True)
                s_b = moon_bounds(s_img)
                sample_bounds.append(s_b)
                sample_peaks.append(float(np.max(s_img)))
            except Exception as e:
                print(f"AVISO: Falha ao detectar disco na amostra {sf.name}: {e}", file=sys.stderr)

        if not sample_bounds:
            raise ValueError("Não foi possível detectar a Lua nos frames de amostragem da sessão.")

        max_dim = max(max(b[2:]) for b in sample_bounds)
        crop_size = int(math.ceil((max_dim + args.margin) / 16.0) * 16)
        if crop_size <= 0:
            raise ValueError(f"Dimensão de corte calculada inválida: {crop_size}")

    # Ganho linear compartilhado calculado na mesma amostragem representativa
    max_sample_peak = max(sample_peaks) if sample_peaks else 0.0
    gain = calculate_sequence_gain(max_sample_peak)

    print(f"PROGRESS_JSON:{json.dumps({'phase': 'geometry', 'crop_size': crop_size, 'gain': gain, 'progress_pct': 5.0, 'msg': f'Dimensões: {crop_size}x{crop_size} | Ganho linear: {gain:.3f}x'})}", flush=True)
    print(f"STATUS: Dimensão calculada: {crop_size}x{crop_size} (Margem: {args.margin}px). Ganho linear compartilhado: {gain:.4f}", flush=True)

    # 2. Leitura, recorte centrado, aplicação de ganho e gravação direta em single-pass
    metadata = [None] * len(files)
    t_start_decode = time.monotonic()
    completed_decode = 0
    valid_count = 0
    skipped_count = 0

    executor = ProcessPoolExecutor(max_workers=max_workers)
    try:
        futures = {
            executor.submit(
                process_and_save_frame,
                f,
                crop_size,
                gain,
                prepared_dir / f"frame_{idx:04d}.tiff",
                True,
            ): (idx, f)
            for idx, f in enumerate(files)
        }

        for fut in as_completed(futures):
            idx, f = futures[fut]
            res = fut.result()
            metadata[idx] = res
            completed_decode += 1

            if res.get("success"):
                valid_count += 1
            else:
                skipped_count += 1

            pct = 5.0 + ((completed_decode / len(files)) * 40.0)
            now = time.monotonic()
            fps = completed_decode / max(0.001, now - t_start_decode)
            rem_s = (len(files) - completed_decode) / max(0.1, fps)

            msg = f"Lendo e preparando {valid_count}/{len(files)} ({fps:.1f} fps)"
            if skipped_count > 0:
                msg += f" [Descartados: {skipped_count}]"

            print(
                f"PROGRESS_JSON:{json.dumps({'phase': 'decode', 'current': completed_decode, 'valid': valid_count, 'skipped': skipped_count, 'total': len(files), 'fps': round(fps, 2), 'rem_seconds': round(rem_s, 1), 'item': f.name, 'crop_size': crop_size, 'gain': gain, 'progress_pct': pct, 'msg': msg})}",
                flush=True,
            )
            if completed_decode % 10 == 0 or completed_decode == len(files):
                print(
                    f"PROGRESS: Lendo e preparando {f.name} ({valid_count}/{completed_decode}) [{fps:.1f} fps]",
                    flush=True,
                )
    except Exception as exc:
        executor.shutdown(wait=False, cancel_futures=True)
        raise exc
    finally:
        executor.shutdown(wait=False)

    if valid_count < 2:
        print(f"ERRO: Menos de 2 imagens válidas após descarte de borda. Válidas: {valid_count}, Descartadas: {skipped_count}", file=sys.stderr)
        sys.exit(2)

    if skipped_count > 0:
        print(f"STATUS: Preparação concluída: {valid_count} frames válidos prontos para PSS ({skipped_count} fotos na borda descartadas).", flush=True)



    # Extrai metadados de câmera/data do primeiro arquivo
    first_file = files[0].stem
    parts = first_file.split("_")
    date_str = parts[0] if len(parts) > 0 and len(parts[0]) == 10 else time.strftime("%Y-%m-%d")
    time_str = parts[1].replace("-", ":") if len(parts) > 1 and len(parts[1]) >= 5 else time.strftime("%H:%M:%S")
    camera_model = "Astro"
    for p in parts:
        if any(c in p.lower() for c in ("canon", "sony", "nikon", "sx60", "sx50", "powershot")):
            camera_model = p
            break

    output_tiff_paths = {}
    best_stack_final = None

    # 4. Execução do PSS para cada percentual configurado
    for kp_idx, kp in enumerate(keep_percents):
        base_pct = 45.0 + (kp_idx / len(keep_percents) * 50.0)
        print(f"PROGRESS_JSON:{json.dumps({'phase': 'pss', 'kp': kp, 'kp_index': kp_idx + 1, 'total_kps': len(keep_percents), 'crop_size': crop_size, 'gain': gain, 'progress_pct': base_pct, 'msg': f'Empilhando PSS (keep={kp}%) [{kp_idx + 1}/{len(keep_percents)}]'})}", flush=True)
        print(f"STATUS: Executando alinhamento e empilhamento PSS (keep_percent={kp}%)...", flush=True)
        cmd = [
            sys.executable, "-u", str(run_pss_script), str(prepared_dir),
            "--out_format", "tiff",
            "--debayering", "Grayscale",
            "--stab_mode", args.stab_mode,
            "--stack_percent", str(kp),
            "--noise", "3",
            "--align_box_width", str(args.align_box_width),
            "--align_search_width", str(args.align_search_width),
            "--stab_sw", "80",
            "--rf_percent", "30",
            "--buffering_level", "2",
            "--protocol",
            "--protocol_detail", "2"
        ]

        env = dict(os.environ, PYTHONUNBUFFERED="1", MPLBACKEND="Agg")
        log_path = run_dir / f"pss_{kp}p.log"
        with log_path.open("w", encoding="utf-8") as log_file:
            res = subprocess.run(
                cmd,
                cwd=str(run_pss_script.parent),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                timeout=args.timeout,
            )

        stacked_raw_path = run_dir / "frames_pss.tiff"
        if res.returncode != 0 or not stacked_raw_path.exists():
            err_msg = f"PSS falhou para {kp}% (código {res.returncode}). Consulte {log_path}"
            print(f"ERRO: {err_msg}", file=sys.stderr)
            raise RuntimeError(err_msg)

        # Leitura do TIFF intermediário (LZW decodificado via OpenCV)
        stacked = cv2.imread(str(stacked_raw_path), cv2.IMREAD_UNCHANGED)
        if stacked is None or stacked.ndim != 2 or stacked.dtype != np.uint16:
            raise RuntimeError(f"TIFF inválido gerado pelo PSS: {stacked_raw_path}")

        # Recorte centrado final e validação de centralização
        final_mono = centred_crop(stacked, crop_size)
        x_m, y_m, w_m, h_m = moon_bounds(final_mono)
        centre_err = [
            x_m + (w_m - 1) / 2.0 - (crop_size - 1) / 2.0,
            y_m + (h_m - 1) / 2.0 - (crop_size - 1) / 2.0,
        ]

        # Nome oficial definitivo
        time_clean = time_str.replace(":", "-")
        out_filename = build_stack_filename(date_str, time_clean, camera_model, kp)
        final_tiff_path = output_dir / out_filename

        tifffile.imwrite(
            final_tiff_path,
            final_mono,
            photometric="minisblack",
            description=f"IRIS PSS lunar stack; keep={kp}%; mono uint16; centred",
        )
        output_tiff_paths[str(kp)] = str(final_tiff_path)
        kp_done_pct = 45.0 + ((kp_idx + 1) / len(keep_percents) * 50.0)
        print(f"PROGRESS_JSON:{json.dumps({'phase': 'kp_done', 'kp': kp, 'filename': final_tiff_path.name, 'crop_size': crop_size, 'gain': gain, 'progress_pct': kp_done_pct, 'completed_stacks': output_tiff_paths, 'msg': f'Stack {kp}% gerado com sucesso'})}", flush=True)
        print(f"SUCCESS: Stack {kp}% gerado: {final_tiff_path.name} (Erro centro: {centre_err})", flush=True)

        if best_stack_final is None or kp == keep_percents[0]:
            best_stack_final = final_mono

        # Remove o arquivo temporário do PSS para próxima iteração
        try:
            stacked_raw_path.unlink()
        except Exception:
            pass

    # 5. Geração de Prévia PNG (8-bit esticada por percentil 99.9 para visualização clara)
    time_clean = time_str.replace(":", "-")
    preview_name = build_preview_filename(date_str, time_clean, camera_model)
    preview_path = output_dir / preview_name
    print(f"PROGRESS_JSON:{json.dumps({'phase': 'preview', 'crop_size': crop_size, 'gain': gain, 'progress_pct': 96.0, 'completed_stacks': output_tiff_paths, 'msg': 'Gerando prévia PNG esticada'})}", flush=True)
    if best_stack_final is not None:
        p_peak = float(np.percentile(best_stack_final, 99.9))
        preview_img = np.uint8(np.clip(best_stack_final.astype(np.float32) * (255.0 / max(1.0, p_peak)), 0, 255))
        cv2.imwrite(str(preview_path), preview_img)

    # 6. Gravação de relatório JSON de metadados
    elapsed = time.monotonic() - start_time
    report_data = {
        "session_dir": str(input_dir),
        "output_dir": str(output_dir),
        "date": date_str,
        "time": time_str,
        "camera_model": camera_model,
        "raw_count": len(files),
        "keep_percents": keep_percents,
        "crop_size": crop_size,
        "shared_gain": gain,
        "output_tiff_paths": output_tiff_paths,
        "preview_path": str(preview_path),
        "elapsed_seconds": round(elapsed, 2),
        "run_id": run_id,
        "status": "success",
    }
    report_name = build_report_filename(date_str, time_clean, camera_model)
    report_path = output_dir / report_name
    report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Limpeza dos frames transitórios para economizar espaço
    try:
        shutil.rmtree(prepared_dir)
    except Exception:
        pass

    print(f"PROGRESS_JSON:{json.dumps({'phase': 'done', 'crop_size': crop_size, 'gain': gain, 'progress_pct': 100.0, 'completed_stacks': output_tiff_paths, 'msg': 'Sessão concluída com sucesso'})}", flush=True)
    print(f"REPORT_JSON:{json.dumps(report_data)}", flush=True)
    print(f"DONE: Sessão concluída com sucesso em {elapsed:.1f}s!", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERRO FATAL: {exc}", file=sys.stderr)
        sys.exit(1)
