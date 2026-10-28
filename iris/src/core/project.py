import json
import sqlite3
import threading
import dataclasses
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from src.core.config import PROJECTS_DIR, config

# Database Central
CENTRAL_DB_PATH = PROJECTS_DIR / "iris_central.db"

def get_db_connection(db_path: Path, timeout: float = 30.0) -> sqlite3.Connection:
    """Cria conexão SQLite otimizada para concorrência com WAL mode e timeout configurado."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn

def get_attached_project_connection(project_db_path: Path, central_db_path: Optional[Path] = None, timeout: float = 30.0) -> sqlite3.Connection:
    """Retorna uma conexão SQLite com o banco do projeto como 'main' e o banco central anexado como 'central' (RFC 08)."""
    init_central_db()
    c_path = central_db_path if central_db_path is not None else CENTRAL_DB_PATH
    conn = get_db_connection(project_db_path, timeout=timeout)
    if project_db_path.resolve() != c_path.resolve():
        try:
            conn.execute("ATTACH DATABASE ? AS central;", (str(c_path.resolve()),))
        except sqlite3.OperationalError as e:
            if "already in use" not in str(e).lower() and "already being used" not in str(e).lower():
                raise
    return conn

CURRENT_SCHEMA_VERSION = 2

SHARED_TABLES_DDL = [
    """CREATE TABLE IF NOT EXISTS timelapses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT,
        sequence_dir TEXT,
        output_video_path TEXT UNIQUE,
        photo_count INTEGER,
        fps INTEGER,
        frames_per_image INTEGER,
        resolution TEXT,
        crop_mode TEXT,
        encoder TEXT,
        duration_seconds REAL,
        speedup_factor INTEGER,
        youtube_video_id TEXT,
        youtube_url TEXT,
        youtube_privacy TEXT,
        status TEXT,
        metadata_json TEXT DEFAULT '{}',
        local_file_deleted INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS edited_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT,
        source_video_paths TEXT,
        output_video_path TEXT UNIQUE,
        mode TEXT,
        clip_count INTEGER DEFAULT 1,
        speed_factor REAL DEFAULT 1.0,
        orig_fps REAL,
        target_fps REAL,
        orig_resolution TEXT,
        target_resolution TEXT,
        trim_start_sec REAL DEFAULT 0.0,
        trim_end_sec REAL DEFAULT 0.0,
        audio_stripped INTEGER DEFAULT 0,
        duration_seconds REAL,
        encoder TEXT,
        youtube_video_id TEXT,
        youtube_url TEXT,
        youtube_privacy TEXT,
        status TEXT DEFAULT 'rendered',
        metadata_json TEXT DEFAULT '{}',
        local_file_deleted INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS astro_stacks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT,
        session_dir TEXT,
        raw_count INTEGER,
        keep_percents TEXT,
        output_dir TEXT,
        output_tiff_paths_json TEXT DEFAULT '{}',
        crop_size INTEGER,
        shared_gain REAL,
        status TEXT DEFAULT 'stacked',
        metadata_json TEXT DEFAULT '{}',
        elapsed_seconds REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_name, session_dir)
    )""",
    """CREATE TABLE IF NOT EXISTS astro_sharpens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT,
        source_stack_path TEXT,
        preset TEXT,
        output_tiff_path TEXT UNIQUE,
        output_png_path TEXT,
        status TEXT DEFAULT 'sharpened',
        metadata_json TEXT DEFAULT '{}',
        elapsed_seconds REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS bird_identifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT,
        item_path TEXT,
        is_video INTEGER DEFAULT 0,
        species_common TEXT,
        species_scientific TEXT,
        confidence REAL,
        top2_common TEXT,
        top2_scientific TEXT,
        top2_confidence REAL,
        top3_common TEXT,
        top3_scientific TEXT,
        top3_confidence REAL,
        needs_review INTEGER DEFAULT 0,
        crop_saved_path TEXT,
        metadata_json TEXT DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(project_name, item_path)
    )""",
    """CREATE TABLE IF NOT EXISTS species_catalog (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        species_common TEXT NOT NULL,
        species_scientific TEXT NOT NULL UNIQUE,
        species_common_en TEXT DEFAULT '',
        family TEXT DEFAULT '',
        order_name TEXT DEFAULT '',
        use_count INTEGER DEFAULT 1,
        source TEXT DEFAULT 'historical',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )"""
]


def init_central_db(force: bool = False):
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    with get_db_connection(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        row = cursor.fetchone()
        ver = row[0] if row else 0

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                name TEXT PRIMARY KEY,
                source_path TEXT,
                current_stage_id TEXT,
                total_source_files INTEGER,
                total_source_size_bytes INTEGER,
                auto_cleanup INTEGER DEFAULT 0,
                geo_location_id TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
                updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
            )
        """)
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN auto_cleanup INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN geo_location_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        for ddl in SHARED_TABLES_DDL:
            cursor.execute(ddl)

        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_species_catalog_names ON species_catalog(species_common, species_scientific)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_species_catalog_usage ON species_catalog(use_count DESC)")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE timelapses ADD COLUMN metadata_json TEXT DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE timelapses ADD COLUMN local_file_deleted INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE edited_videos ADD COLUMN local_file_deleted INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        if ver < CURRENT_SCHEMA_VERSION or force:
            cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        conn.commit()

