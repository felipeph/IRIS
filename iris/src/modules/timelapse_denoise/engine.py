import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional, Callable

import cv2
import numpy as np


def extract_jpeg_app1_segments(jpeg_bytes: bytes) -> bytes:
    """
    Extrai todos os segmentos binários APP1 (0xFFE1 - EXIF, GPS e XMP) do cabeçalho JPEG original.
    Executa em memória em < 0.1ms sem depender de ferramentas externas.
    """
    if not jpeg_bytes or len(jpeg_bytes) < 4 or jpeg_bytes[0:2] != b"\xff\xd8":
        return b""

    pos = 2
    n = len(jpeg_bytes)
    segments: List[bytes] = []

    while pos + 4 <= n:
        if jpeg_bytes[pos] != 0xFF:
            break
        marker = jpeg_bytes[pos + 1]
        # SOS (Start of Scan) ou EOI (End of Image) encerram os metadados de cabeçalho
        if marker in (0xDA, 0xD9):
            break
        # Marcadores standalone sem tamanho
        if marker in (0xD8, 0x01) or (0xD0 <= marker <= 0xD7):
            pos += 2
            continue
        if marker == 0xFF:
            pos += 1
            continue

        seg_len = int.from_bytes(jpeg_bytes[pos + 2 : pos + 4], "big")
        if seg_len < 2 or pos + 2 + seg_len > n:
            break

        if marker == 0xE1:  # APP1 (Exif / XMP)
            segments.append(jpeg_bytes[pos : pos + 2 + seg_len])

        pos += 2 + seg_len

    return b"".join(segments)


def inject_jpeg_app1_segments(encoded_jpeg: bytes, app1_segments: bytes) -> bytes:
    """
    Injeta os segmentos binários APP1 (EXIF/GPS/XMP) em um buffer JPEG recém-codificado.
    """
    if not app1_segments or not encoded_jpeg or len(encoded_jpeg) < 4 or encoded_jpeg[0:2] != b"\xff\xd8":
        return encoded_jpeg

    insert_pos = 2
    # Se iniciar com APP0 (JFIF - 0xFFE0), insere logo após o APP0
    if len(encoded_jpeg) >= 6 and encoded_jpeg[2:4] == b"\xff\xe0":
        app0_len = int.from_bytes(encoded_jpeg[4:6], "big")
        if 2 + 2 + app0_len <= len(encoded_jpeg):
            insert_pos = 4 + app0_len

    return encoded_jpeg[:insert_pos] + app1_segments + encoded_jpeg[insert_pos:]


def read_image_bgr_and_app1(path: Path) -> Tuple[Optional[np.ndarray], bytes]:
    """Lê o arquivo JPEG uma única vez do disco, extraindo a matriz BGR e os segmentos EXIF/APP1."""
    try:
        raw_bytes = path.read_bytes()
        app1 = extract_jpeg_app1_segments(raw_bytes)
        arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img, app1
    except Exception:
        return None, b""


def write_image_bgr_with_app1(
    path: Path,
    img: np.ndarray,
    app1_segments: bytes,
    jpeg_quality: int = 96
) -> bool:
    """Codifica a matriz BGR para JPEG com alta qualidade, injeta o EXIF/APP1 original e grava em disco."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        q = max(70, min(100, int(jpeg_quality)))
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        if not ok:
            return False
        final_bytes = inject_jpeg_app1_segments(buf.tobytes(), app1_segments)
        path.write_bytes(final_bytes)
        return True
    except Exception:
        return False


def build_bilateral_lut(sigma_range: float = 4.5, scale: int = 32) -> np.ndarray:
    """
    Constrói tabela de busca (LUT uint8 de 256 posições) para pesos fotométricos bilaterais
    escalados em ponto fixo (0..scale).
    """
    sigma = max(0.5, float(sigma_range))
    d = np.arange(256, dtype=np.float32)
    weights = np.exp(-0.5 * (d / sigma) ** 2) * float(scale)
    return np.clip(np.round(weights), 0, scale).astype(np.uint8)


def compute_hot_pixel_map(
    frames: List[np.ndarray],
    threshold: int = 8
) -> Tuple[np.ndarray, int]:
    """
    Identifica defeitos estacionários do sensor (hot/warm pixels de exposição longa)
    usando o percentil inferior temporal (via np.partition) comparado à mediana espacial 3x3.

    Como as estrelas reais se movem ao longo dos frames, elas desaparecem no percentil
    inferior temporal, isolando apenas o fundo fixo e os hot pixels da câmera.
    Retorna (mapa_subtracao_uint8, qtd_hot_pixels_detectados).
    """
    if not frames:
        return np.zeros((1, 1, 3), dtype=np.uint8), 0

    if len(frames) < 3:
        return np.zeros_like(frames[0]), 0

    stack = np.stack(frames, axis=0)
    k = 1 if len(frames) >= 5 else 0
    p_low = np.partition(stack, k, axis=0)[k]
    med_spatial = cv2.medianBlur(p_low, 3)
    hot_excess = cv2.subtract(p_low, med_spatial)

    thr = max(1, int(threshold))
    max_ch = hot_excess.max(axis=2)
    hot_mask_2d = max_ch > thr
    hot_count = int(np.count_nonzero(hot_mask_2d))

    if hot_count == 0:
        return np.zeros_like(frames[0]), 0

    mask_u8 = (hot_mask_2d.astype(np.uint8)) * 255
    mask_3ch = cv2.merge([mask_u8, mask_u8, mask_u8])
    hot_defect = cv2.bitwise_and(hot_excess, mask_3ch)
    return hot_defect, hot_count


def _prepare_frame_features(
    raw_bgr: np.ndarray,
    hot_defect: Optional[np.ndarray]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Aplica correção de hot pixels e pré-calcula luminância e guia Gaussiano 3x3."""
    if hot_defect is not None and hot_defect.shape == raw_bgr.shape:
        cleaned = cv2.subtract(raw_bgr, hot_defect)
    else:
        cleaned = raw_bgr
    gray = cv2.cvtColor(cleaned, cv2.COLOR_BGR2GRAY)
    guide = cv2.GaussianBlur(gray, (3, 3), 0.8)
    return cleaned, gray, guide


