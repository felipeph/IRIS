import json
import sqlite3
import threading
import dataclasses
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from src.core.config import PROJECTS_DIR, config
from src.core.project_mixins.schema import CURRENT_SCHEMA_VERSION, SHARED_TABLES_DDL

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
    status: str = "pending"  # pending, copied, error
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
    list_open_projects,
    get_last_active_project,
    save_central_timelapse,
    update_central_timelapse_youtube,
    update_central_timelapse_local_deleted,
    list_central_timelapses,
    save_central_edited_video,
    update_central_edited_video_youtube,
    update_central_edited_video_local_deleted,
    list_central_edited_videos,
    save_central_astro_stack,
    list_central_astro_stacks,
    save_central_astro_sharpen,
    list_central_astro_sharpens,
    reconcile_project_with_central,
    reconcile_all_projects_with_central,
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


__all__ = [
    "PROJECTS_DIR",
    "CENTRAL_DB_PATH",
    "CURRENT_SCHEMA_VERSION",
    "SHARED_TABLES_DDL",
    "get_db_connection",
    "get_attached_project_connection",
    "init_central_db",
    "ProjectItem",
    "ITEM_FIELDS",
    "ITEMS_UPSERT_SQL",
    "_serialize_item",
    "_row_to_item",
    "_build_items_filter_query",
    "Project",
    "get_project",
    "create_project",
    "list_open_projects",
    "get_last_active_project",
    "save_central_timelapse",
    "update_central_timelapse_youtube",
    "update_central_timelapse_local_deleted",
    "list_central_timelapses",
    "save_central_edited_video",
    "update_central_edited_video_youtube",
    "update_central_edited_video_local_deleted",
    "list_central_edited_videos",
    "save_central_astro_stack",
    "list_central_astro_stacks",
    "save_central_astro_sharpen",
    "list_central_astro_sharpens",
    "reconcile_project_with_central",
    "reconcile_all_projects_with_central",
]
