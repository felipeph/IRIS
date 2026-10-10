import subprocess
from typing import Tuple, List, Optional
from src.core.logger import logger

_cached_backend: Optional[str] = None

def clear_encoder_cache() -> None:
    """Limpa o cache de detecção de hardware para permitir nova sondagem."""
    global _cached_backend
    _cached_backend = None

def _get_encoder_config(backend: str, preset: str, crf: int) -> Tuple[str, List[str]]:
    """Gera o nome amigável e os argumentos do FFmpeg para um backend específico."""
    if backend == "nvenc":
        return "h264_nvenc (NVIDIA)", ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf), "-rc", "vbr"]
    elif backend == "qsv":
        return "h264_qsv (Intel Quick Sync)", ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", str(crf)]
    elif backend == "amf":
        return "h264_amf (AMD)", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cbr"]
    else:
        return "libx264 (CPU)", ["-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", str(crf)]

def detect_ffmpeg_encoder(
    preset: str = "ultrafast",
    crf: int = 15,
    force_cpu: bool = False,
    force_recheck: bool = False
) -> Tuple[str, List[str]]:
    """
    Detecta automaticamente aceleração por GPU (NVIDIA NVENC, Intel QSV, AMD AMF)
    ou faz fallback transparente para libx264 (CPU).
    Mantém cache de sessão para evitar chamadas redundantes e timeouts entre vídeos.
    Retorna (encoder_name, encoder_ffmpeg_args).
    """
    global _cached_backend

    if force_cpu:
        return _get_encoder_config("cpu", preset, crf)

    # 1. Se já detectado previamente e não forçado reteste, usa cache
    if not force_recheck and _cached_backend is not None:
        logger.debug(f"[encoder] Reutilizando backend em cache: '{_cached_backend}'")
        return _get_encoder_config(_cached_backend, preset, crf)

    # 2. Sondagem de hardware (timeout de 15s para suportar inicialização de drivers)
    encoders_to_test = [
        ("nvenc", "h264_nvenc (NVIDIA)", ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf), "-rc", "vbr"]),
        ("qsv", "h264_qsv (Intel Quick Sync)", ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", str(crf)]),
        ("amf", "h264_amf (AMD)", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cbr"])
    ]

    for key, label, args in encoders_to_test:
        test_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=1",
            *args, "-f", "null", "-"
        ]
        try:
            res = subprocess.run(
                test_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=15
            )
            if res.returncode == 0:
                _cached_backend = key
                logger.info(f"[encoder] Hardware acceleration detectada e selecionada: {label}")
                return label, args
            else:
                err_detail = (res.stderr or "").strip()
                logger.debug(f"[encoder] Teste de '{label}' retornou código {res.returncode}: {err_detail[:200]}")
        except subprocess.TimeoutExpired:
            logger.warning(f"[encoder] Timeout (15s) excedido ao testar '{label}'.")
        except Exception as e:
            logger.debug(f"[encoder] Erro ao testar '{label}': {e}")

    # Fallback para CPU libx264
    _cached_backend = "cpu"
    logger.warning("[encoder] Nenhuma aceleração de hardware disponível ou funcional. Utilizando fallback libx264 (CPU).")
    return _get_encoder_config("cpu", preset, crf)

