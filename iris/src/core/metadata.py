import subprocess
import json
import shutil
import re
import os
import tempfile
from typing import Callable, Optional
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".crw",
    ".arw", ".srf", ".sr2",
    ".nef", ".nrw",
    ".raf",
    ".rw2",
    ".orf", ".ori",
    ".pef", ".ptx",
    ".dng",
    ".rwl",
    ".3fr", ".fff",
    ".iiq",
    ".mrw",
    ".srw",
    ".x3f",
    ".gpr",
    ".raw",
}

STANDARD_PHOTO_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff",
    ".heic", ".heif", ".webp", ".bmp", ".avif",
}

PHOTO_EXTENSIONS = STANDARD_PHOTO_EXTENSIONS | RAW_EXTENSIONS

VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".m4v",
    ".wmv", ".flv", ".webm", ".mts", ".m2ts",
    ".ts", ".3gp", ".insv", ".lrf",
}

@dataclass
class MediaMetadata:
    file_path: Path
    is_video: bool
    date_str: str          # YYYY-MM-DD
    time_str: str          # HH-mm-SS
    timestamp: datetime
    camera_model: str      # e.g. "HERO5-Black", "SX60", "PowerShot-SX60-HS"
    focal_length_equiv: Optional[float] = None # e.g. 1365.0, 50.0
    focal_str: str = ""         # e.g. "1365mm"
    aperture_str: str = ""      # e.g. "f6.5"
    shutter_str: str = ""       # e.g. "1-1000s"
    iso_str: str = ""           # e.g. "ISO400"
    resolution_str: str = ""    # e.g. "16MP" ou "1080p"
    fps_str: str = ""           # e.g. "60fps"
    duration_str: str = ""      # e.g. "01m45s"
    original_stem: str = ""     # e.g. "IMG_1234"
    extension: str = ""         # e.g. "JPG"
    is_raw: bool = False
    camera_make: str = "Cam" # e.g. "GoPro", "Canon", "Sony"
    width: Optional[int] = None
    height: Optional[int] = None

    @property
    def dimensions_str(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return ""

    @property
    def megapixels_str(self) -> str:
        if self.width and self.height and not self.is_video:
            mp = (self.width * self.height) / 1_000_000
            return f"{round(mp)}MP" if mp >= 1 else f"{self.width}x{self.height}"
        return self.resolution_str or ""

def parse_camera_generic(raw_make: str, raw_model: str) -> tuple[str, str, str]:
    """
    Separa e normaliza fabricante (Make) e modelo (Model) de forma totalmente genérica.
    Retorna: (clean_make, clean_model, combined_camera)
    """
    # 1. Pega o primeiro termo do Make (ignora sufixos corporativos como CORP, INC, etc.)
    make = (raw_make or "").split()[0].strip() if raw_make else "Cam"
    model = (raw_model or "").strip() or make

    # 2. Se o modelo já começa com a marca (case-insensitive), remove para não duplicar
    if make.lower() != "cam" and model.lower().startswith(make.lower()):
        model = model[len(make):].strip(" -_")

    # 3. Sanitiza ambos para caracteres seguros de arquivo
    clean_make = re.sub(r"[^\w\-]+", "", make) or "Cam"
    clean_model = re.sub(r"[^\w\-]+", "-", model).strip("-_") or clean_make
    clean_model = re.sub(r"-+", "-", clean_model)

    # 4. Representação combinada para retrocompatibilidade
    if clean_make.lower() == clean_model.lower():
        combined = clean_make
    elif clean_make.lower() in clean_model.lower():
        combined = clean_model
    else:
        combined = f"{clean_make}_{clean_model}"

    return clean_make, clean_model, combined

def sanitize_camera_name(raw_model: str) -> str:
    _, model, _ = parse_camera_generic("", raw_model)
    return model

def format_shutter(exposure_time) -> str:
    if exposure_time is None:
        return "auto"
    try:
        val = float(exposure_time)
        if val <= 0:
            return "auto"
        if val < 1.0:
            frac = round(1.0 / val)
            return f"1-{frac}s"
        else:
            if val.is_integer():
                return f"{int(val)}s"
            return f"{val:.1f}s".replace(".", "-")
    except (ValueError, TypeError):
        s = str(exposure_time).replace("/", "-").replace(".", "-")
        return f"{s}s"

def format_aperture(fnumber) -> str:
    if fnumber is None:
        return "f0"
    try:
        val = float(fnumber)
        if val.is_integer():
            return f"f{int(val)}"
        return f"f{val:.1f}".replace(".", "-")
    except (ValueError, TypeError):
        return f"f{fnumber}".replace(".", "-")

def format_focal(focal_35mm, focal_real) -> tuple[float, str]:
    target = focal_35mm if focal_35mm else focal_real
    if target is None:
        return 0.0, "0mm"
    try:
        clean_num = re.sub(r"[^\d.]", "", str(target))
        val = float(clean_num) if clean_num else 0.0
        return val, f"{round(val)}mm"
    except (ValueError, TypeError):
        return 0.0, "0mm"

def parse_duration_seconds(val) -> float | None:
    """Converte valores brutos de duração (float, int, '0:00:41', '12.34 s', etc.) para float de segundos."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if val > 0 else 0.0
    s = str(val).strip()
    if not s:
        return None
    # Formato de relógio (e.g. "0:00:41", "0:01:48", "01:23:45.67")
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 3:
                h, m, sec = parts
                return float(h) * 3600 + float(m) * 60 + float(sec)
            elif len(parts) == 2:
                m, sec = parts
                return float(m) * 60 + float(sec)
            elif len(parts) == 4:
                d, h, m, sec = parts
                return float(d) * 86400 + float(h) * 3600 + float(m) * 60 + float(sec)
        except (ValueError, TypeError):
            pass
    # Formato numérico ou com unidade (e.g. "12.34 s", "45s")
    s_clean = re.sub(r"[^\d.]", "", s)
    try:
        return float(s_clean) if s_clean else None
    except ValueError:
        return None

def get_video_duration_ffprobe(file_path: Path) -> float | None:
    """Obtém a duração do vídeo diretamente com ffprobe caso o exiftool não a tenha retornado."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None
    try:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path.resolve()),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None