def denoise_frame_temporal(
    center_idx: int,
    cleaned_frames: List[np.ndarray],
    gray_frames: List[np.ndarray],
    guides: List[np.ndarray],
    lut_u8: np.ndarray,
    scale: int = 32,
    chroma_denoise: bool = True
) -> np.ndarray:
    """
    Aplica o Filtro Bilateral Temporal Guiado (com proteção de estrelas pontuais) sobre o frame central
    da janela deslizante e realiza suavização seletiva de crominância em YCrCb.
    """
    ref = cleaned_frames[center_idx]
    ref_gray = gray_frames[center_idx]
    ref_guide = guides[center_idx]

    acc = cv2.multiply(ref, scale, dtype=cv2.CV_16U)
    w_sum = np.full(ref_gray.shape, scale, dtype=np.uint16)

    for i in range(len(cleaned_frames)):
        if i == center_idx:
            continue
        ad_guide = cv2.absdiff(guides[i], ref_guide)
        ad_pixel = cv2.absdiff(gray_frames[i], ref_gray)
        ad = cv2.max(ad_guide, cv2.divide(ad_pixel, 2))
        w = cv2.LUT(ad, lut_u8)
        w_sum = cv2.add(w_sum, w, dtype=cv2.CV_16U)
        w3 = cv2.merge([w, w, w])
        acc = cv2.add(acc, cv2.multiply(cleaned_frames[i], w3, dtype=cv2.CV_16U))

    w3_sum = cv2.merge([w_sum, w_sum, w_sum])
    out = cv2.divide(acc, w3_sum, dtype=cv2.CV_8U)

    if chroma_denoise:
        ycrcb = cv2.cvtColor(out, cv2.COLOR_BGR2YCrCb)
        ycrcb[..., 1] = cv2.GaussianBlur(ycrcb[..., 1], (5, 5), 1.2)
        ycrcb[..., 2] = cv2.GaussianBlur(ycrcb[..., 2], (5, 5), 1.2)
        out = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)

    return out


