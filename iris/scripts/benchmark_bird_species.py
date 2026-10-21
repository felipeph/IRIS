#!/usr/bin/env python3
"""
Script de Benchmark e Validação de Espécies de Aves (Fase 0)
Testa o pipeline em 2 etapas:
1. Detecção e recorte inteligente (YOLOv8s/n)
2. Classificação fine-grained zero-shot (BioCLIP / OpenCLIP) com prior taxonômico de Minas Gerais / Brasil

Uso:
    python benchmark_bird_species.py --input-dir "C:/Caminho/Para/Fotos_Por_Especie"
"""

import argparse
import os
import sys
import time
from pathlib import Path
import csv

# Garante suporte a UTF-8 no Windows
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

def load_species_list(csv_path: str):
    """Carrega lista taxonômica de espécies."""
    species = []
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            species.append({
                "scientific_name": row["scientific_name"].strip(),
                "common_name": row["common_name_pt"].strip(),
                "family": row.get("family", "").strip(),
                "order": row.get("order", "").strip()
            })
    return species

class BirdBenchmarkPipeline:
    def __init__(self, yolo_model_name="yolov8s.pt", species_csv=None, device=None):
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        print(f"[*] Dispositivo de inferência: {self.device}")
        
        # 1. Carregar YOLO
        from ultralytics import YOLO
        print(f"[*] Carregando detector ({yolo_model_name})...")
        self.yolo = YOLO(yolo_model_name)
        
        # 2. Carregar Lista de Espécies
        if species_csv is None:
            species_csv = Path(__file__).resolve().parent.parent / "src" / "modules" / "bird_id" / "species_lists" / "br_mg_aves.csv"
        self.species_list = load_species_list(str(species_csv))
        print(f"[*] {len(self.species_list)} espécies carregadas na lista de referência.")

        # 3. Carregar BioCLIP / OpenCLIP
        import open_clip
        print("[*] Carregando modelo BioCLIP (hf-hub:imageomics/bioclip)...")
        # Usamos modelo padrão BioCLIP pré-treinado no TreeOfLife-10M
        try:
            self.clip_model, self.clip_preprocess_train, self.clip_preprocess = open_clip.create_model_and_transforms(
                'hf-hub:imageomics/bioclip'
            )
            self.tokenizer = open_clip.get_tokenizer('hf-hub:imageomics/bioclip')
        except Exception as e:
            print(f"[-] Aviso ao carregar BioCLIP: {e}. Usando ViT-B-32 padrão...")
            self.clip_model, _, self.clip_preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
            self.tokenizer = open_clip.get_tokenizer('ViT-B-32')

        self.clip_model = self.clip_model.to(self.device)
        self.clip_model.eval()

        # Pré-computar embeddings de texto das espécies
        print("[*] Pré-computando embeddings de texto das espécies...")
        self.species_text_prompts = [
            f"a photo of {sp['scientific_name']}, a type of bird ({sp['common_name']})"
            for sp in self.species_list
        ]
        
        text_tokens = self.tokenizer(self.species_text_prompts).to(self.device)
        with torch.no_grad():
            text_features = self.clip_model.encode_text(text_tokens)
            self.text_features = text_features / text_features.norm(dim=-1, keepdim=True)
        print("[+] Inicialização completa!")

    def detect_and_crop(self, img_bgr, margin_ratio=0.15):
        """
        Executa YOLO para classe 'bird' (14).
        Retorna o recorte PIL da ave de maior confiança/tamanho.
        Se nenhuma ave for detectada, retorna a imagem inteira com aviso.
        """
        results = self.yolo.predict(img_bgr, classes=[14], conf=0.25, verbose=False)
        best_box = None
        max_score = 0.0
        h, w = img_bgr.shape[:2]

        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                # Prioriza tamanho e confiança
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                area = (x2 - x1) * (y2 - y1)
                score = conf * (area / (w * h))
                if score > max_score or best_box is None:
                    max_score = score
                    best_box = (x1, y1, x2, y2, conf)

        if best_box is not None:
            x1, y1, x2, y2, conf = best_box
            # Adiciona margem
            bw = x2 - x1
            bh = y2 - y1
            mx = int(bw * margin_ratio)
            my = int(bh * margin_ratio)
            crop_x1 = max(0, x1 - mx)
            crop_y1 = max(0, y1 - my)
            crop_x2 = min(w, x2 + mx)
            crop_y2 = min(h, y2 + my)
            
            crop_bgr = img_bgr[crop_y1:crop_y2, crop_x1:crop_x2]
            crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
            return Image.fromarray(crop_rgb), True, conf
        else:
            # Fallback: Imagem completa (ave centralizada)
            crop_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            return Image.fromarray(crop_rgb), False, 0.0

    def classify_crop(self, pil_image, top_k=5):
        """Classifica o recorte nas espécies cadastradas."""
        image_input = self.clip_preprocess(pil_image).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            image_features = self.clip_model.encode_image(image_input)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            
            # Similaridade de cosseno escalonada
            similarity = (100.0 * image_features @ self.text_features.T).softmax(dim=-1)[0]
            
        values, indices = similarity.topk(top_k)
        
        predictions = []
        for val, idx in zip(values, indices):
            sp = self.species_list[idx.item()]
            predictions.append({
                "scientific_name": sp["scientific_name"],
                "common_name": sp["common_name"],
                "confidence": float(val.item())
            })
        return predictions

