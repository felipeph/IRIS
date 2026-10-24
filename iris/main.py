import sys
import time

# Garante suporte completo a UTF-8 no console do Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        if sys.stdin and hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config
from src.core.logger import log_event, bind_project_logger
from src.core.project import list_open_projects, get_project, create_project, get_last_active_project
from src.core.lock import ProjectLock, ProjectLockedError
from src.core.pipeline import PipelineRunner
from src.core.metadata import MEDIA_EXTENSIONS
from src.core.geo import GeoService, GeoLocation, parse_coords, format_gps_token, maps_url, build_location_panel, interactive_add_location_flow

console = Console()

from src.core.config_menu import show_config_menu

import shutil
import re


def select_location_dialog(console: Console, default_id: str = None) -> GeoLocation:
    """Apresenta um menu interativo para seleção, cadastro ou exclusão de geolocalização para o projeto."""
    while True:
        locations = GeoService.get_locations()
        if not locations:
            GeoService.ensure_defaults()
            locations = GeoService.get_locations()

        if not default_id or not GeoService.get_location(default_id):
            default_id = GeoService.get_default_location_id()

        default_idx = 1
        table = Table(title="Localizações Geográficas Predefinidas", border_style="cyan")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Rótulo", style="bold white")
        table.add_column("Status", style="bold yellow")

        for i, loc in enumerate(locations, 1):
            if loc.id == default_id:
                default_idx = i
                def_str = "[bold green]★ SELECIONADO[/bold green]"
            else:
                def_str = ""
            table.add_row(str(i), loc.label, def_str)

        console.print(table)
        console.print("  [cyan]+[/cyan] Cadastrar novo local rapidamente")
        console.print("  [cyan]? ou V[/cyan] Ver detalhes de um local")
        console.print("  [cyan]- ou X[/cyan] [red]Excluir um local cadastrado[/red]")

        choice = Prompt.ask("\nSelecione a localização para o projeto", default=str(default_idx)).strip()
        if choice.upper() in ["?", "V"] or choice.upper().startswith("V ") or choice.upper().startswith("? "):
            parts = choice.split()
            if len(parts) > 1 and parts[1].isdigit():
                v_idx = int(parts[1]) - 1
            else:
                v_choice = Prompt.ask("Digite o número do local para ver detalhes", default=str(default_idx)).strip()
                try:
                    v_idx = int(v_choice) - 1
                except ValueError:
                    v_idx = -1
            if 0 <= v_idx < len(locations):
                target_loc = locations[v_idx]
                console.print()
                console.print(build_location_panel(target_loc, title=f"📍 [DETALHES DA CONFIGURAÇÃO: {target_loc.label}]", border_style="yellow"))
                Prompt.ask("\n[dim]Pressione ENTER para voltar à seleção...[/dim]")
            else:
                console.print("[red]Opção inválida.[/red]")
                time.sleep(1)
            continue
        if choice == "+":
            new_loc = interactive_add_location_flow(console, set_as_default=False)
            if new_loc:
                return new_loc
            continue

        if choice.upper() in ["-", "X"]:
            if len(locations) <= 1:
                console.print("[red]Não é possível excluir o único local cadastrado no sistema.[/red]")
                time.sleep(2)
                continue
            del_choice = Prompt.ask("Digite o número do local que deseja excluir (ou 0 para cancelar)", default="0").strip()
            if del_choice == "0":
                continue
            try:
                del_idx = int(del_choice) - 1
                if 0 <= del_idx < len(locations):
                    target_loc = locations[del_idx]
                    confirmed = Confirm.ask(f"[bold red]Tem certeza que deseja excluir o local '{target_loc.label}' ({target_loc.id})?[/bold red]", default=False)
                    if confirmed:
                        GeoService.delete_location(target_loc.id)
                        console.print(f"[green]Local '{target_loc.label}' excluído com sucesso![/green]")
                        if default_id == target_loc.id:
                            default_id = GeoService.get_default_location_id()
                        time.sleep(1.5)
                else:
                    console.print("[red]Número inválido.[/red]")
                    time.sleep(1)
            except ValueError:
                console.print("[red]Entrada inválida.[/red]")
                time.sleep(1)
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(locations):
                return locations[idx]
            else:
                console.print("[red]Opção inválida.[/red]")
                time.sleep(1)
        except ValueError:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)

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
    elif project.has_items():
        return "Ingestão (Em andamento / Interrompida)"
    else:
        return "Novo Projeto (Não iniciado)"

