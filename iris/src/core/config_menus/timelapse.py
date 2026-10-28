import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config


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
