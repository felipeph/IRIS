import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from src.core.config import config


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
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def _menu_timelapse(console: Console):
    """Sub-menu: Renderização de Timelapse 4K."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: Renderização de Timelapse 4K[/bold yellow]", expand=False))
        
        table = Table(title="Renderização de Timelapse 4K")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        tl_profile = config.get("modules.timelapse.render_profile", "fast")
        tl_prof_desc = "Fast (Intel QSV HW / 1:1 Sensor)" if tl_profile == "fast" else ("Balanced (Bicúbico)" if tl_profile == "balanced" else "Quality (Lanczos/Deband)")
        table.add_row("1", "Perfil Renderização Timelapse", "modules.timelapse.render_profile", tl_prof_desc)
        table.add_row("2", "FPS Timelapse", "modules.timelapse.fps", str(config.get("modules.timelapse.fps", 60)))
        table.add_row("3", "Frames por Foto (FPI)", "modules.timelapse.frames_per_image", str(config.get("modules.timelapse.frames_per_image", 1)))
        table.add_row("4", "Modo de Corte (Crop)", "modules.timelapse.crop_mode", str(config.get("modules.timelapse.crop_mode", "bottom")))
        table.add_row("5", "Fator Qualidade CRF", "modules.timelapse.crf", str(config.get("modules.timelapse.crf", 15)))
        table.add_row("6", "Preset FFmpeg", "modules.timelapse.preset", str(config.get("modules.timelapse.preset", "ultrafast")))
        
        deband_enabled = config.get("modules.timelapse.deband.enabled", True)
        table.add_row("7", "Filtro Deband (Anti-banding)", "modules.timelapse.deband.enabled", "[green]Ativado[/green]" if deband_enabled else "[red]Desativado[/red]")
        grain_enabled = config.get("modules.timelapse.deband.add_grain", True)
        table.add_row("8", "Ruído Temporal (Micro-grão)", "modules.timelapse.deband.add_grain", "[green]Ativado[/green]" if grain_enabled else "[red]Desativado[/red]")
        
        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            curr = config.get("modules.timelapse.render_profile", "fast")
            console.print("Perfis disponíveis: [bold]fast[/bold] (Intel QSV HW / Corte 1:1 Sensor / Máxima velocidade), [bold]balanced[/bold] (Equilibrado / bicúbico), [bold]quality[/bold] (Máxima qualidade / Lanczos 4K + deband)")
            new_val = Prompt.ask("Escolha o perfil para timelapse (fast/balanced/quality)", default=str(curr)).lower().strip()
            if new_val in ["fast", "balanced", "quality"]:
                config.set("modules.timelapse.render_profile", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida! Escolha 'fast', 'balanced' ou 'quality'.[/red]")
            time.sleep(1)
        elif choice == "2":
            new_val = Prompt.ask("Novo FPS para Timelapse", default=str(config.get("modules.timelapse.fps", 60)))
            try:
                config.set("modules.timelapse.fps", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "3":
            new_val = Prompt.ask("Frames por Foto (FPI)", default=str(config.get("modules.timelapse.frames_per_image", 1)))
            try:
                config.set("modules.timelapse.frames_per_image", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "4":
            console.print("Modos de Enquadramento: [bold]bottom[/bold] (Base), [bold]center[/bold] (Centro), [bold]top[/bold] (Topo), [bold]full[/bold] (Quadro Completo com Bordas / Pillarbox)")
            new_val = Prompt.ask("Novo Modo de Corte", default=str(config.get("modules.timelapse.crop_mode", "bottom"))).lower()
            if new_val in ["bottom", "center", "top", "full"]:
                config.set("modules.timelapse.crop_mode", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida! Escolha bottom, center, top ou full.[/red]")
            time.sleep(1)
        elif choice == "5":
            new_val = Prompt.ask("Fator de Qualidade CRF (0-51, menor = melhor)", default=str(config.get("modules.timelapse.crf", 15)))
            try:
                config.set("modules.timelapse.crf", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "6":
            new_val = Prompt.ask("Preset FFmpeg (ultrafast, superfast, medium, slow)", default=str(config.get("modules.timelapse.preset", "ultrafast")))
            config.set("modules.timelapse.preset", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "7":
            curr = config.get("modules.timelapse.deband.enabled", True)
            new_val = Confirm.ask("Ativar filtro Deband 16-bit (suavização de faixas de cor em gradientes)?", default=curr)
            config.set("modules.timelapse.deband.enabled", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "8":
            curr = config.get("modules.timelapse.deband.add_grain", True)
            new_val = Confirm.ask("Ativar injeção de ruído/micro-grão temporal dither (otimização para YouTube)?", default=curr)
            config.set("modules.timelapse.deband.add_grain", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def _menu_video_edit(console: Console):
    """Sub-menu: Edição e Upscale de Vídeo 4K."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: Edição e Upscale de Vídeo 4K[/bold yellow]", expand=False))
        
        table = Table(title="Edição e Upscale de Vídeo 4K")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        ve_profile = config.get("modules.video_edit.render_profile", "fast")
        prof_desc = "Fast (Intel QSV HW)" if ve_profile == "fast" else ("Balanced (Bicúbico/3x3)" if ve_profile == "balanced" else "Quality (Lanczos/16-bit)")
        table.add_row("1", "Perfil Renderização Vídeo", "modules.video_edit.render_profile", prof_desc)
        
        ve_mode = config.get("modules.video_edit.mode", "individual")
        table.add_row("2", "Modo Edição Vídeo", "modules.video_edit.mode", "Individual (1:1)" if ve_mode == "individual" else "Junção por Pasta")
        
        ve_speed = config.get("modules.video_edit.speed", 1.0)
        table.add_row("3", "Velocidade Vídeo (--speed)", "modules.video_edit.speed", f"{ve_speed}x")
        
        ve_fps = config.get("modules.video_edit.target_fps", 60)
        table.add_row("4", "FPS Alvo Saída Vídeos", "modules.video_edit.target_fps", str(ve_fps))
        
        ve_trim = config.get("modules.video_edit.trim_seconds", 2.0)
        table.add_row("5", "Trimming Início/Fim (s)", "modules.video_edit.trim_seconds", f"{ve_trim}s")
        
        ve_strip = config.get("modules.video_edit.strip_audio", False)
        table.add_row("6", "Remover Áudio Vídeos (Mudo)", "modules.video_edit.strip_audio", "[red]Sim (Mudo)[/red]" if ve_strip else "[green]Não (Preservar)[/green]")
        
        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            curr = config.get("modules.video_edit.render_profile", "fast")
            console.print("Perfis disponíveis: [bold]fast[/bold] (Intel QSV hardware / máxima eficiência), [bold]balanced[/bold] (Equilibrado / unsharp 3x3), [bold]quality[/bold] (Máxima qualidade / Lanczos 4K)")
            new_val = Prompt.ask("Escolha o perfil (fast/balanced/quality)", default=str(curr)).lower().strip()
            if new_val in ["fast", "balanced", "quality"]:
                config.set("modules.video_edit.render_profile", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida! Escolha 'fast', 'balanced' ou 'quality'.[/red]")
            time.sleep(1)
        elif choice == "2":
            console.print("Modos de Edição: [bold]individual[/bold] (Upscale 1:1 de cada vídeo individualmente), [bold]joined[/bold] (Junta os vídeos que vieram da mesma pasta de origem)")
            curr = config.get("modules.video_edit.mode", "individual")
            new_val = Prompt.ask("Escolha o modo (individual/joined)", default=curr).lower().strip()
            if new_val in ["individual", "joined"]:
                config.set("modules.video_edit.mode", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida! Escolha 'individual' ou 'joined'.[/red]")
            time.sleep(1)
        elif choice == "3":
            curr = config.get("modules.video_edit.speed", 1.0)
            new_val = Prompt.ask("Velocidade do vídeo (ex: 1.0, 2.0, 0.5)", default=str(curr))
            try:
                val_float = float(new_val.lower().replace("x", ""))
                if val_float <= 0:
                    raise ValueError
                config.set("modules.video_edit.speed", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um multiplicador positivo (ex: 1.0, 2.0, 0.5)![/red]")
            time.sleep(1)
        elif choice == "4":
            curr = config.get("modules.video_edit.target_fps", 60)
            new_val = Prompt.ask("FPS Alvo de Saída (ex: 30, 60)", default=str(curr))
            try:
                val_int = int(new_val)
                if val_int <= 0:
                    raise ValueError
                config.set("modules.video_edit.target_fps", val_int)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro positivo (ex: 30, 60)![/red]")
            time.sleep(1)
        elif choice == "5":
            curr = config.get("modules.video_edit.trim_seconds", 2.0)
            new_val = Prompt.ask("Segundos a cortar no início e fim de cada clipe", default=str(curr))
            try:
                val_float = float(new_val)
                if val_float < 0:
                    raise ValueError
                config.set("modules.video_edit.trim_seconds", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser zero ou um número positivo![/red]")
            time.sleep(1)
        elif choice == "6":
            curr = config.get("modules.video_edit.strip_audio", False)
            new_val = Confirm.ask("Remover áudio dos vídeos editados (produzir vídeo mudo)?", default=curr)
            config.set("modules.video_edit.strip_audio", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def _menu_youtube_notifications(console: Console):
    """Sub-menu: YouTube & Notificações."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: YouTube & Notificações[/bold yellow]", expand=False))
        
        table = Table(title="YouTube & Notificações")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        table.add_row("1", "Privacidade YouTube", "modules.youtube.privacy_status", str(config.get("modules.youtube.privacy_status", "unlisted")))
        table.add_row("2", "Playlist Timelapses", "modules.youtube.playlist", str(config.get("modules.youtube.playlist", "Timelapses")))
        
        ve_pl = config.get("modules.youtube.video_playlist", "Natureza 4K UHD")
        table.add_row("3", "Playlist Vídeos YouTube", "modules.youtube.video_playlist", str(ve_pl))
        table.add_row("4", "Tópico NTFY Notificações", "modules.timelapse.ntfy_topic", str(config.get("modules.timelapse.ntfy_topic", "timelapse-studio-2026")))
        
        clean_enabled = config.get("modules.youtube.cleanup_local_videos", True)
        table.add_row("5", "Limpeza Local Pós-Upload", "modules.youtube.cleanup_local_videos", "[green]Ativada[/green]" if clean_enabled else "[red]Desativada[/red]")
        
        to_trash_val = config.get("modules.youtube.cleanup_to_trash", True)
        trash_display = "[green]Lixeira (send2trash)[/green]" if to_trash_val else "[red]Permanente (unlink)[/red]"
        table.add_row("6", "Destino da Exclusão", "modules.youtube.cleanup_to_trash", trash_display)
        
        auto_clean_yt = config.get("modules.youtube.auto_cleanup_videos", False)
        table.add_row("7", "Limpeza s/ Confirmação", "modules.youtube.auto_cleanup_videos", "[green]Sim (Auto)[/green]" if auto_clean_yt else "[yellow]Não (Confirmar)[/yellow]")
        
        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            new_val = Prompt.ask("Privacidade no YouTube (unlisted, private, public)", default=str(config.get("modules.youtube.privacy_status", "unlisted"))).lower()
            if new_val in ["unlisted", "private", "public"]:
                config.set("modules.youtube.privacy_status", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida![/red]")
            time.sleep(1)
        elif choice == "2":
            new_val = Prompt.ask("Playlist no YouTube (Timelapses)", default=str(config.get("modules.youtube.playlist", "Timelapses")))
            config.set("modules.youtube.playlist", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "3":
            curr = config.get("modules.youtube.video_playlist", "Natureza 4K UHD")
            new_val = Prompt.ask("Nome da Playlist no YouTube para Vídeos Editados", default=curr)
            config.set("modules.youtube.video_playlist", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "4":
            new_val = Prompt.ask("Canal do NTFY", default=str(config.get("modules.timelapse.ntfy_topic", "timelapse-studio-2026")))
            config.set("modules.timelapse.ntfy_topic", new_val)
            config.set("modules.youtube.ntfy_topic", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "5":
            curr = config.get("modules.youtube.cleanup_local_videos", True)
            new_val = Confirm.ask("Ativar limpeza dos vídeos 4K locais após upload verificado no YouTube?", default=curr)
            config.set("modules.youtube.cleanup_local_videos", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "6":
            curr = config.get("modules.youtube.cleanup_to_trash", True)
            new_val = Confirm.ask("Enviar vídeos para a Lixeira do Windows (Sim = Lixeira, Não = Exclusão definitiva imediata)?", default=curr)
            config.set("modules.youtube.cleanup_to_trash", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "7":
            curr = config.get("modules.youtube.auto_cleanup_videos", False)
            new_val = Confirm.ask("Excluir vídeos locais automaticamente sem pedir confirmação no terminal?", default=curr)
            config.set("modules.youtube.auto_cleanup_videos", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def _menu_astro(console: Console):
    """Subpágina de configurações: Astrofotografia Lunar (Stacking PSS e Wavelets)."""
    while True:
        console.clear()
        console.print(Panel(
            "[bold cyan]🌕 Astrofotografia Lunar - Configurações[/bold cyan]\n"
            "[dim]Ajustes de Empilhamento (PSS), Alinhamento, Presets de Wavelets e Limbo[/dim]",
            expand=False,
            border_style="cyan"
        ))

        table = Table(title="Parâmetros de Astrofotografia")
        table.add_column("Opção", style="cyan", width=6)
        table.add_column("Configuração", style="white")
        table.add_column("Chave Interna", style="dim")
        table.add_column("Valor Atual", style="green")

        stack_enabled = config.get("modules.astro_stack.enabled", True)
        table.add_row("1", "Ativar Empilhamento PSS", "modules.astro_stack.enabled", "Ativado" if stack_enabled else "Desativado")

        kps = config.get("modules.astro_stack.keep_percents", [50])
        table.add_row("2", "Percentuais de Stack (Keep %)", "modules.astro_stack.keep_percents", str(kps))

        box_w = config.get("modules.astro_stack.align_box_width", 64)
        table.add_row("3", "Caixa de Alinhamento AP (pixels)", "modules.astro_stack.align_box_width", f"{box_w} px")

        stab_m = config.get("modules.astro_stack.stab_mode", "Surface")
        table.add_row("4", "Modo de Estabilização", "modules.astro_stack.stab_mode", stab_m)

        vpath = config.get("modules.astro_stack.venv_path", "auto")
        table.add_row("5", "Ambiente Virtual Astro (venv)", "modules.astro_stack.venv_path", str(vpath))

        sharpen_enabled = config.get("modules.astro_sharpen.enabled", True)
        table.add_row("6", "Ativar Sharpening Wavelets", "modules.astro_sharpen.enabled", "Ativado" if sharpen_enabled else "Desativado")

        presets = config.get("modules.astro_sharpen.presets", ["registax_fiel", "registax_clean", "registax_iluminado", "registax_pro"])
        table.add_row("7", "Presets de Wavelets Padrão", "modules.astro_sharpen.presets", str(presets))

        limb_guard = config.get("modules.astro_sharpen.use_limb_guard", True)
        table.add_row("8", "Proteção de Limbo (Anti-Halo)", "modules.astro_sharpen.use_limb_guard", "Ativada" if limb_guard else "Desativada")

        clahe_enabled = config.get("modules.astro_sharpen.enable_clahe", True)
        table.add_row("9", "Realce CLAHE 16-bit (Micro-Relevo)", "modules.astro_sharpen.enable_clahe", "Ativado" if clahe_enabled else "Desativado")

        toast = config.get("modules.astro_stack.windows_toast", True)
        table.add_row("10", "Notificações Windows Toast", "modules.astro_stack.windows_toast", "Ativadas" if toast else "Desativadas")

        ntfy = config.get("modules.astro_stack.ntfy_topic", "iris-alerts")
        table.add_row("11", "Tópico NTFY Push", "modules.astro_stack.ntfy_topic", str(ntfy))

        console.print(table)
        console.print("\n[dim]Pressione o número da opção para alterar ou '0' para voltar.[/dim]")

        choice = Prompt.ask("\nEscolha uma opção", default="0")
        if choice == "0":
            break
        elif choice == "1":
            curr = config.get("modules.astro_stack.enabled", True)
            new_val = Confirm.ask("Ativar empilhamento lunar (PSS)?", default=curr)
            config.set("modules.astro_stack.enabled", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "2":
            curr = config.get("modules.astro_stack.keep_percents", [50])
            curr_str = ",".join(str(x) for x in curr) if isinstance(curr, list) else str(curr)
            new_val = Prompt.ask("Digite os percentuais separados por vírgula (ex: 50 ou 25,50)", default=curr_str)
            try:
                parsed = [int(p.strip()) for p in new_val.split(",") if p.strip()]
                if parsed:
                    config.set("modules.astro_stack.keep_percents", parsed)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Lista não pode ser vazia![/red]")
            except ValueError:
                console.print("[red]Formato inválido! Use números separados por vírgula.[/red]")
            time.sleep(1)
        elif choice == "3":
            curr = config.get("modules.astro_stack.align_box_width", 64)
            new_val = Prompt.ask("Largura da caixa dos pontos de alinhamento em pixels (20 a 140)", default=str(curr))
            try:
                val_int = int(new_val)
                if 20 <= val_int <= 140:
                    config.set("modules.astro_stack.align_box_width", val_int)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 20 e 140![/red]")
            except ValueError:
                console.print("[red]Valor deve ser inteiro![/red]")
            time.sleep(1)
        elif choice == "4":
            curr = config.get("modules.astro_stack.stab_mode", "Surface")
            new_val = Prompt.ask("Modo de estabilização (Surface ou Planet)", default=curr)
            if new_val in ["Surface", "Planet"]:
                config.set("modules.astro_stack.stab_mode", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Escolha 'Surface' ou 'Planet'![/red]")
            time.sleep(1)
        elif choice == "5":
            curr = config.get("modules.astro_stack.venv_path", "auto")
            new_val = Prompt.ask("Caminho do ambiente virtual ou executável Python do astro ('auto' para detecção)", default=str(curr))
            config.set("modules.astro_stack.venv_path", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "6":
            curr = config.get("modules.astro_sharpen.enabled", True)
            new_val = Confirm.ask("Ativar aprimoramento por wavelets?", default=curr)
            config.set("modules.astro_sharpen.enabled", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "7":
            console.print("Presets sugeridos: [cyan]registax_fiel, registax_clean, registax_iluminado, registax_pro, registax_dinamico, registax_limb_guard, registax_plus, suave, equilibrado[/cyan]")
            curr = config.get("modules.astro_sharpen.presets", ["registax_fiel", "registax_clean", "registax_iluminado", "registax_pro"])
            curr_str = ",".join(curr) if isinstance(curr, list) else str(curr)
            new_val = Prompt.ask("Digite os presets separados por vírgula", default=curr_str)
            parsed = [p.strip() for p in new_val.split(",") if p.strip()]
            if parsed:
                config.set("modules.astro_sharpen.presets", parsed)
                console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "8":
            curr = config.get("modules.astro_sharpen.use_limb_guard", True)
            new_val = Confirm.ask("Ativar proteção de limbo lunar (anti-halo/ringing)?", default=curr)
            config.set("modules.astro_sharpen.use_limb_guard", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "9":
            curr = config.get("modules.astro_sharpen.enable_clahe", True)
            new_val = Confirm.ask("Ativar CLAHE adaptativo 16-bit para micro-relevo?", default=curr)
            config.set("modules.astro_sharpen.enable_clahe", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "10":
            curr = config.get("modules.astro_stack.windows_toast", True)
            new_val = Confirm.ask("Exibir notificações Toast no Windows ao concluir?", default=curr)
            config.set("modules.astro_stack.windows_toast", new_val)
            config.set("modules.astro_sharpen.windows_toast", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "11":
            curr = config.get("modules.astro_stack.ntfy_topic", "iris-alerts")
            new_val = Prompt.ask("Tópico do NTFY para alertas remotos", default=str(curr))
            config.set("modules.astro_stack.ntfy_topic", new_val)
            config.set("modules.astro_sharpen.ntfy_topic", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def _menu_timelapse_long_exposure(console: Console):
    """Sub-menu: Timelapse de Longa Exposição (Astrofotografia)."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: Timelapse de Longa Exposição (Astrofotografia)[/bold yellow]", expand=False))
        
        table = Table(title="Timelapse de Longa Exposição")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        le_enabled = config.get("classification.timelapse_long_exposure.enabled", True)
        table.add_row("1", "Detecção Longa Exposição Ativa", "classification.timelapse_long_exposure.enabled", "[green]Sim[/green]" if le_enabled else "[red]Não[/red]")
        table.add_row("2", "Pasta Destino", "classification.timelapse_long_exposure.folder", str(config.get("classification.timelapse_long_exposure.folder", "4_Timelapses_LongaExposicao")))
        table.add_row("3", "Min Fotos Longa Exposição", "classification.timelapse_long_exposure.min_photos", str(config.get("classification.timelapse_long_exposure.min_photos", 60)))
        table.add_row("4", "Shutter Mínimo (segundos)", "classification.timelapse_long_exposure.min_shutter_seconds", str(config.get("classification.timelapse_long_exposure.min_shutter_seconds", 5.0)))
        table.add_row("5", "Intervalo Máx Disparos (s)", "classification.timelapse_long_exposure.max_interval_seconds", str(config.get("classification.timelapse_long_exposure.max_interval_seconds", 180.0)))
        
        tol_le = config.get("classification.timelapse_long_exposure.tolerance_ratio", 0.15)
        table.add_row("6", "Tolerância Cadência (ratio)", "classification.timelapse_long_exposure.tolerance_ratio", f"{tol_le:.2f} ({int(tol_le*100)}%)")
        
        table.add_row("7", "FPS Renderização", "modules.timelapse_long_exposure.fps", str(config.get("modules.timelapse_long_exposure.fps", 30)))
        table.add_row("8", "Frames por Foto (FPI)", "modules.timelapse_long_exposure.frames_per_image", str(config.get("modules.timelapse_long_exposure.frames_per_image", 1)))
        table.add_row("9", "Fator Qualidade CRF", "modules.timelapse_long_exposure.crf", str(config.get("modules.timelapse_long_exposure.crf", 15)))
        table.add_row("10", "Modo de Corte (Crop)", "modules.timelapse_long_exposure.crop_mode", str(config.get("modules.timelapse_long_exposure.crop_mode", "center")))
        
        le_prof = config.get("modules.timelapse_long_exposure.render_profile", "quality")
        table.add_row("11", "Perfil Renderização", "modules.timelapse_long_exposure.render_profile", str(le_prof).upper())
        
        deband_le = config.get("modules.timelapse_long_exposure.deband.enabled", True)
        table.add_row("12", "Deband 16-bit Céu Noturno", "modules.timelapse_long_exposure.deband.enabled", "[green]Ativado[/green]" if deband_le else "[red]Desativado[/red]")
        
        grain_le = config.get("modules.timelapse_long_exposure.deband.add_grain", True)
        table.add_row("13", "Ruído Anti-banding YouTube", "modules.timelapse_long_exposure.deband.add_grain", "[green]Ativado[/green]" if grain_le else "[red]Desativado[/red]")
        
        pl_le = config.get("modules.youtube.timelapse_long_exposure_playlist", "Timelapses Longa Exposição")
        table.add_row("14", "Playlist YouTube Dedicada", "modules.youtube.timelapse_long_exposure_playlist", str(pl_le))

        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            curr = config.get("classification.timelapse_long_exposure.enabled", True)
            new_val = Confirm.ask("Ativar perfil de detecção de timelapse para fotos de longa exposição?", default=curr)
            config.set("classification.timelapse_long_exposure.enabled", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "2":
            new_val = Prompt.ask("Nova pasta de destino para timelapses de longa exposição", default=str(config.get("classification.timelapse_long_exposure.folder", "4_Timelapses_LongaExposicao")))
            config.set("classification.timelapse_long_exposure.folder", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "3":
            new_val = Prompt.ask("Nova Qtd Mínima de Fotos para Longa Exposição", default=str(config.get("classification.timelapse_long_exposure.min_photos", 60)))
            try:
                config.set("classification.timelapse_long_exposure.min_photos", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "4":
            new_val = Prompt.ask("Tempo mínimo de obturador (segundos) para considerar Longa Exposição", default=str(config.get("classification.timelapse_long_exposure.min_shutter_seconds", 5.0)))
            try:
                val_float = float(new_val)
                config.set("classification.timelapse_long_exposure.min_shutter_seconds", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número positivo![/red]")
            time.sleep(1)
        elif choice == "5":
            new_val = Prompt.ask("Intervalo máximo entre disparos (segundos)", default=str(config.get("classification.timelapse_long_exposure.max_interval_seconds", 180.0)))
            try:
                val_float = float(new_val)
                config.set("classification.timelapse_long_exposure.max_interval_seconds", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número positivo![/red]")
            time.sleep(1)
        elif choice == "6":
            new_val = Prompt.ask("Tolerância de cadência para Longa Exposição (ex: 0.15 para 15%)", default=str(config.get("classification.timelapse_long_exposure.tolerance_ratio", 0.15)))
            try:
                val_float = float(new_val)
                config.set("classification.timelapse_long_exposure.tolerance_ratio", val_float)
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número![/red]")
            time.sleep(1)
        elif choice == "7":
            new_val = Prompt.ask("FPS de Renderização do Vídeo", default=str(config.get("modules.timelapse_long_exposure.fps", 30)))
            try:
                config.set("modules.timelapse_long_exposure.fps", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "8":
            new_val = Prompt.ask("Frames por Foto (FPI) para Longa Exposição", default=str(config.get("modules.timelapse_long_exposure.frames_per_image", 1)))
            try:
                val_int = int(new_val)
                if val_int < 1:
                    console.print("[red]Valor deve ser maior ou igual a 1![/red]")
                else:
                    config.set("modules.timelapse_long_exposure.frames_per_image", val_int)
                    console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "9":
            new_val = Prompt.ask("Fator de Qualidade CRF (0-51, menor = melhor)", default=str(config.get("modules.timelapse_long_exposure.crf", 15)))
            try:
                config.set("modules.timelapse_long_exposure.crf", int(new_val))
                console.print("[green]Salvo![/green]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "10":
            console.print("Modos de Enquadramento: [bold]center[/bold] (Centro), [bold]bottom[/bold] (Base), [bold]top[/bold] (Topo), [bold]full[/bold] (Quadro Completo)")
            new_val = Prompt.ask("Modo de Corte", default=str(config.get("modules.timelapse_long_exposure.crop_mode", "center"))).lower()
            if new_val in ["center", "bottom", "top", "full"]:
                config.set("modules.timelapse_long_exposure.crop_mode", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida![/red]")
            time.sleep(1)
        elif choice == "11":
            console.print("Perfis disponíveis: [bold]quality[/bold] (Lanczos 4K + deband 16-bit), [bold]fast[/bold] (Intel QSV HW), [bold]balanced[/bold] (Bicúbico)")
            new_val = Prompt.ask("Perfil de renderização", default=str(config.get("modules.timelapse_long_exposure.render_profile", "quality"))).lower().strip()
            if new_val in ["quality", "fast", "balanced"]:
                config.set("modules.timelapse_long_exposure.render_profile", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Opção inválida![/red]")
            time.sleep(1)
        elif choice == "12":
            curr = config.get("modules.timelapse_long_exposure.deband.enabled", True)
            new_val = Confirm.ask("Ativar filtro Deband 16-bit para transições suaves do céu noturno?", default=curr)
            config.set("modules.timelapse_long_exposure.deband.enabled", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "13":
            curr = config.get("modules.timelapse_long_exposure.deband.add_grain", True)
            new_val = Confirm.ask("Ativar micro-grão dither para evitar compressão agressiva do YouTube?", default=curr)
            config.set("modules.timelapse_long_exposure.deband.add_grain", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "14":
            new_val = Prompt.ask("Nome da Playlist no YouTube para Timelapses de Longa Exposição", default=str(config.get("modules.youtube.timelapse_long_exposure_playlist", "Timelapses Longa Exposição")))
            config.set("modules.youtube.timelapse_long_exposure_playlist", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def _menu_bird_id(console: Console):
    """Sub-menu: Identificação de Aves (YOLO + iNaturalist / BioCLIP)."""
    while True:
        console.clear()
        console.print(Panel("[bold yellow]Configurações: Identificação de Aves (YOLO + iNaturalist / BioCLIP)[/bold yellow]", expand=False))
        
        table = Table(title="Identificação Taxonômica de Aves")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Configuração", style="bold white")
        table.add_column("Chave YAML", style="magenta")
        table.add_column("Valor Atual", style="green")
        
        enabled_val = config.get("modules.bird_id.enabled", True)
        table.add_row("1", "Ativar Módulo de Aves", "modules.bird_id.enabled", "[green]Sim[/green]" if enabled_val else "[red]Não[/red]")
        
        provider = config.get("modules.bird_id.classifier_type", "inaturalist")
        table.add_row("2", "Provedor Taxonômico (IA)", "modules.bird_id.classifier_type", f"[bold cyan]{provider}[/bold cyan]")
        
        min_conf = config.get("modules.bird_id.min_species_confidence", 0.70)
        table.add_row("3", "Limiar de Confiança para Ações", "modules.bird_id.min_species_confidence", f"{float(min_conf)*100:.0f}%")
        
        rename_val = config.get("modules.bird_id.rename_files", True)
        table.add_row("4", "Renomeação Tripla (PT + Científico + EN)", "modules.bird_id.rename_files", "[green]Sim[/green]" if rename_val else "[red]Não[/red]")
        
        subfolder_val = config.get("modules.bird_id.organize_in_subfolders", True)
        table.add_row("5", "Organizar em Subpasta por Nome Popular", "modules.bird_id.organize_in_subfolders", "[green]Sim[/green]" if subfolder_val else "[red]Não[/red]")
        
        exif_val = config.get("modules.bird_id.write_exif_tags", True)
        table.add_row("6", "Injetar Metadados EXIF/IPTC (ExifTool)", "modules.bird_id.write_exif_tags", "[green]Sim[/green]" if exif_val else "[red]Não[/red]")
        
        tf_val = config.get("modules.bird_id.video_target_frames", 15)
        table.add_row("7", "Alvo de Frames Amostrados em Vídeo", "modules.bird_id.video_target_frames", str(tf_val))
        
        max_crops = config.get("modules.bird_id.video_max_crops", 5)
        table.add_row("8", "Crops de Vídeo Enviados para Votação", "modules.bird_id.video_max_crops", str(max_crops))
        
        crops_val = config.get("modules.bird_id.video_min_confident_crops", 2)
        table.add_row("9", "Mínimo de Recortes para Validar Vídeo", "modules.bird_id.video_min_confident_crops", str(crops_val))
        
        def_lat = config.get("modules.bird_id.inaturalist.default_lat", -19.92)
        table.add_row("10", "Latitude Padrão (Prior Geo)", "modules.bird_id.inaturalist.default_lat", f"{float(def_lat):.4f}")
        
        def_lng = config.get("modules.bird_id.inaturalist.default_lng", -43.94)
        table.add_row("11", "Longitude Padrão (Prior Geo)", "modules.bird_id.inaturalist.default_lng", f"{float(def_lng):.4f}")
        
        geo_acc = config.get("modules.bird_id.inaturalist.positional_accuracy_meters", 25000)
        table.add_row("12", "Raio de Confiança Geo (metros)", "modules.bird_id.inaturalist.positional_accuracy_meters", f"{int(geo_acc):,}m")
        
        zoom_val = config.get("modules.bird_id.zoom_threshold_mm", 300.0)
        table.add_row("13", "Limiar de Zoom Teleobjetiva (mm)", "modules.bird_id.zoom_threshold_mm", f"{float(zoom_val):.0f}mm")
        
        crops_disk = config.get("modules.bird_id.save_crops", True)
        table.add_row("14", "Salvar Recortes em Disco (recortes_aves/)", "modules.bird_id.save_crops", "[green]Sim[/green]" if crops_disk else "[red]Não[/red]")
        
        yolo_mod = config.get("modules.bird_id.yolo_model", "yolov8s.pt")
        table.add_row("15", "Modelo Detector YOLOv8", "modules.bird_id.yolo_model", str(yolo_mod))
        
        yolo_c = config.get("modules.bird_id.yolo_confidence", 0.25)
        table.add_row("16", "Confiança Mínima YOLO", "modules.bird_id.yolo_confidence", f"{float(yolo_c)*100:.0f}%")
        
        creds_p = config.get("modules.bird_id.inaturalist.credentials_file", "secrets/inaturalist.json")
        table.add_row("17", "Arquivo de Credenciais iNaturalist", "modules.bird_id.inaturalist.credentials_file", str(creds_p))
        
        console.print(table)
        console.print("\n[cyan][0][/cyan] Voltar ao Menu de Categorias")
        
        choice = Prompt.ask("\nEscolha uma opção para editar", default="0")
        if choice == "0":
            break
        elif choice == "1":
            curr = config.get("modules.bird_id.enabled", True)
            new_val = Confirm.ask("Habilitar módulo de identificação de aves no pipeline?", default=curr)
            config.set("modules.bird_id.enabled", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "2":
            curr = config.get("modules.bird_id.classifier_type", "inaturalist")
            new_val = Prompt.ask("Provedor Taxonômico (inaturalist ou bioclip)", default=str(curr)).lower().strip()
            if new_val in ["inaturalist", "bioclip"]:
                config.set("modules.bird_id.classifier_type", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Provedor deve ser 'inaturalist' ou 'bioclip'![/red]")
            time.sleep(1)
        elif choice == "3":
            curr = float(config.get("modules.bird_id.min_species_confidence", 0.70))
            new_val = Prompt.ask("Limiar de confiança para ações ativas (0.10 a 0.99)", default=f"{curr:.2f}")
            try:
                val_f = float(new_val)
                if 0.10 <= val_f <= 0.99:
                    config.set("modules.bird_id.min_species_confidence", val_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve estar entre 0.10 e 0.99![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "4":
            curr = config.get("modules.bird_id.rename_files", True)
            new_val = Confirm.ask("Renomear arquivos incluindo [Nome_PT]_[Cientifico]_[Nome_EN]?", default=curr)
            config.set("modules.bird_id.rename_files", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "5":
            curr = config.get("modules.bird_id.organize_in_subfolders", True)
            new_val = Confirm.ask("Mover para subpasta com nome popular da espécie dentro da categoria?", default=curr)
            config.set("modules.bird_id.organize_in_subfolders", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "6":
            curr = config.get("modules.bird_id.write_exif_tags", True)
            new_val = Confirm.ask("Injetar tags taxonômicas nos metadados EXIF/IPTC via ExifTool?", default=curr)
            config.set("modules.bird_id.write_exif_tags", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "7":
            curr = config.get("modules.bird_id.video_target_frames", 15)
            new_val = Prompt.ask("Quantidade alvo de frames amostrados proporcionalmente à duração (5 a 60)", default=str(curr))
            try:
                tf_int = int(new_val)
                if 5 <= tf_int <= 60:
                    config.set("modules.bird_id.video_target_frames", tf_int)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 5 e 60![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "8":
            curr = config.get("modules.bird_id.video_max_crops", 5)
            new_val = Prompt.ask("Quantidade de melhores recortes de vídeo enviados à API para votação (1 a 15)", default=str(curr))
            try:
                mc_crops = int(new_val)
                if 1 <= mc_crops <= 15:
                    config.set("modules.bird_id.video_max_crops", mc_crops)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 1 e 15![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "9":
            curr = config.get("modules.bird_id.video_min_confident_crops", 2)
            new_val = Prompt.ask("Mínimo de recortes com a mesma espécie para consolidar o vídeo (1 a 10)", default=str(curr))
            try:
                mc_int = int(new_val)
                if 1 <= mc_int <= 10:
                    config.set("modules.bird_id.video_min_confident_crops", mc_int)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser entre 1 e 10![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "10":
            curr = float(config.get("modules.bird_id.inaturalist.default_lat", -19.92))
            new_val = Prompt.ask("Latitude padrão para prior geográfico (-90.0 a 90.0)", default=f"{curr:.4f}")
            try:
                lat_f = float(new_val)
                if -90.0 <= lat_f <= 90.0:
                    config.set("modules.bird_id.inaturalist.default_lat", lat_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Latitude deve estar entre -90.0 e 90.0![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "11":
            curr = float(config.get("modules.bird_id.inaturalist.default_lng", -43.94))
            new_val = Prompt.ask("Longitude padrão para prior geográfico (-180.0 a 180.0)", default=f"{curr:.4f}")
            try:
                lng_f = float(new_val)
                if -180.0 <= lng_f <= 180.0:
                    config.set("modules.bird_id.inaturalist.default_lng", lng_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Longitude deve estar entre -180.0 e 180.0![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "12":
            curr = int(config.get("modules.bird_id.inaturalist.positional_accuracy_meters", 25000))
            new_val = Prompt.ask("Raio de confiança/precisão geográfica em metros (ex: 25000 para 25km)", default=str(curr))
            try:
                acc_i = int(new_val)
                if 100 <= acc_i <= 500000:
                    config.set("modules.bird_id.inaturalist.positional_accuracy_meters", acc_i)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Raio deve estar entre 100m e 500.000m (500km)![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        elif choice == "13":
            curr = config.get("modules.bird_id.zoom_threshold_mm", 300.0)
            new_val = Prompt.ask("Distância focal equivalente mínima para elegibilidade (mm)", default=f"{float(curr):.0f}")
            try:
                val_f = float(new_val)
                if val_f >= 50.0:
                    config.set("modules.bird_id.zoom_threshold_mm", val_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser no mínimo 50mm![/red]")
            except ValueError:
                console.print("[red]Valor deve ser numérico![/red]")
            time.sleep(1)
        elif choice == "14":
            curr = config.get("modules.bird_id.save_crops", True)
            new_val = Confirm.ask("Salvar recortes ampliados na pasta 'recortes_aves/'?", default=curr)
            config.set("modules.bird_id.save_crops", new_val)
            console.print("[green]Salvo![/green]")
            time.sleep(1)
        elif choice == "15":
            console.print("Modelos disponíveis: [bold]yolov8n.pt[/bold] (Nano/Rápido), [bold]yolov8s.pt[/bold] (Small/Padrão), [bold]yolov8m.pt[/bold] (Medium)")
            curr = config.get("modules.bird_id.yolo_model", "yolov8s.pt")
            new_val = Prompt.ask("Escolha o modelo YOLO", default=str(curr)).strip()
            if new_val in ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt"]:
                config.set("modules.bird_id.yolo_model", new_val)
                console.print("[green]Salvo![/green]")
            else:
                console.print("[red]Modelo inválido![/red]")
            time.sleep(1)
        elif choice == "16":
            curr = float(config.get("modules.bird_id.yolo_confidence", 0.25))
            new_val = Prompt.ask("Confiança mínima para detecção YOLO (0.10 a 0.90)", default=f"{curr:.2f}")
            try:
                val_f = float(new_val)
                if 0.10 <= val_f <= 0.90:
                    config.set("modules.bird_id.yolo_confidence", val_f)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve estar entre 0.10 e 0.90![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número decimal![/red]")
            time.sleep(1)
        elif choice == "17":
            curr = config.get("modules.bird_id.inaturalist.credentials_file", "secrets/inaturalist.json")
            new_val = Prompt.ask("Caminho do arquivo JSON com credenciais do iNaturalist", default=str(curr)).strip()
            if new_val:
                config.set("modules.bird_id.inaturalist.credentials_file", new_val)
                console.print("[green]Salvo![/green]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


def show_config_menu(console: Console = None):
    """Menu principal das configurações: hub de categorias e subpáginas."""
    if console is None:
        console = Console()
        
    while True:
        console.clear()
        console.print(Panel(
            "[bold yellow]⚙ Configurações Globais - IRIS[/bold yellow]\n"
            "[dim]Central de Ajustes e Parâmetros (~/.iris/config.yaml)[/dim]",
            expand=False,
            border_style="yellow"
        ))
        
        console.print("\n[bold]Selecione uma categoria de configurações:[/bold]")
        console.print("  [cyan]1.[/cyan] 📦 Armazenamento & Ingestão [dim](Destino, Origem, Threads, Limpeza)[/dim]")
        console.print("  [cyan]2.[/cyan] 🏷 Organização & Classificação [dim](Padrões de Nomes, Detecção Lua, Amostras)[/dim]")
        console.print("  [cyan]3.[/cyan] ⏱ Timelapse 4K [dim](FPS, Qualidade CRF, Corte, Deband, Perfis)[/dim]")
        console.print("  [cyan]4.[/cyan] 🎬 Edição de Vídeo 4K [dim](Modo Junção, Velocidade, Trimming, Áudio, Perfis)[/dim]")
        console.print("  [cyan]5.[/cyan] 📢 YouTube & Notificações [dim](Privacidade, Playlists, Canal NTFY)[/dim]")
        console.print("  [cyan]6.[/cyan] 🌕 Astrofotografia Lunar [dim](Empilhamento PSS, Percentuais, Wavelets, Limbo)[/dim]")
        console.print("  [cyan]7.[/cyan] 🌌 Timelapse Longa Exposição [dim](Mín Fotos, Shutter Mín, Gaps Buffer, Render)[/dim]")
        console.print("  [cyan]8.[/cyan] 🦜 Identificação de Aves [dim](YOLOv8 + iNaturalist, Geo-Prior, Vídeo)[/dim]")
        console.print("  [cyan]0.[/cyan] ↩ Voltar")
        
        choice = Prompt.ask("\nSelecione uma opção", default="0")
        if choice == "0":
            break
        elif choice == "1":
            _menu_storage_ingestion(console)
        elif choice == "2":
            _menu_organization_classification(console)
        elif choice == "3":
            _menu_timelapse(console)
        elif choice == "4":
            _menu_video_edit(console)
        elif choice == "5":
            _menu_youtube_notifications(console)
        elif choice == "6":
            _menu_astro(console)
        elif choice == "7":
            _menu_timelapse_long_exposure(console)
        elif choice == "8":
            _menu_bird_id(console)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)

