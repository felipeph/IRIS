import os
from abc import ABC, abstractmethod
from pathlib import Path
import xxhash

from src.core.project import Project
from src.core.metadata import MEDIA_EXTENSIONS

def is_same_volume(path_a: Path, path_b: Path) -> bool:
    """Verifica se dois caminhos residem no mesmo volume/drive de arquivos."""
    try:
        p1 = path_a.resolve()
        p2 = path_b.resolve()
        if p1.drive and p2.drive:
            return p1.drive.upper() == p2.drive.upper()
        if p1.anchor and p2.anchor and p1.anchor.upper() != p2.anchor.upper():
            return False
        target_stat = p2 if p2.exists() else p2.parent
        return p1.stat().st_dev == target_stat.stat().st_dev
    except Exception:
        return True

def compute_file_hash(path: Path, chunk_size: int = 4 * 1024 * 1024) -> str:
    """Calcula o hash xxHash64 de um arquivo com buffer de alta performance."""
    hasher = xxhash.xxh64()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

def clean_empty_directories(root_dir: Path):
    """Remove pastas vazias recursivamente na origem, preservando a raiz."""
    if not root_dir.exists():
        return
    for dirpath, _, _ in os.walk(str(root_dir), topdown=False):
        p = Path(dirpath)
        try:
            if p.resolve() != root_dir.resolve() and p.exists() and not any(p.iterdir()):
                p.rmdir()
        except OSError:
            pass

class IngestionStrategy(ABC):
    """Classe base abstrata para estratégias de ingestão de mídia do IRIS."""

    VALID_EXTENSIONS = MEDIA_EXTENSIONS

    @abstractmethod
    def execute(self, project: Project, source_dir: Path, dest_dir: Path) -> bool:
        """
        Executa a ingestão dos arquivos da origem para o destino.
        Deve retornar True em caso de sucesso total ou idempotente, False caso contrário.
        """
        pass

    def is_media_file(self, file_path: Path) -> bool:
        """Verifica se o arquivo possui extensão suportada e não é oculto/temporário."""
        return file_path.suffix.lower() in self.VALID_EXTENSIONS and not file_path.name.startswith('.')
