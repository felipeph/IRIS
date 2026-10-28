import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

from .formatting import (
    _extract_temporal_context,
    format_duration_human,
    format_bytes_human,
)
from .geo import resolve_project_geolocation, format_location_block, build_geo_hashtags
from .birds import (
    resolve_bird_identification,
    build_bird_youtube_title,
    resolve_bird_target_playlists,
    format_bird_taxonomy_block,
    build_bird_hashtags,
)


def build_edited_video_youtube_title(
    video_path: Path,
    record: Dict[str, Any],
    project: Optional[Any] = None,
    loc: Optional[Any] = None
) -> str:
    """
    Gera título padronizado para vídeos convencionais sem aves identificadas:
    {Data} ({Hora}) | {Cidade}, {UF}
    Exemplos:
      - Com intervalo de horas: '2026-10-09 (16:22 - 18:35) | Passos, MG'
      - Clipe único curto: '2026-10-09 (16:22) | Passos, MG'
    NUNCA inclui 'Vídeo 4K UHD'.
    """
    date_part, time_str = _extract_temporal_context(video_path, record)

    title_elements = [date_part]
    if time_str:
        title_elements.append(time_str)

    temporal_full = " ".join(title_elements).strip()

    if loc is None:
        loc = resolve_project_geolocation(record, project)

    loc_str = ""
    if loc and getattr(loc, "city", None):
        loc_str = f"{loc.city}, {loc.state}" if getattr(loc, "state", None) else loc.city

    if loc_str:
        title = f"{temporal_full} | {loc_str}"
    else:
        title = temporal_full

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
    Suporta tratamento ornitológico e geográfico diferenciado.
    """
    meta = record.get("metadata_json") or {}

    # Localização do projeto
    loc = resolve_project_geolocation(record, project=project)

    # Verifica se há ave identificada para este vídeo
    bird_info = resolve_bird_identification(record, project=project)

    if bird_info:
        title = build_bird_youtube_title(video_path, record, bird_info, project=project, loc=loc)
        target_playlists = resolve_bird_target_playlists(bird_info, yt_config, loc=loc)
    else:
        title = build_edited_video_youtube_title(video_path, record, project=project, loc=loc)
        target_playlists = []
        if loc and getattr(loc, "city", None):
            city_name = loc.city.strip()
            state_name = getattr(loc, "state", "").strip()
            if city_name:
                geo_pl = f"{city_name} - {state_name}" if state_name else city_name
                target_playlists.append(geo_pl)
        default_pl = yt_config.get("video_playlist", "Natureza 4K UHD")
        if default_pl and default_pl not in target_playlists:
            target_playlists.append(default_pl)

    # Data de captura para a descrição técnica
    first_dt_str = meta.get("first_dt_formatted")
    dt_prefix = ""
    if first_dt_str:
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

    # Informações Técnicas
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
        items_lines = []
        max_items = 50
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

    loc_section = ""
    geo_hts_str = ""
    if loc:
        loc_block = format_location_block(loc)
        if loc_block:
            loc_section = f"\n\n{loc_block}\n"
        geo_hts = build_geo_hashtags(loc)
        if geo_hts:
            geo_hts_str = " ".join(geo_hts) + " "

    description = f"""{intro_hook}Vídeo capturado e masterizado em altíssima definição 4K UHD ({target_res}) a {target_fps} FPS.
Gravado em {dt_prefix}, produzido e publicado de forma automatizada pelo IRIS (Imaging Resources and Integration System).{bird_section}{loc_section}
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

{bird_hts_str}{geo_hts_str}#natureza #4k #uhd #60fps #{cam_make.lower() or 'fotografia'} #iris #automacao
""".replace("\r\n", "\n")

    tags = [
        "4K UHD", "Natureza", "Vídeo 4K", "60 FPS", profile_tag,
        camera_name, cam_make or "Câmera", "IRIS", "Nature"
    ]
    if loc:
        for l_cand in [loc.city, loc.state, loc.country, loc.poi, loc.suburb]:
            if l_cand and l_cand.strip() and l_cand.strip() not in tags:
                tags.append(l_cand.strip())

    if bird_info:
        for b_cand in [
            bird_info.get("species_common"),
            bird_info.get("species_scientific"),
            bird_info.get("species_common_en"),
            bird_info.get("family"),
            bird_info.get("order"),
            "Aves", "Birdwatching", "Observação de Aves", "Ornitologia", "Passarinhada", "Fauna Silvestre", "Wildlife"
        ]:
            if b_cand and b_cand.strip() and b_cand.strip() not in tags:
                tags.append(b_cand.strip())

    return {
        "title": title,
        "description": description[:5000],
        "tags": [t for t in tags if t],
        "category_id": yt_config.get("category_id", "22"),
        "privacy_status": record.get("youtube_privacy") or yt_config.get("privacy_status", "unlisted"),
        "playlist": target_playlists[0] if target_playlists else yt_config.get("video_playlist", "Natureza 4K UHD"),
        "playlists": target_playlists,
        "bird_info": bird_info,
        "geo_location": loc.to_dict() if loc else None
    }
