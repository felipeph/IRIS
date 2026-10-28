import time
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config
from src.core.cleanup import clean_empty_directories


def _menu_storage_ingestion(console: Console):
    """Sub-menu: Armazenamento & Ingestão."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: Armazenamento & Ingestão[/bold yellow]", expand=False))
        
        table = Table(title="Armazenamento & Ingestão")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        table.add_row("1", "Diretório Destino", "general.destination_root", str(config.get("general.destination_root")))
        table.add_row("2", "Origem Padrão", "general.default_source", str(config.get("general.default_source")))
        table.add_row("3", "Nível de Log", "general.log_level", str(config.get("general.log_level", "INFO")))
        
        ingest_strat = config.get("modules.ingestion.strategy", "move")
        strat_display = "Movimentação Nativa (Turbo)" if ingest_strat == "move" else "Cópia Segura (Hash on-the-fly)"
        table.add_row("4", "Estratégia de Ingestão", "modules.ingestion.strategy", strat_display)
        table.add_row("5", "Workers Ingestão (Threads)", "modules.ingestion.max_workers", str(config.get("modules.ingestion.max_workers", 4)))
        
        auto_clean_val = config.get("modules.cleanup.auto_clean", False)
        table.add_row("6", "Limpeza Automática SD (Global)", "modules.cleanup.auto_clean", "[green]Sim[/green]" if auto_clean_val else "[red]Não[/red]")
        
        allow_perm_val = config.get("modules.cleanup.allow_permanent_sd_clean", False)
        table.add_row("7", "Exclusão Permanente SD s/ Lixeira", "modules.cleanup.allow_permanent_sd_clean", "[green]Permitida[/green]" if allow_perm_val else "[yellow]Bloqueada (Segura)[/yellow]")
        table.add_row("8", "🧹 Limpar Pastas Vazias no IRIS", "Ação Imediata", "[cyan]Executar varredura agora[/cyan]")
        
        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
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
            console.print("Estratégias disponíveis: [bold]move[/bold] (Rápida - movimentação nativa do SO), [bold]copy[/bold] (Clássica - cópia segura com fsync)")
            curr = config.get("modules.ingestion.strategy", "move")
            new_val = Prompt.ask("Escolha a estratégia (move/copy)", default=curr).lower()
            if new_val in ["move", "copy"]:
                config.set("modules.ingestion.strategy", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida! Escolha 'move' ou 'copy'.[/red]")
            time.sleep(1)
        elif choice == "5":
            curr = config.get("modules.ingestion.max_workers", 4)
            new_val = Prompt.ask("Quantidade de Workers / Threads para Ingestão (1 a 32)", default=str(curr))
            try:
                workers_int = int(new_val)
                if 1 <= workers_int <= 32:
                    config.set("modules.ingestion.max_workers", workers_int)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 1 e 32![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "6":
            curr = config.get("modules.cleanup.auto_clean", False)
            new_val = Confirm.ask("Ativar limpeza automática da origem por padrão em novos projetos?", default=curr)
            config.set("modules.cleanup.auto_clean", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "7":
            curr = config.get("modules.cleanup.allow_permanent_sd_clean", False)
            new_val = Confirm.ask("Permitir exclusão permanente no SD caso não suporte Lixeira (Zero Data Loss recomenda 'Não')?", default=curr)
            config.set("modules.cleanup.allow_permanent_sd_clean", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "8":
            dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
            console.print(f"\n[cyan]Varrendo pastas vazias em {dest_root}...[/cyan]")
            removed = clean_empty_directories(dest_root, preserve_root=True)
            if removed > 0:
                console.print(f"[bold green]✔ {removed} pasta(s) vazia(s) removida(s) com sucesso![/bold green]")
            else:
                console.print("[yellow]Nenhuma pasta vazia encontrada na raiz do IRIS.[/yellow]")
            time.sleep(2)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def _menu_organization_classification(console: Console):
    """Sub-menu: Organização & Classificação."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: Organização & Classificação[/bold yellow]", expand=False))
        
        table = Table(title="Organização & Classificação")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        table.add_row("1", "Padrão Nome (Fotos)", "naming.photo_pattern", str(config.get("naming.photo_pattern")))
        table.add_row("2", "Padrão Nome (Vídeos)", "naming.video_pattern", str(config.get("naming.video_pattern")))
        table.add_row("3", "Zoom Lua (mm) Threshold", "classification.moon_zoom_threshold_mm", str(config.get("classification.moon_zoom_threshold_mm")))
        
        min_photos_val = config.get("classification.timelapse_normal.min_photos", config.get("classification.timelapse_min_photos", 200))
        table.add_row("4", "Min Fotos Timelapse Normal", "classification.timelapse_normal.min_photos", str(min_photos_val))
        
        sample_enabled = config.get("classification.enable_timelapse_album_samples", True)
        table.add_row("5", "Amostras Timelapse p/ Álbum", "classification.enable_timelapse_album_samples", "[green]Sim[/green]" if sample_enabled else "[red]Não[/red]")
        table.add_row("6", "Intervalo Amostras (min)", "classification.timelapse_sample_interval_minutes", str(config.get("classification.timelapse_sample_interval_minutes", 5.0)))
        
        rec_folders = config.get("classification.recognize_timelapse_folders", True)
        table.add_row("7", "Reconhecer Pastas Timelapse", "classification.recognize_timelapse_folders", "[green]Sim[/green]" if rec_folders else "[red]Não[/red]")
        
        max_int_val = config.get("classification.timelapse_normal.max_interval_seconds", config.get("classification.timelapse_max_interval_seconds", 60.0))
        table.add_row("8", "Intervalo Máx Timelapse Normal (s)", "classification.timelapse_normal.max_interval_seconds", str(max_int_val))
        
        tol_val = config.get("classification.timelapse_normal.tolerance_ratio", config.get("classification.timelapse_tolerance_ratio", 0.25))
        table.add_row("9", "Tolerância Cadência Normal (ratio)", "classification.timelapse_normal.tolerance_ratio", f"{tol_val:.2f} ({int(tol_val*100)}%)")

        burst_enabled = config.get("classification.enable_burst_detection", True)
        table.add_row("10", "Detecção de Fotos em Rajada", "classification.enable_burst_detection", "[green]Ativado[/green]" if burst_enabled else "[red]Desativado[/red]")
        
        burst_int_val = config.get("classification.burst_interval_seconds", 1.5)
        table.add_row("11", "Intervalo Máx Rajada (s)", "classification.burst_interval_seconds", str(burst_int_val))

        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            new_val = Prompt.ask("Novo Padrão de Nome (Fotos)", default=str(config.get("naming.photo_pattern")))
            config.set("naming.photo_pattern", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "2":
            new_val = Prompt.ask("Novo Padrão de Nome (Vídeos)", default=str(config.get("naming.video_pattern")))
            config.set("naming.video_pattern", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "3":
            new_val = Prompt.ask("Novo Zoom Lua (mm) Threshold", default=str(config.get("classification.moon_zoom_threshold_mm")))
            try:
                config.set("classification.moon_zoom_threshold_mm", float(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número![/red]")
            time.sleep(1)
        elif choice == "4":
            curr_min = config.get("classification.timelapse_normal.min_photos", config.get("classification.timelapse_min_photos", 200))
            new_val = Prompt.ask("Nova Qtd Min Fotos p/ Timelapse Normal", default=str(curr_min))
            try:
                val_int = int(new_val)
                config.set("classification.timelapse_normal.min_photos", val_int)
                config.set("classification.timelapse_min_photos", val_int)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "5":
            curr = config.get("classification.enable_timelapse_album_samples", True)
            new_val = Confirm.ask("Copiar automaticamente amostras de timelapses para subpastas de álbuns?", default=curr)
            config.set("classification.enable_timelapse_album_samples", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "6":
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
        elif choice == "7":
            curr = config.get("classification.recognize_timelapse_folders", True)
            new_val = Confirm.ask("Reconhecer automaticamente pastas pré-organizadas com 'timelapse' no nome?", default=curr)
            config.set("classification.recognize_timelapse_folders", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "8":
            curr = config.get("classification.timelapse_normal.max_interval_seconds", config.get("classification.timelapse_max_interval_seconds", 60.0))
            new_val = Prompt.ask("Intervalo máximo entre fotos para Timelapse Normal (segundos)", default=str(curr))
            try:
                val_float = float(new_val)
                if val_float <= 0:
                    raise ValueError
                config.set("classification.timelapse_normal.max_interval_seconds", val_float)
                config.set("classification.timelapse_max_interval_seconds", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número positivo maior que zero![/red]")
            time.sleep(1)
        elif choice == "9":
            curr = config.get("classification.timelapse_normal.tolerance_ratio", config.get("classification.timelapse_tolerance_ratio", 0.25))
            new_val = Prompt.ask("Tolerância de cadência para Timelapse Normal (ex: 0.25 para 25%)", default=str(curr))
            try:
                val_float = float(new_val)
                if val_float <= 0 or val_float >= 2.0:
                    raise ValueError
                config.set("classification.timelapse_normal.tolerance_ratio", val_float)
                config.set("classification.timelapse_tolerance_ratio", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser entre 0.01 e 1.99![/red]")
            time.sleep(1)
        elif choice == "10":
            curr = config.get("classification.enable_burst_detection", True)
            new_val = Confirm.ask("Organizar automaticamente fotos consecutivas em pastas de rajada?", default=curr)
            config.set("classification.enable_burst_detection", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "11":
            curr = config.get("classification.burst_interval_seconds", 1.5)
            new_val = Prompt.ask("Intervalo máximo entre fotos para agrupar em rajada (segundos)", default=str(curr))
            try:
                val_float = float(new_val)
                if val_float <= 0:
                    raise ValueError
                config.set("classification.burst_interval_seconds", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número positivo maior que zero![/red]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)
