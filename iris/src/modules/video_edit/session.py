import os
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

def get_item_source_folder(item: ProjectItem) -> str:
    """Extrai a pasta de origem normalizada do item (onde o arquivo residia originalmente)."""
    cand = item.original_path or item.staging_path or item.organized_path or ""
    if cand:
        try:
            return os.path.normcase(os.path.normpath(str(Path(cand).parent)))
        except Exception:
            return str(Path(cand).parent).lower()
    return ""

def group_videos_into_sessions(
    items: List[ProjectItem],
    mode: str = "individual",
    session_interval_minutes: float = 10.0
) -> List[List[ProjectItem]]:
    """
    Agrupa vídeos em sessões de trabalho para renderização.
    - Se mode == 'individual': Cada vídeo forma um grupo unitário independente (upscale individual 1:1).
    - Se mode == 'joined': Concatena todos os vídeos que vieram da mesma pasta de origem (e mesma câmera)
      em um único vídeo, ordenados cronologicamente, independente do horário em que foram gravados.
    """
    if not items:
        return []

    if mode == "individual":
        # Ordenação cronológica simples
        sorted_items = sorted(items, key=lambda it: parse_item_datetime(it))
        return [[it] for it in sorted_items]

    # Modo Joined: Agrupar por pasta de origem e câmera
    groups: Dict[Tuple[str, Tuple[str, str]], List[ProjectItem]] = defaultdict(list)
    for it in items:
        folder_key = get_item_source_folder(it)
        cam_key = (it.meta_camera_make or "Cam", it.meta_camera_model or "Model")
        groups[(folder_key, cam_key)].append(it)

    all_sessions: List[List[ProjectItem]] = []
    for (folder_key, cam_key), group_items in groups.items():
        group_items.sort(key=lambda it: parse_item_datetime(it))
        all_sessions.append(group_items)

    # Ordenar as sessões finais pela data/hora do primeiro clipe
    all_sessions.sort(key=lambda s: parse_item_datetime(s[0]))
    return all_sessions

