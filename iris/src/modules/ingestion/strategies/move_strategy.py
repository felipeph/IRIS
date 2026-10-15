import os
import shutil
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.live import Live

from src.core.project import Project, ProjectItem
from src.core.ui import ProgressTracker, PipelineUI
from .base import IngestionStrategy, is_same_volume, compute_file_hash, clean_empty_directories

console = Console()

class MoveStrategy(IngestionStrategy):
    """
    Estratégia Turbo de Ingestão: Movimenta arquivos nativamente via SO
    (os.replace no mesmo volume, shutil.move cross-volume), com pool multithreaded,
    resolução estrita de colisões no staging por sufixo incremental (Abordagem C),
    cálculo de xxHash64 pós-mover no SSD e limpeza automática de pastas vazias na origem.
    """

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def execute(self, project: Project, source_dir: Path, dest_dir: Path) -> bool:
        # FASE 1: Varredura rápida da origem
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

        # FASE 2: Mapeamento do destino
        dest_dir.mkdir(parents=True, exist_ok=True)

        # FASE 3: Resolução de Colisões e Planejamento de Movimentação (Abordagem C)
        tasks_to_move = []
        already_ingested_bytes = 0
        reserved_paths: set[Path] = set()

        for src_path in media_files:
            orig_key = str(src_path.resolve())
            src_size = src_path.stat().st_size
            rel_path = src_path.relative_to(source_dir)
            target_candidate = dest_dir / rel_path

            # Checar se já consta registrado e verificado no banco do projeto (retomada idempotente)
            db_item = project.get_item(orig_key)
            if db_item and db_item.status == "copied" and db_item.verified:
                dest_file = Path(db_item.staging_path)
                if dest_file.exists() and dest_file.stat().st_size == src_size:
                    already_ingested_bytes += src_size
                    reserved_paths.add(dest_file)
                    continue

            # Resolução estrita de colisão de nomes por sufixo incremental (_1, _2...)
            resolved_target = self._resolve_collision(target_candidate, reserved_paths)
            tasks_to_move.append((src_path, resolved_target, src_size, orig_key))

        if not tasks_to_move:
            console.print("[green]Todos os arquivos já foram ingeridos e verificados com sucesso![/green]")
            clean_empty_directories(source_dir)
            return True

        # FASE 4 & 5: Movimentação Nativa Multithreaded + xxHash64 no SSD
        tracker = ProgressTracker(total_bytes, mode="bytes")
        tracker.completed_units = already_ingested_bytes
        tracker.last_completed_units = already_ingested_bytes
        start_str = datetime.now().strftime("%H:%M:%S")

        stage_title = f"ETAPA 1: INGESTÃO RÁPIDA (MOVER NATIVO - {self.max_workers} WORKERS)"

        def _worker_move_and_hash(task):
            s_path, t_path, s_size, key = task
            t_path.parent.mkdir(parents=True, exist_ok=True)
            
            same_vol = is_same_volume(s_path, t_path)
            if same_vol:
                os.replace(str(s_path), str(t_path))
            else:
                shutil.move(str(s_path), str(t_path))

            if not (t_path.exists() and t_path.stat().st_size == s_size):
                raise IOError(f"Falha na validação física pós-movimento de {s_path.name}")

            # FASE 5: Cálculo do hash no SSD
            calc_hash = compute_file_hash(t_path)
            return key, str(t_path.resolve()), s_size, calc_hash, s_path.name

        errors = 0
        total_tasks = len(tasks_to_move)

        with Live(
            PipelineUI.generate_renderable(
                tracker, stage_title, start_str, total_files, total_gb, "Preparando movimentação...", "Inicializando"
            ),
            console=console,
            refresh_per_second=4
        ) as live:
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_task = {
                    executor.submit(_worker_move_and_hash, task): task
                    for task in tasks_to_move
                }

                for future in concurrent.futures.as_completed(future_to_task):
                    task = future_to_task[future]
                    orig_key = task[3]
                    src_size = task[2]
                    file_name = task[0].name

                    render_args = (start_str, total_files, total_gb, file_name)

                    try:
                        key, staging_path, size_bytes, final_hash, fname = future.result()
                        
                        tracker.update(size_bytes)
                        live.update(PipelineUI.generate_renderable(tracker, stage_title, *render_args, "Movido e verificado"))

                        # Salva atomicamente no SQLite na thread principal
                        item = ProjectItem(
                            original_path=key,
                            staging_path=staging_path,
                            status="copied",
                            file_size_bytes=size_bytes,
                            file_hash=final_hash,
                            verified=True
                        )
                        project.save_item(item)

                    except Exception as exc:
                        errors += 1
                        console.print(f"\n[red]Erro ao mover/verificar {file_name}: {exc}[/red]")
                        item = ProjectItem(
                            original_path=orig_key,
                            staging_path=str(task[1].resolve()),
                            status="error",
                            file_size_bytes=src_size,
                            verified=False
                        )
                        project.save_item(item)

        if errors > 0:
            console.print(f"\n[yellow]Ingestão finalizada com {errors} erro(s).[/yellow]")
            return False

        # Pós-execução: Limpeza de pastas vazias na origem
        clean_empty_directories(source_dir)

        console.print(f"\n[green]Ingestão por movimentação nativa de {total_files} arquivos concluída e verificada com sucesso![/green]")
        return True
