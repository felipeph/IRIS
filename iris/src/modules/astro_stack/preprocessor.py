"""Pré-processamento e normalização geométrica de frames lunares para empilhamento."""
import math
from pathlib import Path
from typing import Tuple, List, Dict, Any, Union, Optional

import numpy as np


def moon_bounds(image: np.ndarray) -> Tuple[int, int, int, int]:
    """Localiza o maior objeto brilhante conectado (disco lunar).
    
    Retorna (x, y, width, height) onde x e y são coordenadas inteiras do canto superior esquerdo.
    Garante que o disco não toque a borda e possua dimensão mínima.
    """
    import cv2

    peak = float(np.percentile(image, 99.9))
    if peak <= 0:
        raise ValueError("Imagem vazia: não foi possível detectar a Lua.")
    scaled = np.uint8(np.clip(image.astype(np.float32) * (255.0 / peak), 0, 255))
    blurred = cv2.GaussianBlur(scaled, (9, 9), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    if count < 2:
        raise ValueError("Nenhum objeto brilhante detectado.")
    x, y, width, height, area = map(int, stats[1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])])
    if area < 100 or width >= image.shape[1] - 2 or height >= image.shape[0] - 2:
        raise ValueError("O objeto detectado não parece um disco lunar isolado.")
    if x == 0 or y == 0 or x + width >= image.shape[1] or y + height >= image.shape[0]:
        raise ValueError("A Lua toca a borda da imagem; o disco pode estar cortado.")
    return x, y, width, height


def centred_crop(image: np.ndarray, size: int, bounds: Optional[Tuple[int, int, int, int]] = None) -> np.ndarray:
    """Aplica recorte centrado no disco lunar utilizando translação em pixels inteiros.
    
    Zero interpolação / redimensionamento para preservar a fidelidade dos dados brutos dos sensores.
    Se bounds for fornecido, reaproveita as coordenadas evitando o recálculo redundante de moon_bounds.
    """
    if bounds is not None:
        x, y, width, height = bounds
    else:
        x, y, width, height = moon_bounds(image)

    if size < max(width, height) + 16:
        raise ValueError(f"Recorte {size} muito pequeno para a Lua ({width} x {height}).")
    left = int(round(x + (width - 1) / 2.0 - (size - 1) / 2.0))
    top = int(round(y + (height - 1) / 2.0 - (size - 1) / 2.0))
    out = np.zeros((size, size), dtype=image.dtype)
    x0, y0 = max(0, left), max(0, top)
    x1, y1 = min(image.shape[1], left + size), min(image.shape[0], top + size)
    out[y0 - top:y1 - top, x0 - left:x1 - left] = image[y0:y1, x0:x1]
    return out


