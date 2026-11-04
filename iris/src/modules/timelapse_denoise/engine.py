import os
import time
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
import threading
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


def build_q5_shrinkage_lut(sigma_range: float = 4.5, window_size: int = 7, scale: int = 32) -> np.ndarray:
    """
    Constrói tabela de busca (LUT uint8 de 256 posições) em ponto fixo Q5 (scale=32)
    para encolhimento espaço-temporal sem risco de underflow/overflow:
        lut[idx] = round(128 + scale * (d * exp(-0.5 * (d / (2 * sigma))^2)) / E[sum_w]), onde d = (idx - 128) * 2.

    O fator 2*sigma compensa a variância dobrada da diferença direta entre dois frames ruidosos
    sem pré-suavização espacial (Var(Y_i - Y_ref) = 2 * Var(Y)), e norm_denom = 1 + (N - 1) * 0.72
    representa o peso total esperado E[sum_w] em regiões estacionárias.
    """
    sigma_eff = max(1.0, float(sigma_range) * 2.0)
    n = max(1, int(window_size))
    s = max(1, int(scale))
    norm_denom = 1.0 + max(0, n - 1) * 0.72
    lut = np.zeros(256, dtype=np.uint8)
    for idx in range(256):
        d = (idx - 128.0) * 2.0
        w = np.exp(-0.5 * ((d / sigma_eff) ** 2))
        val = 128.0 + (s * d * w) / norm_denom
        lut[idx] = int(np.clip(np.round(val), 0, 255))
    return lut


def build_bilateral_lut(sigma_range: float = 4.5, scale: int = 32) -> np.ndarray:
    """Compatibilidade retroativa: constrói LUT tradicional de pesos gaussianos."""
    sigma = max(0.5, float(sigma_range))
    d = np.arange(256, dtype=np.float32)
    weights = np.exp(-0.5 * (d / sigma) ** 2) * float(scale)
    return np.clip(np.round(weights), 0, scale).astype(np.uint8)


def compute_hot_pixel_map(
    frames: List[np.ndarray],
    threshold: int = 8
) -> Tuple[np.ndarray, int]:
    """
    Identifica defeitos estacionários do sensor (hot/warm pixels de longa exposição)
    usando streaming SIMD cv2.min/cv2.max (segundo menor valor temporal) comparado à mediana espacial 3x3.
    """
    if not frames:
        return np.zeros((1, 1, 3), dtype=np.uint8), 0

    if len(frames) < 3:
        return np.zeros_like(frames[0]), 0

    min1 = frames[0].copy()
    if len(frames) >= 5:
        min2 = np.full_like(min1, 255)
        tmp_max = np.empty_like(min1)
        for f in frames[1:]:
            cv2.max(min1, f, dst=tmp_max)
            cv2.min(min2, tmp_max, dst=min2)
            cv2.min(min1, f, dst=min1)
        p_low = min2
    else:
        for f in frames[1:]:
            cv2.min(min1, f, dst=min1)
        p_low = min1

    med_spatial = cv2.medianBlur(p_low, 3)
    hot_excess = cv2.subtract(p_low, med_spatial)

    thr = max(1, int(threshold))
    b, g, r = cv2.split(hot_excess)
    max_ch = cv2.max(cv2.max(b, g), r)
    _, hot_mask_2d = cv2.threshold(max_ch, thr, 255, cv2.THRESH_BINARY)
    hot_count = int(cv2.countNonZero(hot_mask_2d))

    if hot_count == 0:
        return np.zeros_like(frames[0]), 0

    mask_3ch = cv2.merge([hot_mask_2d, hot_mask_2d, hot_mask_2d])
    hot_defect = cv2.bitwise_and(hot_excess, mask_3ch)
    return hot_defect, hot_count


