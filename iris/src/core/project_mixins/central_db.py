"""
Repositório e Reconciliador do Banco Central (`iris_central.db`).
Consulta dinamicamente `src.core.project` para respeitar redirecionamentos de
`CENTRAL_DB_PATH` e `PROJECTS_DIR` realizados pela suíte de testes.
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional


def list_open_projects() -> List[str]:
    """Lista todos os projetos salvos no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return []
        
    projects = []
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM projects ORDER BY created_at DESC")
            for row in cursor.fetchall():
                projects.append(row[0])
        except sqlite3.OperationalError:
            pass
    return projects


def get_last_active_project() -> Optional[str]:
    """Recupera o nome do último projeto ativo/atualizado no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return None
    try:
        with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM projects ORDER BY updated_at DESC, rowid DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def save_central_timelapse(record: dict):
    """Registra ou atualiza um timelapse no banco central."""
    import src.core.project as p_mod
    p_mod.init_central_db()
    
    raw_meta = record.get("metadata_json", {})
    if isinstance(raw_meta, (dict, list)):
        meta_json_str = json.dumps(raw_meta, ensure_ascii=False)
    elif isinstance(raw_meta, str):
        meta_json_str = raw_meta
    else:
        meta_json_str = "{}"

    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO timelapses (
                project_name, sequence_dir, output_video_path, photo_count,
                fps, frames_per_image, resolution, crop_mode, encoder,
                duration_seconds, speedup_factor, youtube_video_id, youtube_url,
                youtube_privacy, status, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(output_video_path) DO UPDATE SET
                photo_count=excluded.photo_count,
                fps=excluded.fps,
                frames_per_image=excluded.frames_per_image,
                resolution=excluded.resolution,
                crop_mode=excluded.crop_mode,
                encoder=excluded.encoder,
                duration_seconds=excluded.duration_seconds,
                speedup_factor=excluded.speedup_factor,
                youtube_video_id=COALESCE(excluded.youtube_video_id, timelapses.youtube_video_id),
                youtube_url=COALESCE(excluded.youtube_url, timelapses.youtube_url),
                youtube_privacy=COALESCE(excluded.youtube_privacy, timelapses.youtube_privacy),
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
        """, (
            record.get("project_name", ""),
            record.get("sequence_dir", ""),
            record.get("output_video_path", ""),
            record.get("photo_count", 0),
            record.get("fps", 60),
            record.get("frames_per_image", 1),
            record.get("resolution", "3840x2160"),
            record.get("crop_mode", "bottom"),
            record.get("encoder", ""),
            record.get("duration_seconds", 0.0),
            record.get("speedup_factor", 1),
            record.get("youtube_video_id", ""),
            record.get("youtube_url", ""),
            record.get("youtube_privacy", "unlisted"),
            record.get("status", "rendered"),
            meta_json_str
        ))
        conn.commit()


def update_central_timelapse_youtube(video_path: str, video_id: str, url: str):
    """Atualiza o link/ID do YouTube do timelapse no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE timelapses
            SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_id, url, video_path))
        conn.commit()


def update_central_timelapse_local_deleted(video_path: str):
    """Marca no banco central que o arquivo local do timelapse foi excluído."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE timelapses
            SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_path,))
        conn.commit()


