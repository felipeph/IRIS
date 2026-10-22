"""
Detector de Aves do IRIS.
Utiliza Ultralytics YOLOv8 para identificar presença de aves (classe 14) e extrair recortes em alta resolução.
"""

import os
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

import cv2
import numpy as np
from PIL import Image


def safe_imread(path_str: str) -> Optional[np.ndarray]:
    """Lê imagem de forma segura no Windows mesmo com acentos ou caracteres especiais."""
    try:
        with open(path_str, "rb") as f:
            data = np.frombuffer(f.read(), dtype=np.uint8)
            return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None


def safe_read_image_or_raw(path_str: str) -> Optional[np.ndarray]:
    """
    Lê imagem convencional (JPEG/PNG) ou arquivo RAW (.CR2, .CR3, .ARW, .DNG, .NEF).
    Para arquivos RAW, extrai o preview JPEG embutido (~30ms) sem custo de demosaicing completo.
    """
    ext = os.path.splitext(path_str)[1].lower()
    raw_extensions = {".cr2", ".cr3", ".arw", ".dng", ".nef", ".raw"}
    if ext in raw_extensions:
        try:
            import rawpy
            with rawpy.imread(path_str) as raw:
                try:
                    thumb = raw.extract_thumb()
                    if thumb.format == rawpy.ThumbFormat.JPEG:
                        img = cv2.imdecode(np.frombuffer(thumb.data, dtype=np.uint8), cv2.IMREAD_COLOR)
                        if img is not None:
                            return img
                    elif thumb.format == rawpy.ThumbFormat.BITMAP:
                        return cv2.cvtColor(thumb.data, cv2.COLOR_RGB2BGR)
                except Exception:
                    pass

                # Fallback se não tiver thumbnail embutido: meio-tamanho rápido
                rgb = raw.postprocess(half_size=True, use_camera_wb=True)
                return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:
            pass

    return safe_imread(path_str)


def safe_imwrite(path_str: str, img_bgr: np.ndarray, quality: int = 95) -> bool:
    """Salva imagem em disco suportando caminhos com acentuação."""
    try:
        parent = os.path.dirname(path_str)
        if parent:
            os.makedirs(parent, exist_ok=True)
        ext = os.path.splitext(path_str)[1].lower() or ".jpg"
        params = []
        if ext in {".jpg", ".jpeg"}:
            params = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        success, buf = cv2.imencode(ext, img_bgr, params)
        if success:
            with open(path_str, "wb") as f:
                f.write(buf)
            return True
    except Exception:
        pass
    return bool(cv2.imwrite(path_str, img_bgr))


class BirdDetector:
    """Wrapper para detecção de aves e extração de recortes com YOLOv8."""

    def __init__(self, model_name: str = "yolov8s.pt", confidence: float = 0.25):
        from ultralytics import YOLO
        self.model_name = model_name
        self.confidence = confidence
        self.model = YOLO(model_name)

    def detect_and_crop(
        self,
        img_bgr: np.ndarray,
        margin_ratio: float = 0.15
    ) -> Tuple[Image.Image, np.ndarray, bool, float, Optional[Tuple[int, int, int, int]]]:
        """
        Detecta a ave principal (maior área e confiança) e retorna o recorte ampliado.
        Retorna:
            pil_crop: Recorte em formato PIL Image (RGB)
            bgr_crop: Recorte em formato np.ndarray (BGR)
            detected: Se uma ave foi detectada
            conf: Confiança da detecção YOLO
            bbox: (x1, y1, x2, y2) no frame original
        """
        h, w = img_bgr.shape[:2]
        results = self.model.predict(img_bgr, classes=[14], conf=self.confidence, verbose=False)
        
        best_box = None
        max_score = 0.0

        for r in results:
            for box in r.boxes:
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                area = (x2 - x1) * (y2 - y1)
                score = conf * (area / (w * h))
                if score > max_score or best_box is None:
                    max_score = score
                    best_box = (x1, y1, x2, y2, conf)

        if best_box is not None:
            x1, y1, x2, y2, conf = best_box
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
            return Image.fromarray(crop_rgb), crop_bgr, True, conf, (crop_x1, crop_y1, crop_x2, crop_y2)
        else:
            # Fallback para ave centralizada (imagem inteira)
            crop_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            return Image.fromarray(crop_rgb), img_bgr, False, 0.0, None
