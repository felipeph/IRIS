from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import statistics

from src.core.metadata import MediaMetadata
from src.core.namer import generate_target_filename

@dataclass
class ClassifiedItem:
    metadata: MediaMetadata
    category: str  # "astro_lua", "timelapse", "video", "rajada", "avulsa"
    relative_dest_dir: Path
    target_filename: str
    extra_dest_dirs: list[Path] = field(default_factory=list)

def find_timelapse_segments(photos: list[MediaMetadata], config: dict) -> list[tuple[int, int]]:
    """
    Identifica segmentos contíguos de fotos da mesma câmera que formam timelapses.
    """
    tl_min_photos = config.get("timelapse_min_photos", 300)
    tl_max_interval = config.get("timelapse_max_interval_seconds", 60.0)
    tl_tolerance = config.get("timelapse_tolerance_ratio", 1.5)

    if len(photos) < tl_min_photos:
        return []

    deltas = [
        (photos[i].timestamp - photos[i - 1].timestamp).total_seconds()
        for i in range(1, len(photos))
    ]

    segments: list[tuple[int, int]] = []
    n_deltas = len(deltas)
    i = 0

    while i < n_deltas:
        d_start = deltas[i]
        if d_start < 0 or d_start > tl_max_interval:
            i += 1
            continue

        j = i + 1
        cadence = d_start
        recent_deltas = [d_start]

        while j < n_deltas:
            d_next = deltas[j]
            if d_next < 0 or d_next > tl_max_interval:
                break

            allowed = max(1.5, cadence * tl_tolerance)
            if abs(d_next - cadence) <= allowed:
                recent_deltas.append(d_next)
                if len(recent_deltas) > 20:
                    recent_deltas.pop(0)
                cadence = statistics.median(recent_deltas)
                j += 1
            else:
                # Tolerância a 1 frame com jitter de buffer de gravação
                if j + 1 < n_deltas:
                    d_lookahead = deltas[j + 1]
                    if abs(d_lookahead - cadence) <= allowed and d_next <= tl_max_interval:
                        recent_deltas.append(d_next)
                        recent_deltas.append(d_lookahead)
                        if len(recent_deltas) > 20:
                            recent_deltas = recent_deltas[-20:]
                        cadence = statistics.median(recent_deltas)
                        j += 2
                        continue
                break

        # Bloco de intervalos vai de i a j - 1. Total de fotos: j - i + 1
        n_photos = j - i + 1
        if n_photos >= tl_min_photos:
            segments.append((i, j))
            i = j + 1
        else:
            i += 1

    return segments

def _classify_bursts_and_singles(photos: list[MediaMetadata], class_config: dict, name_config: dict, classified: list[ClassifiedItem]):
    if not photos:
        return

    enable_burst = class_config.get("enable_burst_detection", False)
    burst_interval = class_config.get("burst_interval_seconds", 1.5)

    if not enable_burst:
        for it in photos:
            y, m, d = it.date_str.split("-")
            bdir = Path("2_AlbunsDatas") / y / m / d
            target_name = generate_target_filename(it, name_config)
            classified.append(ClassifiedItem(
                metadata=it,
                category="avulsa",
                relative_dest_dir=bdir,
                target_filename=target_name,
            ))
        return

    current_burst = [photos[0]]
    burst_groups = [current_burst]

    for prev, curr in zip(photos[:-1], photos[1:]):
        delta = (curr.timestamp - prev.timestamp).total_seconds()
        if 0.0 <= delta <= burst_interval:
            current_burst.append(curr)
        else:
            current_burst = [curr]
            burst_groups.append(current_burst)

    for group in burst_groups:
        first = group[0]
        y, m, d = first.date_str.split("-")
        if len(group) >= 2:
            bdir = Path("2_AlbunsDatas") / y / m / d / f"rajada_{first.time_str}"
            cat = "rajada"
        else:
            bdir = Path("2_AlbunsDatas") / y / m / d
            cat = "avulsa"

        for it in group:
            target_name = generate_target_filename(it, name_config)
            classified.append(ClassifiedItem(
                metadata=it,
                category=cat,
                relative_dest_dir=bdir,
                target_filename=target_name,
            ))