def extract_hot_pixel_coords(hot_defect: Optional[np.ndarray]) -> Tuple[np.ndarray, np.ndarray]:
    """Extrai coordenadas esparsas (ys, xs) dos hot pixels recortadas das bordas."""
    if hot_defect is None or hot_defect.size <= 3:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)
    b, g, r = cv2.split(hot_defect)
    max_diff = cv2.max(cv2.max(b, g), r)
    ys, xs = np.where(max_diff > 0)
    if len(ys) == 0:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)
    h, w = max_diff.shape
    return np.clip(ys, 1, h - 2).astype(np.int32), np.clip(xs, 1, w - 2).astype(np.int32)


def remove_hot_pixels(
    img: np.ndarray,
    hot_coords: Tuple[np.ndarray, np.ndarray],
    hot_defect: Optional[np.ndarray] = None
) -> np.ndarray:
    """
    Substitui hot pixels estacionários pela mediana 3x3 local calculada apenas
    nas coordenadas esparsas defeituosas (>100x mais rápido que full-frame medianBlur).
    """
    ys_c, xs_c = hot_coords
    if len(ys_c) == 0:
        return img

    if len(ys_c) < 50000:
        cleaned = img.copy()
        neigh = np.stack([
            cleaned[ys_c - 1, xs_c - 1], cleaned[ys_c - 1, xs_c], cleaned[ys_c - 1, xs_c + 1],
            cleaned[ys_c,     xs_c - 1], cleaned[ys_c,     xs_c], cleaned[ys_c,     xs_c + 1],
            cleaned[ys_c + 1, xs_c - 1], cleaned[ys_c + 1, xs_c], cleaned[ys_c + 1, xs_c + 1],
        ], axis=0)
        cleaned[ys_c, xs_c] = np.partition(neigh, 4, axis=0)[4]
        return cleaned

    if hot_defect is not None and hot_defect.shape == img.shape:
        return cv2.subtract(img, hot_defect)
    return img


