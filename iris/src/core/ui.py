import time
from datetime import datetime, timedelta
from rich.console import Group
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table

class ProgressTracker:
    def __init__(self, total_units: float, mode: str = "bytes"):
        """
        mode: "bytes" para taxas de transferência, "items" para contagem de arquivos.
        """
        self.total_units = total_units
        self.completed_units = 0.0
        self.start_time = time.time()
        self.last_update_time = self.start_time
        self.last_completed_units = 0.0
        self.speed = 0.0
        self.speeds = []
        self.mode = mode

    def update(self, units_added: float):
        self.completed_units += units_added
        now = time.time()
        dt = now - self.last_update_time
        if dt > 0.5:
            du = self.completed_units - self.last_completed_units
            current_speed = du / dt
            self.speeds.append(current_speed)
            if len(self.speeds) > 10:
                self.speeds.pop(0)
            self.speed = sum(self.speeds) / len(self.speeds)
            self.last_update_time = now
            self.last_completed_units = self.completed_units

    def get_speed_str(self):
        if self.mode == "bytes":
            if self.speed > 1024**2:
                return f"{self.speed / (1024**2):.1f} MB/s"
            elif self.speed > 1024:
                return f"{self.speed / 1024:.1f} KB/s"
            else:
                return f"{self.speed:.1f} B/s"
        else:
            return f"{self.speed:.1f} itens/s"

    def get_eta_str(self):
        if self.speed == 0:
            return "--:--:--"
        remaining = self.total_units - self.completed_units
        if remaining <= 0:
            return "0:00:00"
        eta_seconds = remaining / self.speed
        return str(timedelta(seconds=int(eta_seconds)))
        
    def get_previsao_fim_str(self):
        if self.speed == 0:
            return "--:--:--"
        remaining = self.total_units - self.completed_units
        if remaining <= 0:
            return datetime.now().strftime("%H:%M:%S")
        eta_seconds = remaining / self.speed
        end_time = datetime.now() + timedelta(seconds=int(eta_seconds))
        return end_time.strftime("%H:%M:%S")

    def get_elapsed_str(self):
        elapsed = time.time() - self.start_time
        return str(timedelta(seconds=int(elapsed)))


