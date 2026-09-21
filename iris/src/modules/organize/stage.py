import os
import shutil
import json
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import xxhash
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from rich.live import Live

from src.core.pipeline import PipelineStage
from src.core.project import Project, ProjectItem
from src.core.config import config
from src.core.ui import ProgressTracker, PipelineUI

console = Console()

def compute_file_hash(path: Path) -> str:
    """Calcula o hash xxHash64 de um arquivo."""
    hasher = xxhash.xxh64()
    chunk_size = 4 * 1024 * 1024  # 4MB
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()

def is_same_volume(path_a: Path, path_b: Path) -> bool:
    """Verifica se dois caminhos residem no mesmo volume/drive de arquivos."""
    try:
        p1 = path_a.resolve()
        p2 = path_b.resolve()
        # No Windows, compara as letras dos drives se presentes (ex: 'C:' e 'C:')
        if p1.drive and p2.drive:
            return p1.drive.upper() == p2.drive.upper()
        # Se âncoras forem diferentes
        if p1.anchor and p2.anchor and p1.anchor.upper() != p2.anchor.upper():
            return False
        # Fallback para st_dev se disponível
        target_stat = p2 if p2.exists() else p2.parent
        return p1.stat().st_dev == target_stat.stat().st_dev
    except Exception:
        return True

def clean_empty_directories(root_dir: Path):
    """Remove pastas vazias recursivamente de baixo para cima."""
    if not root_dir.exists():
        return
    for dirpath, _, _ in os.walk(str(root_dir), topdown=False):
        p = Path(dirpath)
        try:
            if p.exists() and not any(p.iterdir()):
                p.rmdir()
        except Exception:
            pass