def _prepare_frame_features(
    raw_bgr: np.ndarray,
    hot_coords: Tuple[np.ndarray, np.ndarray],
    hot_defect: Optional[np.ndarray] = None
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Aplica correção esparsa de hot pixels e desacopla canais:
    - Y (luminância, resolução total 1-canal)
    - Cr_half, Cb_half (crominância reduzida 2x via INTER_AREA)
    """
    cleaned = remove_hot_pixels(raw_bgr, hot_coords, hot_defect)
    ycrcb = cv2.cvtColor(cleaned, cv2.COLOR_BGR2YCrCb)
    y, cr, cb = cv2.split(ycrcb)
    h, w = y.shape
    cr_s = cv2.resize(cr, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    cb_s = cv2.resize(cb, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    return y, cr_s, cb_s


_tls = threading.local()


def _get_cpu_scratch(h: int, w: int):
    """Retorna buffers thread-local pré-alocados para reutilização zero-alocação (dst=...)."""
    if not hasattr(_tls, "acc16") or _tls.acc16.shape != (h, w):
        _tls.acc16 = np.empty((h, w), dtype=np.uint16)
        _tls.diff = np.empty((h, w), dtype=np.uint8)
        _tls.mapped = np.empty((h, w), dtype=np.uint8)
        _tls.y_out = np.empty((h, w), dtype=np.uint8)
        _tls.cr_acc = np.empty((h // 2, w // 2), dtype=np.uint16)
        _tls.cb_acc = np.empty((h // 2, w // 2), dtype=np.uint16)
        _tls.cr_u8 = np.empty((h // 2, w // 2), dtype=np.uint8)
        _tls.cb_u8 = np.empty((h // 2, w // 2), dtype=np.uint8)
        _tls.cr_full = np.empty((h, w), dtype=np.uint8)
        _tls.cb_full = np.empty((h, w), dtype=np.uint8)
        _tls.ycrcb = np.empty((h, w, 3), dtype=np.uint8)
        _tls.bgr = np.empty((h, w, 3), dtype=np.uint8)
    return _tls


class _GpuOpenCLScratch:
    """Gerencia buffers cv2.UMat na VRAM da GPU (ex: NVIDIA GeForce MX110) com cache de janela deslizante."""

    def __init__(self, h: int, w: int):
        self.h = h
        self.w = w
        self.u_acc16 = cv2.UMat(h, w, cv2.CV_16UC1)
        self.u_diff = cv2.UMat(h, w, cv2.CV_8UC1)
        self.u_mapped = cv2.UMat(h, w, cv2.CV_8UC1)
        self.u_y_out = cv2.UMat(h, w, cv2.CV_8UC1)
        self.u_cr_acc = cv2.UMat(h // 2, w // 2, cv2.CV_16UC1)
        self.u_cb_acc = cv2.UMat(h // 2, w // 2, cv2.CV_16UC1)
        self.u_cr_u8 = cv2.UMat(h // 2, w // 2, cv2.CV_8UC1)
        self.u_cb_u8 = cv2.UMat(h // 2, w // 2, cv2.CV_8UC1)
        self.u_cr_full = cv2.UMat(h, w, cv2.CV_8UC1)
        self.u_cb_full = cv2.UMat(h, w, cv2.CV_8UC1)
        self.u_ycrcb = cv2.UMat(h, w, cv2.CV_8UC3)
        self.u_bgr = cv2.UMat(h, w, cv2.CV_8UC3)
        self.lut_cache: Dict[Tuple[float, int, int], cv2.UMat] = {}
        self.feat_cache: Dict[int, Tuple[cv2.UMat, cv2.UMat, cv2.UMat]] = {}

    def get_gpu_lut(self, sigma_range: float, window_size: int, scale: int = 32) -> cv2.UMat:
        key = (round(sigma_range, 2), window_size, scale)
        if key not in self.lut_cache:
            self.lut_cache[key] = cv2.UMat(build_q5_shrinkage_lut(sigma_range, window_size, scale))
        return self.lut_cache[key]

    def get_gpu_feat(self, idx: int, cpu_feat: Tuple[np.ndarray, np.ndarray, np.ndarray]) -> Tuple[cv2.UMat, cv2.UMat, cv2.UMat]:
        if idx not in self.feat_cache:
            y, cr, cb = cpu_feat
            self.feat_cache[idx] = (cv2.UMat(y), cv2.UMat(cr), cv2.UMat(cb))
            if len(self.feat_cache) > 20:
                oldest = min(self.feat_cache.keys())
                del self.feat_cache[oldest]
        return self.feat_cache[idx]


def denoise_frame_temporal_cpu(
    center_idx: int,
    window_feats: List[Tuple[np.ndarray, np.ndarray, np.ndarray]],
    sigma_range: float = 4.5,
    scale: int = 32,
    chroma_denoise: bool = True,
    lut_q5: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Filtragem bilateral temporal desacoplada (Y 1-canal full-res + Cr/Cb half-res) em CPU.
    Usa acumulador uint16 em ponto fixo Q5 (scale=32) imune a saturação/underflow.
    """
    n = len(window_feats)
    ref_y, ref_cr, ref_cb = window_feats[center_idx]
    h, w = ref_y.shape
    s = _get_cpu_scratch(h, w)

    lut = build_q5_shrinkage_lut(sigma_range, n, scale) if lut_q5 is None else lut_q5

    cv2.multiply(ref_y, scale, dst=s.acc16, dtype=cv2.CV_16U)
    s.cr_acc.fill(0)
    s.cb_acc.fill(0)
    cv2.add(s.cr_acc, ref_cr, dst=s.cr_acc, dtype=cv2.CV_16U)
    cv2.add(s.cb_acc, ref_cb, dst=s.cb_acc, dtype=cv2.CV_16U)

    for i, (yi, cri, cbi) in enumerate(window_feats):
        if i == center_idx:
            continue
        cv2.addWeighted(yi, 0.5, ref_y, -0.5, 128.0, dst=s.diff)
        cv2.LUT(s.diff, lut, dst=s.mapped)
        cv2.add(s.acc16, s.mapped, dst=s.acc16, dtype=cv2.CV_16U)
        cv2.add(s.cr_acc, cri, dst=s.cr_acc, dtype=cv2.CV_16U)
        cv2.add(s.cb_acc, cbi, dst=s.cb_acc, dtype=cv2.CV_16U)

    if n > 1:
        cv2.subtract(s.acc16, (n - 1) * 128, dst=s.acc16, dtype=cv2.CV_16U)
    cv2.divide(s.acc16, scale, dst=s.y_out, dtype=cv2.CV_8U)

    cv2.divide(s.cr_acc, n, dst=s.cr_u8, dtype=cv2.CV_8U)
    cv2.divide(s.cb_acc, n, dst=s.cb_u8, dtype=cv2.CV_8U)
    if chroma_denoise:
        cv2.GaussianBlur(s.cr_u8, (3, 3), 0, dst=s.cr_u8)
        cv2.GaussianBlur(s.cb_u8, (3, 3), 0, dst=s.cb_u8)

    cv2.resize(s.cr_u8, (w, h), dst=s.cr_full, interpolation=cv2.INTER_LINEAR)
    cv2.resize(s.cb_u8, (w, h), dst=s.cb_full, interpolation=cv2.INTER_LINEAR)
    cv2.merge([s.y_out, s.cr_full, s.cb_full], dst=s.ycrcb)
    cv2.cvtColor(s.ycrcb, cv2.COLOR_YCrCb2BGR, dst=s.bgr)
    return s.bgr.copy()


def denoise_frame_temporal_gpu(
    gpu_s: _GpuOpenCLScratch,
    window_indices: List[int],
    window_feats: List[Tuple[np.ndarray, np.ndarray, np.ndarray]],
    center_idx: int,
    sigma_range: float = 4.5,
    scale: int = 32,
    chroma_denoise: bool = True,
) -> np.ndarray:
    """
    Filtragem bilateral temporal acelerada via OpenCL cv2.UMat na GPU (NVIDIA GeForce MX110)
    com acumulador uint16 em ponto fixo Q5 (scale=32) imune a saturação/underflow.
    """
    n = len(window_feats)
    g_feats = [gpu_s.get_gpu_feat(idx, f) for idx, f in zip(window_indices, window_feats)]
    ref_y, ref_cr, ref_cb = g_feats[center_idx]
    h, w = window_feats[center_idx][0].shape

    u_lut = gpu_s.get_gpu_lut(sigma_range, n, scale)
    cv2.multiply(ref_y, scale, dst=gpu_s.u_acc16, dtype=cv2.CV_16U)
    cv2.add(ref_cr, 0, dst=gpu_s.u_cr_acc, dtype=cv2.CV_16U)
    cv2.add(ref_cb, 0, dst=gpu_s.u_cb_acc, dtype=cv2.CV_16U)

    for i, (yi, cri, cbi) in enumerate(g_feats):
        if i == center_idx:
            continue
        cv2.addWeighted(yi, 0.5, ref_y, -0.5, 128.0, dst=gpu_s.u_diff)
        cv2.LUT(gpu_s.u_diff, u_lut, dst=gpu_s.u_mapped)
        cv2.add(gpu_s.u_acc16, gpu_s.u_mapped, dst=gpu_s.u_acc16, dtype=cv2.CV_16U)
        cv2.add(gpu_s.u_cr_acc, cri, dst=gpu_s.u_cr_acc, dtype=cv2.CV_16U)
        cv2.add(gpu_s.u_cb_acc, cbi, dst=gpu_s.u_cb_acc, dtype=cv2.CV_16U)

    if n > 1:
        cv2.subtract(gpu_s.u_acc16, (n - 1) * 128, dst=gpu_s.u_acc16, dtype=cv2.CV_16U)
    cv2.divide(gpu_s.u_acc16, scale, dst=gpu_s.u_y_out, dtype=cv2.CV_8U)

    cv2.divide(gpu_s.u_cr_acc, n, dst=gpu_s.u_cr_u8, dtype=cv2.CV_8U)
    cv2.divide(gpu_s.u_cb_acc, n, dst=gpu_s.u_cb_u8, dtype=cv2.CV_8U)
    if chroma_denoise:
        cv2.GaussianBlur(gpu_s.u_cr_u8, (3, 3), 0, dst=gpu_s.u_cr_u8)
        cv2.GaussianBlur(gpu_s.u_cb_u8, (3, 3), 0, dst=gpu_s.u_cb_u8)

    cv2.resize(gpu_s.u_cr_u8, (w, h), dst=gpu_s.u_cr_full, interpolation=cv2.INTER_LINEAR)
    cv2.resize(gpu_s.u_cb_u8, (w, h), dst=gpu_s.u_cb_full, interpolation=cv2.INTER_LINEAR)
    cv2.merge([gpu_s.u_y_out, gpu_s.u_cr_full, gpu_s.u_cb_full], dst=gpu_s.u_ycrcb)
    cv2.cvtColor(gpu_s.u_ycrcb, cv2.COLOR_YCrCb2BGR, dst=gpu_s.u_bgr)
    return gpu_s.u_bgr.get()


def denoise_frame_temporal(
    center_idx: int,
    cleaned_frames: List[np.ndarray],
    gray_frames: Optional[List[np.ndarray]] = None,
    guides: Optional[List[np.ndarray]] = None,
    lut_u8: Optional[np.ndarray] = None,
    scale: int = 32,
    chroma_denoise: bool = True,
    sigma_range: float = 4.5,
) -> np.ndarray:
    """Wrapper de alto nível para denoise temporal de um frame (aceita lista BGR ou tuplas YCrCb)."""
    n = len(cleaned_frames)
    if n <= 1:
        return cleaned_frames[0].copy()

    if isinstance(cleaned_frames[0], tuple):
        return denoise_frame_temporal_cpu(
            center_idx=center_idx,
            window_feats=cleaned_frames,
            sigma_range=sigma_range,
            scale=scale,
            chroma_denoise=chroma_denoise,
        )

    feats = []
    for f in cleaned_frames:
        ycrcb = cv2.cvtColor(f, cv2.COLOR_BGR2YCrCb)
        y, cr, cb = cv2.split(ycrcb)
        h, w = y.shape
        cr_s = cv2.resize(cr, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        cb_s = cv2.resize(cb, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        feats.append((y, cr_s, cb_s))

    return denoise_frame_temporal_cpu(
        center_idx=center_idx,
        window_feats=feats,
        sigma_range=sigma_range,
        scale=scale,
        chroma_denoise=chroma_denoise,
    )


def get_available_gpu_info() -> Dict[str, Any]:
    """Retorna disponibilidade e especificações da GPU OpenCL detectada."""
    has_ocl = bool(cv2.ocl.haveOpenCL())
    if not has_ocl:
        return {"available": False, "device_name": "None", "vendor": "None"}
    try:
        cv2.ocl.setUseOpenCL(True)
        dev = cv2.ocl.Device.getDefault()
        return {
            "available": True,
            "device_name": dev.name(),
            "vendor": dev.vendorName(),
            "compute_units": dev.maxComputeUnits(),
            "global_mem_mb": dev.globalMemSize() // (1024 * 1024) if hasattr(dev, "globalMemSize") else 0,
        }
    except Exception:
        return {"available": False, "device_name": "None", "vendor": "None"}


def process_sequence_denoise(
    photo_paths: List[Path],
    output_dir: Path,
    window_size: int = 7,
    sigma_range: float = 4.5,
    hot_pixel_threshold: int = 8,
    chroma_denoise: bool = True,
    jpeg_quality: int = 96,
    recalibrate_interval: int = 250,
    use_gpu: bool = True,
    num_workers: Optional[int] = None,
    progress_callback: Optional[Callable[[int, int, str, int], None]] = None
) -> Tuple[bool, Dict[str, Any]]:
    """
    Processa uma sequência de fotos de timelapse noturno usando pipeline paralelo híbrido:
    - Work-Stealing Híbrido Real em Lotes: GPU (NVIDIA MX110 OpenCL) + Pool Multi-Worker CPU SIMD.
    - Acumulador uint16 em ponto fixo Q5 (scale=32) imune a saturação/underflow.
    - Domínio YCrCb desacoplado (Y 1-canal full-res + Cr/Cb half-res).
    - Reparo esparso de hot pixels por coordenadas.
    - Preservação bit-perfect de metadados binários EXIF/GPS.
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

    cpu_cores = os.cpu_count() or 4
    workers = max(2, min(6, cpu_cores)) if num_workers is None else max(1, int(num_workers))
    cv2.setNumThreads(1)

    gpu_info = get_available_gpu_info()
    enable_gpu = bool(use_gpu and gpu_info.get("available", False))
    t0 = time.time()

    # Leitura inicial para calibração de hot pixels
    init_count = min(total, max(w_size, 9))
    init_raws: List[np.ndarray] = []
    init_app1s: Dict[int, bytes] = {}

    for i in range(init_count):
        im, app1 = read_image_bgr_and_app1(photo_paths[i])
        if im is not None:
            init_raws.append(im)
            init_app1s[i] = app1

    if not init_raws:
        return False, {"error": "Falha ao decodificar imagens iniciais da sequência."}

    hot_defect, hot_pixels_detected = compute_hot_pixel_map(init_raws, threshold=hot_pixel_threshold)
    hot_coords = extract_hot_pixel_coords(hot_defect)

    first_h, first_w = init_raws[0].shape[:2]
    gpu_s: Optional[_GpuOpenCLScratch] = None
    gpu_lock = threading.Lock()
    if enable_gpu:
        try:
            cv2.ocl.setUseOpenCL(True)
            gpu_s = _GpuOpenCLScratch(first_h, first_w)
        except Exception:
            gpu_s = None
            enable_gpu = False

    # Cache deslizante: idx -> (app1_bytes, (y, cr_s, cb_s))
    feat_cache: Dict[int, Tuple[bytes, Tuple[np.ndarray, np.ndarray, np.ndarray]]] = {}
    raw_cache: Dict[int, np.ndarray] = {}

    for i in range(len(init_raws)):
        raw = init_raws[i]
        app1 = init_app1s.get(i, b"")
        feat = _prepare_frame_features(raw, hot_coords, hot_defect)
        feat_cache[i] = (app1, feat)
        raw_cache[i] = raw

    def load_and_prep_one(idx: int) -> Tuple[int, Optional[bytes], Optional[Tuple[np.ndarray, np.ndarray, np.ndarray]], Optional[np.ndarray]]:
        raw, app1 = read_image_bgr_and_app1(photo_paths[idx])
        if raw is None:
            return idx, None, None, None
        feat = _prepare_frame_features(raw, hot_coords, hot_defect)
        return idx, app1, feat, raw

    def denoise_and_write_worker(
        center_idx: int,
        win_indices: List[int],
        window_feats: List[Tuple[np.ndarray, np.ndarray, np.ndarray]],
        rel_center: int,
        app1_bytes: bytes,
    ) -> Tuple[int, bool, str]:
        used_device = "cpu"
        denoised_bgr: Optional[np.ndarray] = None

        if enable_gpu and gpu_s is not None and gpu_lock.acquire(blocking=False):
            try:
                denoised_bgr = denoise_frame_temporal_gpu(
                    gpu_s=gpu_s,
                    window_indices=win_indices,
                    window_feats=window_feats,
                    center_idx=rel_center,
                    sigma_range=sigma_range,
                    scale=scale,
                    chroma_denoise=chroma_denoise,
                )
                used_device = "gpu"
            except Exception:
                denoised_bgr = None
            finally:
                gpu_lock.release()

        if denoised_bgr is None:
            denoised_bgr = denoise_frame_temporal_cpu(
                center_idx=rel_center,
                window_feats=window_feats,
                sigma_range=sigma_range,
                scale=scale,
                chroma_denoise=chroma_denoise,
            )
            used_device = "cpu"

        out_path = output_dir / photo_paths[center_idx].name
        ok_write = write_image_bgr_with_app1(out_path, denoised_bgr, app1_bytes, jpeg_quality)
        return center_idx, ok_write, used_device

    gpu_frame_count = 0
    cpu_frame_count = 0
    processed_count = 0
    errors = 0
    batch_size = max(workers * 2, 12)

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        for batch_start in range(0, total, batch_size):
            batch_end = min(total - 1, batch_start + batch_size - 1)
            win_start = max(0, batch_start - radius)
            win_end = min(total - 1, batch_end + radius)

            # 1. Carregar e preparar em paralelo todos os frames novos necessários para este lote
            missing_indices = [i for i in range(win_start, win_end + 1) if i not in feat_cache]
            if missing_indices:
                for idx, app1, feat, raw in pool.map(load_and_prep_one, missing_indices):
                    if feat is not None and app1 is not None and raw is not None:
                        feat_cache[idx] = (app1, feat)
                        raw_cache[idx] = raw
                    else:
                        errors += 1

            # 2. Recalibração periódica de hot pixels
            if (
                recalibrate_interval > 0
                and batch_start > 0
                and (batch_start // recalibrate_interval) > ((batch_start - batch_size) // recalibrate_interval)
            ):
                sample_raws = [raw_cache[i] for i in sorted(raw_cache.keys())[:w_size]]
                if len(sample_raws) >= 5:
                    new_defect, new_hp_count = compute_hot_pixel_map(sample_raws, threshold=hot_pixel_threshold)
                    hot_defect = new_defect
                    hot_coords = extract_hot_pixel_coords(hot_defect)
                    hot_pixels_detected = max(hot_pixels_detected, new_hp_count)

            # 3. Submeter todos os frames do lote para execução paralela real (Work-Stealing GPU MX110 + CPU)
            batch_futures: List[Future] = []
            for center_idx in range(batch_start, batch_end + 1):
                if center_idx not in feat_cache:
                    continue
                s_i = max(0, center_idx - radius)
                e_i = min(total - 1, center_idx + radius)
                win_indices = [i for i in range(s_i, e_i + 1) if i in feat_cache]
                rel_center = win_indices.index(center_idx)
                window_feats = [feat_cache[i][1] for i in win_indices]
                app1_bytes = feat_cache[center_idx][0]

                batch_futures.append(
                    pool.submit(
                        denoise_and_write_worker,
                        center_idx,
                        win_indices,
                        window_feats,
                        rel_center,
                        app1_bytes,
                    )
                )

            for fut in batch_futures:
                c_idx, ok_w, dev_used = fut.result()
                if not ok_w:
                    errors += 1
                else:
                    if dev_used == "gpu":
                        gpu_frame_count += 1
                    else:
                        cpu_frame_count += 1
                    processed_count += 1
                    if progress_callback:
                        progress_callback(processed_count, total, photo_paths[c_idx].name, hot_pixels_detected)

            # 4. Descartar frames antigos que não serão mais usados pelos próximos lotes
            evict_before = max(0, (batch_end + 1) - radius - 1)
            for old_k in [k for k in list(feat_cache.keys()) if k < evict_before]:
                del feat_cache[old_k]
            for old_k in [k for k in list(raw_cache.keys()) if k < evict_before]:
                del raw_cache[old_k]

    finally:
        pool.shutdown(wait=True)

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
        "use_gpu": enable_gpu,
        "gpu_device": gpu_info.get("device_name") if enable_gpu else "None",
        "gpu_frames": gpu_frame_count,
        "cpu_frames": cpu_frame_count,
        "num_workers": workers,
        "elapsed_seconds": elapsed,
        "avg_fps": round(processed_count / max(0.001, elapsed), 2),
        "output_dir": str(output_dir.resolve()),
    }
    return (errors == 0 and processed_count == total), stats
