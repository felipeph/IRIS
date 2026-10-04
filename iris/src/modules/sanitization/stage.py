import os
import shutil
import tempfile
import subprocess
from pathlib import Path
from rich.console import Console
from rich.live import Live
from datetime import datetime

from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.core.ui import ProgressTracker, PipelineUI

console = Console()

class SanitizationStage(PipelineStage):
    def run(self, project: Project) -> bool:
        if not project.items:
            console.print("[yellow]Nenhum arquivo no projeto para sanitizar.[/yellow]")
            return True

        # Pre-flight check
        exiftool_bin = shutil.which("exiftool") or ("C:\\Windows\\exiftool.exe" if Path("C:\\Windows\\exiftool.exe").exists() else None)
        if not exiftool_bin:
            console.print("[bold red]ERRO: exiftool não encontrado no PATH![/bold red]")
            console.print("Por favor, instale o exiftool para continuar.")
            return False

        # Identificar arquivos .jpg e .jpeg na pasta _iris_staging
        items_to_sanitize = []
        for item in project.items:
            if item.status == "copied" and item.staging_path:
                ext = Path(item.staging_path).suffix.lower()
                if ext in [".jpg", ".jpeg"]:
                    items_to_sanitize.append(Path(item.staging_path))

        if not items_to_sanitize:
            console.print("[yellow]Nenhum arquivo JPEG encontrado para sanitização.[/yellow]")
            return True

        console.print(f"[cyan]Sanitizando {len(items_to_sanitize)} imagens JPEG...[/cyan]")
        total_files = len(items_to_sanitize)
        tracker = ProgressTracker(total_files, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")
        
        batch_size = 500
        with Live(PipelineUI.generate_renderable(tracker, "ETAPA: SANITIZAÇÃO DE METADADOS", start_str, total_files, 0.0, "Preparando...", "Inicializando"), console=console, refresh_per_second=4) as live:
            for i in range(0, total_files, batch_size):
                chunk_paths = items_to_sanitize[i:i+batch_size]
                
                with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
                    for p in chunk_paths:
                        f.write(f"{p.resolve()}\n")
                    argfile = f.name
                
                try:
                    cmd = [
                        exiftool_bin,
                        "-MPF:all=",
                        "-trailer:all=",
                        "-MakerNotes:all=",
                        "-PreviewImage=",
                        "-overwrite_original",
                        "-P",
                        "-charset", "filename=utf8",
                        "-@",
                        argfile,
                    ]
                    
                    cur_name = chunk_paths[-1].name if chunk_paths else ""
                    live.update(PipelineUI.generate_renderable(tracker, "ETAPA: SANITIZAÇÃO DE METADADOS", start_str, total_files, 0.0, f"Lote {i//batch_size + 1}", "Sanitizando..."))
                    
                    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
                    if proc.returncode != 0 and proc.stderr:
                        # Warnings do exiftool também vão para o stderr
                        pass
                        
                    tracker.update(len(chunk_paths))
                    live.update(PipelineUI.generate_renderable(tracker, "ETAPA: SANITIZAÇÃO DE METADADOS", start_str, total_files, 0.0, cur_name, "Progresso"))
                except Exception as e:
                    console.print(f"[WARN] Falha ao rodar exiftool na sanitização (lote {i}-{i+len(chunk_paths)}): {e}")
                finally:
                    try:
                        os.unlink(argfile)
                    except OSError:
                        pass
                        
            live.update(PipelineUI.generate_renderable(tracker, "ETAPA: SANITIZAÇÃO DE METADADOS", start_str, total_files, 0.0, "Concluído", "Finalizando"))

        console.print("[bold green]Sanitização concluída![/bold green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return SanitizationStage(stage_id, name)
