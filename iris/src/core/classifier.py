from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
import statistics

from src.core.metadata import MediaMetadata, parse_shutter_seconds
from src.core.namer import generate_target_filename

@dataclass
class ClassifiedItem:
    metadata: MediaMetadata
    category: str  # "astro_lua", "timelapse", "timelapse_long_exposure", "video", "rajada", "avulsa"
    relative_dest_dir: Path
    target_filename: str
    extra_dest_dirs: list[Path] = field(default_factory=list)

@dataclass(frozen=True)
class TimelapseProfile:
    name: str                      # "normal" | "long_exposure"
    category: str                  # "timelapse" | "timelapse_long_exposure"
    root_dir: str                  # "4_Timelapses" | "4_Timelapses_LongaExposicao"
    min_photos: int
    min_interval: float            # cadência mínima aceita (s)
    max_interval: float            # cadência máxima aceita (s)
    tolerance_ratio: float         # ex: 0.25 = ±25% da cadência
    tolerance_min_seconds: float   # piso absoluto da tolerância
    stall_factor_max: float        # delta de travada <= factor * cadência
    max_stall_fraction: float      # % máx de deltas travados no segmento
    min_regular_fraction: float    # % mín de deltas dentro da tolerância
    min_shutter: float | None      # None = sem filtro; senão exige shutter >= valor
    max_shutter: float | None      # normal: shutter < min_shutter da longa exposição

    def eligible(self, shutter: float) -> bool:
        if self.min_shutter is not None and shutter < self.min_shutter:
            return False
        if self.max_shutter is not None and shutter >= self.max_shutter:
            return False
        return True

@dataclass(frozen=True)
class TimelapseSegment:
    start: int
    end: int
    profile: TimelapseProfile

    def __iter__(self):
        yield self.start
        yield self.end

    def __getitem__(self, item):
        if item == 0:
            return self.start
        elif item == 1:
            return self.end
        raise IndexError("TimelapseSegment index out of range")

def load_profiles(cfg: dict | None = None) -> tuple[TimelapseProfile, TimelapseProfile, bool]:
    if cfg is None:
        cfg = {}
    n = cfg.get("timelapse_normal", {})
    le = cfg.get("timelapse_long_exposure", {})
    legacy_astro = cfg.get("astro_timelapse", {})

    le_min_shutter = float(le.get("min_shutter_seconds", legacy_astro.get("min_shutter_seconds", 5.0)))
    le_enabled = bool(le.get("enabled", True))

    normal_min_photos = int(n.get("min_photos", cfg.get("timelapse_min_photos", 200)))
    normal_max_interval = float(n.get("max_interval_seconds", cfg.get("timelapse_max_interval_seconds", 60.0)))
    normal_tol = float(n.get("tolerance_ratio", cfg.get("timelapse_tolerance_ratio", 0.25)))

    normal = TimelapseProfile(
        name="normal",
        category="timelapse",
        root_dir="4_Timelapses",
        min_photos=normal_min_photos,
        min_interval=float(n.get("min_interval_seconds", 0.3)),
        max_interval=normal_max_interval,
        tolerance_ratio=normal_tol,
        tolerance_min_seconds=float(n.get("tolerance_min_seconds", 0.5)),
        stall_factor_max=float(n.get("stall_factor_max", 4.0)),
        max_stall_fraction=float(n.get("max_stall_fraction", 0.05)),
        min_regular_fraction=float(n.get("min_regular_fraction", 0.90)),
        min_shutter=None,
        max_shutter=le_min_shutter,
    )

    le_min_photos = int(le.get("min_photos", 60))
    le_max_interval = float(le.get("max_interval_seconds", legacy_astro.get("max_interval_seconds", 180.0)))
    le_tol = float(le.get("tolerance_ratio", 0.15))

    long_exp = TimelapseProfile(
        name="long_exposure",
        category="timelapse_long_exposure",
        root_dir=str(le.get("folder", "4_Timelapses_LongaExposicao")),
        min_photos=le_min_photos,
        min_interval=le_min_shutter,
        max_interval=le_max_interval,
        tolerance_ratio=le_tol,
        tolerance_min_seconds=float(le.get("tolerance_min_seconds", 3.0)),
        stall_factor_max=float(le.get("stall_factor_max", 5.0)),
        max_stall_fraction=float(le.get("max_stall_fraction", 0.15)),
        min_regular_fraction=float(le.get("min_regular_fraction", 0.85)),
        min_shutter=le_min_shutter,
        max_shutter=None,
    )

    return normal, long_exp, le_enabled

