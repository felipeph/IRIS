import os
import shutil
import json
from pathlib import Path
from rich.console import Console
from rich.progress_bar import ProgressBar
from rich.table import Table

from src.core.pipeline import PipelineStage
from src.core.project import Project, ProjectItem
from src.core.config import config
from src.core.ui import ProgressTracker, PipelineUI
from rich.live import Live
from datetime import datetime

console = Console()

class OrganizeStage(PipelineStage):
    def run(self, project: Project) -> bool:
        items_to_organize = [
            item for item in project.items 
            if item.status == "copied" and item.verified and item.category
        ]

        if not items_to_organize:
            console.print("[yellow]Nenhum arquivo planejado/pronto para organização.[/yellow]")
            return True

        dest_root = Path(config.get("general.destination_root", "/caminho/para/destino"))
        
        console.print(f"[cyan]Organizando fisicamente {len(items_to_organize)} arquivos em {dest_root}...[/cyan]")

        total_bytes = sum(item.file_size_bytes for item in items_to_organize)
        total_files = len(items_to_organize)
        total_gb = total_bytes / (1024**3)

        tracker = ProgressTracker(total_bytes, mode="bytes")
        start_str = datetime.now().strftime("%H:%M:%S")

        errors = 0
        
        with Live(PipelineUI.generate_renderable(tracker, "ETAPA 4: ORGANIZAÇÃO FÍSICA (SSD)", start_str, total_files, total_gb, "Preparando...", "Inicializando"), console=console, refresh_per_second=4) as live:
            for i, item in enumerate(items_to_organize, 1):
                staging_path = Path(item.staging_path)
                current_file_name = staging_path.name
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA 4: ORGANIZAÇÃO FÍSICA (SSD)", start_str, total_files, total_gb, current_file_name, "Movendo arquivo..."))

                if not staging_path.exists():
                    console.print(f"[red]Arquivo não encontrado no staging: {staging_path}[/red]")
                    errors += 1
                    continue

                rel_dir = Path(item.relative_dest_dir)
                target_name = item.target_filename
                
                final_dir = dest_root / rel_dir
                final_path = final_dir / target_name
                
                try:
                    final_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Para segurança, lidar com colisões de nomes (adicionar _1, _2, etc)
                    base_name = final_path.stem
                    ext = final_path.suffix
                    counter = 1
                    while final_path.exists():
                        final_path = final_dir / f"{base_name}_{counter}{ext}"
                        counter += 1
                    
                    # Movemos do staging para o local final (estamos na mesma unidade normalmente, então move é atômico/rápido)
                    # Se for unidades diferentes, shutil.move fará a cópia + deleção.
                    shutil.move(str(staging_path), str(final_path))
                    
                    item.organized_path = str(final_path.resolve())
                    
                    # Lidar com diretórios extras (ex: cópia do vídeo para outra pasta) se houver
                    extra_dirs = json.loads(item.extra_dest_dirs_json)
                    extra_paths = []
                    for edir in extra_dirs:
                        e_dir_path = dest_root / Path(edir)
                        e_dir_path.mkdir(parents=True, exist_ok=True)
                        e_file_path = e_dir_path / final_path.name
                        # Não podemos mover, precisamos copiar
                        shutil.copy2(str(final_path), str(e_file_path))
                        extra_paths.append(str(e_file_path.resolve()))
                    
                    item.extra_organized_paths_json = json.dumps(extra_paths)
                    item.status = "organized"
                    project.save_item(item)
                    
                    tracker.update(item.file_size_bytes)
                        
                except Exception as e:
                    console.print(f"[red]Erro ao organizar {staging_path.name}: {e}[/red]")
                    errors += 1

            live.update(PipelineUI.generate_renderable(tracker, "ETAPA 4: ORGANIZAÇÃO FÍSICA (SSD)", start_str, total_files, total_gb, "Concluído", "Finalizando"))

        if errors > 0:
            console.print(f"[yellow]Organização concluída com {errors} erros.[/yellow]")
            return False
            
        console.print("[bold green]Organização física concluída com sucesso![/bold green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return OrganizeStage(stage_id, name)
