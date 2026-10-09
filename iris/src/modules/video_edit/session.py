from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
from collections import defaultdict

from src.core.project import ProjectItem

def parse_item_datetime(item: ProjectItem) -> datetime:
    """Extrai ou infere o datetime de início de gravação do item."""
    if item.meta_timestamp:
        try:
            return datetime.fromisoformat(item.meta_timestamp)
        except Exception:
            pass
    if item.meta_date_str and item.meta_time_str:
        try:
            dt_str = f"{item.meta_date_str} {item.meta_time_str.replace('-', ':')}"
            return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    # Fallback para timestamp do arquivo no disco
    path_cand = Path(item.organized_path) if item.organized_path else Path(item.staging_path)
    if path_cand.exists():
        return datetime.fromtimestamp(path_cand.stat().st_mtime)
    return datetime.now()

def parse_duration_seconds(item: ProjectItem) -> float:
    """Extrai a duração em segundos do item a partir do metadado."""
    dur_str = item.meta_duration_str or ""
    # Pode ser no formato "00m15s", "15s", "01:23:45", etc.
    if not dur_str:
        return 0.0
    try:
        if "m" in dur_str and "s" in dur_str:
            parts = dur_str.split("m")
            minutes = float(parts[0])
            seconds = float(parts[1].replace("s", ""))
            return (minutes * 60.0) + seconds
        elif "s" in dur_str:
            return float(dur_str.replace("s", ""))
        elif ":" in dur_str:
            time_parts = [float(p) for p in dur_str.split(":")]
            if len(time_parts) == 3:
                return (time_parts[0] * 3600.0) + (time_parts[1] * 60.0) + time_parts[2]
            elif len(time_parts) == 2:
                return (time_parts[0] * 60.0) + time_parts[1]
        return float(dur_str)
    except Exception:
        return 0.0

def group_videos_into_sessions(
    items: List[ProjectItem],
    mode: str = "individual",
    session_interval_minutes: float = 10.0
) -> List[List[ProjectItem]]:
    """
    Agrupa vídeos em sessões de trabalho para renderização.
    - Se mode == 'individual': Cada vídeo forma um grupo unitário independente.
    - Se mode == 'joined': Agrupa vídeos contíguos da mesma câmera com intervalo <= session_interval_minutes.
    """
    if not items:
        return []

    if mode == "individual":
        # Ordenação cronológica simples
        sorted_items = sorted(items, key=lambda it: parse_item_datetime(it))
        return [[it] for it in sorted_items]

    # Modo Joined: Agrupar por câmera e identificar sessões contíguas
    by_camera: Dict[Tuple[str, str], List[ProjectItem]] = defaultdict(list)
    for it in items:
        cam_key = (it.meta_camera_make or "Cam", it.meta_camera_model or "Model")
        by_camera[cam_key].append(it)

    all_sessions: List[List[ProjectItem]] = []
    max_interval_sec = max(1.0, float(session_interval_minutes) * 60.0)

    for cam_key, cam_items in by_camera.items():
        cam_items.sort(key=lambda it: parse_item_datetime(it))
        
        current_session = [cam_items[0]]
        
        for prev, curr in zip(cam_items[:-1], cam_items[1:]):
            prev_start = parse_item_datetime(prev)
            prev_dur = parse_duration_seconds(prev)
            prev_end = prev_start.timestamp() + prev_dur
            curr_start = parse_item_datetime(curr).timestamp()

            # Delta entre o término do clipe anterior e o início do próximo
            delta_sec = curr_start - prev_end
            if delta_sec < 0:
                # Caso de sobreposição de relógio ou cálculo impreciso de duração: usa diferença entre inícios
                delta_sec = max(0.0, curr_start - prev_start.timestamp())

            if delta_sec <= max_interval_sec:
                current_session.append(curr)
            else:
                all_sessions.append(current_session)
                current_session = [curr]

        if current_session:
            all_sessions.append(current_session)

    # Ordenar as sessões finais pela data/hora do primeiro clipe
    all_sessions.sort(key=lambda s: parse_item_datetime(s[0]))
    return all_sessions