def run_pipeline_for_project(active_project):
    """Executa o pipeline para o projeto ativo com bloqueio exclusivo anti-concorrência."""
    lock = ProjectLock(active_project.name)
    try:
        lock.acquire()
    except ProjectLockedError as e:
        console.clear()
        panel_msg = (
            f"[bold red]❌ PROJETO JÁ EM EXECUÇÃO EM OUTRO TERMINAL[/bold red]\n\n"
            f"[yellow]O projeto '[bold]{e.project_name}[/bold]' está em uso pelo processo PID [bold]{e.pid}[/bold][/yellow]\n"
            f"[dim]Computador:[/dim] {e.hostname}\n"
            f"[dim]Bloqueado desde:[/dim] {e.acquired_at}\n\n"
            f"[white]Para garantir a integridade dos seus dados e evitar colisões físicas de arquivos,\n"
            f"não é permitido abrir o mesmo projeto em dois terminais simultaneamente.[/white]\n\n"
            f"[cyan]💡 Dica: Você pode abrir ou processar outro projeto em paralelo neste terminal![/cyan]"
        )
        console.print(Panel(panel_msg, expand=False, border_style="red"))
        Prompt.ask("\n[dim]Pressione ENTER para voltar ao menu...[/dim]")
        return

    bind_project_logger(active_project.name)
    active_project.touch()
    runner = PipelineRunner()
    
    try:
        while True:
            console.clear()
            
            # Cabeçalho
            status = get_project_status_text(active_project)
            header_text = (
                "[bold white]:camera: IRIS - IMAGING RESOURCES AND INTEGRATION SYSTEM :rocket:[/bold white]\n"
                f"[dim]Projeto Ativo:[/dim] [cyan][{active_project.name}][/cyan]\n"
                f"[dim]Status:[/dim] [yellow][{status}][/yellow]"
            )
            console.print(Panel(header_text, expand=False, border_style="cyan"))

            # Localização Ativa do Projeto
            loc = GeoService.get_location(active_project.geo_location_id) if active_project.geo_location_id else None
            if not loc:
                loc = GeoService.get_default_location()
                if loc and not active_project.geo_location_id:
                    active_project.geo_location_id = loc.id
                    active_project.save()

            if loc:
                console.print(build_location_panel(loc, title="📍 [LOCALIZAÇÃO ATIVA DO PROJETO]", border_style="yellow"))
            
            # Status do Ambiente
            dest_root = config.get("general.destination_root", "C:\\IRIS")
            free_space = get_free_space_gb(dest_root)
            
            # Realiza scan rápido se o projeto for novo e não tiver dados de contagem
            if active_project.total_source_files == 0 and not active_project.has_items():
                from pathlib import Path
                source_dir = Path(active_project.source_path)
                if source_dir.exists():
                    count = 0
                    size = 0
                    for p in source_dir.rglob("*"):
                        if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS and not p.name.startswith('.'):
                            count += 1
                            size += p.stat().st_size
                    active_project.total_source_files = count
                    active_project.total_source_size_bytes = size
                    active_project.save()
            
            total_size_gb = active_project.total_source_size_bytes / (1024**3)
            medias_count = active_project.total_source_files
            copied_count = active_project.get_items_count()
            
            space_status = "[green]:white_check_mark: Suficiente[/green]" if free_space > total_size_gb else "[red]:x: Insuficiente[/red]"
            
            clean_status = "[green]:wastebasket: Ativada (Sem confirmação)[/green]" if active_project.auto_cleanup else "[yellow]Desativada (Preservar origem)[/yellow]"
            ingest_strat_val = config.get("modules.ingestion.strategy", "move")
            ingest_workers_val = config.get("modules.ingestion.max_workers", 4)
            ingest_mode_str = f"[bold green]Movimentação Nativa ({ingest_workers_val} workers)[/bold green]" if ingest_strat_val == "move" else "[cyan]Cópia Segura (Hash on-the-fly)[/cyan]"

            env_text = (
                "[bold]\\[STATUS DO AMBIENTE][/bold]\n"
                f"  [dim]• Espaço Livre SSD:[/dim]   {free_space:.2f} GB\n"
                f"  [dim]• Origem Ativa:[/dim]       {active_project.source_path}\n"
                f"  [dim]• Mídias Mapeadas:[/dim]    {medias_count} arquivos ({total_size_gb:.2f} GB) - {copied_count} copiados\n"
                f"  [dim]• Modo Ingestão:[/dim]      {ingest_mode_str}\n"
                f"  [dim]• Limpeza Automática:[/dim] {clean_status}\n"
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
            console.print("  [cyan]G.[/cyan] :round_pushpin: Alterar Localização do Projeto")
            console.print("  [cyan]L.[/cyan] :wastebasket: Alternar Limpeza Automática")
            console.print("  [cyan]P.[/cyan] :open_file_folder: Voltar / Selecionar Projeto")
            console.print("  [cyan]C.[/cyan] :gear: Configurações")
            console.print("  [cyan]0.[/cyan] :door: Sair")
            
            choice = Prompt.ask("\nSelecione uma opção", default="R").upper()
            
            if choice == "0":
                console.print("Até logo!")
                sys.exit(0)
            elif choice == "G":
                new_loc = select_location_dialog(console, default_id=active_project.geo_location_id)
                if new_loc:
                    active_project.geo_location_id = new_loc.id
                    active_project.save()
                    console.print(f"\n[bold green]✔ Localização do projeto alterada para: {new_loc.label}[/bold green]")
                    time.sleep(1.5)
            elif choice == "L":
                active_project.auto_cleanup = not active_project.auto_cleanup
                active_project.save()
                status_txt = "[green]Ativada (arquivos verificados irão para a lixeira sem confirmação)[/green]" if active_project.auto_cleanup else "[yellow]Desativada (origem preservada no fluxo sequencial)[/yellow]"
                console.print(f"\nLimpeza automática do projeto: {status_txt}")
                time.sleep(1.5)
            elif choice == "P":
                break
            elif choice == "C":
                show_config_menu()
            elif choice == "R" or choice == "":
                if loc:
                    confirmed_loc = Confirm.ask(f"\n[bold yellow]📍 Confirmar localização '{loc.label}' para o processamento?[/bold yellow]", default=True)
                    if not confirmed_loc:
                        new_loc = select_location_dialog(console, default_id=active_project.geo_location_id)
                        if new_loc:
                            active_project.geo_location_id = new_loc.id
                            active_project.save()
                            loc = new_loc
                            console.print(f"[green]Localização atualizada para: {loc.label}[/green]")

                last_stage_id = stages[-1].stage_id if stages else None
                if active_project.current_stage_id and active_project.current_stage_id == last_stage_id:
                    console.print(f"\n[yellow]ℹ Este projeto já concluiu todas as etapas (Última: {active_project.current_stage_id}).[/yellow]")
                    restart = Confirm.ask("Deseja reiniciar a execução do pipeline desde a primeira etapa?", default=False)
                    if restart:
                        active_project.current_stage_id = ""
                        active_project.save()
                        runner.run_project(active_project)
                    else:
                        console.print("[dim]Dica: Você pode selecionar uma etapa individual pelo seu número para reexecutar apenas ela.[/dim]")
                else:
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
    finally:
        lock.release()
        bind_project_logger("")

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
        
    console.print("\n[bold cyan]📍 Defina a localização geográfica do projeto:[/bold cyan]")
    loc = select_location_dialog(console)
    active_project = create_project(proj_name, source_path, geo_location_id=loc.id if loc else None)
    console.print(f"[green]Projeto '{proj_name}' criado com sucesso (Localização: {loc.label if loc else 'Padrão'}).[/green]")
    
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
            "[bold white]:camera: IRIS - IMAGING RESOURCES AND INTEGRATION SYSTEM :rocket:[/bold white]\n"
            "[dim]Central de Processamento de Fotos e Vídeos[/dim]",
            expand=False,
            border_style="cyan"
        ))
        
        last_project_name = get_last_active_project()
        last_project = get_project(last_project_name) if last_project_name else None
        
        # Painel do Último Projeto
        if last_project:
            status = get_project_status_text(last_project)
            medias_count = last_project.total_source_files
            copied_count = last_project.get_items_count()
            
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