init_central_db()

@dataclass
class ProjectItem:
    """Representa um arquivo sendo processado no projeto."""
    original_path: str
    staging_path: str
    status: str = "pending" # pending, copied, error
    file_size_bytes: int = 0
    file_hash: str = ""
    verified: bool = False
    
    # Metadata fields (Normalized)
    meta_is_video: Optional[bool] = None
    meta_date_str: str = ""
    meta_time_str: str = ""
    meta_timestamp: str = ""
    meta_camera_model: str = ""
    meta_camera_make: str = ""
    meta_focal_length_equiv: Optional[float] = None
    meta_focal_str: str = ""
    meta_aperture_str: str = ""
    meta_shutter_str: str = ""
    meta_iso_str: str = ""
    meta_resolution_str: str = ""
    meta_fps_str: str = ""
    meta_duration_str: str = ""
    meta_original_stem: str = ""
    meta_extension: str = ""
    meta_is_raw: Optional[bool] = None
    meta_width: Optional[int] = None
    meta_height: Optional[int] = None
    meta_latitude: Optional[float] = None
    meta_longitude: Optional[float] = None
    meta_gps_accuracy: Optional[float] = None
    geo_source: str = ""
    geo_written: bool = False

    # Organization fields
    category: str = ""
    target_filename: str = ""
    relative_dest_dir: str = ""
    extra_dest_dirs_json: str = "[]"
    organized_path: str = ""
    extra_organized_paths_json: str = "[]"
    burst_id: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProjectItem":
        valid = getattr(cls, "_valid_fields", None)
        if valid is None:
            valid = {f.name for f in dataclasses.fields(cls)}
            cls._valid_fields = valid
        return cls(**{k: v for k, v in data.items() if k in valid})

ITEM_FIELDS = [f.name for f in dataclasses.fields(ProjectItem)]
_ITEM_PLACEHOLDERS = ", ".join(["?"] * len(ITEM_FIELDS))
_ITEM_UPDATES = ", ".join([f"{c}=excluded.{c}" for c in ITEM_FIELDS if c != "original_path"])
ITEMS_UPSERT_SQL = f"""
    INSERT INTO items ({", ".join(ITEM_FIELDS)})
    VALUES ({_ITEM_PLACEHOLDERS})
    ON CONFLICT(original_path) DO UPDATE SET
        {_ITEM_UPDATES}
"""

def _serialize_item(item: ProjectItem) -> tuple:
    vals = []
    for f in ITEM_FIELDS:
        v = getattr(item, f)
        if f in ("verified", "geo_written"):
            vals.append(int(v))
        elif f in ("meta_is_video", "meta_is_raw") and v is not None:
            vals.append(int(v))
        elif f in ("meta_latitude", "meta_longitude", "meta_gps_accuracy") and v is not None:
            vals.append(float(v))
        else:
            vals.append(v)
    return tuple(vals)

