import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

from src.core.config import PROJECTS_DIR

# Database Central
CENTRAL_DB_PATH = PROJECTS_DIR / "iris_central.db"

def init_central_db():
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                name TEXT PRIMARY KEY,
                source_path TEXT,
                current_stage_id TEXT,
                total_source_files INTEGER,
                total_source_size_bytes INTEGER,
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
        
        self._project_db_file = PROJECTS_DIR / f"{self.name}.db"

    def _init_project_db(self):
        with sqlite3.connect(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    original_path TEXT PRIMARY KEY,
                    staging_path TEXT,
                    status TEXT,
                    file_size_bytes INTEGER,
                    file_hash TEXT,
                    verified INTEGER
                )
            """)
            conn.commit()

    def save_metadata(self):
        """Salva metadados do projeto no banco central."""
        with sqlite3.connect(CENTRAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO projects (name, source_path, current_stage_id, total_source_files, total_source_size_bytes, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    source_path=excluded.source_path,
                    current_stage_id=excluded.current_stage_id,
                    total_source_files=excluded.total_source_files,
                    total_source_size_bytes=excluded.total_source_size_bytes,
                    updated_at=CURRENT_TIMESTAMP
            """, (self.name, self.source_path, self.current_stage_id, self.total_source_files, self.total_source_size_bytes))
            conn.commit()
            
    def load_metadata(self) -> bool:
        """Carrega metadados do banco central. Retorna True se sucesso."""
        if not CENTRAL_DB_PATH.exists():
            return False
        with sqlite3.connect(CENTRAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT source_path, current_stage_id, total_source_files, total_source_size_bytes FROM projects WHERE name=?", (self.name,))
            row = cursor.fetchone()
            if row:
                self.source_path, self.current_stage_id, self.total_source_files, self.total_source_size_bytes = row
                self._init_project_db()
                return True
            return False

    def get_items(self) -> List[ProjectItem]:
        """Recupera todos os itens do banco de dados do projeto."""
        if not self._project_db_file.exists():
            return []
        items = []
        with sqlite3.connect(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT original_path, staging_path, status, file_size_bytes, file_hash, verified FROM items")
            for row in cursor.fetchall():
                items.append(ProjectItem(
                    original_path=row[0],
                    staging_path=row[1],
                    status=row[2],
                    file_size_bytes=row[3],
                    file_hash=row[4],
                    verified=bool(row[5])
                ))
        return items

    def save_item(self, item: ProjectItem):
        """Salva ou atualiza um item no banco do projeto atomicamente."""
        self._init_project_db()
        with sqlite3.connect(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO items (original_path, staging_path, status, file_size_bytes, file_hash, verified)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(original_path) DO UPDATE SET
                    staging_path=excluded.staging_path,
                    status=excluded.status,
                    file_size_bytes=excluded.file_size_bytes,
                    file_hash=excluded.file_hash,
                    verified=excluded.verified
            """, (item.original_path, item.staging_path, item.status, item.file_size_bytes, item.file_hash, int(item.verified)))
            conn.commit()

    def get_item(self, original_path: str) -> Optional[ProjectItem]:
        """Busca um item especifico no banco pelo original_path."""
        if not self._project_db_file.exists():
            return None
        with sqlite3.connect(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT original_path, staging_path, status, file_size_bytes, file_hash, verified FROM items WHERE original_path=?", (original_path,))
            row = cursor.fetchone()
            if row:
                return ProjectItem(
                    original_path=row[0],
                    staging_path=row[1],
                    status=row[2],
                    file_size_bytes=row[3],
                    file_hash=row[4],
                    verified=bool(row[5])
                )
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

    def save(self):
        # Para compatibilidade com códigos que apenas chamavam p.save() para salvar metadados
        self.save_metadata()

def get_project(name: str) -> Optional[Project]:
    """Recupera um projeto existente ou retorna None."""
    p = Project(name)
    if p.load_metadata():
        return p
    return None

def create_project(name: str, source_path: str) -> Project:
    """Cria e salva um novo projeto."""
    p = Project(name, source_path)
    p.save_metadata()
    p._init_project_db()
    return p

def list_open_projects() -> List[str]:
    """Lista todos os projetos salvos no banco central."""
    if not CENTRAL_DB_PATH.exists():
        return []
        
    projects = []
    with sqlite3.connect(CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name FROM projects ORDER BY created_at DESC")
            for row in cursor.fetchall():
                projects.append(row[0])
        except sqlite3.OperationalError:
            pass
    return projects
