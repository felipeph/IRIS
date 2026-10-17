from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import statistics

from src.core.metadata import MediaMetadata, parse_shutter_seconds
from src.core.namer import generate_target_filename

@dataclass
class ClassifiedItem:
    metadata: MediaMetadata
    category: str  # "astro_lua", "timelapse", "video", "rajada", "avulsa"
    relative_dest_dir: Path
    target_filename: str
    extra_dest_dirs: list[Path] = field(default_factory=list)

def is_timelapse_folder_name(folder_name: str) -> bool:
    """Verifica se o nome de uma pasta indica explicitamente ser um timelapse."""
    if not folder_name:
        return False
    clean = folder_name.lower().replace("_", " ").replace("-", " ")
    return "timelapse" in clean or "time lapse" in clean

def find_timelapse_segments(photos: list[MediaMetadata], config: dict) -> list[tuple[int, int]]:
    """
    Identifica segmentos contíguos de fotos da mesma câmera que formam timelapses.
    Em astrofotografia de longa exposição (shutter >= 5s), ajusta dinamicamente
    o intervalo tolerado e permite gaps harmônicos decorrentes de gravação do buffer.
    Para fotos diurnas / pássaros (shutter < 5s), mantém tolerância estrita sem pontes de pausa.
    """
    tl_min_photos = config.get("timelapse_min_photos", 60)
    base_max_interval = config.get("timelapse_max_interval_seconds", 60.0)
    tl_tolerance = config.get("timelapse_tolerance_ratio", 1.5)

    astro_cfg = config.get("astro_timelapse", {})
    astro_min_shutter = astro_cfg.get("min_shutter_seconds", 5.0)
    astro_max_gap = astro_cfg.get("max_gap_seconds", 600.0)

    if len(photos) < tl_min_photos:
        return []

    deltas = [
        (photos[i].timestamp - photos[i - 1].timestamp).total_seconds()
        for i in range(1, len(photos))
    ]
    shutters = [parse_shutter_seconds(p.shutter_str) or 0.0 for p in photos]

    segments: list[tuple[int, int]] = []
    n_deltas = len(deltas)
    i = 0

    while i < n_deltas:
        d_start = deltas[i]
        shutter_i = shutters[i]
        is_long_exposure = shutter_i >= astro_min_shutter

        # Em longa exposição, o tempo de obturador é somado ao teto base
        max_start = max(base_max_interval, shutter_i + base_max_interval) if is_long_exposure else base_max_interval

        if d_start < 0 or d_start > max_start:
            i += 1
            continue

        j = i + 1
        cadence = d_start
        recent_deltas = [d_start]

        while j < n_deltas:
            d_next = deltas[j]
            shutter_j = shutters[j]
            is_le_j = shutter_j >= astro_min_shutter
            max_allowed_j = max(base_max_interval, shutter_j + base_max_interval) if is_le_j else base_max_interval

            allowed = max(2.0, cadence * tl_tolerance)

            # Caso 1: Próximo intervalo está dentro da cadência normal
            if abs(d_next - cadence) <= allowed:
                recent_deltas.append(d_next)
                if len(recent_deltas) > 20:
                    recent_deltas.pop(0)
                cadence = statistics.median(recent_deltas)
                j += 1
            # Caso 2: Em longa exposição (astrofotografia), permite frames pulados (2x/3x cadência) ou pausas noturnas
            elif is_long_exposure and is_le_j and (
                abs(d_next - 2 * cadence) <= allowed or
                abs(d_next - 3 * cadence) <= allowed or
                (d_next <= astro_max_gap)
            ):
                if j + 1 < n_deltas:
                    d_after = deltas[j + 1]
                    if abs(d_after - cadence) <= allowed or abs(d_after - 2 * cadence) <= allowed:
                        recent_deltas.append(cadence)
                        j += 1
                        continue
                if d_next <= astro_max_gap:
                    recent_deltas.append(cadence)
                    j += 1
                    continue
                break
            else:
                # Tolerância padrão a 1 frame com jitter de gravação (se não ultrapassar o teto)
                if j + 1 < n_deltas:
                    d_lookahead = deltas[j + 1]
                    if abs(d_lookahead - cadence) <= allowed and d_next <= max_allowed_j:
                        recent_deltas.append(cadence)
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

