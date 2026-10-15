import os
from datetime import datetime
from pathlib import Path
import xxhash

from rich.console import Console
from rich.live import Live

from src.core.project import Project, ProjectItem
from src.core.ui import ProgressTracker, PipelineUI
from .base import IngestionStrategy

console = Console()

def copy_and_verify(src_path: Path, dest_path: Path, live: Live, tracker: ProgressTracker, render_args) -> tuple[bool, str]:
    """Copia arquivo calculando hash on-the-fly, sincroniza no disco e verifica."""
    chunk_size = 4 * 1024 * 1024  # 4MB chunk
    hasher_src = xxhash.xxh64()
    
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        # 1. Copiar com hash on-the-fly
        with open(src_path, 'rb') as f_src, open(dest_path, 'wb') as f_dest:
            while True:
                chunk = f_src.read(chunk_size)
                if not chunk:
                    break
                hasher_src.update(chunk)
                f_dest.write(chunk)
                tracker.update(len(chunk))
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA 1: INGESTÃO E VALIDAÇÃO (CÓPIA SD -> SSD)", *render_args, "Ingestão: Copiando..."))
                
            # Forçar a escrita física
            f_dest.flush()
            os.fsync(f_dest.fileno())
            
        src_hash = hasher_src.hexdigest()
        
        # 2. Ler do destino para validar o hash
        hasher_dest = xxhash.xxh64()
        live.update(PipelineUI.generate_renderable(tracker, "ETAPA 1: INGESTÃO E VALIDAÇÃO (CÓPIA SD -> SSD)", *render_args, "Ingestão: Verificando disco..."))
        
        with open(dest_path, 'rb') as f_dest:
            while True:
                chunk = f_dest.read(chunk_size)
                if not chunk:
                    break
                hasher_dest.update(chunk)
                
        dest_hash = hasher_dest.hexdigest()
        
        if src_hash == dest_hash:
            return True, src_hash
        else:
            return False, ""
            
    except Exception as e:
        console.print(f"\n[red]Exceção durante copy_and_verify: {e}[/red]")
        return False, ""

def _get_copy_and_verify():
    try:
        import src.modules.ingestion.stage as stage_mod
        return getattr(stage_mod, "copy_and_verify", copy_and_verify)
    except Exception:
        return copy_and_verify

class CopyStrategy(IngestionStrategy):
    """
    Estratégia Clássica de Ingestão: Copia arquivos de mídia calculando
    hash xxHash on-the-fly e forçando fsync para garantir integridade.
    """

    def execute(self, project: Project, source_dir: Path, dest_dir: Path) -> bool:
        console.print(f"[cyan]Buscando arquivos de mídia em {source_dir}...[/cyan]")
        media_files = []
        total_bytes = 0
        for p in source_dir.rglob("*"):
            if p.is_file() and self.is_media_file(p):
                media_files.append(p)
                total_bytes += p.stat().st_size

        if not media_files:
            console.print("[yellow]Nenhuma mídia suportada encontrada na origem.[/yellow]")
            return True

        total_files = len(media_files)
        total_gb = total_bytes / (1024**3)
        files_to_copy = []
        already_copied_bytes = 0
        reserved_paths: set[Path] = set()

        # Verificando no DB local do projeto quais arquivos já foram copiados e verificados (retomada idempotente)
        for src_path in media_files:
            orig_key = str(src_path.resolve())
            item = project.get_item(orig_key)
            src_size = src_path.stat().st_size
            
            if item and item.status == "copied" and item.verified:
                dest_path = Path(item.staging_path)
                if dest_path.exists() and dest_path.stat().st_size == src_size:
                    already_copied_bytes += src_size
                    reserved_paths.add(dest_path)
                    continue
                    
            files_to_copy.append(src_path)

        if not files_to_copy:
            console.print("[green]Todos os arquivos já foram ingeridos e verificados com sucesso![/green]")
            return True

        tracker = ProgressTracker(total_bytes, mode="bytes")
        tracker.completed_units = already_copied_bytes
        tracker.last_completed_units = already_copied_bytes
        start_str = datetime.now().strftime("%H:%M:%S")

        stage_title = "ETAPA 1: INGESTÃO E VALIDAÇÃO (CÓPIA SD -> SSD)"

        with Live(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_files, total_gb, "Preparando...", "Inicializando"), console=console, refresh_per_second=4) as live:
            for i, src_path in enumerate(files_to_copy, 1):
                src_size = src_path.stat().st_size
                current_file_name = src_path.name
                
                render_args = (start_str, total_files, total_gb, current_file_name)
                live.update(PipelineUI.generate_renderable(tracker, stage_title, *render_args, "Iniciando arquivo..."))
                
                rel_path = src_path.relative_to(source_dir)
                target_candidate = dest_dir / rel_path
                target_path = self._resolve_collision(target_candidate, reserved_paths)
                orig_key = str(src_path.resolve())
                fn_copy_and_verify = _get_copy_and_verify()
                success, final_hash = fn_copy_and_verify(src_path, target_path, live, tracker, render_args)
                
                if success:
                    item = ProjectItem(
                        original_path=orig_key,
                        staging_path=str(target_path.resolve()),
                        status="copied",
                        file_size_bytes=src_size,
                        file_hash=final_hash,
                        verified=True
                    )
                    project.save_item(item)
                    live.update(PipelineUI.generate_renderable(tracker, stage_title, *render_args, "Verificação concluída"))
                else:
                    live.stop()
                    console.print(f"[red]Erro na cópia ou falha de verificação (hash mismatch) em {src_path.name}.[/red]")
                    target_path.unlink(missing_ok=True)
                    item = ProjectItem(
                        original_path=orig_key,
                        staging_path=str(target_path.resolve()),
                        status="error",
                        file_size_bytes=src_size,
                        verified=False
                    )
                    project.save_item(item)
                    return False

        console.print(f"\n[green]Ingestão de {total_files} arquivos concluída e verificada com sucesso![/green]")
        return True