def process_sequence_denoise(
    photo_paths: List[Path],
    output_dir: Path,
    window_size: int = 7,
    sigma_range: float = 4.5,
    hot_pixel_threshold: int = 8,
    chroma_denoise: bool = True,
    jpeg_quality: int = 96,
    recalibrate_interval: int = 60,
    progress_callback: Optional[Callable[[int, int, str, int], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Processa uma sequência ordenada de fotos de timelapse noturno usando uma janela deslizante
    em memória (O(W) RAM), removendo hot pixels fixos, ruído temporal de leitura/ISO e ruído
    de crominância com preservação estrita de estrelas em movimento e metadados EXIF/GPS.
    """
    total = len(photo_paths)
    if total == 0:
        return False, {"error": "Nenhum arquivo fornecido para denoise."}

    output_dir.mkdir(parents=True, exist_ok=True)
    w_size = max(3, int(window_size))
    if w_size % 2 == 0:
        w_size += 1
    radius = w_size // 2

    scale = 32
    lut_u8 = build_bilateral_lut(sigma_range=sigma_range, scale=scale)
    t0 = time.time()

    # Cache deslizante de leitura: idx -> (raw_bgr, app1, cleaned_bgr, gray, guide)
    cache: Dict[int, Tuple[np.ndarray, bytes, np.ndarray, np.ndarray, np.ndarray]] = {}
    hot_defect: Optional[np.ndarray] = None
    hot_pixels_detected = 0

    io_pool = ThreadPoolExecutor(max_workers=2)
    read_futures: Dict[int, Future] = {}
    write_futures: deque[Future] = deque()

    def schedule_read(idx: int):
        if 0 <= idx < total and idx not in cache and idx not in read_futures:
            read_futures[idx] = io_pool.submit(read_image_bgr_and_app1, photo_paths[idx])

    def get_raw(idx: int) -> Tuple[Optional[np.ndarray], bytes]:
        if idx in read_futures:
            fut = read_futures.pop(idx)
            return fut.result()
        return read_image_bgr_and_app1(photo_paths[idx])

    # Pré-agendar leitura dos primeiros frames para calibração inicial de hot pixels
    init_count = min(total, max(w_size, 9))
    for i in range(init_count):
        schedule_read(i)

    init_raws: List[np.ndarray] = []
    init_app1s: Dict[int, bytes] = {}
    for i in range(init_count):
        im, app1 = get_raw(i)
        if im is not None:
            init_raws.append(im)
            init_app1s[i] = app1

    if not init_raws:
        io_pool.shutdown(wait=False)
        return False, {"error": "Falha ao decodificar imagens da sequência."}

    hot_defect, hot_pixels_detected = compute_hot_pixel_map(init_raws, threshold=hot_pixel_threshold)

    # Povoar cache inicial com os frames já lidos
    for i, im in enumerate(init_raws):
        cleaned, gray, guide = _prepare_frame_features(im, hot_defect)
        cache[i] = (im, init_app1s.get(i, b""), cleaned, gray, guide)

    processed_count = 0
    errors = 0

    try:
        for center_idx in range(total):
            start_i = max(0, center_idx - radius)
            end_i = min(total - 1, center_idx + radius)

            # Agendar prefetch dos próximos frames
            for prefetch_i in range(end_i, min(total, end_i + 3)):
                schedule_read(prefetch_i)

            # Garantir que todos os frames da janela [start_i..end_i] estão no cache
            for i in range(start_i, end_i + 1):
                if i not in cache:
                    im, app1 = get_raw(i)
                    if im is None:
                        continue
                    cleaned, gray, guide = _prepare_frame_features(im, hot_defect)
                    cache[i] = (im, app1, cleaned, gray, guide)

            # Recalibrar mapa de hot pixels periodicamente caso a janela esteja completa
            if (
                recalibrate_interval > 0
                and center_idx > 0
                and center_idx % recalibrate_interval == 0
                and (end_i - start_i + 1) >= 5
            ):
                window_raws = [cache[i][0] for i in range(start_i, end_i + 1) if i in cache]
                if len(window_raws) >= 5:
                    new_defect, new_hp_count = compute_hot_pixel_map(window_raws, threshold=hot_pixel_threshold)
                    hot_defect = new_defect
                    hot_pixels_detected = max(hot_pixels_detected, new_hp_count)
                    for i in list(cache.keys()):
                        raw_i, app1_i, _, _, _ = cache[i]
                        c_i, g_i, gu_i = _prepare_frame_features(raw_i, hot_defect)
                        cache[i] = (raw_i, app1_i, c_i, g_i, gu_i)

            if center_idx not in cache:
                errors += 1
                continue

            win_indices = [i for i in range(start_i, end_i + 1) if i in cache]
            rel_center = win_indices.index(center_idx)
            cleaned_list = [cache[i][2] for i in win_indices]
            gray_list = [cache[i][3] for i in win_indices]
            guide_list = [cache[i][4] for i in win_indices]
            app1_bytes = cache[center_idx][1]

            denoised_bgr = denoise_frame_temporal(
                center_idx=rel_center,
                cleaned_frames=cleaned_list,
                gray_frames=gray_list,
                guides=guide_list,
                lut_u8=lut_u8,
                scale=scale,
                chroma_denoise=chroma_denoise,
            )

            out_path = output_dir / photo_paths[center_idx].name

            # Limitar fila de escrita assíncrona para não acumular memória
            while len(write_futures) >= 4:
                done_fut = write_futures.popleft()
                if not done_fut.result():
                    errors += 1

            write_futures.append(
                io_pool.submit(write_image_bgr_with_app1, out_path, denoised_bgr, app1_bytes, jpeg_quality)
            )

            # Descartar frames antigos fora da janela deslizante
            evict_before = start_i - 1
            for old_k in [k for k in cache.keys() if k <= evict_before]:
                del cache[old_k]

            processed_count += 1
            if progress_callback:
                progress_callback(processed_count, total, photo_paths[center_idx].name, hot_pixels_detected)

        while write_futures:
            done_fut = write_futures.popleft()
            if not done_fut.result():
                errors += 1

    finally:
        io_pool.shutdown(wait=True)

    elapsed = round(time.time() - t0, 2)
    stats = {
        "total_photos": total,
        "processed_photos": processed_count,
        "errors": errors,
        "window_size": w_size,
        "sigma_range": sigma_range,
        "hot_pixel_threshold": hot_pixel_threshold,
        "hot_pixels_detected": hot_pixels_detected,
        "chroma_denoise": chroma_denoise,
        "jpeg_quality": jpeg_quality,
        "elapsed_seconds": elapsed,
        "avg_fps": round(processed_count / max(0.001, elapsed), 2),
        "output_dir": str(output_dir.resolve()),
    }
    return (errors == 0 and processed_count == total), stats
