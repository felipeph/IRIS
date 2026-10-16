import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from send2trash import send2trash

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.prompt import Confirm

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.modules.ingestion.strategies.base import compute_file_hash

console = Console()

def is_removable_media(path: Path) -> bool:
    """
    Verifica se o caminho reside em uma mídia removível (ex: Cartão SD, Pen Drive).
    No Windows, mídias removíveis (DRIVE_REMOVABLE = 2) não possuem Lixeira ($RECYCLE.BIN).
    """
    if os.name != "nt":
        return False
    try:
        resolved = path.resolve()
        drive = resolved.drive
        if not drive:
            return False
        root = drive if drive.endswith("\\") else drive + "\\"
        import ctypes
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)
        # DRIVE_REMOVABLE = 2
        return drive_type == 2
    except Exception:
        return False

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
    top_panel = Panel(info_text, title="ETAPA 4: LIMPEZA DA ORIGEM (SD)", title_align="left", border_style="red", expand=False)
    
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
    fazendo uma verificação extra criptográfica (Hash-Guard xxHash64) no SSD
    e protegendo mídias removíveis sem Lixeira (Zero Data Loss).
    """

    def run(self, project: Project, auto_clean: bool = False, **kwargs) -> bool:
        console.print(f"[yellow]Iniciando {self.name}...[/yellow]")
        
        source_dir = Path(project.source_path)
        if not source_dir.exists() or not source_dir.is_dir():
            console.print(f"[red]Erro: Pasta de origem inválida ou inexistente: {source_dir}[/red]")
            return False

        # Verifica no DB local do projeto quais arquivos estão com verified=True
        items = project.get_items(status="copied", verified=True)
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
        console.print(f"[cyan]Encontrados {total_files} arquivos marcados como verificados ({total_gb:.2f} GB) e prontos para limpeza no SD.[/cyan]")
        
        is_auto = auto_clean or getattr(project, "auto_cleanup", False)
        allow_permanent_config = bool(config.get("modules.cleanup.allow_permanent_sd_clean", False))
        is_removable = is_removable_media(source_dir)
        allow_permanent = False

        if is_auto:
            if is_removable and not allow_permanent_config:
                # Proteção Zero Data Loss: Recusa exclusão permanente em SD no modo automático
                console.print(Panel(
                    f"[bold yellow]AVISO ZERO DATA LOSS: Limpeza ignorada para '{source_dir}'.[/bold yellow]\n"
                    f"[white]A unidade foi identificada como mídia removível (Cartão SD/USB) sem suporte a Lixeira.[/white]\n"
                    f"[white]A flag [bold cyan]'modules.cleanup.allow_permanent_sd_clean'[/bold cyan] está desativada.[/white]\n"
                    f"[green]✔ Todos os {total_files} arquivos originais foram preservados no cartão com segurança.[/green]\n"
                    f"[dim]Para autorizar exclusão permanente autônoma, ative 'allow_permanent_sd_clean' nas configurações.[/dim]",
                    title="[bold blue]Proteção Zero Data Loss[/bold blue]",
                    border_style="yellow",
                    expand=False
                ))
                return True
            elif is_removable and allow_permanent_config:
                console.print(f"[bold yellow]⚡ Limpeza automática autorizada para mídia removível ({source_dir.drive}) via allow_permanent_sd_clean=True.[/bold yellow]")
                allow_permanent = True
            else:
                console.print("[bold yellow]⚡ Limpeza automática ativada: enviando arquivos verificados para a Lixeira sem confirmação...[/bold yellow]")
                allow_permanent = allow_permanent_config
        else:
            # Modo Interativo
            if is_removable:
                console.print(Panel(
                    f"[bold red]ATENÇÃO: A unidade '{source_dir.drive}' (Cartão SD / Mídia Removível) NÃO suporta Lixeira do sistema operacional.[/bold red]\n"
                    f"[white]A exclusão dos arquivos originais será [/white][bold red]PERMANENTE[/bold red][white] e não poderá ser desfeita via Lixeira.[/white]\n"
                    f"[dim]Total: {total_files} arquivos ({total_gb:.2f} GB) prontos para limpeza.[/dim]",
                    title="[bold yellow]Mídia Removível Detectada[/bold yellow]",
                    border_style="red",
                    expand=False
                ))
                if not Confirm.ask("[bold red]Deseja EXCLUIR PERMANENTEMENTE os arquivos originais verificados do cartão?[/bold red]", default=False):
                    console.print("[yellow]Operação cancelada pelo usuário. Arquivos originais preservados no cartão.[/yellow]")
                    return True
                allow_permanent = True
            else:
                if not Confirm.ask("[bold red]Deseja enviar estes arquivos verificados da origem para a Lixeira?[/bold red]"):
                    console.print("[yellow]Operação cancelada pelo usuário.[/yellow]")
                    return True
                allow_permanent = allow_permanent_config
            
        tracker = CleanupTracker(total_bytes_to_delete)
        start_str = datetime.now().strftime("%H:%M:%S")
        
        deleted_count = 0
        skipped_count = 0
        
        with Live(generate_renderable(tracker, start_str, total_files, total_gb, "Preparando..."), console=console, refresh_per_second=4) as live:
            for orig_path, item in items_to_delete:
                file_size = orig_path.stat().st_size
                current_file_name = orig_path.name
                
                render_args = (start_str, total_files, total_gb, current_file_name)
                live.update(generate_renderable(tracker, *render_args, "Limpando SD: Verificando integridade no SSD..."))
                
                # Double check no SSD (suporta staging_path ou organized_path caso já tenha sido organizado)
                dest_path = Path(item.staging_path)
                if not dest_path.exists() and item.organized_path and Path(item.organized_path).exists():
                    dest_path = Path(item.organized_path)

                is_safe_to_delete = False
                
                if not dest_path.exists():
                    # Destino no SSD ausente: perigo de perda de dados!
                    is_safe_to_delete = False
                elif dest_path.stat().st_size != item.file_size_bytes:
                    # Tamanho no SSD divergente: perigo de arquivo corrompido/truncado!
                    is_safe_to_delete = False
                elif item.file_hash:
                    # Validação criptográfica de integridade no SSD antes de qualquer exclusão
                    dest_hash = compute_file_hash(dest_path)
                    if dest_hash == item.file_hash:
                        is_safe_to_delete = True
                    else:
                        # Hash divergente: corrupção ou alteração desconhecida no SSD!
                        is_safe_to_delete = False
                else:
                    # Sem hash registrado no banco: recusa por segurança (Zero Data Loss)
                    is_safe_to_delete = False
                
                if is_safe_to_delete:
                    live.update(generate_renderable(tracker, *render_args, "Limpando SD: Enviando para a lixeira..."))
                    trash_succeeded = False
                    try:
                        send2trash(str(orig_path))
                        trash_succeeded = True
                        deleted_count += 1
                        tracker.update(file_size)
                    except Exception:
                        trash_succeeded = False
                    
                    if not trash_succeeded:
                        # Fallback seguro: só faz unlink() se a exclusão permanente foi explicitamente autorizada
                        if allow_permanent:
                            live.update(generate_renderable(tracker, *render_args, "Limpando SD: Exclusão permanente autorizada..."))
                            try:
                                orig_path.unlink()
                                deleted_count += 1
                                tracker.update(file_size)
                            except Exception:
                                skipped_count += 1
                                tracker.update(file_size)
                        else:
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
        console.print(f"  • [cyan]Arquivos removidos:[/cyan] {deleted_count}")
        console.print(f"  • [yellow]Arquivos preservados/falhas:[/yellow] {skipped_count}")
        console.print(f"  • [cyan]Pastas vazias removidas:[/cyan] {empty_dirs_removed}")
        
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return CleanupStage(stage_id, name)