def list_central_timelapses(project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista timelapses cadastrados no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return []
    results = []
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if project_name:
            cursor.execute("SELECT * FROM timelapses WHERE project_name=? ORDER BY created_at DESC", (project_name,))
        else:
            cursor.execute("SELECT * FROM timelapses ORDER BY created_at DESC")
        for row in cursor.fetchall():
            d = dict(row)
            raw_meta = d.get("metadata_json")
            if isinstance(raw_meta, str) and raw_meta:
                try:
                    d["metadata_json"] = json.loads(raw_meta)
                except Exception:
                    d["metadata_json"] = {}
            elif not isinstance(raw_meta, dict):
                d["metadata_json"] = {}
            d["local_file_deleted"] = bool(d.get("local_file_deleted", 0))
            results.append(d)
    return results


def save_central_edited_video(record: Dict[str, Any]):
    """Salva ou atualiza um vídeo editado no banco central de dados."""
    import src.core.project as p_mod
    p_mod.init_central_db()
    meta = record.get("metadata_json", {})
    meta_json_str = json.dumps(meta) if isinstance(meta, dict) else str(meta)
    
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        src_paths = record.get("source_video_paths", record.get("source_files", []))
        src_paths_str = json.dumps(src_paths) if isinstance(src_paths, list) else str(src_paths)
        
        speed_val = record.get("speed_factor", record.get("speed", 1.0))
        res_val = record.get("target_resolution", record.get("resolution", "3840x2160"))
        trim_start = record.get("trim_start_sec", record.get("trim_seconds", 0.0))
        trim_end = record.get("trim_end_sec", record.get("trim_seconds", 0.0))
        audio_strip = record.get("audio_stripped", not record.get("has_audio", True))

        cursor.execute("""
            INSERT INTO edited_videos (
                project_name, source_video_paths, output_video_path, mode, clip_count,
                speed_factor, orig_fps, target_fps, orig_resolution, target_resolution,
                trim_start_sec, trim_end_sec, audio_stripped, duration_seconds, encoder,
                youtube_video_id, youtube_url, youtube_privacy, status, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(output_video_path) DO UPDATE SET
                mode=excluded.mode,
                clip_count=excluded.clip_count,
                speed_factor=excluded.speed_factor,
                orig_fps=excluded.orig_fps,
                target_fps=excluded.target_fps,
                orig_resolution=excluded.orig_resolution,
                target_resolution=excluded.target_resolution,
                trim_start_sec=excluded.trim_start_sec,
                trim_end_sec=excluded.trim_end_sec,
                audio_stripped=excluded.audio_stripped,
                duration_seconds=excluded.duration_seconds,
                encoder=excluded.encoder,
                youtube_video_id=COALESCE(excluded.youtube_video_id, edited_videos.youtube_video_id),
                youtube_url=COALESCE(excluded.youtube_url, edited_videos.youtube_url),
                youtube_privacy=COALESCE(excluded.youtube_privacy, edited_videos.youtube_privacy),
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
        """, (
            record.get("project_name", ""),
            src_paths_str,
            record.get("output_video_path", ""),
            record.get("mode", "individual"),
            record.get("clip_count", 1),
            speed_val,
            record.get("orig_fps", 30.0),
            record.get("target_fps", 60.0),
            record.get("orig_resolution", "1920x1080"),
            res_val,
            trim_start,
            trim_end,
            1 if audio_strip else 0,
            record.get("duration_seconds", 0.0),
            record.get("encoder", ""),
            record.get("youtube_video_id", ""),
            record.get("youtube_url", ""),
            record.get("youtube_privacy", "unlisted"),
            record.get("status", "rendered"),
            meta_json_str
        ))
        conn.commit()


def update_central_edited_video_youtube(video_path: str, video_id: str, url: str):
    """Atualiza o link/ID do YouTube do vídeo editado no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE edited_videos
            SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_id, url, video_path))
        conn.commit()


def update_central_edited_video_local_deleted(video_path: str):
    """Marca no banco central que o arquivo local do vídeo editado foi excluído."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE edited_videos
            SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_path,))
        conn.commit()


