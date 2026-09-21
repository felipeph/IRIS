import re
from pathlib import Path
from src.core.metadata import MediaMetadata

def sanitize_filename(name: str) -> str:
    # Replace illegal Windows filename chars and dots with hyphen
    clean = re.sub(r'[\\/*?:"<>|.]', "-", name)
    # Replace any spaces with hyphen
    clean = re.sub(r"\s+", "-", clean)
    # Remove multiple consecutive underscores or hyphens
    clean = re.sub(r"_+", "_", clean)
    clean = re.sub(r"-+", "-", clean)
    clean = clean.replace("-_", "_").replace("_-", "_")
    return clean.strip("._- ")

def clean_original_stem(original: str, meta: MediaMetadata) -> str:
    cleaned = original
    
    tokens_to_remove = []
    if meta.date_str: 
        tokens_to_remove.append(meta.date_str)
        tokens_to_remove.append(meta.date_str.replace("-", ""))
    if meta.time_str: 
        tokens_to_remove.append(meta.time_str)
        tokens_to_remove.append(meta.time_str.replace("-", ""))
    if meta.camera_model and meta.camera_model != "Cam": tokens_to_remove.append(meta.camera_model)
    if meta.camera_make and meta.camera_make != "Cam": tokens_to_remove.append(meta.camera_make)
    if meta.dimensions_str: tokens_to_remove.append(meta.dimensions_str)
    if meta.resolution_str: tokens_to_remove.append(meta.resolution_str)
    if meta.fps_str: tokens_to_remove.append(meta.fps_str)
    if meta.duration_str: tokens_to_remove.append(meta.duration_str)
    
    # Sort by length descending to remove longer overlapping strings first
    tokens_to_remove.sort(key=len, reverse=True)
    
    for token in tokens_to_remove:
        # Replaces exact matches with a space (to keep boundaries distinct)
        cleaned = re.compile(re.escape(token), re.IGNORECASE).sub(" ", cleaned)

    # Regex for common date/time formats that might not exactly match EXIF
    # Matches YYYY-MM-DD or YYYYMMDD
    cleaned = re.sub(r"(?<!\d)\d{4}[-_]?\d{2}[-_]?\d{2}(?!\d)", " ", cleaned)
    # Matches HH-MM-SS or HH_MM_SS (requires delimiters to avoid matching random 6 digits)
    cleaned = re.sub(r"(?<!\d)\d{2}[-_]\d{2}[-_]\d{2}(?!\d)", " ", cleaned)

    return cleaned

def generate_target_filename(meta: MediaMetadata, config: dict | None = None) -> str:
    if config is None:
        config = {}

    cleaned_stem = clean_original_stem(meta.original_stem, meta)
    original_clean = re.sub(r"[^A-Za-z0-9_-]", "", cleaned_stem)
    # Strip any separators that formed at the ends after stripping
    original_clean = original_clean.strip("-_")

    make = getattr(meta, "camera_make", "Cam") or "Cam"
    model = meta.camera_model or "Cam"
    if make == "Cam" or make.lower() == model.lower() or make.lower() in model.lower():
        camera_str = model
    else:
        camera_str = f"{make}_{model}"

    width_val = getattr(meta, "width", None)
    height_val = getattr(meta, "height", None)
    width_str = str(width_val) if width_val is not None else ""
    height_str = str(height_val) if height_val is not None else ""
    dimensions_str = getattr(meta, "dimensions_str", "") or (f"{width_str}x{height_str}" if (width_str and height_str) else "")
    megapixels_str = getattr(meta, "megapixels_str", "") or (meta.resolution_str or "")

    if meta.is_video:
        pattern = config.get("video_pattern", "{date}_{time}_{camera}_{resolution}_{fps}_{duration}_{original}.{ext}")
        res = pattern.format(
            date=meta.date_str,
            time=meta.time_str,
            camera=camera_str,
            make=make,
            model=model,
            camera_make=make,
            camera_model=model,
            resolution=meta.resolution_str or "1080p",
            width=width_str,
            height=height_str,
            dimensions=dimensions_str,
            megapixels=megapixels_str,
            mp=megapixels_str,
            fps=meta.fps_str or "30fps",
            duration=meta.duration_str or "00s",
            original=original_clean,
            ext=meta.extension.lower(),
        )
    else:
        # Photo
        pattern = config.get("photo_pattern", "{date}_{time}_{camera}_{focal}_{aperture}_{shutter}_{iso}_{original}.{ext}")
        res = pattern.format(
            date=meta.date_str,
            time=meta.time_str,
            camera=camera_str,
            make=make,
            model=model,
            camera_make=make,
            camera_model=model,
            focal=meta.focal_str or "",
            aperture=meta.aperture_str or "",
            shutter=meta.shutter_str or "",
            iso=meta.iso_str or "",
            resolution=meta.resolution_str or "",
            megapixels=megapixels_str,
            mp=megapixels_str,
            width=width_str,
            height=height_str,
            dimensions=dimensions_str,
            original=original_clean,
            ext=meta.extension.lower(),
        )

    # Split name and ext to sanitize base name
    dot_idx = res.rfind(".")
    if dot_idx != -1:
        base = res[:dot_idx]
        ext = res[dot_idx + 1:]
    else:
        base = res
        ext = meta.extension.lower()

    base_clean = sanitize_filename(base)
    return f"{base_clean}.{ext}"
