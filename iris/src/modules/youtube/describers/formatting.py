import re
import math
import unicodedata
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

from src.core.metadata import parse_shutter_seconds


def format_duration_human(seconds: float) -> str:
    """Formata duração em segundos para texto legível em português."""
    if seconds <= 0:
        return "0 segundos"
    
    total_sec = int(round(seconds))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    secs = total_sec % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours} hora" if hours == 1 else f"{hours} horas")
    if minutes > 0:
        parts.append(f"{minutes} minuto" if minutes == 1 else f"{minutes} minutos")
    if secs > 0 or not parts:
        if not parts and seconds < 60 and seconds != round(seconds):
            return f"{seconds:.1f} segundos"
        parts.append(f"{secs} segundo" if secs == 1 else f"{secs} segundos")

    if len(parts) == 1:
        return parts[0]
    elif len(parts) == 2:
        return f"{parts[0]} e {parts[1]}"
    else:
        return f"{parts[0]}, {parts[1]} e {parts[2]}"


def format_bytes_human(num_bytes: int) -> str:
    """Formata quantidade de bytes em representação legível (B, KB, MB, GB)."""
    if num_bytes <= 0:
        return "0 MB"
    if num_bytes >= 1024**3:
        return f"{num_bytes / (1024**3):.2f} GB"
    elif num_bytes >= 1024**2:
        return f"{num_bytes / (1024**2):.1f} MB"
    elif num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} B"


def _parse_shutter_value(val: str) -> Optional[float]:
    """Converte representações de obturador (ex: '1/1000s', '1-500s', '2s', '0.5s') em segundos (float)."""
    return parse_shutter_seconds(val)


def _parse_iso_value(val: str) -> Optional[int]:
    """Converte representações de ISO (ex: 'ISO100', 'ISO 400', '800') para int."""
    m = re.search(r'\d+', val)
    if m:
        try:
            return int(m.group(0))
        except ValueError:
            pass
    return None


def _parse_aperture_value(val: str) -> Optional[float]:
    """Converte representações de abertura (ex: 'f4.0', 'f/4', 'f5.6') para float."""
    clean = val.lower().replace("f", "").replace("/", "").strip()
    try:
        return float(clean)
    except ValueError:
        return None


def summarize_exposure_param(values: List[str], param_type: str = "generic") -> str:
    """
    Resume uma lista de valores de exposição.
    Se for constante, retorna o valor único (ex: 'f/4.0', '1/125s', 'ISO 100').
    Se variar, calcula o intervalo min-max (ex: '1/1000s – 1/30s', 'ISO 100 – ISO 800').
    """
    valid = [v.strip() for v in values if v and v.strip() and v.strip().lower() != "auto"]
    if not valid:
        return "Automático / Variável"

    unique = sorted(list(set(valid)))
    if len(unique) == 1:
        u = unique[0]
        if param_type == "aperture":
            f_val = _parse_aperture_value(u)
            return f"f/{f_val:.1f}" if f_val is not None else (f"f/{u.lstrip('f').lstrip('/')}")
        elif param_type == "iso":
            iso_num = _parse_iso_value(u)
            return f"ISO {iso_num}" if iso_num is not None else f"ISO {u}"
        return u

    # Múltiplos valores
    if param_type == "iso":
        parsed = [(v, _parse_iso_value(v)) for v in valid]
        with_nums = [(raw, num) for raw, num in parsed if num is not None]
        if with_nums:
            min_raw = min(with_nums, key=lambda x: x[1])[1]
            max_raw = max(with_nums, key=lambda x: x[1])[1]
            if min_raw == max_raw:
                return f"ISO {min_raw}"
            return f"ISO {min_raw} – ISO {max_raw}"

    elif param_type == "aperture":
        parsed = [(v, _parse_aperture_value(v)) for v in valid]
        with_nums = [(raw, num) for raw, num in parsed if num is not None]
        if with_nums:
            min_val = min(with_nums, key=lambda x: x[1])[1]
            max_val = max(with_nums, key=lambda x: x[1])[1]
            if min_val == max_val:
                return f"f/{min_val:.1f}"
            return f"f/{min_val:.1f} – f/{max_val:.1f}"

    elif param_type == "shutter":
        parsed = [(v, _parse_shutter_value(v)) for v in valid]
        with_nums = [(raw, num) for raw, num in parsed if num is not None]
        if with_nums:
            min_item = min(with_nums, key=lambda x: x[1])
            max_item = max(with_nums, key=lambda x: x[1])
            if min_item[1] == max_item[1]:
                return min_item[0]

            def _fmt_s(s_val: float) -> str:
                if s_val < 1.0 and s_val > 0:
                    den = int(round(1.0 / s_val))
                    return f"1/{den}s"
                elif s_val == round(s_val):
                    return f"{int(s_val)}s"
                else:
                    return f"{s_val:.1f}s"
            return f"{_fmt_s(min_item[1])} – {_fmt_s(max_item[1])}"

    return f"{unique[0]} – {unique[-1]}"


