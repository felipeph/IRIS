"""
ProjectBase Mixin (RFC 09).
Gerencia metadados, ciclo de vida do projeto, inicialização do banco SQLite,
transações aninhadas e dual-write atômico.
"""

import sqlite3
import threading
from pathlib import Path
from typing import Optional, Any


class _ProjectTransactionContext:
    """Gerencia transações atômicas seguras no SQLite com suporte a aninhamento (SAVEPOINT)."""

    def __init__(self, project: Any):
        self.project = project
        self._is_top_level = False
        self._sp_name = ""

    def __enter__(self):
        conn = self.project._get_active_conn()
        if conn is None:
            self._is_top_level = True
            import src.core.project as p_mod
            conn = p_mod.get_db_connection(self.project._project_db_file)
            conn.execute("BEGIN IMMEDIATE;")
            self.project._set_active_conn(conn)
        else:
            self._is_top_level = False
            depth = self.project._increment_tx_depth()
            self._sp_name = f"sp_{depth}"
            conn.execute(f"SAVEPOINT {self._sp_name};")
        return self.project

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        conn = self.project._get_active_conn()
        if conn is None:
            return False

        try:
            if exc_type is not None:
                if self._is_top_level:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                else:
                    if self._sp_name:
                        try:
                            conn.execute(f"ROLLBACK TO {self._sp_name};")
                            conn.execute(f"RELEASE {self._sp_name};")
                        except Exception:
                            pass
            else:
                if self._is_top_level:
                    conn.commit()
                else:
                    if self._sp_name:
                        conn.execute(f"RELEASE {self._sp_name};")
        finally:
            if self._is_top_level:
                try:
                    conn.close()
                finally:
                    self.project._clear_active_conn()
            else:
                self.project._decrement_tx_depth()

        return False


class ProjectBase:
    """Mixin base de ciclo de vida e gerenciamento do SQLite do Projeto."""

    def __init__(self, name: str, source_path: str = ""):
        self.name = name
        self.source_path = source_path
        self.current_stage_id = ""
        self.total_source_files = 0
        self.total_source_size_bytes = 0
        self.auto_cleanup: bool = False
        self._db_initialized: bool = False
        self._tx_local = threading.local()

    @property
    def project_dir(self) -> Path:
        """Diretório de trabalho e artefatos dedicados a este projeto."""
        import src.core.project as p_mod
        d = p_mod.PROJECTS_DIR / self.name
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def _project_db_file(self) -> Path:
        import src.core.project as p_mod
        return p_mod.PROJECTS_DIR / f"{self.name}.db"

    def _get_active_conn(self) -> Optional[sqlite3.Connection]:
        return getattr(self._tx_local, "conn", None)

    def _set_active_conn(self, conn: sqlite3.Connection):
        self._tx_local.conn = conn
        self._tx_local.depth = 1

    def _clear_active_conn(self):
        self._tx_local.conn = None
        self._tx_local.depth = 0

    def _increment_tx_depth(self) -> int:
        depth = getattr(self._tx_local, "depth", 1) + 1
        self._tx_local.depth = depth
        return depth

    def _decrement_tx_depth(self) -> int:
        depth = max(1, getattr(self._tx_local, "depth", 1) - 1)
        self._tx_local.depth = depth
        return depth

    def _ensure_db_initialized(self):
        """Garante inicialização do esquema sem chamadas redundantes ao filesystem."""
        if not getattr(self, "_db_initialized", False):
            self._init_project_db()

    def transaction(self) -> _ProjectTransactionContext:
        """Context manager para agrupar operações em uma transação única no SQLite."""
        return _ProjectTransactionContext(self)

    def _execute_dual_write(self, main_sql: str, main_params: tuple, central_sql: str, central_params: tuple):
        """Executa gravação atômica simultânea no banco do projeto e no banco central via ATTACH DATABASE (RFC 08)."""
        self._ensure_db_initialized()
        import src.core.project as p_mod
        active_conn = self._get_active_conn()
        if active_conn is not None:
            active_conn.execute(main_sql, main_params)
            if self._project_db_file.resolve() != p_mod.CENTRAL_DB_PATH.resolve():
                try:
                    active_conn.execute(central_sql, central_params)
                except sqlite3.OperationalError:
                    pass
            return

        with p_mod.get_attached_project_connection(self._project_db_file, p_mod.CENTRAL_DB_PATH) as conn:
            conn.execute("BEGIN IMMEDIATE;")
            try:
                conn.execute(main_sql, main_params)
                if self._project_db_file.resolve() != p_mod.CENTRAL_DB_PATH.resolve():
                    conn.execute(central_sql, central_params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _init_project_db(self, force: bool = False):
        if getattr(self, "_db_initialized", False) and not force and self._project_db_file.exists():
            return

        import src.core.project as p_mod
        with p_mod.get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version")
            db_version = cursor.fetchone()[0]

            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS items (
                    {", ".join(p_mod.ITEM_FIELDS)}
                )
            """)

            cursor.execute("PRAGMA table_info(items)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            for col in p_mod.ITEM_FIELDS:
                if col not in existing_cols:
                    if col == "verified":
                        cursor.execute("ALTER TABLE items ADD COLUMN verified INTEGER DEFAULT 0")
                    elif col in ("meta_is_video", "meta_is_raw"):
                        cursor.execute(f"ALTER TABLE items ADD COLUMN {col} INTEGER DEFAULT 0")
                    elif col in ("file_size_bytes", "meta_duration_seconds", "meta_width", "meta_height"):
                        cursor.execute(f"ALTER TABLE items ADD COLUMN {col} INTEGER DEFAULT 0")
                    elif col == "meta_fps":
                        cursor.execute(f"ALTER TABLE items ADD COLUMN {col} REAL DEFAULT 0.0")
                    else:
                        cursor.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT DEFAULT ''")

            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_original_path ON items(original_path)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_status ON items(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_category ON items(category)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_items_status_verified ON items(status, verified)")

            for ddl in p_mod.SHARED_TABLES_DDL:
                cursor.execute(ddl)

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

            cursor.execute(f"PRAGMA user_version = {p_mod.CURRENT_SCHEMA_VERSION}")
            conn.commit()

        self._db_initialized = True

    def save_metadata(self):
        """Salva metadados do projeto no banco central."""
        import src.core.project as p_mod
        p_mod.init_central_db()
        with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
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
        import src.core.project as p_mod
        if not p_mod.CENTRAL_DB_PATH.exists():
            return False
        with p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source_path, current_stage_id, total_source_files, total_source_size_bytes, auto_cleanup FROM projects WHERE name=?", (self.name,))
            row = cursor.fetchone()
            if row:
                self.source_path, self.current_stage_id, self.total_source_files, self.total_source_size_bytes = row[0], row[1], row[2], row[3]
                self.auto_cleanup = bool(row[4]) if len(row) > 4 and row[4] is not None else False
                self._init_project_db()
                return True
            return False

    def touch(self):
        """Atualiza a data de acesso do projeto no banco central."""
        self.save_metadata()

    def save(self):
        """Salva metadados do projeto."""
        self.save_metadata()
