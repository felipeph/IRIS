"""Módulo de compilação de metadados e descrição rica para vídeos do YouTube no IRIS."""

import re
import math
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple


def format_duration_human(seconds: float) -> str:
    """Formata duração em segundos para texto legível em português."""
    if seconds <= 0:
        return "0 segundos"
    
    total_sec = int(round(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} hora" if hours == 1 else f"{hours} horas")
    if minutes > 0:
        parts.append(f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos")
    if secs > 0 or not parts:
        if not parts and seconds < 60 and seconds != round(seconds):
            return f"{seconds:.1f} segundos"
        parts.append(f"{secs} segundo" if secs == 1 else f"{secs} segundos")

    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} e {parts[1]}"
    else:
        return f"{parts[0]}, {parts[1]} e {parts[2]}"


def format_bytes_human(num_bytes: int) -> str:
    """Formata quantidade de bytes em representação legível (B, KB, MB, GB)."""
    if num_bytes <= 0:
        return "0 MB"
    if num_bytes >= 1024**3:
        return f"{num_bytes / (1024**3):.2f} GB"
    elif num_bytes >= 1024**2:
        return f"{num_bytes / (1024**2):.1f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


from src.core.metadata import parse_shutter_seconds

def _parse_shutter_value(val: str) -> Optional[float]:
    """Converte representações de obturador (ex: '1/1000s', '1-500s', '2s', '0.5s') em segundos (float)."""
    return parse_shutter_seconds(val)


def _parse_iso_value(val: str) -> Optional[int]:
    """Converte representações de ISO (ex: 'ISO100', 'ISO 400', '800') para int."""
    m = re.search(r'\d+', val)
    if m:
        try:
            return int(m.group(0))
        except ValueError:
            pass
    return None


def _parse_aperture_value(val: str) -> Optional[float]:
    """Converte representações de abertura (ex: 'f4.0', 'f/4', 'f5.6') para float."""
    clean = val.lower().replace("f", "").replace("/", "").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def summarize_exposure_param(values: List[str], param_type: str = "generic") -> str:
    """
    Resume uma lista de valores de exposição.
    Se for constante, retorna o valor único (ex: 'f/4.0', '1/125s', 'ISO 100').
    Se variar, calcula o intervalo min-max (ex: '1/1000s – 1/30s', 'ISO 100 – ISO 800').
    """
    valid = [v.strip() for v in values if v and v.strip() and v.strip().lower() != "auto"]
    if not valid:
        return "Automático / Variável"

    unique = sorted(list(set(valid)))
    if len(unique) == 1:
        u = unique[0]
        if param_type == "aperture":
            f_val = _parse_aperture_value(u)
            return f"f/{f_val:.1f}" if f_val is not None else (f"f/{u.lstrip('f').lstrip('/')}")
        elif param_type == "iso":
            iso_num = _parse_iso_value(u)
            return f"ISO {iso_num}" if iso_num is not None else f"ISO {u}"
        return u

    # Múltiplos valores
    if param_type == "iso":
        parsed = [(v, _parse_iso_value(v)) for v in valid]
        with_nums = [(raw, num) for raw, num in parsed if num is not None]
        if with_nums:
            min_raw = min(with_nums, key=lambda x: x[1])[1]
            max_raw = max(with_nums, key=lambda x: x[1])[1]
            if min_raw == max_raw:
                return f"ISO {min_raw}"
            return f"ISO {min_raw} – ISO {max_raw}"

    elif param_type == "aperture":
        parsed = [(v, _parse_aperture_value(v)) for v in valid]
        with_nums = [(raw, num) for raw, num in parsed if num is not None]
        if with_nums:
            min_val = min(with_nums, key=lambda x: x[1])[1]
            max_val = max(with_nums, key=lambda x: x[1])[1]
            if min_val == max_val:
                return f"f/{min_val:.1f}"
            return f"f/{min_val:.1f} – f/{max_val:.1f}"

    elif param_type == "shutter":
        parsed = [(v, _parse_shutter_value(v)) for v in valid]
        with_nums = [(raw, num) for raw, num in parsed if num is not None]
        if with_nums:
            min_item = min(with_nums, key=lambda x: x[1])
            max_item = max(with_nums, key=lambda x: x[1])
            if min_item[1] == max_item[1]:
                return min_item[0]
            # Normalizar para visualização limpa
            def _fmt_s(s_val: float) -> str:
                if s_val < 1.0 and s_val > 0:
                    den = int(round(1.0 / s_val))
                    return f"1/{den}s"
                elif s_val == round(s_val):
                    return f"{int(s_val)}s"
                else:
                    return f"{s_val:.1f}s"
            return f"{_fmt_s(min_item[1])} – {_fmt_s(max_item[1])}"

    return f"{unique[0]} – {unique[-1]}"


def calculate_aspect_ratio(width: Optional[int], height: Optional[int]) -> str:
    """Calcula a proporção da imagem (ex: 4:3, 16:9, 3:2)."""
    if not width or not height or width <= 0 or height <= 0:
        return ""
    g = math.gcd(width, height)
    rx = width // g
    ry = height // g

    # Normalizações para proporções fotográficas comuns
    ratio_val = width / height
    if abs(ratio_val - 4/3) < 0.05:
        return "4:3"
    elif abs(ratio_val - 16/9) < 0.05:
        return "16:9"
    elif abs(ratio_val - 3/2) < 0.05:
        return "3:2"
    elif abs(ratio_val - 1.0) < 0.02:
        return "1:1"
    elif abs(ratio_val - 16/10) < 0.05:
        return "16:10"
    elif abs(ratio_val - 5/4) < 0.05:
        return "5:4"

    return f"{rx}:{ry}"


def build_youtube_title(video_path: Path, record: Dict[str, Any]) -> str:
    """Gera título limpo e atrativo para o YouTube, limitado a 100 caracteres."""
    name = video_path.name
    parts = name.split('_')
    date_part = parts[0] if len(parts) > 0 else datetime.now().strftime('%Y-%m-%d')
    time_part = parts[1] if len(parts) > 1 else ""

    # Extrai modelo de câmera se presente
    meta = record.get("metadata_json") or {}
    camera = meta.get("camera_model") or record.get("camera_model")
    if not camera and len(parts) > 2 and not parts[2].startswith("timelapse"):
        candidate = parts[2]
        if not re.search(r'\d+x\d+', candidate) and not candidate.endswith("fps"):
            camera = candidate

    if "-" in time_part:
        t1, t2 = time_part.split("-", 1)
        t1_clean = t1.replace('h', ':').replace('m', '')
        t2_clean = t2.replace('h', ':').replace('m', '')
        time_str = f"({t1_clean} - {t2_clean})"
    else:
        time_str = ""

    title_elements = [date_part]
    if time_str:
        title_elements.append(time_str)
    title_elements.append("- Timelapse 4K UHD")

    title = " ".join(title_elements)
    if len(title) > 100:
        title = title[:97] + "..."
    return title


def build_youtube_tags(record: Dict[str, Any], extra_tags: Optional[List[str]] = None) -> List[str]:
    """Gera lista de tags relevantes e otimizadas para busca no YouTube."""
    tags = ["timelapse", "4k", "uhd", "60fps", "natureza", "fotografia", "iris"]
    
    meta = record.get("metadata_json") or {}
    cam_model = meta.get("camera_model") or ""
    cam_make = meta.get("camera_make") or ""
    if cam_make and cam_make.lower() not in tags:
        tags.append(cam_make.lower())
    if cam_model and cam_model.lower() not in tags:
        tags.append(cam_model.lower().replace(" ", ""))

    date_str = meta.get("date_str") or ""
    if date_str and date_str not in tags:
        tags.append(date_str)

    if extra_tags:
        for t in extra_tags:
            t_clean = t.strip().lower()
            if t_clean and t_clean not in tags:
                tags.append(t_clean)

    return tags[:25]


def build_rich_youtube_description(record: Dict[str, Any], project_name: str = "") -> str:
    """
    Compila uma descrição técnica completa e rica para o YouTube com:
    - Gancho inicial resumido
    - ⏱️ TEMPO E CAPTURA (início, fim, duração real, fotos, intervalo, ritmo de quadros)
    - 📷 EQUIPAMENTO E ARQUIVOS ORIGINAIS (câmera, lente, abertura, obturador, ISO, resolução, armazenamento)
    - 🎞️ PROCESSAMENTO E ENGENHARIA DE VÍDEO (IRIS) (4K UHD 60fps, Lanczos, Deband 16-bit, encoder, compressão)
    - 📂 RASTREABILIDADE DO PROJETO (projeto, arquivo gerado, pasta de sequência)
    - Hashtags
    """
    meta: Dict[str, Any] = record.get("metadata_json") or {}

    # 1. Informações Básicas e Resumo
    fps = record.get("fps", 60)
    res = record.get("resolution", "3840x2160")
    photo_count = record.get("photo_count", 0)
    dur_sec = record.get("duration_seconds", 0.0)
    speedup = record.get("speedup_factor", 1)
    fpi = record.get("frames_per_image", meta.get("frames_per_image", 1))
    encoder = record.get("encoder", meta.get("encoder", "FFmpeg"))
    crop_mode = record.get("crop_mode", meta.get("crop_mode", "center")).capitalize()

    # Datas de captura
    first_dt_str = meta.get("first_dt_formatted")
    last_dt_str = meta.get("last_dt_formatted")
    date_part = meta.get("date_str")

    # Fallback se datas formatadas não estiverem em meta
    if not first_dt_str and meta.get("first_dt_iso"):
        try:
            dt1 = datetime.fromisoformat(meta["first_dt_iso"])
            first_dt_str = dt1.strftime("%d/%m/%Y às %H:%M:%S")
            date_part = dt1.strftime("%d/%m/%Y")
        except Exception:
            pass
    if not last_dt_str and meta.get("last_dt_iso"):
        try:
            dt2 = datetime.fromisoformat(meta["last_dt_iso"])
            last_dt_str = dt2.strftime("%d/%m/%Y às %H:%M:%S")
        except Exception:
            pass

    date_label = date_part or "Data não especificada"

    # Tempo real decorrido
    real_sec = meta.get("real_duration_seconds", 0.0)
    if real_sec <= 0 and dur_sec > 0 and speedup > 0:
        real_sec = dur_sec * speedup
    real_duration_human = format_duration_human(real_sec)

    # Intervalo entre fotos
    avg_interval_sec = meta.get("avg_interval_seconds", 0.0)
    if avg_interval_sec <= 0 and photo_count > 1 and real_sec > 0:
        avg_interval_sec = round(real_sec / (photo_count - 1), 1)

    interval_desc = f"{avg_interval_sec:.1f} segundos (Intervalômetro)" if avg_interval_sec > 0 else "N/A"

    # Ritmo visual
    effective_rate = round(fps / max(1, fpi), 1)
    pace_desc = f"{effective_rate:.0f} fotos/segundo (exposição de {fpi} quadro(s) por foto a {fps} FPS)"

    # 2. Equipamento e Arquivos Originais
    cam_make = meta.get("camera_make", "")
    cam_model = meta.get("camera_model", "")
    if cam_make and cam_model and not cam_model.startswith(cam_make):
        camera_name = f"{cam_make} {cam_model}".strip()
    else:
        camera_name = cam_model or cam_make or "Câmera Digital"

    orig_formats = meta.get("orig_formats", [])
    format_str = "/".join(orig_formats) if orig_formats else "JPG"

    orig_w = meta.get("orig_width", 0)
    orig_h = meta.get("orig_height", 0)
    orig_aspect = calculate_aspect_ratio(orig_w, orig_h)
    
    if orig_w > 0 and orig_h > 0:
        mp = (orig_w * orig_h) / 1_000_000
        res_orig_desc = f"{orig_w}x{orig_h} ({mp:.1f} MP)" + (f" • Proporção {orig_aspect}" if orig_aspect else "")
    else:
        res_orig_desc = "Resolução Nativa Original"

    # Exposição consolidada
    aperture_str = meta.get("aperture_summary") or summarize_exposure_param(meta.get("apertures", []), "aperture")
    shutter_str = meta.get("shutter_summary") or summarize_exposure_param(meta.get("shutters", []), "shutter")
    iso_str = meta.get("iso_summary") or summarize_exposure_param(meta.get("isos", []), "iso")
    focal_str = meta.get("focal_summary") or summarize_exposure_param(meta.get("focals", []), "generic")
    focal_equiv = meta.get("focal_equiv_summary") or ""
    if focal_equiv:
        focal_display = f"{focal_str} ({focal_equiv} equiv. 35mm)" if (focal_str and focal_str != focal_equiv) else f"{focal_equiv} equiv. 35mm"
    else:
        focal_display = focal_str or "Distância Focal Padrão"

    # Tamanho total original
    orig_bytes = meta.get("total_orig_size_bytes", 0)
    orig_size_desc = format_bytes_human(orig_bytes)
    if orig_bytes > 0 and photo_count > 0:
        avg_photo_bytes = orig_bytes // photo_count
        orig_storage_desc = f"{orig_size_desc} (média de {format_bytes_human(avg_photo_bytes)}/foto)"
    else:
        orig_storage_desc = orig_size_desc

    # 3. Processamento e Engenharia de Vídeo
    render_stats = meta.get("render_stats", {})
    render_sec = render_stats.get("render_time_seconds") or meta.get("render_time_seconds", 0.0)
    render_fps = render_stats.get("avg_fps") or meta.get("render_avg_fps", 0.0)

    render_perf_desc = ""
    if render_sec > 0:
        fps_info = f" (média de {render_fps:.1f} FPS de codificação)" if render_fps > 0 else ""
        render_perf_desc = f"\n• Tempo de Renderização: {format_duration_human(render_sec)}{fps_info}"

    # Compressão
    video_bytes = meta.get("video_size_bytes", 0)
    compression_line = ""
    if orig_bytes > 0 and video_bytes > 0:
        savings = (1.0 - (video_bytes / orig_bytes)) * 100.0
        compression_line = f"\n• Taxa de Compressão: {format_bytes_human(orig_bytes)} (Originais) ➔ {format_bytes_human(video_bytes)} (Vídeo Final) • Redução de {savings:.1f}%"
    elif video_bytes > 0:
        compression_line = f"\n• Tamanho do Arquivo: {format_bytes_human(video_bytes)}"

    render_stats = meta.get("render_stats") or {}
    deband_enabled = render_stats.get("deband_enabled", meta.get("deband_enabled", True))
    deband_grain = render_stats.get("deband_grain", meta.get("deband_grain", True))

    if deband_enabled and deband_grain:
        deband_desc = "Filtro Deband 16-bit com micro-grão temporal dither (calibrado para mitigar color banding na compressão VP09/AV01 do YouTube)"
    elif deband_enabled:
        deband_desc = "Filtro Deband 16-bit sem grão (suavização de faixas de cor)"
    else:
        deband_desc = "Desativado (Renderização Direta Lanczos)"

    is_direct_crop = meta.get("is_direct_crop", False)
    tl_render_profile = meta.get("render_profile")
    if crop_mode.lower() == "full":
        framing_desc = "Quadro Completo 100% com Bordas Laterais (Pillarbox 4K UHD Nativo) • Sem Cortes de Sensor"
    elif is_direct_crop:
        framing_desc = f"Corte Direto 1:1 Nativo 4K do Sensor (Alinhamento: {crop_mode}) • Sem Redimensionamento"
    elif tl_render_profile == "fast":
        framing_desc = f"Intel QSV VPP Escala HQ em Hardware (Alinhamento: {crop_mode})"
    elif tl_render_profile == "balanced":
        framing_desc = f"Escalonamento Bicúbico 4K com corte inteligente (Alinhamento: {crop_mode})"
    else:
        framing_desc = f"Lanczos 3 com corte inteligente (Alinhamento: {crop_mode})"

    # 4. Rastreabilidade
    proj = project_name or record.get("project_name") or "IRIS Project"
    out_video_name = Path(record.get("output_video_path", "video.mp4")).name
    seq_dir_name = record.get("sequence_dir", "")
    if seq_dir_name:
        seq_display = Path(seq_dir_name).as_posix()
        if "4_Timelapses_LongaExposicao" in seq_display:
            seq_display = "4_Timelapses_LongaExposicao" + seq_display.split("4_Timelapses_LongaExposicao", 1)[1]
        elif "4_Timelapses" in seq_display:
            seq_display = "4_Timelapses" + seq_display.split("4_Timelapses", 1)[1]
    else:
        seq_display = "Sequência IRIS"

    # Período de gravação
    if first_dt_str and last_dt_str:
        period_line = f"• Período de Gravação: {first_dt_str} até {last_dt_str}"
    elif first_dt_str:
        period_line = f"• Início da Gravação: {first_dt_str}"
    else:
        period_line = f"• Data de Captura: {date_label}"

    formatted_photo_count = f"{photo_count:,}".replace(",", ".")

    # Montagem da Descrição
    description = f"""Vídeo Timelapse renderizado em alta definição 4K UHD ({res}) a {fps} FPS.
Capturado em {date_label}, produzido e renderizado de forma automatizada pelo IRIS (Imaging Resources and Integration System).

⏱️ TEMPO E CAPTURA:
{period_line}
• Duração Real da Cena: {real_duration_human} ({int(round(real_sec))}s)
• Total de Disparos: {formatted_photo_count} fotos
• Intervalo Médio: {interval_desc}
• Duração do Vídeo: {dur_sec:.1f} segundos
• Fator de Aceleração: {speedup}x mais rápido que a vida real
• Ritmo Visual: {pace_desc}

📷 EQUIPAMENTO E ARQUIVOS ORIGINAIS:
• Câmera: {camera_name}
• Formato de Origem: {format_str}
• Resolução Original: {res_orig_desc}
• Distância Focal: {focal_display}
• Abertura: {aperture_str}
• Tempo de Exposição (Shutter): {shutter_str}
• Sensibilidade: {iso_str}
• Armazenamento Original: {orig_storage_desc}

🎞️ PROCESSAMENTO E ENGENHARIA DE VÍDEO (IRIS):
• Resolução Final: 4K UHD ({res}) • Proporção 16:9
• Taxa de Quadros: {fps:.1f} FPS
• Enquadramento: {framing_desc}
• Otimização para YouTube: {deband_desc}
• Encoder: {encoder} (Aceleração por Hardware)
• Perfil de Cor: BT.709 Standard Broadcast (HD/UHD){compression_line}{render_perf_desc}

📂 RASTREABILIDADE DO PROJETO:
• Sistema: IRIS Studio Engine
• Projeto: {proj}
• Arquivo Gerado: {out_video_name}
• Sequência: {seq_display}

#timelapse #4k #uhd #60fps #{cam_make.lower() or 'fotografia'} #iris #automacao
""".replace("\r\n", "\n")

    return description[:5000]


from datetime import datetime, timedelta


def build_edited_video_youtube_title(video_path: Path, record: Dict[str, Any]) -> str:
    """
    Gera título padronizado para o YouTube no formato oficial igual ao dos timelapses:
    Exemplos:
      - Com intervalo de horas: '2026-10-09 (16:22 - 18:35) - Vídeo 4K UHD'
      - Clipe único com duração > 1 min: '2026-10-09 (16:22 - 16:25) - Vídeo 4K UHD'
      - Clipe único curto (mesmo minuto): '2026-10-09 (16:22) - Vídeo 4K UHD'
    """
    meta = record.get("metadata_json") or {}
    name = video_path.name
    parts = name.split('_')

    date_part = ""
    time_str = ""

    # 1. Tentar extrair do nome do arquivo (ex: 2026-10-09_16h22m-18h35m_... ou 2026-10-09_16h22m_...)
    if len(parts) > 0 and re.match(r'^\d{4}-\d{2}-\d{2}$', parts[0]):
        date_part = parts[0]
    
    time_part = parts[1] if len(parts) > 1 else ""

    # Duração total para cálculo de término se necessário
    dur_sec = float(record.get("duration_seconds") or meta.get("final_duration_seconds") or meta.get("total_orig_duration_seconds") or 0.0)

    if "-" in time_part and not time_part.startswith("to-"):
        # Intervalo gravado no nome (ex: 16h22m-18h35m)
        t1, t2 = time_part.split("-", 1)
        t1_clean = t1.replace('h', ':').replace('m', '')
        t2_clean = t2.replace('h', ':').replace('m', '')
        if t1_clean and t2_clean and t1_clean != t2_clean:
            time_str = f"({t1_clean} - {t2_clean})"
        elif t1_clean:
            time_str = f"({t1_clean})"
    elif time_part and ("h" in time_part or "m" in time_part):
        # Tempo único no nome (ex: 14h30m)
        t_clean = time_part.replace('h', ':').replace('m', '')
        # Se dur_sec >= 60 e temos date_part, calcular horário de término
        if dur_sec >= 60.0 and date_part and re.match(r'^\d{1,2}:\d{2}$', t_clean):
            try:
                dt_start = datetime.strptime(f"{date_part} {t_clean}", "%Y-%m-%d %H:%M")
                dt_end = dt_start + timedelta(seconds=dur_sec)
                t_end = dt_end.strftime("%H:%M")
                if t_end != t_clean:
                    time_str = f"({t_clean} - {t_end})"
                else:
                    time_str = f"({t_clean})"
            except Exception:
                time_str = f"({t_clean})"
        elif t_clean:
            time_str = f"({t_clean})"

    # 2. Fallback caso date_part ou time_str não tenham sido resolvidos pelo nome
    if not date_part or not time_str:
        first_dt = None
        last_dt = None
        if meta.get("first_dt_iso"):
            try:
                first_dt = datetime.fromisoformat(meta["first_dt_iso"])
            except Exception:
                pass
        if meta.get("last_dt_iso"):
            try:
                last_dt = datetime.fromisoformat(meta["last_dt_iso"])
            except Exception:
                pass

        if not first_dt and meta.get("first_dt_formatted"):
            # Ex: "17/08/2026 às 14:30:22"
            try:
                f_parts = meta["first_dt_formatted"].split(" às ")
                dt_str = f"{f_parts[0]} {f_parts[1]}"
                first_dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M:%S")
            except Exception:
                pass

        if first_dt:
            if not date_part:
                date_part = first_dt.strftime("%Y-%m-%d")
            if not time_str:
                start_hm = first_dt.strftime("%H:%M")
                if last_dt and last_dt.strftime("%H:%M") != start_hm:
                    end_hm = last_dt.strftime("%H:%M")
                    time_str = f"({start_hm} - {end_hm})"
                elif dur_sec >= 60.0:
                    dt_end = first_dt + timedelta(seconds=dur_sec)
                    end_hm = dt_end.strftime("%H:%M")
                    if end_hm != start_hm:
                        time_str = f"({start_hm} - {end_hm})"
                    else:
                        time_str = f"({start_hm})"
                else:
                    time_str = f"({start_hm})"

    if not date_part:
        date_part = datetime.now().strftime("%Y-%m-%d")

    title_elements = [date_part]
    if time_str:
        title_elements.append(time_str)
    title_elements.append("- Vídeo 4K UHD")

    title = " ".join(title_elements)
    if len(title) > 100:
        title = title[:97] + "..."
    return title


def build_edited_video_youtube_metadata(
    video_path: Path,
    record: Dict[str, Any],
    yt_config: Dict[str, Any],
    project: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Compila os metadados oficiais e a ficha técnica completa para vídeos editados/upscalados no YouTube.
    """
    meta = record.get("metadata_json") or {}
    
    # 1. Título padronizado igual ao dos timelapses (YYYY-MM-DD (HH:MM - HH:MM) - Vídeo 4K UHD)
    title = build_edited_video_youtube_title(video_path, record)

    # Data de captura para a descrição técnica
    first_dt_str = meta.get("first_dt_formatted")
    dt_prefix = ""
    if first_dt_str:
        # Ex: "17/08/2026 às 14:30:22" -> "17/08/2026 14:30"
        parts = first_dt_str.split(" às ")
        if len(parts) == 2:
            time_part = ":".join(parts[1].split(":")[:2])
            dt_prefix = f"{parts[0]} {time_part}"
        else:
            dt_prefix = first_dt_str
    elif meta.get("date_str"):
        dt_prefix = meta.get("date_str")
    else:
        dt_prefix = datetime.now().strftime("%d/%m/%Y %H:%M")

    cam_make = meta.get("camera_make", "")
    cam_model = meta.get("camera_model", "")
    if cam_make and cam_model and not cam_model.startswith(cam_make):
        camera_name = f"{cam_make} {cam_model}".strip()
    else:
        camera_name = cam_model or cam_make or "Câmera"

    # 2. Informações Técnicas
    orig_w = meta.get("orig_width") or record.get("orig_resolution", "1920x1080").split("x")[0]
    orig_h = meta.get("orig_height") or record.get("orig_resolution", "1920x1080").split("x")[-1]
    target_res = record.get("target_resolution", "3840x2160")
    orig_fps = record.get("orig_fps") or meta.get("orig_fps", 30.0)
    target_fps = int(record.get("target_fps") or meta.get("target_fps", 60))
    speed = float(record.get("speed_factor") or meta.get("speed_factor", 1.0))
    clip_count = int(record.get("clip_count") or meta.get("clip_count", 1))
    trim_sec = float(record.get("trim_start_sec") or meta.get("trim_seconds", 0.0))
    audio_stripped = bool(record.get("audio_stripped") or meta.get("audio_stripped", False))
    dur_sec = float(record.get("duration_seconds") or meta.get("final_duration_seconds", 0.0))
    orig_dur = float(meta.get("total_orig_duration_seconds", dur_sec * speed))
    encoder = record.get("encoder") or meta.get("encoder", "FFmpeg")
    video_bytes = meta.get("video_size_bytes") or (video_path.stat().st_size if video_path.exists() else 0)
    proj = record.get("project_name") or (project.name if project else "IRIS Project")

    # Formatações
    speed_desc = f"{speed:.1f}x (Aceleração com preservação temporal)" if speed > 1.0 else (
        f"{speed:.1f}x (Câmera lenta com interpolação de quadros)" if speed < 1.0 else "1.0x (Velocidade Normal)"
    )
    fps_desc = f"{orig_fps:.1f} FPS original ➔ {target_fps} FPS final (Normalização até {target_fps} FPS)"
    trim_desc = f"{trim_sec:.1f}s no início e {trim_sec:.1f}s no fim (remoção de instabilidade de obturador)" if trim_sec > 0 else "Desativado (duração integral preservada)"
    audio_desc = "Descartado / Mudo (-an)" if audio_stripped else f"Estéreo AAC 320 kbps (Sincronizado via atempo {speed:.1f}x)"
    clip_desc = f"{clip_count} clipe unitário" if clip_count == 1 else f"{clip_count} tomadas fundidas em sessão contígua"
    size_desc = format_bytes_human(video_bytes)

    render_stats = meta.get("render_stats") or {}
    render_sec = render_stats.get("render_time_seconds", 0.0)
    render_fps = render_stats.get("avg_fps", 0.0)
    render_line = f"\n• Tempo de Renderização: {format_duration_human(render_sec)} (média de {render_fps:.1f} FPS de codificação)" if render_sec > 0 else ""

    raw_paths = record.get("source_video_paths") or record.get("source_files") or []
    if isinstance(raw_paths, str):
        try:
            src_paths = json.loads(raw_paths)
        except Exception:
            src_paths = [raw_paths] if raw_paths else []
    elif isinstance(raw_paths, (list, tuple)):
        src_paths = list(raw_paths)
    else:
        src_paths = []

    if len(src_paths) == 1:
        p_name = Path(src_paths[0]).name if src_paths[0] else "Desconhecido"
        trace_source = f"• Arquivo Original: {p_name}"
    elif len(src_paths) > 1:
        # Modo joined / múltiplos clipes: lista com nome completo de cada arquivo de origem
        items_lines = []
        max_items = 50  # salvaguarda contra limite estrito de 5.000 chars do YouTube
        for idx, p in enumerate(src_paths):
            if idx >= max_items:
                remaining = len(src_paths) - max_items
                items_lines.append(f"  - ... e mais {remaining} arquivo(s)")
                break
            name = Path(p).name if p else ""
            if name:
                items_lines.append(f"  - {name}")
        joined_items = "\n".join(items_lines)
        trace_source = (
            f"• Modo de Edição: Sessão Concatenada ({len(src_paths)} clipes unidos)\n"
            f"• Arquivos Originais Concatenados:\n{joined_items}"
        )
    else:
        trace_source = "• Origem: Mapeamento interno IRIS"

    profile = str(meta.get("render_profile") or record.get("render_profile") or "quality").lower()
    if profile == "fast":
        profile_desc = "Perfil Rápido (Aceleração por Hardware Intel QSV VPP)"
        upscale_desc = "Aceleração por Hardware Intel QSV VPP (3840x2160 UHD @ 60 FPS)"
        filter_desc = "Filtros de Software Desativados (Foco em Alta Eficiência Energética e Velocidade)"
        profile_tag = "Intel QSV"
    elif profile == "balanced":
        profile_desc = "Perfil Balanceado (Equilíbrio entre Nitidez e Desempenho)"
        upscale_desc = "Interpolação Bicúbica Suave com Realce 1080p Nativo (3840x2160 UHD)"
        filter_desc = "Unsharp Mask Leve 3x3 em 1080p Nativo Pré-Upscale"
        profile_tag = "Bicubic"
    else:
        profile_desc = "Perfil Qualidade Máxima (Preservação de Texturas e Gradientes)"
        upscale_desc = "Interpolação Lanczos de Alta Precisão (3840x2160 UHD)"
        filter_desc = "Unsharp Mask 5x5 + Deband 16-bit com micro-dither em 1080p Nativo Pré-Upscale"
        profile_tag = "Lanczos"

    description = f"""Vídeo capturado e masterizado em altíssima definição 4K UHD ({target_res}) a {target_fps} FPS.
Gravado em {dt_prefix}, produzido e publicado de forma automatizada pelo IRIS (Imaging Resources and Integration System).

⏱️ TEMPO, CAPTURA E VELOCIDADE:
• Data e Hora de Captura: {dt_prefix}
• Duração Original da Gravação: {format_duration_human(orig_dur)} ({orig_dur:.1f}s)
• Trimming Aplicado: {trim_desc}
• Duração do Vídeo Master: {format_duration_human(dur_sec)} ({dur_sec:.1f}s)
• Multiplicador de Velocidade: {speed_desc}
• Taxa de Quadros (FPS): {fps_desc}
• Composição da Cena: {clip_desc}

📷 EQUIPAMENTO E ARQUIVO ORIGINAL:
• Câmera: {camera_name}
• Resolução Nativa Original: {orig_w}x{orig_h} (Proporção 16:9)
• Áudio: {audio_desc}

🛠️ PROCESSAMENTO E ENGENHARIA DE VÍDEO (MASTERIZAÇÃO 4K):
• Perfil de Renderização: {profile_desc}
• Motor de Upscale: {upscale_desc}
• Tratamento de Imagem: {filter_desc}
• Acelerador de Codificação: {encoder}
• Tamanho do Vídeo Master: {size_desc}{render_line}

📁 RASTREABILIDADE IRIS:
• Projeto: {proj}
• Arquivo Gerado: {video_path.name}
{trace_source}
• Pipeline: IRIS v2.0 - Video Mastering Stage

#natureza #4k #uhd #60fps #{cam_make.lower() or 'fotografia'} #iris #automacao
""".replace("\r\n", "\n")

    tags = [
        "4K UHD", "Natureza", "Vídeo 4K", "60 FPS", profile_tag,
        camera_name, cam_make or "Câmera", "IRIS", "Nature"
    ]

    return {
        "title": title,
        "description": description[:5000],
        "tags": [t for t in tags if t],
        "category_id": yt_config.get("category_id", "22"),
        "privacy_status": record.get("youtube_privacy") or yt_config.get("privacy_status", "unlisted")
    }