class OrganizeStage(PipelineStage):
    def run(self, project: Project, interactive: bool = True) -> bool:
        items_to_organize = [
            item for item in project.items 
            if item.status == "copied" and item.verified and item.category
        ]

        if not items_to_organize:
            already_organized = [item for item in project.items if item.status == "organized"]
            if already_organized:
                console.print("[green]Todos os itens deste projeto já foram organizados fisicamente.[/green]")
            else:
                console.print("[yellow]Nenhum arquivo planejado/pronto para organização.[/yellow]")
            return True

        dest_root = Path(config.get("general.destination_root", "/caminho/para/destino"))
        
        # 1. Tabela de Resumo Prévia
        console.print(f"\n[bold cyan]=== Resumo da Organização Física ({project.name}) ===[/bold cyan]")
        summary_table = Table(title="Plano de Distribuição de Mídias", show_header=True, header_style="bold magenta")
        summary_table.add_column("Categoria", style="cyan")
        summary_table.add_column("Destino Relativo", style="white")
        summary_table.add_column("Arquivos", justify="right", style="green")
        summary_table.add_column("Tamanho Total", justify="right", style="yellow")

        groups = defaultdict(lambda: {"count": 0, "size": 0})
        for it in items_to_organize:
            key = (it.category, it.relative_dest_dir)
            groups[key]["count"] += 1
            groups[key]["size"] += it.file_size_bytes

        total_bytes = sum(item.file_size_bytes for item in items_to_organize)
        total_files = len(items_to_organize)
        total_gb = total_bytes / (1024**3)

        for (cat, rel_dir), data in sorted(groups.items()):
            size_mb = data["size"] / (1024**2)
            size_str = f"{size_mb:.1f} MB" if size_mb < 1024 else f"{size_mb/1024:.2f} GB"
            summary_table.add_row(cat, str(rel_dir), str(data["count"]), size_str)

        summary_table.add_section()
        total_str = f"{total_bytes/(1024**2):.1f} MB" if total_gb < 1 else f"{total_gb:.2f} GB"
        summary_table.add_row("[bold]TOTAL[/bold]", f"[bold]{dest_root}[/bold]", f"[bold]{total_files}[/bold]", f"[bold]{total_str}[/bold]")
        console.print(summary_table)

        # Confirmação caso modo interativo
        if interactive:
            console.print("\n[bold yellow]Atenção:[/bold yellow] Os arquivos serão movidos da staging ('1_Entrada') para os destinos definitivos.")
            confirmed = Confirm.ask("Deseja iniciar a movimentação física dos arquivos?", default=True)
            if not confirmed:
                console.print("[yellow]Operação cancelada pelo usuário.[/yellow]")
                return False

        tracker = ProgressTracker(total_bytes, mode="bytes")
        start_str = datetime.now().strftime("%H:%M:%S")
        errors = 0

        with Live(PipelineUI.generate_renderable(tracker, "ETAPA 4: ORGANIZAÇÃO FÍSICA (SSD)", start_str, total_files, total_gb, "Preparando...", "Inicializando"), console=console, refresh_per_second=4) as live:
            for item in items_to_organize:
                staging_path = Path(item.staging_path)
                current_file_name = item.target_filename or staging_path.name
                live.update(PipelineUI.generate_renderable(tracker, "ETAPA 4: ORGANIZAÇÃO FÍSICA (SSD)", start_str, total_files, total_gb, current_file_name, "Organizando..."))

                rel_dir = Path(item.relative_dest_dir)
                target_name = item.target_filename
                final_dir = dest_root / rel_dir
                final_path = final_dir / target_name

                # Caso o arquivo não esteja no staging: verificar auto-recuperação
                if not staging_path.exists():
                    if final_path.exists() and final_path.stat().st_size == item.file_size_bytes:
                        # Checar se o hash confere
                        dest_hash = compute_file_hash(final_path)
                        if dest_hash == item.file_hash:
                            item.organized_path = str(final_path.resolve())
                            item.status = "organized"
                            project.save_item(item)
                            tracker.update(item.file_size_bytes)
                            continue
                    
                    console.print(f"[red]Arquivo não encontrado no staging: {staging_path}[/red]")
                    errors += 1
                    continue

                try:
                    final_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Verificação e Resolução de Colisões
                    is_already_identical = False
                    if final_path.exists():
                        if final_path.stat().st_size == item.file_size_bytes and compute_file_hash(final_path) == item.file_hash:
                            is_already_identical = True
                        else:
                            # Conteúdo diferente: aplicar sufixo incremental _1, _2...
                            base_name = final_path.stem
                            ext = final_path.suffix
                            counter = 1
                            while final_path.exists():
                                if final_path.stat().st_size == item.file_size_bytes and compute_file_hash(final_path) == item.file_hash:
                                    is_already_identical = True
                                    break
                                final_path = final_dir / f"{base_name}_{counter}{ext}"
                                counter += 1

                    if is_already_identical:
                        # Já existe arquivo idêntico no destino: remove duplicata do staging
                        staging_path.unlink()
                        item.organized_path = str(final_path.resolve())
                    else:
                        # Movimentação física
                        same_vol = is_same_volume(staging_path, final_path)
                        if same_vol:
                            shutil.move(str(staging_path), str(final_path))
                            if not (final_path.exists() and final_path.stat().st_size == item.file_size_bytes):
                                raise IOError(f"Falha na validação pós-movimento de {staging_path.name}")
                        else:
                            # Volumes distintos: cópia segura + verificação de integridade antes de descartar a origem
                            shutil.copy2(str(staging_path), str(final_path))
                            dest_hash = compute_file_hash(final_path)
                            if dest_hash != item.file_hash:
                                if final_path.exists():
                                    final_path.unlink()
                                raise IOError(f"Hash divergente no destino para {staging_path.name}")
                            staging_path.unlink()

                        item.organized_path = str(final_path.resolve())

                    # Cópia para destinos extras (se houver)
                    extra_dirs = json.loads(item.extra_dest_dirs_json) if item.extra_dest_dirs_json else []
                    extra_paths = []
                    for edir in extra_dirs:
                        try:
                            e_dir_path = dest_root / Path(edir)
                            e_dir_path.mkdir(parents=True, exist_ok=True)
                            e_file_path = e_dir_path / final_path.name
                            shutil.copy2(str(final_path), str(e_file_path))
                            extra_paths.append(str(e_file_path.resolve()))
                        except Exception as extra_err:
                            console.print(f"[yellow]Aviso ao copiar extra para {edir}: {extra_err}[/yellow]")
                    
                    item.extra_organized_paths_json = json.dumps(extra_paths)
                    item.status = "organized"
                    project.save_item(item)
                    tracker.update(item.file_size_bytes)

                except Exception as e:
                    console.print(f"[red]Erro ao organizar {staging_path.name}: {e}[/red]")
                    errors += 1

            live.update(PipelineUI.generate_renderable(tracker, "ETAPA 4: ORGANIZAÇÃO FÍSICA (SSD)", start_str, total_files, total_gb, "Concluído", "Finalizando"))

        # Limpeza de pastas vazias do staging do projeto caso não haja erros críticos
        if errors == 0:
            staging_project_root = Path(dest_root) / "1_Entrada" / project.name
            clean_empty_directories(staging_project_root)
            if staging_project_root.exists() and not any(staging_project_root.iterdir()):
                try:
                    staging_project_root.rmdir()
                except Exception:
                    pass

        if errors > 0:
            console.print(f"[yellow]Organização concluída com {errors} erros.[/yellow]")
            return False
            
        console.print("[bold green]Organização física concluída com sucesso![/bold green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return OrganizeStage(stage_id, name)
