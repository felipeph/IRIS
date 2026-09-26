import os
from pathlib import Path
from rich.console import Console

from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.core.config import config
from src.core.metadata import MEDIA_EXTENSIONS
from .strategies import IngestionStrategy, CopyStrategy, MoveStrategy
from .strategies.copy_strategy import copy_and_verify

console = Console()

class IngestionStage(PipelineStage):
    """
    Etapa de Ingestão de Mídias (SD -> SSD).
    Suporta Strategy Pattern:
      - 'move' (padrão): Movimentação nativa turbo via SO com pool multithreaded.
      - 'copy': Cópia clássica com cálculo de hash xxHash on-the-fly e fsync.
    """
    
    VALID_EXTENSIONS = MEDIA_EXTENSIONS

    def _get_destination_dir(self, project: Project) -> Path:
        dest_root = config.get("general.destination_root", "/caminho/para/destino")
        return Path(dest_root) / "1_Entrada" / project.name / "raw"

    def _is_media_file(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.VALID_EXTENSIONS and not file_path.name.startswith('.')

    def get_strategy(self) -> IngestionStrategy:
        strategy_conf = config.get("modules.ingestion.strategy", "move")
        strategy_name = str(strategy_conf).lower() if strategy_conf else "move"
        
        workers_conf = config.get("modules.ingestion.max_workers", 4)
        try:
            max_workers = int(workers_conf)
        except (ValueError, TypeError):
            max_workers = 4

        if strategy_name == "move":
            return MoveStrategy(max_workers=max_workers)
        return CopyStrategy()

    def run(self, project: Project) -> bool:
        source_dir = Path(project.source_path)
        if not source_dir.exists() or not source_dir.is_dir():
            console.print(f"[red]Erro: Pasta de origem inválida ou inexistente: {source_dir}[/red]")
            return False

        dest_dir = self._get_destination_dir(project)
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            console.print(f"[red]Erro ao criar diretório destino {dest_dir}: {e}[/red]")
            return False

        strategy = self.get_strategy()
        return strategy.execute(project, source_dir, dest_dir)

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return IngestionStage(stage_id, name)
