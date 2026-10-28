import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config


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
        
        ve_auto_birds = config.get("modules.video_edit.auto_join_birds", True)
        table.add_row("7", "Auto-Join Aves (Mesmo Dia)", "modules.video_edit.auto_join_birds", "[green]Sim (Ativada)[/green]" if ve_auto_birds else "[yellow]Não (Desativada)[/yellow]")
        
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
            console.print("Modos de Edição: [bold]individual[/bold] (Upscale 1:1 de cada vídeo), [bold]joined[/bold] (Concatena vídeos da mesma pasta). [dim]Nota: Aves da mesma espécie no mesmo dia são unificadas automaticamente se a opção 7 estiver ativa.[/dim]")
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
        elif choice == "7":
            curr = config.get("modules.video_edit.auto_join_birds", True)
            new_val = Confirm.ask("Unir automaticamente múltiplos vídeos da mesma ave gravados no mesmo dia?", default=curr)
            config.set("modules.video_edit.auto_join_birds", new_val)
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
        
        chunk_mb = config.get("modules.youtube.chunk_size_mb", 64)
        table.add_row("8", "Tamanho do Chunk Upload", "modules.youtube.chunk_size_mb", f"{chunk_mb} MB")
        
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
        elif choice == "8":
            curr = config.get("modules.youtube.chunk_size_mb", 64)
            new_val = Prompt.ask("Tamanho do chunk de upload em MB (recomendado: 64, mínimo: 1)", default=str(curr))
            try:
                val_int = int(new_val)
                if val_int >= 1:
                    config.set("modules.youtube.chunk_size_mb", val_int)
                    console.print("[green]Salvo![/green]")
                else:
                    console.print("[red]Valor deve ser maior ou igual a 1 MB![/red]")
            except ValueError:
                console.print("[red]Valor deve ser um número inteiro![/red]")
            time.sleep(1)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)
