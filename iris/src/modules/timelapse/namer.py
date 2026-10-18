import re
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple

def sanitize_name_token(text: str) -> str:
    """Substitui caracteres especiais por hífens e limpa extremidades."""
    if not text:
        return ""
    cleaned = re.sub(r'[^A-Za-z0-9]+', '-', str(text)).strip('-')
    return cleaned

def generate_timelapse_video_name(
    first_dt: datetime,
    last_dt: datetime,
    camera_model: str,
    orig_w: int,
    orig_h: int,
    total_photos: int,
    fps: int = 60,
    fpi: int = 1,
    target_height: int = 2160,
    crop_mode: str = "center",
    is_test: bool = False,
    is_long_exposure: bool = False
) -> str:
    """
    Gera o nome dinâmico oficial do vídeo timelapse.
    Exemplo: 2016-05-14_22h15m-22h28m_Canon-PowerShot-SX50-HS_4000x2248_4K_center_60fps_1fpi_97x_00m08s_timelapse.mp4
    """
    first_date_str = first_dt.strftime('%Y-%m-%d')
    last_date_str = last_dt.strftime('%Y-%m-%d')
    first_time_str = first_dt.strftime('%Hh%Mm')
    last_time_str = last_dt.strftime('%Hh%Mm')

    if first_date_str == last_date_str:
        range_str = f"{first_date_str}_{first_time_str}-{last_time_str}"
    else:
        range_str = f"{first_date_str}_{first_time_str}-to-{last_date_str}_{last_time_str}"

    cam_str = sanitize_name_token(camera_model) or "Camera"
    dim_str = f"{orig_w}x{orig_h}" if orig_w and orig_h else "AutoRes"
    res_str = "4K" if target_height >= 2160 else ("1080p" if target_height == 1080 else f"{target_height}p")
    crop_str = sanitize_name_token(crop_mode).lower() if crop_mode else "center"
    if not crop_str:
        crop_str = "center"

    total_frames = max(1, total_photos * fpi)
    total_seconds = total_frames / fps if fps > 0 else 0
    m, s = divmod(int(total_seconds), 60)
    h, m = divmod(m, 60)
    duration_str = f"{h:02d}h{m:02d}m{s:02d}s" if h > 0 else f"{m:02d}m{s:02d}s"

    real_world_seconds = max(1.0, (last_dt - first_dt).total_seconds())
    if total_seconds > 0:
        speedup = max(1, int(round(real_world_seconds / total_seconds)))
        speedup_str = f"{speedup}x"
    else:
        speedup_str = "1x"

    if is_long_exposure:
        suffix = "timelapse_longa_exposicao_teste.mp4" if is_test else "timelapse_longa_exposicao.mp4"
    else:
        suffix = "timelapse_teste.mp4" if is_test else "timelapse.mp4"
    return f"{range_str}_{cam_str}_{dim_str}_{res_str}_{crop_str}_{fps}fps_{fpi}fpi_{speedup_str}_{duration_str}_{suffix}"

def resolve_produced_output_path(
    dest_root: Path,
    first_dt: datetime,
    video_name: str
) -> Path:
    """
    Resolve o caminho físico definitivo na nova categoria 6_Produzidos:
    dest_root / 6_Produzidos / YYYY / MM / DD / <video_name>.mp4
    """
    y = first_dt.strftime('%Y')
    m = first_dt.strftime('%m')
    d = first_dt.strftime('%d')
    output_dir = dest_root / "6_Produzidos" / y / m / d
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / video_name