class PipelineUI:
    @staticmethod
    def generate_renderable(tracker: ProgressTracker, stage_title: str, start_str: str, 
                            total_files: int, total_gb: float, current_item_name: str, status_msg: str):
        
        info_text = (
            f"  [bold]• Início:[/bold]    {start_str}\n"
            f"  [bold]• Arquivos:[/bold]  {total_files:,}\n"
            f"  [bold]• Volume:[/bold]    {total_gb:.2f} GB"
        )
        top_panel = Panel(info_text, title=stage_title, title_align="left", border_style="blue", expand=False)
        
        completed = tracker.completed_units
        total = tracker.total_units
        percentage = (completed / total * 100) if total > 0 else 0
        
        bar = ProgressBar(total=total, completed=completed, width=40)
        
        progress_table = Table.grid(padding=(0, 1))
        progress_table.add_column()
        progress_table.add_column()
        
        if tracker.mode == "bytes":
            copied_gb = completed / (1024**3)
            progress_table.add_row(bar, f"{percentage:.1f}% ({copied_gb:.2f} GB / {total_gb:.2f} GB)")
        else:
            progress_table.add_row(bar, f"{percentage:.1f}% ({int(completed)} / {int(total)})")
        
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold blue")
        table.add_column()
        
        table.add_row("Operação:", status_msg)
        table.add_row("Arquivo atual:", f"[yellow]{current_item_name}[/yellow]")
        table.add_row("Progresso:", progress_table)
        table.add_row("Velocidade:", f"[cyan]{tracker.get_speed_str()}[/cyan]")
        table.add_row("Tempo decorrido:", tracker.get_elapsed_str())
        table.add_row("Tempo restante:", f"[magenta]{tracker.get_eta_str()}[/magenta]")
        table.add_row("Previsão fim:", f"[bold cyan]{tracker.get_previsao_fim_str()}[/bold cyan]")
        
        return Group(top_panel, "", table)

    @staticmethod
    def generate_video_renderable(
        stage_title: str,
        start_str: str,
        total_photos: int,
        total_frames: int,
        current_frame: int,
        fps_target: int,
        current_fps: float,
        current_speed: str,
        encoder_name: str,
        resolution: str,
        output_name: str,
        status_msg: str,
        elapsed_str: str,
        eta_str: str,
        previsao_fim_str: str
    ):
        info_text = (
            f"  [bold]• Início:[/bold]     {start_str}\n"
            f"  [bold]• Fotos:[/bold]      {total_photos:,} imagens\n"
            f"  [bold]• Resolução:[/bold]  {resolution} @ {fps_target} FPS\n"
            f"  [bold]• Encoder:[/bold]    {encoder_name}"
        )
        top_panel = Panel(info_text, title=stage_title, title_align="left", border_style="cyan", expand=False)
        
        pct = (current_frame / total_frames * 100) if total_frames > 0 else 0
        bar = ProgressBar(total=total_frames, completed=current_frame, width=40)
        
        progress_table = Table.grid(padding=(0, 1))
        progress_table.add_column()
        progress_table.add_column()
        progress_table.add_row(bar, f"{pct:.1f}% ({current_frame:,} / {total_frames:,} frames)")
        
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold cyan")
        table.add_column()
        
        table.add_row("Operação:", status_msg)
        table.add_row("Vídeo saída:", f"[yellow]{output_name}[/yellow]")
        table.add_row("Progresso:", progress_table)
        table.add_row("Velocidade:", f"[cyan]{current_fps:.1f} fps ({current_speed})[/cyan]")
        table.add_row("Tempo decorrido:", elapsed_str)
        table.add_row("Tempo restante:", f"[magenta]{eta_str}[/magenta]")
        table.add_row("Previsão fim:", f"[bold cyan]{previsao_fim_str}[/bold cyan]")
        
        return Group(top_panel, "", table)

    @staticmethod
    def generate_upload_renderable(
        stage_title: str,
        start_str: str,
        video_title: str,
        video_filename: str,
        total_bytes: int,
        uploaded_bytes: int,
        speed_str: str,
        elapsed_str: str,
        eta_str: str,
        previsao_fim_str: str,
        status_msg: str
    ):
        total_mb = total_bytes / (1024**2)
        info_text = (
            f"  [bold]• Início:[/bold]      {start_str}\n"
            f"  [bold]• Arquivo:[/bold]     {video_filename}\n"
            f"  [bold]• Tamanho:[/bold]     {total_mb:.2f} MB\n"
            f"  [bold]• Título YT:[/bold]   {video_title[:50]}"
        )
        top_panel = Panel(info_text, title=stage_title, title_align="left", border_style="red", expand=False)
        
        pct = (uploaded_bytes / total_bytes * 100) if total_bytes > 0 else 0
        bar = ProgressBar(total=total_bytes, completed=uploaded_bytes, width=40)
        
        progress_table = Table.grid(padding=(0, 1))
        progress_table.add_column()
        progress_table.add_column()
        uploaded_mb = uploaded_bytes / (1024**2)
        progress_table.add_row(bar, f"{pct:.1f}% ({uploaded_mb:.1f} MB / {total_mb:.1f} MB)")
        
        table = Table.grid(padding=(0, 2))
        table.add_column(style="bold red")
        table.add_column()
        
        table.add_row("Operação:", status_msg)
        table.add_row("Progresso:", progress_table)
        table.add_row("Velocidade:", f"[cyan]{speed_str}[/cyan]")
        table.add_row("Tempo decorrido:", elapsed_str)
        table.add_row("Tempo restante:", f"[magenta]{eta_str}[/magenta]")
        table.add_row("Previsão fim:", f"[bold cyan]{previsao_fim_str}[/bold cyan]")
        
        return Group(top_panel, "", table)