def safe_imread(path_str: str):
    """Lê imagem suportando caminhos Windows com acentuação."""
    try:
        with open(path_str, "rb") as f:
            data = np.frombuffer(f.read(), dtype=np.uint8)
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None

def extract_expected_species(folder_name: str):
    """
    Extrai nome científico e comum a partir do nome da pasta.
    Ex: '2017-12-17 Belvedere - Lavadeira-mascarada (Fluvicola nengeta) [01]'
    -> scientific: 'Fluvicola nengeta', common: 'Lavadeira-mascarada'
    """
    import re
    # Procura por parênteses contendo 2 palavras em latim (gênero e espécie)
    sci_match = re.search(r'\(([A-Z][a-z]+ [a-z]+)\)', folder_name)
    scientific = sci_match.group(1).strip() if sci_match else None
    
    # Remove prefixo de data e sufixos
    clean = re.sub(r'^\d{4}-\d{2}-\d{2}\s*', '', folder_name)
    clean = re.sub(r'\[.*?\]', '', clean).strip()
    return scientific, clean

def run_benchmark(input_dir: str, output_csv: str = "benchmark_species_results.csv", max_per_species: int = 10):
    input_path = Path(input_dir)
    if not input_path.exists():
        print(f"[-] Diretório não encontrado: {input_dir}")
        return

    pipeline = BirdBenchmarkPipeline()
    valid_exts = {".jpg", ".jpeg", ".png"}

    # Descobrir estrutura
    images = []
    species_counts = {}

    for root, dirs, files in os.walk(input_path):
        folder_p = Path(root)
        sci_name, common_name = extract_expected_species(folder_p.name)
        
        # Se não achou na pasta atual, tenta a pasta pai (caso de pastas aninhadas)
        if not sci_name and folder_p.parent != input_path:
            sci_name, common_name = extract_expected_species(folder_p.parent.name)

        label_key = sci_name or folder_p.name

        for f in sorted(files):
            p = folder_p / f
            if p.suffix.lower() in valid_exts:
                if max_per_species > 0:
                    current_count = species_counts.get(label_key, 0)
                    if current_count >= max_per_species:
                        continue
                    species_counts[label_key] = current_count + 1

                images.append((p, sci_name, common_name))

    print(f"\n[+] Total de imagens selecionadas para o benchmark: {len(images)}")
    if max_per_species > 0:
        print(f"[*] (Limitado a até {max_per_species} imagens por espécie para teste ágil)")
    if not images:
        return

    results = []
    top1_correct = 0
    top3_correct = 0
    total_evaluated = 0

    print("\n" + "=" * 76)
    print(f"{'ARQUIVO':<25} | {'ESPERADO (CIENTÍFICO)':<22} | {'PREDIÇÃO TOP-1':<18} | {'CONF'}")
    print("=" * 76)

    start_time = time.time()
    for img_path, expected_sci, expected_comm in images:
        img_bgr = safe_imread(str(img_path))
        if img_bgr is None:
            continue

        crop_pil, detected, yolo_conf = pipeline.detect_and_crop(img_bgr)
        preds = pipeline.classify_crop(crop_pil, top_k=3)
        top1 = preds[0]

        is_top1 = False
        is_top3 = False

        if expected_sci:
            total_evaluated += 1
            if top1["scientific_name"].lower() == expected_sci.lower():
                is_top1 = True
                top1_correct += 1
            
            if any(p["scientific_name"].lower() == expected_sci.lower() for p in preds):
                is_top3 = True
                top3_correct += 1
        elif expected_comm != "Desconhecido":
            total_evaluated += 1
            exp_clean = expected_comm.lower()
            if any(exp_clean in p["common_name"].lower() for p in [top1]):
                is_top1 = True
                top1_correct += 1
            if any(exp_clean in p["common_name"].lower() for p in preds):
                is_top3 = True
                top3_correct += 1

        fname = img_path.name[:24]
        top1_disp = f"{top1['common_name']}"[:17]
        conf_disp = f"{top1['confidence']*100:.1f}%"
        exp_disp = (expected_sci or expected_comm or "Desconhecido")[:22]

        mark = "✓" if is_top1 else ("~" if is_top3 else "✗")
        print(f"{fname:<25} | {exp_disp:<22} | {top1_disp:<18} | {conf_disp:<6} {mark}")

        results.append({
            "path": str(img_path),
            "expected_sci": expected_sci or "",
            "expected_comm": expected_comm or "",
            "detected_by_yolo": detected,
            "yolo_conf": yolo_conf,
            "top1_common": top1["common_name"],
            "top1_scientific": top1["scientific_name"],
            "top1_conf": top1["confidence"],
            "top2_common": preds[1]["common_name"],
            "top2_scientific": preds[1]["scientific_name"],
            "top2_conf": preds[1]["confidence"],
            "top3_common": preds[2]["common_name"],
            "top3_scientific": preds[2]["scientific_name"],
            "top3_conf": preds[2]["confidence"],
            "is_top1": is_top1,
            "is_top3": is_top3
        })

    elapsed = time.time() - start_time
    fps = len(images) / elapsed if elapsed > 0 else 0

    print("=" * 70)
    print(f"\n[+] Benchmark concluído em {elapsed:.2f}s ({fps:.2f} img/s)")
    if total_evaluated > 0:
        print(f"[*] Top-1 Accuracy: {top1_correct}/{total_evaluated} ({top1_correct/total_evaluated*100:.1f}%)")
        print(f"[*] Top-3 Accuracy: {top3_correct}/{total_evaluated} ({top3_correct/total_evaluated*100:.1f}%)")

    # Salva CSV
    with open(output_csv, mode="w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    print(f"[*] Relatório detalhado salvo em: {output_csv}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark de Espécies de Aves (BioCLIP + YOLO)")
    parser.add_argument("--input-dir", required=True, help="Diretório com as imagens (organizadas em subpastas por espécie)")
    parser.add_argument("--out-csv", default="benchmark_species_results.csv", help="Caminho do CSV de saída")
    parser.add_argument("--max-per-species", type=int, default=10, help="Máximo de imagens por espécie para teste inicial ágil (0 para todas)")
    args = parser.parse_args()
    
    run_benchmark(args.input_dir, args.out_csv, max_per_species=args.max_per_species)