def list_central_edited_videos(project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista vídeos editados cadastrados no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return []
    results = []
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if project_name:
            cursor.execute("SELECT * FROM edited_videos WHERE project_name=? ORDER BY created_at DESC", (project_name,))
        else:
            cursor.execute("SELECT * FROM edited_videos ORDER BY created_at DESC")
        for row in cursor.fetchall():
            d = dict(row)
            d["speed"] = d.get("speed_factor", 1.0)
            d["resolution"] = d.get("target_resolution", "3840x2160")
            d["trim_seconds"] = d.get("trim_start_sec", 0.0)
            d["has_audio"] = 1 if not d.get("audio_stripped", 0) else 0
            raw_meta = d.get("metadata_json")
            if isinstance(raw_meta, str) and raw_meta:
                try:
                    d["metadata_json"] = json.loads(raw_meta)
                except Exception:
                    d["metadata_json"] = {}
            elif not isinstance(raw_meta, dict):
                d["metadata_json"] = {}
            
            raw_src = d.get("source_video_paths")
            if isinstance(raw_src, str) and raw_src:
                try:
                    d["source_video_paths"] = json.loads(raw_src)
                except Exception:
                    d["source_video_paths"] = [raw_src]
            d["local_file_deleted"] = bool(d.get("local_file_deleted", 0))
            results.append(d)
    return results


def save_central_astro_stack(record: Dict[str, Any]):
    """Salva/atualiza uma sessão de empilhamento no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        p_mod.init_central_db()
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        keep_percents = record.get("keep_percents", [])
        keep_percents_str = json.dumps(list(keep_percents)) if isinstance(keep_percents, (list, tuple)) else str(keep_percents)
        out_paths = record.get("output_tiff_paths_json", {})
        out_paths_str = json.dumps(out_paths) if isinstance(out_paths, (dict, list)) else str(out_paths)
        meta_val = record.get("metadata_json", {})
        meta_json_str = json.dumps(meta_val) if isinstance(meta_val, dict) else str(meta_val)
        
        cursor.execute("""
            INSERT INTO astro_stacks (
                project_name, session_dir, raw_count, keep_percents, output_dir,
                output_tiff_paths_json, crop_size, shared_gain, status, metadata_json, elapsed_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_name, session_dir) DO UPDATE SET
                raw_count=excluded.raw_count,
                keep_percents=excluded.keep_percents,
                output_dir=excluded.output_dir,
                output_tiff_paths_json=excluded.output_tiff_paths_json,
                crop_size=excluded.crop_size,
                shared_gain=excluded.shared_gain,
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                elapsed_seconds=excluded.elapsed_seconds,
                updated_at=CURRENT_TIMESTAMP
        """, (
            record.get("project_name", ""),
            record.get("session_dir", ""),
            record.get("raw_count", 0),
            keep_percents_str,
            record.get("output_dir", ""),
            out_paths_str,
            record.get("crop_size", 0),
            record.get("shared_gain", 1.0),
            record.get("status", "stacked"),
            meta_json_str,
            record.get("elapsed_seconds", 0.0)
        ))
        conn.commit()


def list_central_astro_stacks(project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista sessões de empilhamento cadastradas no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return []
    results = []
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if project_name:
            cursor.execute("SELECT * FROM astro_stacks WHERE project_name=? ORDER BY created_at DESC", (project_name,))
        else:
            cursor.execute("SELECT * FROM astro_stacks ORDER BY created_at DESC")
        for row in cursor.fetchall():
            d = dict(row)
            for json_col in ("keep_percents", "output_tiff_paths_json", "metadata_json"):
                val = d.get(json_col)
                if isinstance(val, str) and val:
                    try:
                        d[json_col] = json.loads(val)
                    except Exception:
                        pass
            results.append(d)
    return results


def save_central_astro_sharpen(record: Dict[str, Any]):
    """Salva/atualiza uma imagem com sharpening no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        p_mod.init_central_db()
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        meta_val = record.get("metadata_json", {})
        meta_json_str = json.dumps(meta_val) if isinstance(meta_val, dict) else str(meta_val)
        cursor.execute("""
            INSERT INTO astro_sharpens (
                project_name, source_stack_path, preset, output_tiff_path, output_png_path,
                status, metadata_json, elapsed_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(output_tiff_path) DO UPDATE SET
                preset=excluded.preset,
                output_png_path=excluded.output_png_path,
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                elapsed_seconds=excluded.elapsed_seconds,
                updated_at=CURRENT_TIMESTAMP
        """, (
            record.get("project_name", ""),
            record.get("source_stack_path", ""),
            record.get("preset", ""),
            record.get("output_tiff_path", ""),
            record.get("output_png_path", ""),
            record.get("status", "sharpened"),
            meta_json_str,
            record.get("elapsed_seconds", 0.0)
        ))
        conn.commit()


def list_central_astro_sharpens(project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista imagens com sharpening cadastradas no banco central."""
    import src.core.project as p_mod
    if not p_mod.CENTRAL_DB_PATH.exists():
        return []
    results = []
    with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if project_name:
            cursor.execute("SELECT * FROM astro_sharpens WHERE project_name=? ORDER BY created_at DESC", (project_name,))
        else:
            cursor.execute("SELECT * FROM astro_sharpens ORDER BY created_at DESC")
        for row in cursor.fetchall():
            d = dict(row)
            val = d.get("metadata_json")
            if isinstance(val, str) and val:
                try:
                    d["metadata_json"] = json.loads(val)
                except Exception:
                    pass
            results.append(d)
    return results


def reconcile_project_with_central(
    project_name: str,
    project_db_file: Optional[Path] = None,
    central_db_file: Optional[Path] = None,
) -> Dict[str, int]:
    """
    Reconcilia registros entre o banco local do projeto e o banco central (RFC 08).
    Garante sincronização bidirecional/auto-cura em caso de falhas prévias.
    Retorna contagem de registros sincronizados por tabela.
    """
    import src.core.project as p_mod
    if project_db_file is None:
        project_db_file = p_mod.PROJECTS_DIR / f"{project_name}.db"
    if central_db_file is None:
        central_db_file = p_mod.CENTRAL_DB_PATH

    if not project_db_file.exists():
        return {}

    p_mod.init_central_db()
    stats = {"timelapses": 0, "edited_videos": 0, "astro_stacks": 0, "astro_sharpens": 0}

    if project_db_file.resolve() == central_db_file.resolve():
        return stats

    with p_mod.get_attached_project_connection(project_db_file, central_db_file) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO central.timelapses (
                project_name, sequence_dir, output_video_path, photo_count,
                fps, frames_per_image, resolution, crop_mode, encoder,
                duration_seconds, speedup_factor, youtube_video_id, youtube_url,
                youtube_privacy, status, metadata_json, local_file_deleted, created_at, updated_at
            )
            SELECT 
                project_name, sequence_dir, output_video_path, photo_count,
                fps, frames_per_image, resolution, crop_mode, encoder,
                duration_seconds, speedup_factor, youtube_video_id, youtube_url,
                youtube_privacy, status, metadata_json, local_file_deleted, created_at, updated_at
            FROM main.timelapses
        """)
        stats["timelapses"] = cursor.rowcount

        cursor.execute("""
            INSERT OR REPLACE INTO central.edited_videos (
                project_name, source_video_paths, output_video_path, mode,
                clip_count, speed_factor, orig_fps, target_fps, orig_resolution,
                target_resolution, trim_start_sec, trim_end_sec, audio_stripped,
                duration_seconds, encoder, youtube_video_id, youtube_url,
                youtube_privacy, status, metadata_json, local_file_deleted, created_at, updated_at
            )
            SELECT
                project_name, source_video_paths, output_video_path, mode,
                clip_count, speed_factor, orig_fps, target_fps, orig_resolution,
                target_resolution, trim_start_sec, trim_end_sec, audio_stripped,
                duration_seconds, encoder, youtube_video_id, youtube_url,
                youtube_privacy, status, metadata_json, local_file_deleted, created_at, updated_at
            FROM main.edited_videos
        """)
        stats["edited_videos"] = cursor.rowcount

        cursor.execute("""
            INSERT OR REPLACE INTO central.astro_stacks (
                project_name, session_dir, raw_count, keep_percents, output_dir,
                output_tiff_paths_json, crop_size, shared_gain, status, metadata_json, elapsed_seconds, created_at, updated_at
            )
            SELECT
                project_name, session_dir, raw_count, keep_percents, output_dir,
                output_tiff_paths_json, crop_size, shared_gain, status, metadata_json, elapsed_seconds, created_at, updated_at
            FROM main.astro_stacks
        """)
        stats["astro_stacks"] = cursor.rowcount

        cursor.execute("""
            INSERT OR REPLACE INTO central.astro_sharpens (
                project_name, source_stack_path, preset, output_tiff_path, output_png_path,
                status, metadata_json, elapsed_seconds, created_at, updated_at
            )
            SELECT
                project_name, source_stack_path, preset, output_tiff_path, output_png_path,
                status, metadata_json, elapsed_seconds, created_at, updated_at
            FROM main.astro_sharpens
        """)
        stats["astro_sharpens"] = cursor.rowcount

        cursor.execute("""
            INSERT OR REPLACE INTO central.bird_identifications (
                project_name, item_path, is_video, species_common, species_scientific,
                confidence, top2_common, top2_scientific, top2_confidence,
                top3_common, top3_scientific, top3_confidence, needs_review,
                crop_saved_path, metadata_json, created_at, updated_at
            )
            SELECT
                project_name, item_path, is_video, species_common, species_scientific,
                confidence, top2_common, top2_scientific, top2_confidence,
                top3_common, top3_scientific, top3_confidence, needs_review,
                crop_saved_path, metadata_json, created_at, updated_at
            FROM main.bird_identifications
        """)
        stats["bird_identifications"] = cursor.rowcount

        conn.commit()

    return stats


def reconcile_all_projects_with_central(central_db_file: Optional[Path] = None) -> Dict[str, Dict[str, int]]:
    """Reconcilia todos os projetos locais existentes com o banco central."""
    import src.core.project as p_mod
    if not p_mod.PROJECTS_DIR.exists():
        return {}
    results = {}
    for db_path in p_mod.PROJECTS_DIR.glob("*.db"):
        if db_path.name == "iris_central.db":
            continue
        project_name = db_path.stem
        results[project_name] = reconcile_project_with_central(
            project_name, project_db_file=db_path, central_db_file=central_db_file
        )
    return results