def _row_to_item(row: sqlite3.Row) -> ProjectItem:
    """Deserializa uma linha SQLite em instância de ProjectItem."""
    d = dict(row)
    d['verified'] = bool(d['verified'])
    if d.get('geo_written') is not None:
        d['geo_written'] = bool(d['geo_written'])
    if d.get('meta_is_video') is not None:
        d['meta_is_video'] = bool(d['meta_is_video'])
    if d.get('meta_is_raw') is not None:
        d['meta_is_raw'] = bool(d['meta_is_raw'])
    if d.get('meta_latitude') is not None:
        d['meta_latitude'] = float(d['meta_latitude'])
    if d.get('meta_longitude') is not None:
        d['meta_longitude'] = float(d['meta_longitude'])
    if d.get('meta_gps_accuracy') is not None:
        d['meta_gps_accuracy'] = float(d['meta_gps_accuracy'])
    return ProjectItem.from_dict(d)

def _build_items_filter_query(
    base_sql: str,
    status: Optional[str] = None,
    category: Optional[str] = None,
    verified: Optional[bool] = None,
    limit: Optional[int] = None,
    burst_id: Optional[str] = None,
) -> tuple[str, list]:
    """Constrói dinamicamente cláusula WHERE parametrizada para filtros na tabela items."""
    conditions = []
    params = []
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if category is not None:
        conditions.append("category = ?")
        params.append(category)
    if verified is not None:
        conditions.append("verified = ?")
        params.append(1 if verified else 0)
    if burst_id is not None:
        conditions.append("burst_id = ?")
        params.append(burst_id)

    sql = base_sql
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql, params

from src.core.project_mixins import (
    ProjectBase,
    _ProjectTransactionContext,
    ProjectItemsMixin,
    ProjectMediaMixin,
    ProjectAstroMixin,
    ProjectBirdsMixin,
)

class Project(ProjectBase, ProjectItemsMixin, ProjectMediaMixin, ProjectAstroMixin, ProjectBirdsMixin):
    """Gerencia o estado de um projeto de ingestão e processamento (RFC 09 decomposto em mixins modulares)."""
    pass



def get_project(name: str) -> Optional[Project]:
    """Recupera um projeto existente ou retorna None."""
    p = Project(name)
    if p.load_metadata():
        return p
    return None

def create_project(name: str, source_path: str, auto_cleanup: Optional[bool] = None, geo_location_id: Optional[str] = None) -> Project:
    """Cria e salva um novo projeto."""
    p = Project(name, source_path)
    if auto_cleanup is None:
        p.auto_cleanup = bool(config.get("modules.cleanup.auto_clean", False))
    else:
        p.auto_cleanup = bool(auto_cleanup)

    if geo_location_id is None:
        from src.core.geo import GeoService
        p.geo_location_id = GeoService.get_default_location_id()
    else:
        p.geo_location_id = str(geo_location_id)

    p.save_metadata()
    p._init_project_db()
    return p

def list_open_projects() -> List[str]:
    """Lista todos os projetos salvos no banco central."""
    if not CENTRAL_DB_PATH.exists():
        return []
        
    projects = []
    with get_db_connection(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM projects ORDER BY created_at DESC")
            for row in cursor.fetchall():
                projects.append(row[0])
        except sqlite3.OperationalError:
            pass
    return projects

def save_central_timelapse(record: dict):
    """Registra ou atualiza um timelapse no banco central."""
    init_central_db()
    
    raw_meta = record.get("metadata_json", {})
    if isinstance(raw_meta, (dict, list)):
        meta_json_str = json.dumps(raw_meta, ensure_ascii=False)
    elif isinstance(raw_meta, str):
        meta_json_str = raw_meta
    else:
        meta_json_str = "{}"

    with get_db_connection(CENTRAL_DB_PATH) as conn:
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
    if not CENTRAL_DB_PATH.exists():
        return
    with get_db_connection(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE timelapses
            SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_id, url, video_path))
        conn.commit()

