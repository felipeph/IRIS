import os
import json
import shutil
import ctypes
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor

def prepare_numbered_sequence(
    photo_paths: List[Path],
    target_dir: Path,
    is_test: bool = False,
    test_sample_size: int = 120
) -> Tuple[bool, Path, List[Path]]:
    """
    Prepara uma sequência numerada em pasta temporária via Hardlinks (zero-copy)
    com fallback transparente para cópia física, pronta para o demuxer image2 do FFmpeg.
    Retorna (sucesso, temp_dir, fotos_ordenadas).
    """
    if not photo_paths:
        return False, target_dir, []

    # Ordenar por nome ou data
    sorted_photos = sorted(photo_paths, key=lambda p: p.name)
    if is_test and test_sample_size > 0:
        sorted_photos = sorted_photos[:test_sample_size]

    temp_sequence_dir = target_dir / ".temp_sequence"

    # Limpar qualquer sequência temporária anterior
    if temp_sequence_dir.exists():
        try:
            shutil.rmtree(temp_sequence_dir, ignore_errors=True)
        except Exception:
            pass

    temp_sequence_dir.mkdir(parents=True, exist_ok=True)

    # Ocultar pasta no Windows
    if os.name == 'nt':
        try:
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(str(temp_sequence_dir), FILE_ATTRIBUTE_HIDDEN)
        except Exception:
            pass

    use_hardlinks = True
    hardlink_count = 0
    copy_count = 0

    for idx, src_path in enumerate(sorted_photos, start=1):
        dst_path = temp_sequence_dir / f"{idx:06d}.jpg"
        if use_hardlinks:
            try:
                os.link(str(src_path), str(dst_path))
                hardlink_count += 1
            except OSError:
                use_hardlinks = False
                shutil.copy2(str(src_path), str(dst_path))
                copy_count += 1
        else:
            shutil.copy2(str(src_path), str(dst_path))
            copy_count += 1

    # Salva metadados de apoio
    info_path = temp_sequence_dir / "sequence_info.json"
    try:
        with open(info_path, "w", encoding="utf-8") as f:
            json.dump({
                "count": len(sorted_photos),
                "first_photo": str(sorted_photos[0].resolve()),
                "last_photo": str(sorted_photos[-1].resolve()),
                "hardlinks": hardlink_count,
                "copies": copy_count
            }, f, indent=2)
    except Exception:
        pass

    return True, temp_sequence_dir, sorted_photos

def clean_sequence_dir(temp_sequence_dir: Path):
    """Remove a pasta temporária de sequência e seus links/arquivos com segurança."""
    if temp_sequence_dir and temp_sequence_dir.exists():
        try:
            shutil.rmtree(temp_sequence_dir, ignore_errors=True)
        except Exception:
            pass
