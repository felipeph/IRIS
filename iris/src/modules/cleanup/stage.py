import os
import time
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.prompt import Confirm

from src.core.pipeline import PipelineStage
from src.core.project import Project

console = Console()

class CleanupTracker:
    def __init__(self, total_bytes):
        self.total_bytes = total_bytes
        self.deleted_bytes = 0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_deleted_bytes = 0
        self.speed = 0.0
        self.speeds = []

    def update(self, bytes_removed):
        self.deleted_bytes += bytes_removed
        now = time.time()
        dt = now - self.last_update_time
        if dt > 0.5:
            db = self.deleted_bytes - self.last_deleted_bytes
            current_speed = db / dt
            self.speeds.append(current_speed)
            if len(self.speeds) > 10:
                self.speeds.pop(0)
            self.speed = sum(self.speeds) / len(self.speeds)
            self.last_update_time = now
            self.last_deleted_bytes = self.deleted_bytes

    def get_speed_str(self):
        if self.speed > 1024**2:
            return f"{self.speed / (1024**2):.1f} MB/s"
        elif self.speed > 1024:
            return f"{self.speed / 1024:.1f} KB/s"
        else:
            return f"{self.speed:.1f} B/s"

    def get_eta_str(self):
        if self.speed == 0:
            return "--:--:--"
        remaining_bytes = self.total_bytes - self.deleted_bytes
        if remaining_bytes <= 0:
            return "0:00:00"
        eta_seconds = remaining_bytes / self.speed
        return str(timedelta(seconds=int(eta_seconds)))

    def get_previsao_fim_str(self):
        if self.speed == 0:
            return "--:--:--"
        remaining_bytes = self.total_bytes - self.deleted_bytes
        if remaining_bytes <= 0:
            return datetime.now().strftime("%H:%M:%S")
        eta_seconds = remaining_bytes / self.speed
        end_time = datetime.now() + timedelta(seconds=int(eta_seconds))
        return end_time.strftime("%H:%M:%S")

    def get_elapsed_str(self):
        elapsed = time.time() - self.start_time
        return str(timedelta(seconds=int(elapsed)))

def generate_renderable(tracker, start_str, total_files, total_gb, current_file_name, status_msg="Limpando SD"):
    info_text = (
        f"  [bold]• Início:[/bold]    {start_str}\n"
        f"  [bold]• Arquivos:[/bold]  {total_files:,}\n"
        f"  [bold]• Volume:[/bold]    {total_gb:.2f} GB"
    )
    top_panel = Panel(info_text, title="ETAPA 2: LIMPEZA DA ORIGEM (SD)", title_align="left", border_style="red", expand=False)
    
    completed = tracker.deleted_bytes
    total = tracker.total_bytes
    percentage = (completed / total * 100) if total > 0 else 0
    deleted_gb = completed / (1024**3)
    
    bar = ProgressBar(total=total, completed=completed, width=40, style="red")
    
    progress_table = Table.grid(padding=(0, 1))
    progress_table.add_column()
    progress_table.add_column()
    progress_table.add_row(bar, f"{percentage:.1f}% ({deleted_gb:.2f} GB / {total_gb:.2f} GB)")
    
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold red")
    table.add_column()
    
    table.add_row("Operacao:", status_msg)
    table.add_row("Arquivo atual:", f"[yellow]{current_file_name}[/yellow]")
    table.add_row("Progresso:", progress_table)
    table.add_row("Velocidade:", f"[cyan]{tracker.get_speed_str()}[/cyan]")
    table.add_row("Tempo decorrido:", tracker.get_elapsed_str())
    table.add_row("Tempo restante:", f"[magenta]{tracker.get_eta_str()}[/magenta]")
    table.add_row("Previsao fim:", f"[bold cyan]{tracker.get_previsao_fim_str()}[/bold cyan]")
    
    return Group(top_panel, "", table)

class CleanupStage(PipelineStage):
    """
    Etapa para limpar (apagar) os arquivos da origem (SD)
    após terem sido verificados com sucesso no banco SQLite,
    fazendo uma verificação extra (double check) no SSD.
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
            
        # Filtra apenas os que ainda existem no SD
        items_to_delete = []
        total_bytes_to_delete = 0
        for item in verified_items:
            orig_path = Path(item.original_path)
            if orig_path.exists():
                items_to_delete.append((orig_path, item))
                total_bytes_to_delete += orig_path.stat().st_size
                
        if not items_to_delete:
            console.print("[yellow]Os arquivos verificados já não se encontram mais no SD.[/yellow]")
            return True
            
        total_files = len(items_to_delete)
        total_gb = total_bytes_to_delete / (1024**3)
        console.print(f"[cyan]Encontrados {total_files} arquivos marcados como verificados ({total_gb:.2f} GB) e prontos para exclusão no SD.[/cyan]")
        
        # Pede confirmação (proteção)
        if not Confirm.ask("[bold red]Tem certeza que deseja APAGAR permanentemente estes arquivos da origem?[/bold red]"):
            console.print("[yellow]Operação cancelada pelo usuário.[/yellow]")
            return True
            
        tracker = CleanupTracker(total_bytes_to_delete)
        start_str = datetime.now().strftime("%H:%M:%S")
        
        deleted_count = 0
        skipped_count = 0
        
        with Live(generate_renderable(tracker, start_str, total_files, total_gb, "Preparando..."), console=console, refresh_per_second=4) as live:
            for orig_path, item in items_to_delete:
                file_size = orig_path.stat().st_size
                current_file_name = orig_path.name
                
                render_args = (start_str, total_files, total_gb, current_file_name)
                live.update(generate_renderable(tracker, *render_args, "Limpando SD: Verificando destino..."))
                
                # Double check no SSD
                dest_path = Path(item.staging_path)
                is_safe_to_delete = False
                
                if dest_path.exists() and dest_path.stat().st_size == file_size:
                    is_safe_to_delete = True
                else:
                    is_safe_to_delete = False
                
                if is_safe_to_delete:
                    live.update(generate_renderable(tracker, *render_args, "Limpando SD: Apagando origem..."))
                    try:
                        orig_path.unlink()
                        deleted_count += 1
                        tracker.update(file_size)
                    except Exception as e:
                        skipped_count += 1
                        tracker.update(file_size)
                else:
                    skipped_count += 1
                    tracker.update(file_size)
                    
        # Limpar pastas vazias
        console.print("[cyan]Iniciando remoção de pastas vazias na origem...[/cyan]")
        empty_dirs_removed = 0
        for dirpath, dirnames, filenames in os.walk(source_dir, topdown=False):
            # Não tentar apagar o diretório raiz da origem
            if Path(dirpath) == source_dir:
                continue
                
            try:
                if not os.listdir(dirpath): # se estiver vazio
                    os.rmdir(dirpath)
                    empty_dirs_removed += 1
            except OSError:
                pass
                
        console.print(f"\n[green]Limpeza concluída![/green]")
        console.print(f"  • [cyan]Arquivos apagados:[/cyan] {deleted_count}")
        console.print(f"  • [yellow]Arquivos ignorados/falhas:[/yellow] {skipped_count}")
        console.print(f"  • [cyan]Pastas vazias removidas:[/cyan] {empty_dirs_removed}")
        
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return CleanupStage(stage_id, name)