def update_central_timelapse_local_deleted(video_path: str):
    """Marca no banco central que o arquivo local do timelapse foi excluído."""
    if not CENTRAL_DB_PATH.exists():
        return
    with get_db_connection(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE timelapses
            SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_path,))
        conn.commit()

def list_central_timelapses(project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista timelapses cadastrados no banco central."""
    if not CENTRAL_DB_PATH.exists():
        return []
    results = []
    with get_db_connection(CENTRAL_DB_PATH) as conn:
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
    init_central_db()
    meta = record.get("metadata_json", {})
    meta_json_str = json.dumps(meta) if isinstance(meta, dict) else str(meta)
    src_paths = record.get("source_video_paths", [])
    src_paths_str = json.dumps(src_paths) if isinstance(src_paths, list) else str(src_paths)
    
    with get_db_connection(CENTRAL_DB_PATH) as conn:
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
    if not CENTRAL_DB_PATH.exists():
        return
    with get_db_connection(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE edited_videos
            SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_id, url, video_path))
        conn.commit()

def update_central_edited_video_local_deleted(video_path: str):
    """Marca no banco central que o arquivo local do vídeo editado foi excluído."""
    if not CENTRAL_DB_PATH.exists():
        return
    with get_db_connection(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE edited_videos
            SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """, (video_path,))
        conn.commit()

def list_central_edited_videos(project_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """Lista vídeos editados cadastrados no banco central."""
    if not CENTRAL_DB_PATH.exists():
        return []
    results = []
    with get_db_connection(CENTRAL_DB_PATH) as conn:
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

def get_last_active_project() -> Optional[str]:
    """Recupera o nome do último projeto ativo/atualizado no banco central."""
    if not CENTRAL_DB_PATH.exists():
        return None
    try:
        with get_db_connection(CENTRAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM projects ORDER BY updated_at DESC, rowid DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception:
        return None


def save_central_astro_stack(record: Dict[str, Any]):
    """Salva/atualiza uma sessão de empilhamento no banco central."""
    if not CENTRAL_DB_PATH.exists():
        init_central_db()
    with get_db_connection(CENTRAL_DB_PATH) as conn:
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
    if not CENTRAL_DB_PATH.exists():
        return []
    results = []
    with get_db_connection(CENTRAL_DB_PATH) as conn:
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
    if not CENTRAL_DB_PATH.exists():
        init_central_db()
    with get_db_connection(CENTRAL_DB_PATH) as conn:
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
    if not CENTRAL_DB_PATH.exists():
        return []
    results = []
    with get_db_connection(CENTRAL_DB_PATH) as conn:
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
    if project_db_file is None:
        project_db_file = PROJECTS_DIR / f"{project_name}.db"
    if central_db_file is None:
        central_db_file = CENTRAL_DB_PATH

    if not project_db_file.exists():
        return {}

    init_central_db()
    stats = {"timelapses": 0, "edited_videos": 0, "astro_stacks": 0, "astro_sharpens": 0}

    # Se forem o mesmo arquivo físico, nada a reconciliar
    if project_db_file.resolve() == central_db_file.resolve():
        return stats

    with get_attached_project_connection(project_db_file, central_db_file) as conn:
        cursor = conn.cursor()
        
        # 1. Timelapses: Copia do local para o central os ausentes ou atualizados
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

        # 2. Edited videos
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

        # 3. Astro stacks
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

        # 4. Astro sharpens
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

        # 5. Bird identifications
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
    if not PROJECTS_DIR.exists():
        return {}
    results = {}
    for db_path in PROJECTS_DIR.glob("*.db"):
        if db_path.name == "iris_central.db":
            continue
        project_name = db_path.stem
        results[project_name] = reconcile_project_with_central(
            project_name, project_db_file=db_path, central_db_file=central_db_file
        )
    return results