def read_mono(path: Union[str, Path], fast_demosaic: bool = True) -> np.ndarray:
    """Lê um arquivo RAW ou imagem convencional e retorna matriz monocromática uint16."""
    import cv2
    path = Path(path)
    ext = path.suffix.lower()

    if ext in {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raw"}:
        try:
            import rawpy
            with rawpy.imread(str(path)) as raw:
                params = {
                    "output_bps": 16,
                    "no_auto_bright": True,
                    "use_camera_wb": True,
                    "gamma": (1, 1),
                }
                if fast_demosaic and hasattr(rawpy, "DemosaicAlgorithm"):
                    params["demosaic_algorithm"] = rawpy.DemosaicAlgorithm.LINEAR
                rgb = raw.postprocess(**params)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        except ImportError:
            raise RuntimeError(
                "rawpy é necessário para decodificar arquivos RAW. Verifique o ambiente virtual do módulo astro."
            )

    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Não foi possível abrir o arquivo: {path}")
    if image.ndim == 3:
        image = cv2.cvtColor(
            image,
            cv2.COLOR_BGRA2GRAY if image.shape[2] == 4 else cv2.COLOR_BGR2GRAY,
        )
    if image.dtype == np.uint8:
        image = image.astype(np.uint16) * 257
    if image.dtype != np.uint16:
        raise ValueError("A entrada deve ser RAW ou imagem de 8/16 bits.")
    return image


def calculate_sequence_gain(peak_val: float) -> float:
    """Calcula ganho linear comum para toda a sequência sem esticar frames independentemente."""
    if peak_val <= 0:
        return 1.0
    return 60000.0 / peak_val


def _write_tiff(path: Union[str, Path], img: np.ndarray) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        import tifffile
        tifffile.imwrite(str(p), img, photometric="minisblack")
    except ImportError:
        import cv2
        cv2.imwrite(str(p), img)


def _read_tiff(path: Union[str, Path]) -> np.ndarray:
    try:
        import tifffile
        return tifffile.imread(path)
    except ImportError:
        import cv2
        return cv2.imread(str(path), cv2.IMREAD_UNCHANGED)


def process_and_save_frame(
    file_path: Union[str, Path],
    crop_size: int,
    gain: float,
    output_tiff_path: Union[str, Path],
    fast_demosaic: bool = True,
) -> Dict[str, Any]:
    """Processa um frame em passo único: decodifica, localiza bounds, recorta centrado,
    aplica ganho escalar e grava diretamente o TIFF final pronto para o PSS.
    
    Elimina qualquer necessidade de arquivos ou pastas temporárias intermediárias.
    Retorna dicionário com success=True ou success=False em caso de borda tocada / falha.
    """
    path = Path(file_path)
    out_path = Path(output_tiff_path)

    try:
        img = read_mono(path, fast_demosaic=fast_demosaic)
        bounds = moon_bounds(img)
        peak = float(np.max(img))
        cropped = centred_crop(img, crop_size, bounds=bounds)

        if abs(gain - 1.0) >= 1e-4:
            scaled = np.uint16(np.clip(cropped.astype(np.float32) * gain, 0, 65535))
        else:
            scaled = cropped

        _write_tiff(out_path, scaled)

        return {
            "success": True,
            "file": str(path),
            "filename": path.name,
            "tiff_path": str(out_path),
            "shape": list(img.shape),
            "moon_bounds": list(bounds),
            "peak": peak,
        }
    except Exception as exc:
        return {
            "success": False,
            "file": str(path),
            "filename": path.name,
            "error": str(exc),
        }



def process_single_frame(
    file_path: Union[str, Path],
    crop_size: int,
    output_tiff_path: Union[str, Path],
    fast_demosaic: bool = True,
) -> Dict[str, Any]:
    """Processa um frame isolado: decodifica, localiza bounds, recorta e grava TIFF intermediário.
    
    Retorna dicionário com metadados para evitar acúmulo de matrizes brutas na memória RAM.
    """
    path = Path(file_path)
    out_path = Path(output_tiff_path)

    img = read_mono(path, fast_demosaic=fast_demosaic)
    bounds = moon_bounds(img)
    peak = float(np.max(img))
    cropped = centred_crop(img, crop_size, bounds=bounds)

    _write_tiff(out_path, cropped)

    return {
        "file": str(path),
        "filename": path.name,
        "temp_tiff": str(out_path),
        "shape": list(img.shape),
        "moon_bounds": list(bounds),
        "peak": peak,
    }


def scale_single_frame(
    src_tiff_path: Union[str, Path],
    dst_tiff_path: Union[str, Path],
    gain: float,
) -> None:
    """Aplica ganho linear sobre o frame recortado temporário e salva o frame final do PSS."""
    src_p = Path(src_tiff_path)
    dst_p = Path(dst_tiff_path)

    if abs(gain - 1.0) < 1e-4:
        if src_p != dst_p:
            if dst_p.exists():
                dst_p.unlink()
            src_p.rename(dst_p)
        return

    img = _read_tiff(src_p)
    scaled = np.uint16(np.clip(img.astype(np.float32) * gain, 0, 65535))
    _write_tiff(dst_p, scaled)

    if src_p != dst_p and src_p.exists():
        try:
            src_p.unlink()
        except Exception:
            pass