def calculate_aspect_ratio(width: Optional[int], height: Optional[int]) -> str:
    """Calcula a proporção da imagem (ex: 4:3, 16:9, 3:2)."""
    if not width or not height or width <= 0 or height <= 0:
        return ""
    g = math.gcd(width, height)
    rx = width // g
    ry = height // g

    # Normalizações para proporções fotográficas comuns
    ratio_val = width / height
    if abs(ratio_val - 4/3) < 0.05:
        return "4:3"
    elif abs(ratio_val - 16/9) < 0.05:
        return "16:9"
    elif abs(ratio_val - 3/2) < 0.05:
        return "3:2"
    elif abs(ratio_val - 1.0) < 0.02:
        return "1:1"
    elif abs(ratio_val - 16/10) < 0.05:
        return "16:10"
    elif abs(ratio_val - 5/4) < 0.05:
        return "5:4"

    return f"{rx}:{ry}"


def sanitize_hashtag(text: str) -> str:
    """Converte um termo ou nome em hashtag limpa (PascalCase, sem acentos, sem espaços ou pontuação)."""
    if not text:
        return ""
    normalized = unicodedata.normalize('NFKD', str(text)).encode('ASCII', 'ignore').decode('utf-8')
    clean = re.sub(r'[^a-zA-Z0-9]+', ' ', normalized).strip()
    if not clean:
        return ""
    words = [w.capitalize() for w in clean.split() if w]
    return "".join(words)


def _extract_temporal_context(video_path: Path, record: Dict[str, Any]) -> Tuple[str, str]:
    """Extrai contexto temporal (data_str e time_str) a partir do nome do arquivo ou metadados."""
    meta = record.get("metadata_json") or {}
    name = video_path.name
    parts = name.split('_')

    date_part = ""
    time_str = ""

    # 1. Tentar extrair do nome do arquivo (ex: 2026-10-09_16h22m-18h35m_... ou 2026-10-23_14-30_...)
    if len(parts) > 0 and re.match(r'^\d{4}-\d{2}-\d{2}$', parts[0]):
        date_part = parts[0]
    
    time_part = parts[1] if len(parts) > 1 else ""

    # Duração total para cálculo de término se necessário
    dur_sec = float(record.get("duration_seconds") or meta.get("final_duration_seconds") or meta.get("total_orig_duration_seconds") or 0.0)

    if "-" in time_part and not time_part.startswith("to-"):
        # Novo formato HH-MM (ex: 14-30) ou intervalo gravado no nome (ex: 16h22m-18h35m)
        if re.match(r'^\d{2}-\d{2}$', time_part):
            t_clean = time_part.replace('-', ':')
            time_str = f"({t_clean})"
        else:
            t1, t2 = time_part.split("-", 1)
            t1_clean = t1.replace('h', ':').replace('m', '')
            t2_clean = t2.replace('h', ':').replace('m', '')
            if t1_clean and t2_clean and t1_clean != t2_clean:
                time_str = f"({t1_clean} - {t2_clean})"
            elif t1_clean:
                time_str = f"({t1_clean})"
    elif time_part and ("h" in time_part or "m" in time_part):
        # Tempo único no nome legado (ex: 14h30m)
        t_clean = time_part.replace('h', ':').replace('m', '')
        if dur_sec >= 60.0 and date_part and re.match(r'^\d{1,2}:\d{2}$', t_clean):
            try:
                dt_start = datetime.strptime(f"{date_part} {t_clean}", "%Y-%m-%d %H:%M")
                dt_end = dt_start + timedelta(seconds=dur_sec)
                t_end = dt_end.strftime("%H:%M")
                if t_end != t_clean:
                    time_str = f"({t_clean} - {t_end})"
                else:
                    time_str = f"({t_clean})"
            except Exception:
                time_str = f"({t_clean})"
        elif t_clean:
            time_str = f"({t_clean})"

    # 2. Fallback caso date_part ou time_str não tenham sido resolvidos pelo nome
    if not date_part or not time_str:
        first_dt = None
        last_dt = None
        if meta.get("first_dt_iso"):
            try:
                first_dt = datetime.fromisoformat(meta["first_dt_iso"])
            except Exception:
                pass
        if meta.get("last_dt_iso"):
            try:
                last_dt = datetime.fromisoformat(meta["last_dt_iso"])
            except Exception:
                pass

        if not first_dt and meta.get("first_dt_formatted"):
            try:
                f_parts = meta["first_dt_formatted"].split(" às ")
                dt_str = f"{f_parts[0]} {f_parts[1]}"
                first_dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M:%S")
            except Exception:
                pass

        if first_dt:
            if not date_part:
                date_part = first_dt.strftime("%Y-%m-%d")
            if not time_str:
                start_hm = first_dt.strftime("%H:%M")
                if last_dt and last_dt.strftime("%H:%M") != start_hm:
                    end_hm = last_dt.strftime("%H:%M")
                    time_str = f"({start_hm} - {end_hm})"
                elif dur_sec >= 60.0:
                    dt_end = first_dt + timedelta(seconds=dur_sec)
                    end_hm = dt_end.strftime("%H:%M")
                    if end_hm != start_hm:
                        time_str = f"({start_hm} - {end_hm})"
                    else:
                        time_str = f"({start_hm})"
                else:
                    time_str = f"({start_hm})"

    if not date_part:
        date_part = datetime.now().strftime("%Y-%m-%d")

    return date_part, time_str
