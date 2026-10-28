import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config


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

