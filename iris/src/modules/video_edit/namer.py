import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Union

def sanitize_name_token(text: str) -> str:
    """
    Substitui caracteres especiais, espaços e pontos por hífens.
    Garante que não haja pontos no meio de tokens de arquivo.
    """
    if not text:
        return ""
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '-', str(text)).strip('-')
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
    final_duration_s: Optional[float] = None
) -> str:
    """
    Gera o nome oficial exaustivo do vídeo editado em 7_Video_Editado_4K.
    REGRA CRÍTICA: Não contém nenhum ponto '.' no corpo do nome, utilizando '-' em substituição,
    reservando o ponto exclusivamente para a extensão (.mp4).

    Exemplo gerado:
    2026-08-17_14h30m_Canon-SX60_1clipe_orig-1920x1080_to_4K-3840x2160_orig30fps_to_60fps_speed2-0x_trim2-0s_mute_00m13s_video_editado.mp4
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
    # 1. Intervalo de Datas/Horas
    first_date_str = first_dt.strftime('%Y-%m-%d')
    first_time_str = first_dt.strftime('%Hh%Mm')
    
    if last_dt and clip_count > 1:
        last_date_str = last_dt.strftime('%Y-%m-%d')
        last_time_str = last_dt.strftime('%Hh%Mm')
        if first_date_str == last_date_str:
            time_range = f"{first_date_str}_{first_time_str}-{last_time_str}"
        else:
            time_range = f"{first_date_str}_{first_time_str}-to-{last_date_str}_{last_time_str}"
    else:
        time_range = f"{first_date_str}_{first_time_str}"

    # 2. Câmera
    cam_str = sanitize_name_token(camera_model) or "Camera"

    # 3. Quantidade de clipes
    clipe_str = f"{clip_count}clipe" if clip_count == 1 else f"{clip_count}clipes"

    # 4. Resoluções original e final
    dim_orig = f"orig-{orig_w}x{orig_h}" if orig_w and orig_h else "orig-AutoRes"
    res_label = "4K" if target_h >= 2160 else f"{target_h}p"
    dim_target = f"{res_label}-{target_w}x{target_h}"
    res_str = f"{dim_orig}_to_{dim_target}"

    # 5. FPS original e final (sem pontos)
    if orig_fps > 0:
        orig_fps_str = f"orig{format_number_no_dot(orig_fps, precision=2 if orig_fps != round(orig_fps) else 0)}fps"
    else:
        orig_fps_str = "origAutoFPS"
    target_fps_str = f"to_{target_fps}fps"
    fps_full_str = f"{orig_fps_str}_{target_fps_str}"

    # 6. Velocidade (sem pontos)
    speed_num_str = format_number_no_dot(speed, precision=1 if speed != int(speed) else 1)
    speed_str = f"speed{speed_num_str}x"

    # 7. Trimming (sem pontos)
    trim_num_str = format_number_no_dot(resolved_trim, precision=1 if resolved_trim != int(resolved_trim) else (1 if resolved_trim > 0 else 0))
    trim_str = f"trim{trim_num_str}s"

    # 8. Estado do áudio
    audio_str = "mute" if resolved_mute else "audio"

    # 9. Duração final resultante
    total_seconds = max(0.0, resolved_dur)
    m, s = divmod(int(round(total_seconds)), 60)
    h, m = divmod(m, 60)
    duration_str = f"{h:02d}h{m:02d}m{s:02d}s" if h > 0 else f"{m:02d}m{s:02d}s"

    # 10. Sufixo
    suffix = "video_editado.mp4"

    # Montagem e validação final anti-ponto
    base_name = f"{time_range}_{cam_str}_{clipe_str}_{res_str}_{fps_full_str}_{speed_str}_{trim_str}_{audio_str}_{duration_str}_{suffix[:-4]}"
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
