"""
Processador de Vídeo para Identificação de Espécies (IRIS Bird ID).
Amostra frames, filtra por nitidez (variância do Laplaciano), extrai os melhores recortes
e realiza a votação ponderada da espécie predominante.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .detector import BirdDetector
from .classifier import BirdClassifier


def calculate_sharpness(img_gray: np.ndarray) -> float:
    """Calcula a nitidez através da variância do operador Laplaciano."""
    return float(cv2.Laplacian(img_gray, cv2.CV_64F).var())


class VideoBirdProcessor:
    """Processa clipes de vídeo para inferência de espécies de aves."""

    def __init__(self, detector: BirdDetector, classifier: BirdClassifier):
        self.detector = detector
        self.classifier = classifier

    def process_video(
        self,
        video_path: Path,
        sample_interval_sec: Optional[float] = None,
        target_frames: int = 15,
        min_interval_sec: float = 0.5,
        max_interval_sec: float = 5.0,
        min_confident_crops: int = 3,
        max_crops_to_classify: int = 15,
        debug_crops_dir: Optional[Path] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Amostra o clipe de vídeo adaptativamente com base em sua duração,
        ranqueia os recortes mais nítidos e vota a espécie predominante.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps

        # Amostragem adaptativa baseada na duração do clipe se sample_interval_sec não for fixo
        if sample_interval_sec is not None:
            actual_interval = sample_interval_sec
        else:
            tf = max(1, target_frames)
            adaptive_interval = duration_sec / tf
            actual_interval = max(min_interval_sec, min(max_interval_sec, adaptive_interval))

        frame_step = max(1, int(fps * actual_interval))

        candidates = []
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_step == 0:
                h, w = frame.shape[:2]
                results = self.detector.model.predict(frame, classes=[14], conf=self.detector.confidence, verbose=False)

                for r in results:
                    for box in r.boxes:
                        conf = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        bw = x2 - x1
                        bh = y2 - y1

                        if bw < 40 or bh < 40:
                            continue

                        # Margem contextual de 15%
                        mx = int(bw * 0.15)
                        my = int(bh * 0.15)
                        crop_x1 = max(0, x1 - mx)
                        crop_y1 = max(0, y1 - my)
                        crop_x2 = min(w, x2 + mx)
                        crop_y2 = min(h, y2 + my)

                        crop_bgr = frame[crop_y1:crop_y2, crop_x1:crop_x2]
                        gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
                        sharpness = calculate_sharpness(gray)
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

        if not candidates:
            return None

        # Ranqueia pelos melhores scores de nitidez
        candidates.sort(key=lambda x: x["score"], reverse=True)
        selected_crops = candidates[:max_crops_to_classify]

        votes = defaultdict(float)
        vote_counts = Counter()
        species_meta = {}

        best_crop_bgr = selected_crops[0]["bgr_img"]

        for i, item in enumerate(selected_crops):
            preds = self.classifier.classify_crop(item["pil_img"], top_k=3, use_tta=True)
            top1 = preds[0]
            sp_key = (top1["scientific_name"], top1["common_name"])
            votes[sp_key] += top1["confidence"]
            vote_counts[sp_key] += 1
            if sp_key not in species_meta:
                species_meta[sp_key] = {
                    "common_en": top1.get("common_name_en", ""),
                    "family": top1.get("family", ""),
                    "order": top1.get("order", "")
                }

        total_weight = sum(votes.values())
        sorted_votes = sorted(votes.items(), key=lambda x: x[1], reverse=True)

        predominant_sci, predominant_comm = sorted_votes[0][0]
        confidence_pct = (sorted_votes[0][1] / total_weight) if total_weight > 0 else 0.0
        meta_top1 = species_meta.get((predominant_sci, predominant_comm), {})

        crops_for_top_species = vote_counts[(predominant_sci, predominant_comm)]
        is_confident = crops_for_top_species >= min_confident_crops

        # Top 2 e Top 3
        top2_sci, top2_comm, top2_conf = "", "", 0.0
        if len(sorted_votes) > 1:
            top2_sci, top2_comm = sorted_votes[1][0]
            top2_conf = sorted_votes[1][1] / total_weight

        top3_sci, top3_comm, top3_conf = "", "", 0.0
        if len(sorted_votes) > 2:
            top3_sci, top3_comm = sorted_votes[2][0]
            top3_conf = sorted_votes[2][1] / total_weight

        return {
            "is_video": True,
            "duration_sec": duration_sec,
            "evaluated_crops": len(selected_crops),
            "species_common": predominant_comm,
            "species_common_en": meta_top1.get("common_en", ""),
            "species_scientific": predominant_sci,
            "family": meta_top1.get("family", ""),
            "order": meta_top1.get("order", ""),
            "confidence": confidence_pct,
            "species_crops_count": crops_for_top_species,
            "min_confident_crops": min_confident_crops,
            "is_confident_detection": is_confident,
            "top2_common": top2_comm,
            "top2_scientific": top2_sci,
            "top2_confidence": top2_conf,
            "top3_common": top3_comm,
            "top3_scientific": top3_sci,
            "top3_confidence": top3_conf,
            "best_crop_bgr": best_crop_bgr,
            "vote_distribution": {
                f"{comm} ({sci})": {
                    "votes": vote_counts[(sci, comm)],
                    "weight_pct": round((weight / total_weight) * 100, 1)
                }
                for (sci, comm), weight in sorted_votes
            }
        }
