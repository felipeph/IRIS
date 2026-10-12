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
                local_file_deleted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            cursor.execute("ALTER TABLE timelapses ADD COLUMN metadata_json TEXT DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE timelapses ADD COLUMN local_file_deleted INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS edited_videos (
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
            )
        """)
        try:
            cursor.execute("ALTER TABLE edited_videos ADD COLUMN local_file_deleted INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS astro_stacks (
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
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS astro_sharpens (
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
            )
        """)
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
                    local_file_deleted INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                cursor.execute("ALTER TABLE timelapses ADD COLUMN metadata_json TEXT DEFAULT '{}'")
            except sqlite3.OperationalError:
                pass
            try:
                cursor.execute("ALTER TABLE timelapses ADD COLUMN local_file_deleted INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS edited_videos (
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
                )
            """)
            try:
                cursor.execute("ALTER TABLE edited_videos ADD COLUMN local_file_deleted INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS astro_stacks (
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
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS astro_sharpens (
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
                )
            """)
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
                d["local_file_deleted"] = bool(d.get("local_file_deleted", 0))
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

    def mark_timelapse_local_deleted(self, video_path: str):
        """Marca no banco do projeto e banco central que o arquivo local do timelapse foi excluído."""
        if not self._project_db_file.exists():
            return
        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE timelapses
                SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
                WHERE output_video_path=?
            """, (video_path,))
            conn.commit()
        update_central_timelapse_local_deleted(video_path)

    def save_edited_video(self, record: Dict[str, Any]):
        """Salva ou atualiza um vídeo editado no banco do projeto e no banco central."""
        self._init_project_db()
        record_copy = dict(record)
        record_copy["project_name"] = self.name
        
        meta = record_copy.get("metadata_json", {})
        meta_json_str = json.dumps(meta) if isinstance(meta, dict) else str(meta)
        src_paths = record_copy.get("source_video_paths", record_copy.get("source_files", []))
        src_paths_str = json.dumps(src_paths) if isinstance(src_paths, list) else str(src_paths)
        
        speed_val = record_copy.get("speed_factor", record_copy.get("speed", 1.0))
        res_val = record_copy.get("target_resolution", record_copy.get("resolution", "3840x2160"))
        trim_start = record_copy.get("trim_start_sec", record_copy.get("trim_seconds", 0.0))
        trim_end = record_copy.get("trim_end_sec", record_copy.get("trim_seconds", 0.0))
        audio_strip = record_copy.get("audio_stripped", not record_copy.get("has_audio", True))

        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO edited_videos (
                    project_name, source_video_paths, output_video_path, mode, clip_count,
                    speed_factor, orig_fps, target_fps, orig_resolution, target_resolution,
                    trim_start_sec, trim_end_sec, audio_stripped, duration_seconds, encoder,
                    youtube_video_id, youtube_url, youtube_privacy, status, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                self.name,
                src_paths_str,
                record_copy.get("output_video_path", ""),
                record_copy.get("mode", "individual"),
                record_copy.get("clip_count", 1),
                speed_val,
                record_copy.get("orig_fps", 30.0),
                record_copy.get("target_fps", 60.0),
                record_copy.get("orig_resolution", "1920x1080"),
                res_val,
                trim_start,
                trim_end,
                1 if audio_strip else 0,
                record_copy.get("duration_seconds", 0.0),
                record_copy.get("encoder", ""),
                record_copy.get("youtube_video_id", ""),
                record_copy.get("youtube_url", ""),
                record_copy.get("youtube_privacy", "unlisted"),
                record_copy.get("status", "rendered"),
                meta_json_str
            ))
            conn.commit()
            
        save_central_edited_video(record_copy)

    def get_edited_videos(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera todos os vídeos editados do projeto (opcionalmente filtrando por status)."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        with get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM edited_videos WHERE status=? ORDER BY created_at ASC", (status,))
            else:
                cursor.execute("SELECT * FROM edited_videos ORDER BY created_at ASC")
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

    def update_edited_video_youtube(self, video_path: str, video_id: str, url: str):
        """Atualiza o link/ID do YouTube do vídeo editado no banco do projeto e no banco central."""
        if not self._project_db_file.exists():
            return
        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE edited_videos
                SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
                WHERE output_video_path=?
            """, (video_id, url, video_path))
            conn.commit()
        update_central_edited_video_youtube(video_path, video_id, url)

    def mark_edited_video_local_deleted(self, video_path: str):
        """Marca no banco do projeto e banco central que o arquivo local do vídeo editado foi excluído."""
        if not self._project_db_file.exists():
            return
        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE edited_videos
                SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
                WHERE output_video_path=?
            """, (video_path,))
            conn.commit()
        update_central_edited_video_local_deleted(video_path)

    def add_astro_stack(self, record: Dict[str, Any]):
        """Registra uma sessão de empilhamento lunar no banco do projeto e no banco central."""
        self._init_project_db()
        record_copy = dict(record)
        record_copy["project_name"] = self.name
        
        keep_percents = record_copy.get("keep_percents", [])
        if isinstance(keep_percents, (list, tuple)):
            keep_percents_str = json.dumps(list(keep_percents))
        else:
            keep_percents_str = str(keep_percents)
            
        out_paths = record_copy.get("output_tiff_paths_json", {})
        if isinstance(out_paths, (dict, list)):
            out_paths_str = json.dumps(out_paths)
        else:
            out_paths_str = str(out_paths)
            
        meta_val = record_copy.get("metadata_json", {})
        meta_json_str = json.dumps(meta_val) if isinstance(meta_val, dict) else str(meta_val)

        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
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
                self.name,
                record_copy.get("session_dir", ""),
                record_copy.get("raw_count", 0),
                keep_percents_str,
                record_copy.get("output_dir", ""),
                out_paths_str,
                record_copy.get("crop_size", 0),
                record_copy.get("shared_gain", 1.0),
                record_copy.get("status", "stacked"),
                meta_json_str,
                record_copy.get("elapsed_seconds", 0.0)
            ))
            conn.commit()
            
        save_central_astro_stack(record_copy)

    def get_astro_stacks(self, session_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera sessões de empilhamento registradas no projeto."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        with get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if session_dir:
                cursor.execute("SELECT * FROM astro_stacks WHERE project_name=? AND session_dir=? ORDER BY created_at DESC", (self.name, session_dir))
            else:
                cursor.execute("SELECT * FROM astro_stacks WHERE project_name=? ORDER BY created_at DESC", (self.name,))
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

    def is_astro_session_stacked(self, session_dir: str) -> bool:
        """Verifica se uma sessão lunar já foi empilhada com sucesso."""
        stacks = self.get_astro_stacks(session_dir)
        return any(s.get("status") in ("stacked", "done", "success", "completed") for s in stacks)

    def add_astro_sharpen(self, record: Dict[str, Any]):
        """Registra uma imagem aprimorada por wavelets no banco do projeto e no central."""
        self._init_project_db()
        record_copy = dict(record)
        record_copy["project_name"] = self.name
        
        meta_val = record_copy.get("metadata_json", {})
        meta_json_str = json.dumps(meta_val) if isinstance(meta_val, dict) else str(meta_val)

        with get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
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
                self.name,
                record_copy.get("source_stack_path", ""),
                record_copy.get("preset", ""),
                record_copy.get("output_tiff_path", ""),
                record_copy.get("output_png_path", ""),
                record_copy.get("status", "sharpened"),
                meta_json_str,
                record_copy.get("elapsed_seconds", 0.0)
            ))
            conn.commit()
            
        save_central_astro_sharpen(record_copy)

    def get_astro_sharpens(self, source_stack_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera imagens com sharpening registradas no projeto."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        with get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if source_stack_path:
                cursor.execute("SELECT * FROM astro_sharpens WHERE project_name=? AND source_stack_path=? ORDER BY created_at DESC", (self.name, source_stack_path))
            else:
                cursor.execute("SELECT * FROM astro_sharpens WHERE project_name=? ORDER BY created_at DESC", (self.name,))
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



