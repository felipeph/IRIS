import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config
from src.core.logger import log_event, bind_project_logger
from src.core.project import list_open_projects, get_project, create_project, get_last_active_project
from src.core.lock import ProjectLock, ProjectLockedError
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
        table.add_row("3", "Nível de Log", str(config.get("general.log_level", "INFO")))
        table.add_row("4", "Padrão Nome (Fotos)", str(config.get("naming.photo_pattern")))
        table.add_row("5", "Padrão Nome (Vídeos)", str(config.get("naming.video_pattern")))
        table.add_row("6", "Zoom Lua (mm) Threshold", str(config.get("classification.moon_zoom_threshold_mm")))
        table.add_row("7", "Min Fotos Timelapse", str(config.get("classification.timelapse_min_photos")))
        table.add_row("8", "FPS Timelapse", str(config.get("modules.timelapse.fps", 60)))
        table.add_row("9", "Frames por Foto (FPI)", str(config.get("modules.timelapse.frames_per_image", 1)))
        table.add_row("10", "Modo de Corte (Crop)", str(config.get("modules.timelapse.crop_mode", "bottom")))
        table.add_row("11", "Fator Qualidade CRF", str(config.get("modules.timelapse.crf", 15)))
        table.add_row("12", "Preset FFmpeg", str(config.get("modules.timelapse.preset", "ultrafast")))
        table.add_row("13", "Privacidade YouTube", str(config.get("modules.youtube.privacy_status", "unlisted")))
        table.add_row("14", "Playlist YouTube", str(config.get("modules.youtube.playlist", "Timelapses")))
        table.add_row("15", "Tópico NTFY Notificações", str(config.get("modules.timelapse.ntfy_topic", "timelapse-studio-2026")))
        auto_clean_val = config.get("modules.cleanup.auto_clean", False)
        table.add_row("16", "Limpeza Automática SD (Global)", "[green]Sim[/green]" if auto_clean_val else "[red]Não[/red]")
        sample_enabled = config.get("classification.enable_timelapse_album_samples", True)
        table.add_row("17", "Amostras Timelapse p/ Álbum", "[green]Sim[/green]" if sample_enabled else "[red]Não[/red]")
        table.add_row("18", "Intervalo Amostras (min)", str(config.get("classification.timelapse_sample_interval_minutes", 5.0)))
        
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
            new_val = Prompt.ask("Novo Nível de Log (INFO, DEBUG, WARNING, ERROR)", default=str(config.get("general.log_level", "INFO"))).upper()
            if new_val in ["INFO", "DEBUG", "WARNING", "ERROR"]:
                config.set("general.log_level", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida![/red]")
            time.sleep(1)
        elif choice == "4":
            new_val = Prompt.ask("Novo Padrão de Nome (Fotos)", default=str(config.get("naming.photo_pattern")))
            config.set("naming.photo_pattern", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "5":
            new_val = Prompt.ask("Novo Padrão de Nome (Vídeos)", default=str(config.get("naming.video_pattern")))
            config.set("naming.video_pattern", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "6":
            new_val = Prompt.ask("Novo Zoom Lua (mm) Threshold", default=str(config.get("classification.moon_zoom_threshold_mm")))
            try:
                config.set("classification.moon_zoom_threshold_mm", float(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número![/red]")
            time.sleep(1)
        elif choice == "7":
            new_val = Prompt.ask("Nova Qtd Min Fotos p/ Timelapse", default=str(config.get("classification.timelapse_min_photos")))
            try:
                config.set("classification.timelapse_min_photos", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "8":
            new_val = Prompt.ask("Novo FPS para Timelapse", default=str(config.get("modules.timelapse.fps", 60)))
            try:
                config.set("modules.timelapse.fps", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "9":
            new_val = Prompt.ask("Frames por Foto (FPI)", default=str(config.get("modules.timelapse.frames_per_image", 1)))
            try:
                config.set("modules.timelapse.frames_per_image", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "10":
            console.print("Modos de Enquadramento: [bold]bottom[/bold] (Base), [bold]center[/bold] (Centro), [bold]top[/bold] (Topo)")
            new_val = Prompt.ask("Novo Modo de Corte", default=str(config.get("modules.timelapse.crop_mode", "bottom"))).lower()
            if new_val in ["bottom", "center", "top"]:
                config.set("modules.timelapse.crop_mode", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida! Escolha bottom, center ou top.[/red]")
            time.sleep(1)
        elif choice == "11":
            new_val = Prompt.ask("Fator de Qualidade CRF (0-51, menor = melhor)", default=str(config.get("modules.timelapse.crf", 15)))
            try:
                config.set("modules.timelapse.crf", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "12":
            new_val = Prompt.ask("Preset FFmpeg (ultrafast, superfast, medium, slow)", default=str(config.get("modules.timelapse.preset", "ultrafast")))
            config.set("modules.timelapse.preset", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "13":
            new_val = Prompt.ask("Privacidade no YouTube (unlisted, private, public)", default=str(config.get("modules.youtube.privacy_status", "unlisted"))).lower()
            if new_val in ["unlisted", "private", "public"]:
                config.set("modules.youtube.privacy_status", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida![/red]")
            time.sleep(1)
        elif choice == "14":
            new_val = Prompt.ask("Playlist no YouTube", default=str(config.get("modules.youtube.playlist", "Timelapses")))
            config.set("modules.youtube.playlist", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "15":
            new_val = Prompt.ask("Canal do NTFY", default=str(config.get("modules.timelapse.ntfy_topic", "timelapse-studio-2026")))
            config.set("modules.timelapse.ntfy_topic", new_val)
            config.set("modules.youtube.ntfy_topic", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "16":
            curr = config.get("modules.cleanup.auto_clean", False)
            new_val = Confirm.ask("Ativar limpeza automática da origem por padrão em novos projetos?", default=curr)
            config.set("modules.cleanup.auto_clean", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "17":
            curr = config.get("classification.enable_timelapse_album_samples", True)
            new_val = Confirm.ask("Copiar automaticamente amostras de timelapses para subpastas de álbuns?", default=curr)
            config.set("classification.enable_timelapse_album_samples", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "18":
            curr = config.get("classification.timelapse_sample_interval_minutes", 5.0)
            new_val = Prompt.ask("Intervalo de tempo entre amostras (minutos)", default=str(curr))
            try:
                val_float = float(new_val)
                if val_float <= 0:
                    raise ValueError
                config.set("classification.timelapse_sample_interval_minutes", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número positivo maior que zero![/red]")
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
            
            clean_status = "[green]:wastebasket: Ativada (Sem confirmação)[/green]" if active_project.auto_cleanup else "[yellow]Desativada (Preservar origem)[/yellow]"
            env_text = (
                "[bold]\\[STATUS DO AMBIENTE][/bold]\n"
                f"  [dim]• Espaço Livre SSD:[/dim]   {free_space:.2f} GB\n"
                f"  [dim]• Origem Ativa:[/dim]       {active_project.source_path}\n"
                f"  [dim]• Mídias Mapeadas:[/dim]    {medias_count} arquivos ({total_size_gb:.2f} GB) - {copied_count} copiados\n"
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
            console.print("  [cyan]L.[/cyan] :wastebasket: Alternar Limpeza Automática")
            console.print("  [cyan]P.[/cyan] :open_file_folder: Voltar / Selecionar Projeto")
            console.print("  [cyan]C.[/cyan] :gear: Configurações")
            console.print("  [cyan]0.[/cyan] :door: Sair")
            
            choice = Prompt.ask("\nSelecione uma opção", default="R").upper()
            
            if choice == "0":
                console.print("Até logo!")
                sys.exit(0)
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
        
        last_project_name = get_last_active_project()
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
