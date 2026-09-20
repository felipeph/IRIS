import os
import time
from pathlib import Path
from rich.console import Console
from rich.prompt import Confirm
from src.core.pipeline import PipelineStage
from src.core.project import Project

console = Console()

class CleanupStage(PipelineStage):
    """
    Etapa para limpar (apagar) os arquivos da origem (SD)
    após terem sido verificados com sucesso no banco SQLite.
    """

    def run(self, project: Project) -> bool:
        console.print(f"[yellow]Iniciando {self.name}...[/yellow]")
        
        source_dir = Path(project.source_path)
        if not source_dir.exists() or not source_dir.is_dir():
            console.print(f"[red]Erro: Pasta de origem inválida ou inexistente: {source_dir}[/red]")
            return False

        # Verifica no DB local do projeto quais arquivos estão com verified=True
        items = project.get_items()
        verified_items = [item for item in items if item.status == "copied" and item.verified]
        
        if not verified_items:
            console.print("[yellow]Nenhum arquivo verificado com sucesso no banco de dados para ser apagado.[/yellow]")
            return True
            
        console.print(f"[cyan]Encontrados {len(verified_items)} arquivos marcados como verificados e prontos para exclusão no SD.[/cyan]")
        
        # Pede confirmação (proteção)
        if not Confirm.ask("[bold red]Tem certeza que deseja APAGAR permanentemente estes arquivos da origem?[/bold red]"):
            console.print("[yellow]Operação cancelada pelo usuário.[/yellow]")
            return True
            
        deleted_count = 0
        for item in verified_items:
            try:
                orig_path = Path(item.original_path)
                if orig_path.exists():
                    os.remove(orig_path)
                    deleted_count += 1
            except Exception as e:
                console.print(f"[red]Erro ao apagar {item.original_path}: {e}[/red]")
                
        console.print(f"[green]Limpeza concluída! {deleted_count} arquivos apagados do SD.[/green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return CleanupStage(stage_id, name)