def _classify_timelapse(photos: list[MediaMetadata], name_config: dict, classified: list[ClassifiedItem], class_config: dict | None = None):
    if not photos:
        return
    first = photos[0]
    parts = first.date_str.split("-")
    if len(parts) == 3:
        y, m, d = parts
    else:
        y, m, d = "SemData", "00", "00"

    cam_folder = first.camera_make or "Camera"
    tl_dir = Path("4_Timelapses") / cam_folder / y / m / d / f"timelapse_{first.time_str}"

    # Configuração de Amostragem para Álbuns (2_AlbunsDatas)
    enable_samples = True
    sample_interval_sec = 300.0  # 5 minutos padrão
    if class_config:
        enable_samples = class_config.get("enable_timelapse_album_samples", True)
        interval_min = class_config.get("timelapse_sample_interval_minutes", 5.0)
        try:
            sample_interval_sec = max(1.0, float(interval_min) * 60.0)
        except (ValueError, TypeError):
            sample_interval_sec = 300.0

    album_sample_dir = Path("2_AlbunsDatas") / y / m / d / f"timelapse_amostras_{first.time_str}"

    sampled_indices = set()
    if enable_samples and photos:
        # Primeiro frame garantido
        sampled_indices.add(0)
        last_sampled_dt = photos[0].timestamp

        # Intermediários espaçados por sample_interval_sec
        for idx in range(1, len(photos) - 1):
            curr_dt = photos[idx].timestamp
            if curr_dt and last_sampled_dt:
                delta = (curr_dt - last_sampled_dt).total_seconds()
                if delta >= sample_interval_sec:
                    sampled_indices.add(idx)
                    last_sampled_dt = curr_dt

        # Último frame garantido
        if len(photos) > 1:
            sampled_indices.add(len(photos) - 1)

    for idx, it in enumerate(photos):
        target_name = generate_target_filename(it, name_config)
        extra_dirs = [album_sample_dir] if idx in sampled_indices else []
        classified.append(ClassifiedItem(
            metadata=it,
            category="timelapse",
            relative_dest_dir=tl_dir,
            target_filename=target_name,
            extra_dest_dirs=extra_dirs,
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
        # Camada 1: Reconhecimento Estrutural por Pasta Pré-Organizada
        recognize_folders = class_config.get("recognize_timelapse_folders", True)
        min_folder_photos = class_config.get("timelapse_min_photos_folder", 30)

        remaining_general_photos: list[MediaMetadata] = []

        if recognize_folders:
            by_folder: dict[str, list[MediaMetadata]] = {}
            for item in general_photo_items:
                folder_name = getattr(item, "source_folder_name", "") or item.file_path.parent.name
                by_folder.setdefault(folder_name, []).append(item)

            for folder_name, f_photos in by_folder.items():
                if is_timelapse_folder_name(folder_name) and len(f_photos) >= min_folder_photos:
                    f_photos.sort(key=lambda x: x.timestamp)
                    _classify_timelapse(f_photos, name_config, classified, class_config=class_config)
                else:
                    remaining_general_photos.extend(f_photos)
        else:
            remaining_general_photos = general_photo_items

        # Camada 2: Classificação Heurística por Câmera (para cartões SD / DCIM)
        if remaining_general_photos:
            by_camera: dict[tuple[str, str], list[MediaMetadata]] = {}
            for item in remaining_general_photos:
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
                        _classify_timelapse(cam_photos[start_idx:end_idx + 1], name_config, classified, class_config=class_config)
                        cur_idx = end_idx + 1
                    if cur_idx < len(cam_photos):
                        _classify_bursts_and_singles(cam_photos[cur_idx:], class_config, name_config, classified)

    return classified
