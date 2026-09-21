import subprocess
from typing import Tuple, List

def detect_ffmpeg_encoder(preset: str = "ultrafast", crf: int = 15, force_cpu: bool = False) -> Tuple[str, List[str]]:
    """
    Detecta automaticamente aceleração por GPU (NVIDIA NVENC, Intel QSV, AMD AMF)
    ou faz fallback transparente para libx264 (CPU).
    Retorna (encoder_name, encoder_ffmpeg_args).
    """
    if force_cpu:
        cpu_args = ["-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", str(crf)]
        return "libx264 (CPU)", cpu_args

    encoders_to_test = [
        ("h264_nvenc (NVIDIA)", ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf), "-rc", "vbr"]),
        ("h264_qsv (Intel Quick Sync)", ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", str(crf)]),
        ("h264_amf (AMD)", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cbr"])
    ]
    
    for label, args in encoders_to_test:
        test_cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=1",
            *args, "-f", "null", "-"
        ]
        try:
            res = subprocess.run(test_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
            if res.returncode == 0:
                return label, args
        except Exception:
            pass
            
    # Fallback para CPU libx264
    cpu_args = ["-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", str(crf)]
    return "libx264 (CPU)", cpu_args