def is_timelapse_folder_name(folder_name: str) -> bool:
    """Verifica se o nome de uma pasta indica explicitamente ser um timelapse."""
    if not folder_name:
        return False
    clean = folder_name.lower().replace("_", " ").replace("-", " ")
    return "timelapse" in clean or "time lapse" in clean

def _is_isolated_stall(deltas: list[float], j: int, anchor: float, tol: float, profile: TimelapseProfile) -> bool:
    d = deltas[j]
    if d <= anchor + tol or d > anchor * profile.stall_factor_max:
        return False
    # Travada isolada de buffer / frame pulado: o delta seguinte retorna à cadência
    if j + 1 < len(deltas):
        nxt = deltas[j + 1]
        return abs(nxt - anchor) <= tol
    return False

def _validate_segment(n_photos: int, ok_deltas: list[float], stalls: int, profile: TimelapseProfile) -> bool:
    if n_photos < profile.min_photos:
        return False
    total_deltas = n_photos - 1
    if total_deltas <= 0:
        return False

    reg_fraction = len(ok_deltas) / total_deltas
    if reg_fraction < profile.min_regular_fraction:
        return False

    stall_fraction = stalls / total_deltas
    if stall_fraction > profile.max_stall_fraction:
        return False

    if len(ok_deltas) >= 2:
        mean_d = statistics.mean(ok_deltas)
        if mean_d > 0:
            stdev_d = statistics.stdev(ok_deltas)
            cv = stdev_d / mean_d
            max_cv = 0.20 if profile.name == "normal" else 0.25
            if cv > max_cv:
                return False

    return True

def _scan_segments(
    photos: list[MediaMetadata],
    shutters: list[float],
    profile: TimelapseProfile,
    skip: set[int]
) -> list[TimelapseSegment]:
    if len(photos) < profile.min_photos:
        return []

    deltas = [
        (photos[k].timestamp - photos[k - 1].timestamp).total_seconds()
        for k in range(1, len(photos))
    ]
    n_deltas = len(deltas)
    segments: list[TimelapseSegment] = []
    i = 0
    W = 8

    while i < n_deltas:
        if i in skip or not profile.eligible(shutters[i]):
            i += 1
            continue

        if (len(photos) - i) < profile.min_photos:
            break

        win_size = min(W, n_deltas - i)
        if win_size < 4:
            break

        window = deltas[i : i + win_size]
        eligible_window = True
        for idx in range(i, i + win_size + 1):
            if idx in skip or not profile.eligible(shutters[idx]):
                eligible_window = False
                break
        if not eligible_window:
            i += 1
            continue

        anchor = statistics.median(window)
        if not (profile.min_interval <= anchor <= profile.max_interval):
            i += 1
            continue

        if profile.name == "long_exposure" and anchor < shutters[i] * 0.9:
            i += 1
            continue

        tol = max(profile.tolerance_min_seconds, anchor * profile.tolerance_ratio)
        reg_count = sum(1 for d in window if abs(d - anchor) <= tol)
        if reg_count < int(win_size * 0.75):
            i += 1
            continue

        j = i
        ok_deltas = []
        stalls = 0
        regular_anchor = anchor

        while j < n_deltas:
            next_photo_idx = j + 1
            if next_photo_idx in skip or not profile.eligible(shutters[next_photo_idx]):
                break

            d = deltas[j]
            if abs(d - regular_anchor) <= tol:
                ok_deltas.append(d)
                if len(ok_deltas) >= 5:
                    cand = statistics.median(ok_deltas[-20:])
                    if abs(cand - anchor) <= anchor * 0.10:
                        regular_anchor = cand
                j += 1
            elif _is_isolated_stall(deltas, j, regular_anchor, tol, profile):
                stalls += 1
                if stalls > max(2, int(profile.max_stall_fraction * (j - i + 1))):
                    break
                j += 1
            else:
                break

        n_photos = j - i + 1
        if _validate_segment(n_photos, ok_deltas, stalls, profile):
            segments.append(TimelapseSegment(i, j, profile))
            i = j + 1
        else:
            i += 1

    return segments

