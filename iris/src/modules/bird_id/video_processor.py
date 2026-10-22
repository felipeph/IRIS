"""
Processador de Vídeo para Identificação de Espécies (IRIS Bird ID).
Desacoplado em duas etapas atômicas:
1. extract_best_video_crops: Amostra frames, detecta aves via YOLOv8, ranqueia por nitidez
   (variância do Laplaciano) e salva os melhores recortes em disco.
2. classify_video_crops: Lê os recortes salvos, consulta o classificador taxonômico e
   realiza votação ponderada da espécie predominante.
"""

from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Optional

import cv2
import numpy as np
from PIL import Image

from .detector import BirdDetector, safe_imread, safe_imwrite
from .classifier import BirdClassifier


def calculate_sharpness(img_gray: np.ndarray) -> float:
    """Calcula a nitidez através da variância do operador Laplaciano."""
    return float(cv2.Laplacian(img_gray, cv2.CV_64F).var())


class VideoBirdProcessor:
    """Processa clipes de vídeo para detecção e inferência taxonômica de espécies de aves."""

    def __init__(self, detector: Optional[BirdDetector] = None, classifier: Optional[BirdClassifier] = None):
        self.detector = detector
        self.classifier = classifier

    def extract_best_video_crops(
        self,
        video_path: Path,
        output_dir: Optional[Path] = None,
        stem: str = "",
        sample_interval_sec: Optional[float] = None,
        target_frames: int = 15,
        min_interval_sec: float = 0.5,
        max_interval_sec: float = 5.0,
        max_crops_to_extract: int = 5
    ) -> Optional[Dict[str, Any]]:
        """
        Etapa 1 (Atômica): Amostra o clipe de vídeo adaptativamente com base em sua duração,
        detecta aves via YOLOv8, calcula nitidez (Laplaciano) e extrai/salva em disco
        os N melhores recortes.
        """
        if self.detector is None:
            raise ValueError("BirdDetector é obrigatório para extrair recortes de vídeo.")

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_sec = total_frames / fps

        # Amostragem adaptativa proporcional à duração do clipe
        if sample_interval_sec is not None:
            actual_interval = sample_interval_sec
        else:
            tf = max(1, target_frames)
            adaptive_interval = duration_sec / tf
            actual_interval = max(min_interval_sec, min(max_interval_sec, adaptive_interval))

        frame_step = max(1, int(fps * actual_interval))

        candidates = []
        frame_idx = 0
        sampled_count = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_step == 0:
                sampled_count += 1
                h, w = frame.shape[:2]
                results = self.detector.model.predict(
                    frame,
                    classes=[14],
                    conf=self.detector.confidence,
                    verbose=False
                )

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

        # Ranqueia pelos melhores scores de nitidez e seleciona até max_crops_to_extract
        candidates.sort(key=lambda x: x["score"], reverse=True)
        selected_candidates = candidates[:max_crops_to_extract]

        saved_crops = []
        file_stem = stem or video_path.stem

        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)

        for c in selected_candidates:
            crop_path_str = ""
            if output_dir:
                crop_file = output_dir / f"crop_{file_stem}_f{c['frame_idx']}.jpg"
                safe_imwrite(str(crop_file), c["bgr_img"], quality=95)
                crop_path_str = str(crop_file.resolve())

            crop_entry = {
                "frame_idx": c["frame_idx"],
                "timestamp_s": round(c["timestamp_s"], 2),
                "yolo_conf": round(float(c["yolo_conf"]), 4),
                "sharpness": round(float(c["sharpness"]), 2),
                "score": round(float(c["score"]), 2),
                "crop_path": crop_path_str
            }
            if not output_dir:
                crop_entry["pil_img"] = c["pil_img"]
                crop_entry["bgr_img"] = c["bgr_img"]

            saved_crops.append(crop_entry)

        best_crop = saved_crops[0] if saved_crops else None
        best_crop_bgr = selected_candidates[0]["bgr_img"] if selected_candidates else None

        return {
            "duration_sec": duration_sec,
            "total_sampled_frames": sampled_count,
            "detected_bird_frames": len(candidates),
            "saved_crops": saved_crops,
            "best_crop_path": best_crop["crop_path"] if best_crop else "",
            "best_crop_bgr": best_crop_bgr
        }

    def classify_video_crops(
        self,
        saved_crops: List[Dict[str, Any]],
        classifier: Optional[BirdClassifier] = None,
        duration_sec: float = 0.0,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        accuracy: Optional[float] = None,
        observed_on: Optional[Any] = None,
        min_confident_crops: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Etapa 2 (Atômica): Recebe os recortes extraídos de um vídeo, consulta o classificador
        taxonômico para cada recorte e consolida a espécie predominante por votação ponderada.
        """
        clf = classifier or self.classifier
        if clf is None:
            raise ValueError("BirdClassifier é obrigatório para classificar recortes de vídeo.")

        if not saved_crops:
            return None

        votes = defaultdict(float)
        vote_counts = Counter()
        species_meta = {}
        best_crop_bgr = None

        for item in saved_crops:
            pil_img = item.get("pil_img")
            if pil_img is None and item.get("crop_path"):
                bgr = safe_imread(item["crop_path"])
                if bgr is not None:
                    if best_crop_bgr is None:
                        best_crop_bgr = bgr
                    pil_img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))

            if pil_img is None:
                continue

            preds = clf.classify_crop(
                pil_img,
                top_k=3,
                use_tta=True,
                lat=lat,
                lng=lng,
                accuracy=accuracy,
                observed_on=observed_on
            )
            if not preds:
                continue

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

        if not votes:
            return None

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
            "evaluated_crops": len(saved_crops),
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
            "best_crop_bgr": best_crop_bgr if best_crop_bgr is not None else (saved_crops[0].get("bgr_img") if saved_crops else None),
            "best_crop_path": saved_crops[0].get("crop_path", "") if saved_crops else "",
            "vote_distribution": {
                f"{comm} ({sci})": {
                    "votes": vote_counts[(sci, comm)],
                    "weight_pct": round((weight / total_weight) * 100, 1)
                }
                for (sci, comm), weight in sorted_votes
            }
        }

    def process_video(
        self,
        video_path: Path,
        sample_interval_sec: Optional[float] = None,
        target_frames: int = 15,
        min_interval_sec: float = 0.5,
        max_interval_sec: float = 5.0,
        min_confident_crops: int = 2,
        max_crops_to_classify: int = 5,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        accuracy: Optional[float] = None,
        observed_on: Optional[Any] = None,
        debug_crops_dir: Optional[Path] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Método composto para compatibilidade retroativa: extrai e classifica em sequência única.
        """
        extraction = self.extract_best_video_crops(
            video_path=video_path,
            output_dir=debug_crops_dir,
            stem=video_path.stem,
            sample_interval_sec=sample_interval_sec,
            target_frames=target_frames,
            min_interval_sec=min_interval_sec,
            max_interval_sec=max_interval_sec,
            max_crops_to_extract=max_crops_to_classify
        )
        if not extraction or not extraction.get("saved_crops"):
            return None

        classification = self.classify_video_crops(
            saved_crops=extraction["saved_crops"],
            classifier=self.classifier,
            duration_sec=extraction["duration_sec"],
            lat=lat,
            lng=lng,
            accuracy=accuracy,
            observed_on=observed_on,
            min_confident_crops=min_confident_crops
        )
        if not classification:
            return None

        classification["best_crop_bgr"] = extraction.get("best_crop_bgr")
        classification["best_crop_path"] = extraction.get("best_crop_path", "")
        return classification
