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
        table.add_row("4", "Min Fotos Timelapse", "classification.timelapse_min_photos", str(config.get("classification.timelapse_min_photos")))
        
        sample_enabled = config.get("classification.enable_timelapse_album_samples", True)
        table.add_row("5", "Amostras Timelapse p/ Álbum", "classification.enable_timelapse_album_samples", "[green]Sim[/green]" if sample_enabled else "[red]Não[/red]")
        table.add_row("6", "Intervalo Amostras (min)", "classification.timelapse_sample_interval_minutes", str(config.get("classification.timelapse_sample_interval_minutes", 5.0)))
        
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
            new_val = Prompt.ask("Nova Qtd Min Fotos p/ Timelapse", default=str(config.get("classification.timelapse_min_photos")))
            try:
                config.set("classification.timelapse_min_photos", int(new_val))
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
        table.add_row("2", "Modo Edição Vídeo", "modules.video_edit.mode", "Individual (1:1)" if ve_mode == "individual" else "Junção de Sessão")
        
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
            console.print("Modos de Edição: [bold]individual[/bold] (1:1 independente), [bold]joined[/bold] (Junção de sessão contígua)")
            curr = config.get("modules.video_edit.mode", "individual")
            new_val = Prompt.ask("Escolha o modo (individual/joined)", default=curr).lower()
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

        kps = config.get("modules.astro_stack.keep_percents", [10, 25, 50])
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
            curr = config.get("modules.astro_stack.keep_percents", [10, 25, 50])
            curr_str = ",".join(str(x) for x in curr) if isinstance(curr, list) else str(curr)
            new_val = Prompt.ask("Digite os percentuais separados por vírgula (ex: 10,25,50 ou 100)", default=curr_str)
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
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)