def get_video_dimensions_ffprobe(file_path: Path) -> tuple[int | None, int | None]:
    """Obtém largura e altura do vídeo diretamente com ffprobe caso o exiftool não as tenha retornado."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return None, None
    try:
        cmd = [
            ffprobe_bin,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            str(file_path.resolve()),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0 and proc.stdout.strip():
            parts = proc.stdout.strip().split("x")
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None, None

def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds <= 0:
        return "00s"
    total_sec = max(1, int(round(seconds)))
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    s = total_sec % 60
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    if m > 0:
        return f"{m:02d}m{s:02d}s"
    return f"{s:02d}s"

def extract_metadata_batch(
    file_paths: list[Path],
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> list[MediaMetadata]:
    """Extracts metadata for a batch of files using exiftool in safe chunks with an argfile and ffprobe."""
    if not file_paths:
        return []

    exiftool_bin = shutil.which("exiftool") or ("C:\\Windows\\exiftool.exe" if Path("C:\\Windows\\exiftool.exe").exists() else None)
    results = []

    # Map of path -> raw exif dict
    exif_map: dict[str, dict] = {}

    if exiftool_bin:
        batch_size = 500
        for i in range(0, len(file_paths), batch_size):
            batch = file_paths[i:i + batch_size]
            with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                for p in batch:
                    f.write(f"{p.resolve()}\n")
                argfile = f.name

            try:
                cmd = [
                    exiftool_bin,
                    "-json",
                    "-charset", "filename=utf8",
                    "-DateTimeOriginal",
                    "-CreateDate",
                    "-ModifyDate",
                    "-Model",
                    "-Make",
                    "-FocalLengthIn35mmFormat",
                    "-FocalLength",
                    "-FNumber",
                    "-ExposureTime",
                    "-ISO",
                    "-ImageWidth",
                    "-ImageHeight",
                    "-Duration#",
                    "-Duration",
                    "-VideoFrameRate",
                    "-@",
                    argfile,
                ]

                proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if proc.returncode == 0 and proc.stdout:
                    parsed = json.loads(proc.stdout)
                    for item in parsed:
                        src_file = Path(item.get("SourceFile", "")).resolve()
                        exif_map[str(src_file)] = item
                elif proc.returncode != 0 and proc.stderr:
                    print(f"[WARN] Erro no exiftool lote {i}-{i+len(batch)}: {proc.stderr[:150]}")
            except Exception as e:
                print(f"[WARN] Falha ao rodar exiftool em lote ({i}-{i+len(batch)}): {e}")
            finally:
                try:
                    os.unlink(argfile)
                except OSError:
                    pass

            if progress_callback:
                cur_name = batch[-1].name if batch else ""
                try:
                    progress_callback(min(i + len(batch), len(file_paths)), len(file_paths), cur_name)
                except TypeError:
                    progress_callback(min(i + len(batch), len(file_paths)), len(file_paths))

    for p in file_paths:
        p_res = p.resolve()
        ext = p.suffix.lower()
        is_video = ext in VIDEO_EXTENSIONS
        is_raw = ext in RAW_EXTENSIONS
        raw_exif = exif_map.get(str(p_res), {})

        # Date parsing
        date_raw = raw_exif.get("DateTimeOriginal") or raw_exif.get("CreateDate") or raw_exif.get("ModifyDate")
        dt = None
        if date_raw:
            try:
                # Exif dates are usually "YYYY:MM:DD HH:MM:SS"
                clean_dt = str(date_raw)[:19].replace("-", ":")
                dt = datetime.strptime(clean_dt, "%Y:%m:%d %H:%M:%S")
            except Exception:
                pass
        
        if dt is None:
            # Fallback to the oldest between file mtime and ctime
            stat = p.stat()
            oldest_time = min(stat.st_mtime, stat.st_ctime)
            dt = datetime.fromtimestamp(oldest_time)

        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H-%M-%S")

        # Camera
        raw_make = raw_exif.get("Make") or ""
        raw_model = raw_exif.get("Model") or ""
        cam_make, cam_model, _ = parse_camera_generic(raw_make, raw_model)

        # Focal
        focal_val, focal_str = format_focal(
            raw_exif.get("FocalLengthIn35mmFormat"),
            raw_exif.get("FocalLength")
        )

        # Aperture
        aperture_str = format_aperture(raw_exif.get("FNumber"))

        # Shutter
        shutter_str = format_shutter(raw_exif.get("ExposureTime"))

        # ISO
        iso_raw = raw_exif.get("ISO")
        iso_str = f"ISO{iso_raw}" if iso_raw else "auto"

        # Resolution / Duration / FPS
        w_raw = raw_exif.get("ImageWidth")
        h_raw = raw_exif.get("ImageHeight")
        width = None
        height = None
        if w_raw is not None:
            try:
                width = int(round(float(w_raw)))
            except (ValueError, TypeError):
                width = None
        if h_raw is not None:
            try:
                height = int(round(float(h_raw)))
            except (ValueError, TypeError):
                height = None

        if (width is None or height is None) and is_video and p.exists():
            ff_w, ff_h = get_video_dimensions_ffprobe(p)
            if width is None:
                width = ff_w
            if height is None:
                height = ff_h

        res_str = ""
        fps_str = ""
        dur_str = ""

        if is_video:
            # Check video duration / fps
            dur_raw = raw_exif.get("Duration")
            dur_sec = parse_duration_seconds(dur_raw)
            if (dur_sec is None or dur_sec <= 0) and p.exists():
                dur_sec = get_video_duration_ffprobe(p)
            
            dur_str = format_duration(dur_sec)
            
            fps_raw = raw_exif.get("VideoFrameRate")
            if fps_raw:
                try:
                    fps_str = f"{round(float(fps_raw))}fps"
                except ValueError:
                    fps_str = f"{fps_raw}fps"
            else:
                fps_str = "30fps"

            if height:
                if height >= 2160:
                    res_str = "4K"
                elif height >= 1080:
                    res_str = "1080p"
                elif height >= 720:
                    res_str = "720p"
                else:
                    res_str = f"{height}p"
            else:
                res_str = "1080p"
        else:
            if width and height:
                mp = (width * height) / 1_000_000
                res_str = f"{round(mp)}MP" if mp >= 1 else f"{width}x{height}"
            else:
                res_str = ""

        meta = MediaMetadata(
            file_path=p,
            is_video=is_video,
            date_str=date_str,
            time_str=time_str,
            timestamp=dt,
            camera_model=cam_model,
            camera_make=cam_make,
            focal_length_equiv=focal_val,
            focal_str=focal_str,
            aperture_str=aperture_str,
            shutter_str=shutter_str,
            iso_str=iso_str,
            resolution_str=res_str,
            fps_str=fps_str,
            duration_str=dur_str,
            original_stem=p.stem,
            extension=p.suffix.lstrip(".").upper(),
            is_raw=is_raw,
            width=width,
            height=height,
        )
        results.append(meta)

    return results
