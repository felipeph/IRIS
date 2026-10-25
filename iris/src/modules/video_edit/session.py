import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict

from src.core.project import ProjectItem
from src.modules.bird_id.action import sanitize_bird_token

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

def _validate_bird_record(rec: Dict[str, Any], min_confidence: float) -> Optional[Dict[str, Any]]:
    """Valida se o registro taxonômico possui espécie confirmada e atinge os critérios de qualidade."""
    if not isinstance(rec, dict):
        return None
    c_pt = str(rec.get("species_common") or "").strip()
    sci = str(rec.get("species_scientific") or "").strip()
    if not (c_pt or sci):
        return None

    if rec.get("needs_review", False):
        return None

    try:
        conf = float(rec.get("confidence", 0.0))
    except (ValueError, TypeError):
        conf = 0.0

    meta = rec.get("metadata_json") if isinstance(rec.get("metadata_json"), dict) else {}
    is_early_exit = bool(meta.get("burst_early_exit", False))

    if conf > 0.0 and conf < min_confidence and not is_early_exit:
        return None

    return rec

def resolve_item_bird_info(
    item: ProjectItem,
    project: Optional[Any] = None,
    bird_ident_map: Optional[Dict[str, Dict[str, Any]]] = None,
    min_confidence: float = 0.70
) -> Optional[Dict[str, Any]]:
    """
    Localiza e valida o registro taxonômico de ave associado a um item de vídeo.
    Consulta mapa explícito, SQLite do projeto (get_bird_identification) e varredura de nomes.
    """
    cand_paths = [item.organized_path, item.staging_path, item.original_path]
    clean_cands = [p for p in cand_paths if p]

    # 1. Consulta em mapa fornecido explicitamente
    if bird_ident_map:
        for c in clean_cands:
            rec = bird_ident_map.get(str(c))
            if not rec:
                try:
                    rec = bird_ident_map.get(str(Path(c).resolve()))
                except Exception:
                    pass
            if not rec:
                rec = bird_ident_map.get(Path(c).name)
            if rec:
                validated = _validate_bird_record(rec, min_confidence)
                if validated:
                    return validated

    # 2. Consulta no banco de dados SQLite do projeto via get_bird_identification
    if project and hasattr(project, "get_bird_identification"):
        for c in clean_cands:
            p_cand = Path(c)
            rec = None
            try:
                rec = project.get_bird_identification(str(p_cand.resolve()))
            except Exception:
                pass
            if not rec:
                rec = project.get_bird_identification(str(p_cand))
            if rec:
                validated = _validate_bird_record(rec, min_confidence)
                if validated:
                    return validated

    # 3. Varredura por nome de arquivo em list_bird_identifications
    if project and hasattr(project, "list_bird_identifications"):
        cand_names = {Path(c).name.lower() for c in clean_cands}
        try:
            all_birds = project.list_bird_identifications()
            for b in all_birds:
                b_path = b.get("item_path", "")
                if b_path and Path(b_path).name.lower() in cand_names:
                    validated = _validate_bird_record(b, min_confidence)
                    if validated:
                        return validated
        except Exception:
            pass

    return None

def group_videos_into_sessions(
    items: List[ProjectItem],
    mode: str = "individual",
    session_interval_minutes: float = 10.0,
    project: Optional[Any] = None,
    bird_ident_map: Optional[Dict[str, Dict[str, Any]]] = None,
    auto_join_birds: bool = True,
    min_species_confidence: float = 0.70
) -> List[List[ProjectItem]]:
    """
    Agrupa vídeos em sessões de trabalho para renderização.
    - Se auto_join_birds == True:
        Vídeos com ave identificada gravados no mesmo dia são automaticamente
        agrupados por (data, espécie, câmera) em sessões contínuas.
    - Se mode == 'individual':
        Vídeos restantes (sem espécie de ave) formam grupos unitários 1:1.
    - Se mode == 'joined':
        Concatena todos os vídeos restantes que vieram da mesma pasta de origem (e mesma câmera)
        em um único vídeo, ordenados cronologicamente.
    """
    if not items:
        return []

    # Se auto_join_birds estiver desativado, segue a lógica clássica
    if not auto_join_birds:
        if mode == "individual":
            sorted_items = sorted(items, key=lambda it: parse_item_datetime(it))
            return [[it] for it in sorted_items]

        groups: Dict[Tuple[str, Tuple[str, str]], List[ProjectItem]] = defaultdict(list)
        for it in items:
            folder_key = get_item_source_folder(it)
            cam_key = (it.meta_camera_make or "Cam", it.meta_camera_model or "Model")
            groups[(folder_key, cam_key)].append(it)

        all_sessions: List[List[ProjectItem]] = []
        for (folder_key, cam_key), group_items in groups.items():
            group_items.sort(key=lambda it: parse_item_datetime(it))
            all_sessions.append(group_items)

        all_sessions.sort(key=lambda s: parse_item_datetime(s[0]))
        return all_sessions

    # Modo inteligente com Auto-Join de Aves por Espécie e Dia
    bird_groups: Dict[Tuple[str, str, Tuple[str, str]], List[ProjectItem]] = defaultdict(list)
    remaining_items: List[ProjectItem] = []

    for it in items:
        b_info = resolve_item_bird_info(
            it,
            project=project,
            bird_ident_map=bird_ident_map,
            min_confidence=min_species_confidence
        )
        if b_info:
            c_pt = b_info.get("species_common", "")
            sci = b_info.get("species_scientific", "")
            spec_token = sanitize_bird_token(c_pt) or sanitize_bird_token(sci)
            if spec_token:
                dt = parse_item_datetime(it)
                date_str = dt.strftime("%Y-%m-%d")
                cam_key = (it.meta_camera_make or "Cam", it.meta_camera_model or "Model")
                group_key = (date_str, spec_token.lower(), cam_key)
                bird_groups[group_key].append(it)
                continue

        remaining_items.append(it)

    all_sessions: List[List[ProjectItem]] = []

    # Adiciona grupos de aves (ordenados internamente por datetime)
    for (date_str, spec_token, cam_key), group_items in bird_groups.items():
        group_items.sort(key=lambda it: parse_item_datetime(it))
        all_sessions.append(group_items)

    # Processa itens restantes (sem ave identificada)
    if remaining_items:
        if mode == "individual":
            for it in remaining_items:
                all_sessions.append([it])
        else:
            # mode == "joined": agrupa por pasta e câmera
            folder_groups: Dict[Tuple[str, Tuple[str, str]], List[ProjectItem]] = defaultdict(list)
            for it in remaining_items:
                folder_key = get_item_source_folder(it)
                cam_key = (it.meta_camera_make or "Cam", it.meta_camera_model or "Model")
                folder_groups[(folder_key, cam_key)].append(it)

            for (folder_key, cam_key), group_items in folder_groups.items():
                group_items.sort(key=lambda it: parse_item_datetime(it))
                all_sessions.append(group_items)

    # Ordenar todas as sessões pela data/hora do primeiro clipe
    all_sessions.sort(key=lambda s: parse_item_datetime(s[0]))
    return all_sessions

