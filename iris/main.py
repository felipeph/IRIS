import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from src.core.config import config
from src.core.logger import log_event
from src.core.project import list_open_projects, get_project, create_project
from src.core.pipeline import PipelineRunner

console = Console()

def show_config_menu():
    """Sub-menu para gerenciar as configurações da Iris."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações Globais - Iris[/bold yellow]", expand=False))
        
        table = Table(title="Configurações Atuais (~/.iris/config.yaml)")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Chave", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        table.add_row("1", "Diretório Destino", str(config.get("general.destination_root")))
        table.add_row("2", "Origem Padrão", str(config.get("general.default_source")))
        table.add_row("3", "Limpar Último Projeto", str(config.get("general.last_project")))
        
        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            new_val = Prompt.ask("Novo Diretório Destino", default=str(config.get("general.destination_root")))
            config.set("general.destination_root", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "2":
            new_val = Prompt.ask("Nova Origem Padrão", default=str(config.get("general.default_source")))
            config.set("general.default_source", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "3":
            config.set("general.last_project", None)
            console.print("[green]Último projeto limpo![/green]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)

import shutil

def get_free_space_gb(folder: str) -> float:
    try:
        _, _, free = shutil.disk_usage(folder)
        return free / (1024**3)
    except Exception:
        return 0.0

def get_project_status_text(project) -> str:
    """Retorna uma string amigável descrevendo o status atual do projeto."""
    if project.current_stage_id:
        return f"Última etapa: {project.current_stage_id}"
    elif len(project.items) > 0:
        return "Ingestão (Em andamento / Interrompida)"
    else:
        return "Novo Projeto (Não iniciado)"

def run_pipeline_for_project(active_project):
    """Executa o pipeline para o projeto ativo e salva o estado."""
    config.set("general.last_project", active_project.name)
    runner = PipelineRunner()
    
    while True:
        console.clear()
        
        # Cabeçalho
        status = get_project_status_text(active_project)
        header_text = (
            "[bold white]:camera: IRIS - ASSISTENTE INTEGRADO DE MÍDIA :rocket:[/bold white]\n"
            f"[dim]Projeto Ativo:[/dim] [cyan][{active_project.name}][/cyan]\n"
            f"[dim]Status:[/dim] [yellow][{status}][/yellow]"
        )
        console.print(Panel(header_text, expand=False, border_style="cyan"))
        
        # Status do Ambiente
        dest_root = config.get("general.destination_root", "/caminho/para/destino")
        free_space = get_free_space_gb(dest_root)
        
        # Realiza scan rápido se o projeto for novo e não tiver dados de contagem
        if active_project.total_source_files == 0:
            from pathlib import Path
            source_dir = Path(active_project.source_path)
            valid_exts = {'.jpg', '.jpeg', '.png', '.mp4', '.mov', '.cr2', '.cr3', '.raw'}
            if source_dir.exists():
                count = 0
                size = 0
                for p in source_dir.rglob("*"):
                    if p.is_file() and p.suffix.lower() in valid_exts and not p.name.startswith('.'):
                        count += 1
                        size += p.stat().st_size
                active_project.total_source_files = count
                active_project.total_source_size_bytes = size
                active_project.save()
        
        total_size_gb = active_project.total_source_size_bytes / (1024**3)
        medias_count = active_project.total_source_files
        copied_count = len(active_project.items)
        
        space_status = "[green]:white_check_mark: Suficiente[/green]" if free_space > total_size_gb else "[red]:x: Insuficiente[/red]"
        
        env_text = (
            "[bold]\\[STATUS DO AMBIENTE][/bold]\n"
            f"  [dim]• Espaço Livre SSD:[/dim]   {free_space:.2f} GB\n"
            f"  [dim]• Origem Ativa:[/dim]       {active_project.source_path}\n"
            f"  [dim]• Mídias Mapeadas:[/dim]    {medias_count} arquivos ({total_size_gb:.2f} GB) - {copied_count} copiados\n"
            f"  [dim]• Status de Espaço:[/dim]   {space_status}\n"
            f"  [dim]• Raiz de Destino:[/dim]    {dest_root}"
        )
        console.print(Panel(env_text, expand=False, border_style="green"))
        
        # Ações
        console.print("\n[bold]\\[ENTER] :rocket: EXECUTAR TUDO (Sequencial)[/bold]")
        console.print("-" * 60)
        
        stages = runner.stages
        for i, stage in enumerate(stages, 1):
            console.print(f"  [cyan]{i}.[/cyan] :arrow_forward: Etapa {i}: {stage.name}")
            
        console.print("-" * 60)
        console.print("  [cyan]P.[/cyan] :open_file_folder: Voltar / Selecionar Projeto")
        console.print("  [cyan]C.[/cyan] :gear: Configurações")
        console.print("  [cyan]0.[/cyan] :door: Sair")
        
        choice = Prompt.ask("\nSelecione uma opção", default="R").upper()
        
        if choice == "0":
            console.print("Até logo!")
            sys.exit(0)
        elif choice == "P":
            break
        elif choice == "C":
            show_config_menu()
        elif choice == "R" or choice == "":
            runner.run_project(active_project)
            Prompt.ask("\n[dim]Pressione ENTER para continuar...[/dim]")
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(stages):
                    runner.run_stage(active_project, stages[idx].stage_id)
                    Prompt.ask("\n[dim]Pressione ENTER para continuar...[/dim]")
                else:
                    console.print("[red]Opção inválida.[/red]")
                    time.sleep(1)
            except ValueError:
                console.print("[red]Opção inválida.[/red]")
                time.sleep(1)

def start_new_project_flow():
    """Fluxo para criar um novo projeto."""
    console.print("\n[bold green]=== Novo Projeto ===[/bold green]")
    
    default_src = config.get("general.default_source", "/caminho/para/origem")
    source_path = Prompt.ask("Caminho de origem (Cartão SD/HD)", default=default_src)
    
    from pathlib import Path
    from datetime import datetime
    
    p = Path(source_path)
    folder_name = p.name if p.name else p.drive.replace(':', '')
    if not folder_name:
        folder_name = "ORIGEM"
        
    default_proj_name = datetime.now().strftime("%Y-%m-%d_%H-%M") + f"_{folder_name}"
    
    proj_name = Prompt.ask("Nome do projeto", default=default_proj_name)
    if not proj_name.strip():
        proj_name = default_proj_name
        
    if get_project(proj_name):
        console.print(f"[red]Erro: O projeto '{proj_name}' já existe. Retome-o na lista de projetos antigos.[/red]")
        time.sleep(2)
        return
        
    active_project = create_project(proj_name, source_path)
    console.print(f"[green]Projeto '{proj_name}' criado com sucesso.[/green]")
    
    run_pipeline_for_project(active_project)

def resume_project_flow(proj_name):
    """Retoma um projeto específico."""
    active_project = get_project(proj_name)
    if active_project:
        console.print(f"[green]Projeto '{proj_name}' carregado.[/green]")
        run_pipeline_for_project(active_project)
    else:
        console.print(f"[red]Projeto '{proj_name}' não encontrado.[/red]")
        time.sleep(2)

def list_projects_menu():
    """Mostra a lista de projetos antigos para escolha."""
    open_projects = list_open_projects()
    if not open_projects:
        console.print("[yellow]Nenhum projeto encontrado.[/yellow]")
        time.sleep(2)
        return
        
    console.print("\n[bold cyan]Projetos antigos encontrados:[/bold cyan]")
    for i, proj_name in enumerate(open_projects, 1):
        console.print(f"  [{i}] {proj_name}")
        
    console.print(f"  [0] Voltar")
    
    choice = Prompt.ask("\nSelecione um projeto para retomar", default="0")
    if choice == "0":
        return
    else:
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(open_projects):
                proj_name = open_projects[idx]
                resume_project_flow(proj_name)
            else:
                console.print("[red]Opção inválida.[/red]")
                time.sleep(1)
        except ValueError:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)

def main_menu():
    log_event("Iris CLI iniciada", "info")
    
    while True:
        console.clear()
        
        # Header principal
        console.print(Panel(
            "[bold white]:camera: IRIS - ASSISTENTE INTEGRADO DE MÍDIA :rocket:[/bold white]\n"
            "[dim]Central de Processamento de Fotos e Vídeos[/dim]",
            expand=False,
            border_style="cyan"
        ))
        
        last_project_name = config.get("general.last_project")
        last_project = get_project(last_project_name) if last_project_name else None
        
        # Painel do Último Projeto
        if last_project:
            status = get_project_status_text(last_project)
            medias_count = last_project.total_source_files
            copied_count = len(last_project.items)
            
            project_info = (
                f"[bold yellow]:open_file_folder: Último projeto acessado:[/bold yellow] [cyan][{last_project.name}][/cyan]\n"
                f"   [dim]• Status:[/dim] {status}\n"
                f"   [dim]• Mídias:[/dim] {medias_count} arquivos mapeados ({copied_count} copiados)\n"
                f"   [dim]• Origem:[/dim] {last_project.source_path}"
            )
            console.print(Panel(project_info, expand=False, border_style="yellow"))
            default_choice = "1"
        else:
            console.print(Panel("[dim]Nenhum projeto anterior encontrado.[/dim]", expand=False, border_style="dim"))
            default_choice = "2"
            
        console.print("\n[bold]Como deseja começar?[/bold]")
        
        if last_project:
            console.print("  [cyan][ENTER] ou 1.[/cyan] :arrows_counterclockwise: Retomar último projeto")
            console.print("             [cyan]2.[/cyan] :heavy_plus_sign: Criar um NOVO projeto")
        else:
            console.print("  [cyan][ENTER] ou 2.[/cyan] :heavy_plus_sign: Criar um NOVO projeto (Padrão)")
            
        console.print("             [cyan]3.[/cyan] :open_file_folder: Selecionar outro projeto da lista")
        console.print("             [cyan]S.[/cyan] :gear: Configurações")
        console.print("             [cyan]0.[/cyan] :door: Sair")
        
        choice = Prompt.ask("\nSelecione uma opção", default=default_choice).upper()
        
        if choice == "1" and last_project:
            run_pipeline_for_project(last_project)
        elif choice == "2" or (choice == "1" and not last_project):
            start_new_project_flow()
        elif choice == "3":
            list_projects_menu()
        elif choice == "S":
            show_config_menu()
        elif choice == "0":
            console.print("[green]Até logo![/green]")
            log_event("Iris CLI encerrada pelo usuário", "info")
            sys.exit(0)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrompido pelo usuário.[/yellow]")
        log_event("Iris CLI interrompida (SIGINT)", "warning")
        sys.exit(0)
