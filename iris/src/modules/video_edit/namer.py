import re
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Union

from src.core.geo import format_gps_token

def sanitize_name_token(text: str) -> str:
    """
    Substitui caracteres especiais, acentos, espaços e pontos por hífens.
    Garante que não haja pontos no meio de tokens de arquivo.
    """
    if not text:
        return ""
    normalized = unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8')
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '-', normalized).strip('-')
    cleaned = cleaned.replace('.', '-')
    cleaned = re.sub(r'-+', '-', cleaned)
    return cleaned

def format_number_no_dot(val: Any, precision: int = 1) -> str:
    """
    Converte um float/número para string substituindo o ponto decimal por traço '-'.
    Ex: 2.0 -> '2-0', 0.5 -> '0-5', 29.97 -> '29-97' (se precision >= 2).
    Se precision=0, retorna inteiro arredondado (ex: '30').
    """
    try:
        f_val = float(val)
    except (ValueError, TypeError):
        return str(val).replace(".", "-")

    if precision == 0:
        return str(int(round(f_val)))
    formatted = f"{f_val:.{precision}f}"
    return formatted.replace(".", "-")

def generate_edited_video_name(
    first_dt: datetime,
    last_dt: Optional[datetime] = None,
    camera_model: str = "Camera",
    species_pt: Optional[str] = None,
    orig_w: int = 1920,
    orig_h: int = 1080,
    target_w: int = 3840,
    target_h: int = 2160,
    orig_fps: float = 30.0,
    target_fps: int = 60,
    speed: float = 1.0,
    trim_sec: Optional[float] = None,
    audio_stripped: Optional[bool] = None,
    duration_sec: Optional[float] = None,
    clip_count: int = 1,
    trim_seconds: Optional[float] = None,
    has_audio: Optional[bool] = None,
    final_duration_s: Optional[float] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    gps_token: Optional[str] = None
) -> str:
    """
    Gera o nome oficial simplificado do vídeo editado em 7_Video_Editado_4K:
    {date_time}_{especie}_{camera}_{clip_count}_{resolucao}_{fps}_{velocidade}_{trim}_{audio}_{duracao}_{gps}.mp4

    Exemplo com ave e GPS:
    2026-10-23_14-30_Bem-te-vi_Canon-SX60_3clipes_1920x1080-to-3840x2160_fps-30-to-60_1-0x_trim2-0s_audio_00m45s_S20-4569_W45-4383.mp4
    """
    # Resolução de argumentos com aliases
    resolved_trim = trim_seconds if trim_seconds is not None else (trim_sec if trim_sec is not None else 2.0)
    if audio_stripped is not None:
        resolved_mute = audio_stripped
    elif has_audio is not None:
        resolved_mute = not has_audio
    else:
        resolved_mute = False
    resolved_dur = final_duration_s if final_duration_s is not None else (duration_sec if duration_sec is not None else 0.0)

    # 1. Data e Horário inicial no formato YYYY-MM-DD_HH-MM
    date_time_str = first_dt.strftime('%Y-%m-%d_%H-%M')

    # 2. Espécie da ave em português (se informada)
    species_token = sanitize_name_token(species_pt) if species_pt else ""

    # 3. Câmera
    cam_str = sanitize_name_token(camera_model) or "Camera"

    # 4. Quantidade de clipes
    clipe_str = f"{clip_count}clipe" if clip_count == 1 else f"{clip_count}clipes"

    # 5. Resoluções original e final simplificadas
    w_orig = orig_w or 1920
    h_orig = orig_h or 1080
    w_target = target_w or 3840
    h_target = target_h or 2160
    res_str = f"{w_orig}x{h_orig}-to-{w_target}x{h_target}"

    # 6. FPS original e final simplificados
    if orig_fps > 0:
        orig_fps_str = format_number_no_dot(orig_fps, precision=2 if orig_fps != round(orig_fps) else 0)
    else:
        orig_fps_str = "30"
    fps_str = f"fps-{orig_fps_str}-to-{target_fps}"

    # 7. Velocidade simplificada (sem a palavra 'speed')
    speed_num_str = format_number_no_dot(speed, precision=1 if speed != int(speed) else 1)
    speed_str = f"{speed_num_str}x"

    # 8. Trimming (sem pontos)
    trim_num_str = format_number_no_dot(resolved_trim, precision=1 if resolved_trim != int(resolved_trim) else (1 if resolved_trim > 0 else 0))
    trim_str = f"trim{trim_num_str}s"

    # 9. Estado do áudio
    audio_str = "mute" if resolved_mute else "audio"

    # 10. Duração final resultante
    total_seconds = max(0.0, resolved_dur)
    m, s = divmod(int(round(total_seconds)), 60)
    h, m = divmod(m, 60)
    duration_str = f"{h:02d}h{m:02d}m{s:02d}s" if h > 0 else f"{m:02d}m{s:02d}s"

    # 11. Coordenadas GPS (formato S20-4569_W45-4383)
    gps_str = ""
    if lat is not None and lng is not None:
        try:
            gps_str = format_gps_token(float(lat), float(lng))
        except Exception:
            gps_str = ""
    elif gps_token:
        gps_str = sanitize_name_token(gps_token)

    # Montagem dos tokens em ordem estrita
    tokens = [date_time_str]
    if species_token:
        tokens.append(species_token)
    tokens.extend([
        cam_str,
        clipe_str,
        res_str,
        fps_str,
        speed_str,
        trim_str,
        audio_str,
        duration_str
    ])
    if gps_str:
        tokens.append(gps_str)

    base_name = "_".join(tokens)
    # Garante que não sobrou nenhum ponto no corpo antes da extensão
    base_name_clean = base_name.replace(".", "-")
    base_name_clean = re.sub(r"-+", "-", base_name_clean)

    return f"{base_name_clean}.mp4"

def resolve_edited_output_path(
    dest_root: Path,
    first_dt: datetime,
    video_name: str
) -> Path:
    """
    Resolve o caminho físico definitivo na raiz 7_Video_Editado_4K:
    dest_root / 7_Video_Editado_4K / YYYY / MM / DD / <video_name>.mp4
    """
    y = first_dt.strftime('%Y')
    m = first_dt.strftime('%m')
    d = first_dt.strftime('%d')
    output_dir = dest_root / "7_Video_Editado_4K" / y / m / d
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / video_name
