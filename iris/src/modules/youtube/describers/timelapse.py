from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.core.geo import GeoLocation
from .formatting import (
    format_duration_human,
    format_bytes_human,
    summarize_exposure_param,
    calculate_aspect_ratio,
)
from .geo import resolve_project_geolocation, format_location_block, build_geo_hashtags
from .birds import format_bird_taxonomy_block, build_bird_hashtags


def build_youtube_title(
    video_path: Path,
    record: Dict[str, Any],
    loc: Optional[GeoLocation] = None,
    project: Optional[Any] = None
) -> str:
    """Gera título padronizado para vídeos timelapse no YouTube: {Data} ({Hora}) | {Cidade}, {UF} | Timelapse 4K UHD."""
    name = video_path.name
    parts = name.split('_')
    date_part = parts[0] if len(parts) > 0 else datetime.now().strftime('%Y-%m-%d')
    time_part = parts[1] if len(parts) > 1 else ""

    if "-" in time_part:
        t1, t2 = time_part.split("-", 1)
        t1_clean = t1.replace('h', ':').replace('m', '')
        t2_clean = t2.replace('h', ':').replace('m', '')
        time_str = f"({t1_clean} - {t2_clean})" if (t1_clean and t2_clean) else ""
    elif time_part and ("h" in time_part or "m" in time_part):
        t_clean = time_part.replace('h', ':').replace('m', '')
        time_str = f"({t_clean})"
    else:
        time_str = ""

    title_elements = [date_part]
    if time_str:
        title_elements.append(time_str)
    temporal_full = " ".join(title_elements).strip()

    # Identificar se é longa exposição
    seq_dir = str(record.get("sequence_dir", ""))
    out_vid = str(record.get("output_video_path", "")) or name
    is_le = "4_Timelapses_LongaExposicao" in seq_dir or "longa_exposicao" in out_vid or "longa-exposicao" in out_vid

    format_desc = "Timelapse Longa Exposição 4K UHD" if is_le else "Timelapse 4K UHD"

    if loc is None:
        loc = resolve_project_geolocation(record, project=project)

    loc_str = ""
    if loc and getattr(loc, "city", None):
        loc_str = f"{loc.city}, {loc.state}" if getattr(loc, "state", None) else loc.city

    if loc_str:
        title = f"{temporal_full} | {loc_str} | {format_desc}"
    else:
        title = f"{temporal_full} | {format_desc}"

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


def build_rich_youtube_description(
    record: Dict[str, Any],
    project_name: str = "",
    bird_info: Optional[Dict[str, Any]] = None,
    loc: Optional[Any] = None
) -> str:
    """
    Compila uma descrição técnica completa e rica para o YouTube com:
    - Gancho inicial resumido (com menção à espécie se bird_info fornecido)
    - 🐦 IDENTIFICAÇÃO TAXONÔMICA (AVES) (se bird_info fornecido)
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

    # Gancho inicial e bloco de ave se presente
    if bird_info:
        c_pt = bird_info.get("species_common", "")
        sci = bird_info.get("species_scientific", "")
        c_en = bird_info.get("species_common_en", "")
        intro_hook = f"Registro em altíssima definição de {c_pt} ({sci})"
        if c_en and c_en.lower() != c_pt.lower():
            intro_hook += f", conhecido em inglês como {c_en}.\n"
        else:
            intro_hook += ".\n"
        bird_section = f"\n\n{format_bird_taxonomy_block(bird_info)}\n"
        bird_hts_list = build_bird_hashtags(bird_info)
        bird_hts_str = " ".join(bird_hts_list) + " " if bird_hts_list else ""
    else:
        intro_hook = ""
        bird_section = ""
        bird_hts_str = ""

    if not loc and meta.get("geo_location") and isinstance(meta["geo_location"], dict):
        loc = GeoLocation.from_dict(meta["geo_location"])

    loc_section = ""
    geo_hts_str = ""
    if loc:
        loc_block = format_location_block(loc)
        if loc_block:
            loc_section = f"\n\n{loc_block}\n"
        geo_hts = build_geo_hashtags(loc)
        if geo_hts:
            geo_hts_str = " ".join(geo_hts) + " "

    # Montagem da Descrição
    description = f"""{intro_hook}Vídeo Timelapse renderizado em alta definição 4K UHD ({res}) a {fps} FPS.
Capturado em {date_label}, produzido e renderizado de forma automatizada pelo IRIS (Imaging Resources and Integration System).{bird_section}{loc_section}
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

{bird_hts_str}{geo_hts_str}#timelapse #4k #uhd #60fps #{cam_make.lower() or 'fotografia'} #iris #automacao
""".replace("\r\n", "\n")

    return description[:5000]