def find_timelapse_segments(photos: list[MediaMetadata], config: dict | None = None) -> list[TimelapseSegment]:
    """
    Identifica segmentos contíguos de fotos da mesma câmera que formam timelapses.
    Separa a detecção em dois perfis independentes:
    1. Longa Exposição (shutter >= min_shutter_seconds): astrofotografia, gaps harmônicos de buffer.
    2. Normal (shutter < min_shutter_seconds): fotos diurnas/gerais com cadência estrita e anti-rajada.
    """
    if not photos or len(photos) < 2:
        return []

    if config is None:
        config = {}

    normal_prof, le_prof, le_enabled = load_profiles(config)
    shutters = [parse_shutter_seconds(p.shutter_str) or 0.0 for p in photos]

    segments: list[TimelapseSegment] = []
    used_photo_indices: set[int] = set()

    # 1. Escanear primeiro por Longa Exposição (mais restritivo / específico)
    if le_enabled:
        le_segments = _scan_segments(photos, shutters, le_prof, skip=set())
        for seg in le_segments:
            segments.append(seg)
            used_photo_indices.update(range(seg.start, seg.end + 1))

    # 2. Escanear em seguida por Normal (fotos gerais / diurnas), pulando fotos já usadas
    normal_segments = _scan_segments(photos, shutters, normal_prof, skip=used_photo_indices)
    segments.extend(normal_segments)

    segments.sort(key=lambda s: s.start)
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

def _classify_timelapse(
    photos: list[MediaMetadata],
    name_config: dict,
    classified: list[ClassifiedItem],
    class_config: dict | None = None,
    profile: TimelapseProfile | None = None
):
    if not photos:
        return
    first = photos[0]
    parts = first.date_str.split("-")
    if len(parts) == 3:
        y, m, d = parts
    else:
        y, m, d = "SemData", "00", "00"

    root_dir = profile.root_dir if profile else "4_Timelapses"
    category = profile.category if profile else "timelapse"

    cam_folder = first.camera_make or "Camera"
    tl_dir = Path(root_dir) / cam_folder / y / m / d / f"timelapse_{first.time_str}"

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
            category=category,
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
                    shutters = [parse_shutter_seconds(p.shutter_str) or 0.0 for p in f_photos]
                    med_shutter = statistics.median(shutters) if shutters else 0.0
                    normal_prof, le_prof, le_enabled = load_profiles(class_config)
                    chosen_prof = le_prof if (le_enabled and med_shutter >= le_prof.min_shutter) else normal_prof
                    _classify_timelapse(f_photos, name_config, classified, class_config=class_config, profile=chosen_prof)
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
                    for seg in segments:
                        start_idx = seg.start
                        end_idx = seg.end
                        if start_idx > cur_idx:
                            _classify_bursts_and_singles(cam_photos[cur_idx:start_idx], class_config, name_config, classified)
                        _classify_timelapse(
                            cam_photos[start_idx:end_idx + 1],
                            name_config,
                            classified,
                            class_config=class_config,
                            profile=seg.profile
                        )
                        cur_idx = end_idx + 1
                    if cur_idx < len(cam_photos):
                        _classify_bursts_and_singles(cam_photos[cur_idx:], class_config, name_config, classified)

    return classified
