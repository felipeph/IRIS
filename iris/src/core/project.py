import json
import sqlite3
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

def init_central_db():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    with get_db_connection(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                name TEXT PRIMARY KEY,
                source_path TEXT,
                current_stage_id TEXT,
                total_source_files INTEGER,
                total_source_size_bytes INTEGER,
                auto_cleanup INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
                updated_at TIMESTAMP DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now'))
            )
        """)
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN auto_cleanup INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS timelapses (
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            cursor.execute("ALTER TABLE timelapses ADD COLUMN metadata_json TEXT DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
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

    # Organization fields
    category: str = ""
    target_filename: str = ""
    relative_dest_dir: str = ""
    extra_dest_dirs_json: str = "[]"
    organized_path: str = ""
    extra_organized_paths_json: str = "[]"
    
    @classmethod
    def from_dict(cls, data: dict) -> "ProjectItem":
        return cls(**data)

class Project:
    """Gerencia o estado de um projeto de ingestão e processamento."""
    
    def __init__(self, name: str, source_path: str = ""):
        self.name = name
        self.source_path = source_path
        self.current_stage_id = ""
        self.total_source_files = 0
        self.total_source_size_bytes = 0
        self.auto_cleanup: bool = False
        
        self._project_db_file = PROJECTS_DIR / f"{self.name}.db"

    def _init_project_db(self):
        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            
            # Destructive migration: Se houver coluna metadata_json, deleta a tabela!
            try:
                cursor.execute("SELECT metadata_json FROM items LIMIT 1")
                cursor.execute("DROP TABLE items")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    original_path TEXT PRIMARY KEY,
                    staging_path TEXT,
                    status TEXT,
                    file_size_bytes INTEGER,
                    file_hash TEXT,
                    verified INTEGER,
                    meta_is_video INTEGER,
                    meta_date_str TEXT,
                    meta_time_str TEXT,
                    meta_timestamp TEXT,
                    meta_camera_model TEXT,
                    meta_camera_make TEXT,
                    meta_focal_length_equiv REAL,
                    meta_focal_str TEXT,
                    meta_aperture_str TEXT,
                    meta_shutter_str TEXT,
                    meta_iso_str TEXT,
                    meta_resolution_str TEXT,
                    meta_fps_str TEXT,
                    meta_duration_str TEXT,
                    meta_original_stem TEXT,
                    meta_extension TEXT,
                    meta_is_raw INTEGER,
                    meta_width INTEGER,
                    meta_height INTEGER,
                    category TEXT DEFAULT '',
                    target_filename TEXT DEFAULT '',
                    relative_dest_dir TEXT DEFAULT '',
                    extra_dest_dirs_json TEXT DEFAULT '[]',
                    organized_path TEXT DEFAULT '',
                    extra_organized_paths_json TEXT DEFAULT '[]'
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS timelapses (
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                cursor.execute("ALTER TABLE timelapses ADD COLUMN metadata_json TEXT DEFAULT '{}'")
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def save_metadata(self):
        """Salva metadados do projeto no banco central."""
        init_central_db()
        with get_db_connection(CENTRAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO projects (name, source_path, current_stage_id, total_source_files, total_source_size_bytes, auto_cleanup, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%d %H:%M:%f', 'now'))
                ON CONFLICT(name) DO UPDATE SET
                    source_path=excluded.source_path,
                    current_stage_id=excluded.current_stage_id,
                    total_source_files=excluded.total_source_files,
                    total_source_size_bytes=excluded.total_source_size_bytes,
                    auto_cleanup=excluded.auto_cleanup,
                    updated_at=strftime('%Y-%m-%d %H:%M:%f', 'now')
            """, (self.name, self.source_path, self.current_stage_id, self.total_source_files, self.total_source_size_bytes, int(self.auto_cleanup)))
            conn.commit()
            
    def load_metadata(self) -> bool:
        """Carrega metadados do banco central. Retorna True se sucesso."""
        if not CENTRAL_DB_PATH.exists():
            return False
        with get_db_connection(CENTRAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source_path, current_stage_id, total_source_files, total_source_size_bytes, auto_cleanup FROM projects WHERE name=?", (self.name,))
            row = cursor.fetchone()
            if row:
                self.source_path, self.current_stage_id, self.total_source_files, self.total_source_size_bytes = row[0], row[1], row[2], row[3]
                self.auto_cleanup = bool(row[4]) if len(row) > 4 and row[4] is not None else False
                self._init_project_db()
                return True
            return False

    def get_items(self) -> List[ProjectItem]:
        """Recupera todos os itens do banco de dados do projeto."""
        if not self._project_db_file.exists():
            return []
        items = []
        with get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items")
            for row in cursor.fetchall():
                d = dict(row)
                d['verified'] = bool(d['verified'])
                if d['meta_is_video'] is not None: d['meta_is_video'] = bool(d['meta_is_video'])
                if d['meta_is_raw'] is not None: d['meta_is_raw'] = bool(d['meta_is_raw'])
                items.append(ProjectItem.from_dict(d))
        return items

    def save_item(self, item: ProjectItem):
        """Salva ou atualiza um item no banco do projeto atomicamente."""
        self._init_project_db()
        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            d = asdict(item)
            d['verified'] = int(d['verified'])
            if d['meta_is_video'] is not None: d['meta_is_video'] = int(d['meta_is_video'])
            if d['meta_is_raw'] is not None: d['meta_is_raw'] = int(d['meta_is_raw'])
            
            columns = list(d.keys())
            placeholders = ", ".join(["?"] * len(columns))
            updates = ", ".join([f"{c}=excluded.{c}" for c in columns if c != "original_path"])
            
            sql = f"""
                INSERT INTO items ({", ".join(columns)})
                VALUES ({placeholders})
                ON CONFLICT(original_path) DO UPDATE SET
                    {updates}
            """
            cursor.execute(sql, tuple(d.values()))
            conn.commit()

    def get_item(self, original_path: str) -> Optional[ProjectItem]:
        """Busca um item especifico no banco pelo original_path."""
        if not self._project_db_file.exists():
            return None
        with get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE original_path=?", (original_path,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                d['verified'] = bool(d['verified'])
                if d['meta_is_video'] is not None: d['meta_is_video'] = bool(d['meta_is_video'])
                if d['meta_is_raw'] is not None: d['meta_is_raw'] = bool(d['meta_is_raw'])
                return ProjectItem.from_dict(d)
        return None
            
    @property
    def items(self) -> List[ProjectItem]:
        # Retorna os itens carregados para manter compatibilidade de leitura com códigos antigos
        return self.get_items()
        
    @items.setter
    def items(self, value: List[ProjectItem]):
        # O setter da propriedade fará upsert
        for item in value:
            self.save_item(item)

    def touch(self):
        """Atualiza a data de acesso do projeto no banco central."""
        self.save_metadata()

    def save(self):
        # Para compatibilidade com códigos que apenas chamavam p.save() para salvar metadados
        self.save_metadata()

    def save_timelapse(self, record: dict):
        """Salva ou atualiza um timelapse no banco do projeto e sincroniza no banco central."""
        self._init_project_db()
        record_copy = dict(record)
        record_copy["project_name"] = self.name
        
        raw_meta = record_copy.get("metadata_json", {})
        if isinstance(raw_meta, (dict, list)):
            meta_json_str = json.dumps(raw_meta, ensure_ascii=False)
        elif isinstance(raw_meta, str):
            meta_json_str = raw_meta
        else:
            meta_json_str = "{}"
        
        with get_db_connection(self._project_db_file) as conn:
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
                self.name,
                record_copy.get("sequence_dir", ""),
                record_copy.get("output_video_path", ""),
                record_copy.get("photo_count", 0),
                record_copy.get("fps", 60),
                record_copy.get("frames_per_image", 1),
                record_copy.get("resolution", "3840x2160"),
                record_copy.get("crop_mode", "bottom"),
                record_copy.get("encoder", ""),
                record_copy.get("duration_seconds", 0.0),
                record_copy.get("speedup_factor", 1),
                record_copy.get("youtube_video_id", ""),
                record_copy.get("youtube_url", ""),
                record_copy.get("youtube_privacy", "unlisted"),
                record_copy.get("status", "rendered"),
                meta_json_str
            ))
            conn.commit()
            
        save_central_timelapse(record_copy)

    def get_timelapses(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera todos os timelapses do projeto (opcionalmente filtrando por status)."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        with get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM timelapses WHERE status=? ORDER BY created_at ASC", (status,))
            else:
                cursor.execute("SELECT * FROM timelapses ORDER BY created_at ASC")
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
                results.append(d)
        return results

    def update_timelapse_youtube(self, video_path: str, video_id: str, url: str):
        """Atualiza o link/ID do YouTube do timelapse no banco do projeto e no banco central."""
        if not self._project_db_file.exists():
            return
        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE timelapses
                SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
                WHERE output_video_path=?
            """, (video_id, url, video_path))
            conn.commit()
        update_central_timelapse_youtube(video_path, video_id, url)


def get_project(name: str) -> Optional[Project]:
    """Recupera um projeto existente ou retorna None."""
    p = Project(name)
    if p.load_metadata():
        return p
    return None

def create_project(name: str, source_path: str, auto_cleanup: Optional[bool] = None) -> Project:
    """Cria e salva um novo projeto."""
    p = Project(name, source_path)
    if auto_cleanup is None:
        p.auto_cleanup = bool(config.get("modules.cleanup.auto_clean", False))
    else:
        p.auto_cleanup = bool(auto_cleanup)
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