def _classify_timelapse(photos: list[MediaMetadata], name_config: dict, classified: list[ClassifiedItem]):
    if not photos:
        return
    first = photos[0]
    y, m, d = first.date_str.split("-")
    cam_folder = first.camera_make or "Camera"
    tl_dir = Path("4_Timelapses") / cam_folder / y / m / d / f"timelapse_{first.time_str}"

    for it in photos:
        target_name = generate_target_filename(it, name_config)
        classified.append(ClassifiedItem(
            metadata=it,
            category="timelapse",
            relative_dest_dir=tl_dir,
            target_filename=target_name,
        ))

def classify_media_batch(items: list[MediaMetadata], class_config: dict | None = None, name_config: dict | None = None) -> list[ClassifiedItem]:
    if not items:
        return []

    if class_config is None:
        class_config = {}
    if name_config is None:
        name_config = {}

    # Ordenar itens cronologicamente
    sorted_items = sorted(items, key=lambda x: x.timestamp)
    classified: list[ClassifiedItem] = []

    astro_items: list[MediaMetadata] = []
    video_items: list[MediaMetadata] = []
    general_photo_items: list[MediaMetadata] = []

    moon_zoom = class_config.get("moon_zoom_threshold_mm", 1000.0)
    for item in sorted_items:
        # 1. Astrofotografia (Lua RAW teleobjetiva)
        is_moon_focal = item.focal_length_equiv is not None and item.focal_length_equiv >= moon_zoom
        if item.is_raw and (is_moon_focal or "sx60" in item.camera_model.lower() or "sx50" in item.camera_model.lower()):
            astro_items.append(item)
        # 2. Vídeos
        elif item.is_video:
            video_items.append(item)
        # 3. Fotos Gerais (GoPro, Canon, Sony, smartphones, etc.)
        else:
            general_photo_items.append(item)

    # Processar itens de Astrofotografia (Lua)
    if astro_items:
        current_session = [astro_items[0]]
        astro_sessions = [current_session]
        for prev, curr in zip(astro_items[:-1], astro_items[1:]):
            delta = (curr.timestamp - prev.timestamp).total_seconds()
            if delta <= 60.0:
                current_session.append(curr)
            else:
                current_session = [curr]
                astro_sessions.append(current_session)

        for session in astro_sessions:
            first = session[0]
            y, m, d = first.date_str.split("-")
            session_dir = Path("5_Astrofotografia") / "Lua" / y / m / d / f"sessao_{first.time_str}"
            for it in session:
                target_name = generate_target_filename(it, name_config)
                classified.append(ClassifiedItem(
                    metadata=it,
                    category="astro_lua",
                    relative_dest_dir=session_dir,
                    target_filename=target_name,
                ))

    # Processar Vídeos
    for it in video_items:
        y, m, d = it.date_str.split("-")
        vdir = Path("3_Videos") / y / m / d
        target_name = generate_target_filename(it, name_config)
        classified.append(ClassifiedItem(
            metadata=it,
            category="video",
            relative_dest_dir=vdir,
            target_filename=target_name,
        ))

    # Processar Fotos Gerais por Câmera / Fonte
    if general_photo_items:
        by_camera: dict[tuple[str, str], list[MediaMetadata]] = {}
        for item in general_photo_items:
            cam_key = (item.camera_make or "Cam", item.camera_model or "Model")
            by_camera.setdefault(cam_key, []).append(item)

        for _, cam_photos in by_camera.items():
            cam_photos.sort(key=lambda x: x.timestamp)
            segments = find_timelapse_segments(cam_photos, class_config)

            if not segments:
                _classify_bursts_and_singles(cam_photos, class_config, name_config, classified)
            else:
                cur_idx = 0
                for start_idx, end_idx in segments:
                    if start_idx > cur_idx:
                        _classify_bursts_and_singles(cam_photos[cur_idx:start_idx], class_config, name_config, classified)
                    _classify_timelapse(cam_photos[start_idx:end_idx + 1], name_config, classified)
                    cur_idx = end_idx + 1
                if cur_idx < len(cam_photos):
                    _classify_bursts_and_singles(cam_photos[cur_idx:], class_config, name_config, classified)

    return classified
