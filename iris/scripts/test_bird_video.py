#!/usr/bin/env python3
"""
Teste de Detecção e Classificação de Espécie em Vídeo (IRIS Bird ID)
1. Amostra frames uniformemente ao longo do vídeo.
2. Detecta aves com YOLOv8 e extrai recortes de alta resolução.
3. Avalia nitidez (Laplaciano) e tamanho para descartar frames borrados.
4. Classifica os melhores recortes com BioCLIP (Zero-Shot com prior taxonômico de MG).
5. Realiza a votação da espécie predominante no clipe.

Uso:
    python test_bird_video.py --video "caminho_do_video.mp4"
"""

import argparse
import os
import sys
import time
from pathlib import Path
from collections import Counter, defaultdict

# Suporte a UTF-8 no Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cv2
import numpy as np
import torch
from PIL import Image

# Importa pipeline do benchmark existente
sys.path.append(str(Path(__file__).resolve().parent))
from benchmark_bird_species import BirdBenchmarkPipeline

def calculate_sharpness(img_gray):
    """Calcula a nitidez através da variância do Laplaciano."""
    return cv2.Laplacian(img_gray, cv2.CV_64F).var()

def process_video(
    video_path: str,
    sample_interval_sec: float = 2.0,
    max_crops_to_classify: int = 15,
    out_debug_dir: str = "scratch/bird_video_crops"
):
    video_path = Path(video_path)
    if not video_path.exists():
        print(f"[-] Vídeo não encontrado: {video_path}")
        return

    os.makedirs(out_debug_dir, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"[-] Erro ao abrir vídeo com OpenCV: {video_path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_sec = total_frames / fps
    frame_step = max(1, int(fps * sample_interval_sec))

    print("\n" + "=" * 70)
    print("           IRIS BIRD ID - AVALIAÇÃO DE VÍDEO")
    print("=" * 70)
    print(f" Arquivo         : {video_path.name}")
    print(f" Duração         : {duration_sec:.1f}s ({total_frames} frames @ {fps:.1f} fps)")
    print(f" Amostragem      : 1 frame a cada {sample_interval_sec}s (passo de {frame_step} frames)")
    print("=" * 70)

    pipeline = BirdBenchmarkPipeline()
    candidates = []

    print("\n[*] Fase 1: Amostrando frames e detectando aves com YOLO...")
    frame_idx = 0
    sampled_count = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            sampled_count += 1
            h, w = frame.shape[:2]
            # Inferência YOLO
            results = pipeline.yolo.predict(frame, classes=[14], conf=0.30, verbose=False)
            
            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    bw = x2 - x1
                    bh = y2 - y1

                    # Filtra caixas muito minúsculas (< 40x40 px)
                    if bw < 40 or bh < 40:
                        continue

                    # Adiciona margem de 15%
                    mx = int(bw * 0.15)
                    my = int(bh * 0.15)
                    crop_x1 = max(0, x1 - mx)
                    crop_y1 = max(0, y1 - my)
                    crop_x2 = min(w, x2 + mx)
                    crop_y2 = min(h, y2 + my)

                    crop_bgr = frame[crop_y1:crop_y2, crop_x1:crop_x2]
                    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
                    sharpness = calculate_sharpness(gray)

                    # Score composto: nitidez * confiança * área
                    area = bw * bh
                    score = sharpness * conf * np.sqrt(area)

                    crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
                    pil_img = Image.fromarray(crop_rgb)

                    timestamp_s = frame_idx / fps
                    candidates.append({
                        "pil_img": pil_img,
                        "bgr_img": crop_bgr,
                        "frame_idx": frame_idx,
                        "timestamp_s": timestamp_s,
                        "yolo_conf": conf,
                        "sharpness": sharpness,
                        "score": score
                    })

        frame_idx += 1

    cap.release()
    print(f"[+] Total de frames amostrados: {sampled_count}")
    print(f"[+] Total de aves detectadas: {len(candidates)}")

    if not candidates:
        print("[-] Nenhuma ave detectada no vídeo.")
        return

    # Ordena pelos melhores scores de nitidez e confiança
    candidates.sort(key=lambda x: x["score"], reverse=True)
    selected_crops = candidates[:max_crops_to_classify]

    print(f"\n[*] Fase 2: Classificando os {len(selected_crops)} melhores recortes com BioCLIP...")
    votes = defaultdict(float)
    vote_counts = Counter()
    crop_details = []

    for i, item in enumerate(selected_crops):
        preds = pipeline.classify_crop(item["pil_img"], top_k=3)
        top1 = preds[0]

        # Salva recorte anotado na pasta debug
        t_str = f"{item['timestamp_s']:.1f}s".replace(".", "-")
        crop_fname = f"crop_{i+1:02d}_{t_str}_{top1['common_name']}.jpg"
        cv2.imwrite(os.path.join(out_debug_dir, crop_fname), item["bgr_img"])

        # Votação ponderada pela confiança do BioCLIP
        sp_key = (top1["scientific_name"], top1["common_name"])
        votes[sp_key] += top1["confidence"]
        vote_counts[sp_key] += 1

        crop_details.append({
            "time": item["timestamp_s"],
            "yolo_conf": item["yolo_conf"],
            "sharpness": item["sharpness"],
            "top1": top1,
            "top2": preds[1],
            "top3": preds[2]
        })

        print(f"  • Frame {item['frame_idx']} ({item['timestamp_s']:.1f}s) -> {top1['common_name']} ({top1['scientific_name']}) - Conf: {top1['confidence']*100:.1f}%")

    # Determina a espécie predominante
    sorted_votes = sorted(votes.items(), key=lambda x: x[1], reverse=True)
    total_vote_weight = sum(votes.values())

    print("\n" + "=" * 70)
    print("                 RESULTADO DA VOTAÇÃO")
    print("=" * 70)
    print(f"{'ESPÉCIE PREDOMINANTE':<28} | {'VOTOS':<8} | {'PESO RELATIVO':<14}")
    print("-" * 70)
    for (sci, comm), weight in sorted_votes:
        count = vote_counts[(sci, comm)]
        rel_weight = (weight / total_vote_weight) * 100 if total_vote_weight > 0 else 0
        print(f"{comm:<28} | {count:<8} | {rel_weight:.1f}% ({sci})")

    predominant_sci, predominant_comm = sorted_votes[0][0]
    predominant_pct = (sorted_votes[0][1] / total_vote_weight) * 100

    print("=" * 70)
    print(f" ⭐ ESPÉCIE DETECTADA NO VÍDEO: {predominant_comm} ({predominant_sci})")
    print(f" ⭐ NÍVEL DE CERTEZA DO CLIPE : {predominant_pct:.1f}%")
    print(f" ⭐ RECORTES SALVOS EM        : {os.path.abspath(out_debug_dir)}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Teste de Detecção e Classificação de Espécie em Vídeo")
    parser.add_argument("--video", required=True, help="Caminho do vídeo (.mp4, .mov, etc.)")
    parser.add_argument("--sample-interval", type=float, default=2.0, help="Intervalo de amostragem em segundos (padrão: 2.0s)")
    parser.add_argument("--max-crops", type=int, default=15, help="Quantidade máxima de recortes a classificar (padrão: 15)")
    args = parser.parse_args()

    process_video(args.video, sample_interval_sec=args.sample_interval, max_crops_to_classify=args.max_crops)
