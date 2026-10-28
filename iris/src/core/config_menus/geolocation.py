import time
from typing import List
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from src.core.config import config
from src.core.geo import (
    GeoService,
    GeoLocation,
    parse_coords,
    build_location_panel,
    interactive_add_location_flow,
    reverse_geocode,
)


def _add_location_flow(console: Console):
    """Fluxo interativo para cadastrar um novo local predefinido."""
    interactive_add_location_flow(console)


def _edit_location_flow(console: Console, loc: GeoLocation):
    """Fluxo interativo para editar ou excluir um local predefinido."""
    while True:
        console.clear()
        console.print(build_location_panel(loc, title=f"📍 [CONFIGURAÇÃO: {loc.label}]", border_style="yellow"))

        console.print("  [cyan]1.[/cyan] Alterar Coordenadas (Latitude, Longitude)")
        console.print("  [cyan]2.[/cyan] Alterar Rótulo")
        console.print("  [cyan]3.[/cyan] Alterar Ponto de Interesse / Parque")
        console.print("  [cyan]4.[/cyan] Alterar Bairro")
        console.print("  [cyan]5.[/cyan] Alterar Cidade/Município")
        console.print("  [cyan]6.[/cyan] Alterar Estado")
        console.print("  [cyan]7.[/cyan] Alterar País")
        console.print("  [cyan]8.[/cyan] Alterar Raio de Precisão")
        console.print("  [cyan]P.[/cyan] Definir como Padrão Global")
        console.print("  [cyan]X.[/cyan] [red]Excluir este local[/red]")
        console.print("  [cyan]0.[/cyan] Voltar")

        sub_choice = Prompt.ask("\nEscolha um campo para alterar", default="0").strip().upper()
        if sub_choice == "0":
            break
        elif sub_choice == "1":
            new_c = Prompt.ask("Novas coordenadas", default=f"{loc.lat:.6f}, {loc.lng:.6f}")
            try:
                lat, lng = parse_coords(new_c)
                loc.lat = lat
                loc.lng = lng
                re_query = Confirm.ask("Deseja consultar a API para atualizar automaticamente cidade, bairro e parque?", default=True)
                if re_query:
                    with console.status("[bold cyan]Consultando dados geográficos na API...[/bold cyan]", spinner="dots"):
                        info = reverse_geocode(lat, lng)
                    if info.get("city"):
                        loc.city = info["city"]
                    if info.get("state"):
                        loc.state = info["state"]
                    if info.get("country"):
                        loc.country = info["country"]
                    if info.get("suburb"):
                        loc.suburb = info["suburb"]
                    if info.get("poi"):
                        loc.poi = info["poi"]
                GeoService.update_location(loc)
                console.print("[green]Coordenadas atualizadas com sucesso![/green]")
            except ValueError as e:
                console.print(f"[red]Erro: {e}[/red]")
            time.sleep(1.2)
        elif sub_choice == "2":
            new_l = Prompt.ask("Novo rótulo", default=loc.label).strip()
            if new_l:
                loc.label = new_l
                GeoService.update_location(loc)
                console.print("[green]Rótulo atualizado![/green]")
            time.sleep(1.2)
        elif sub_choice == "3":
            loc.poi = Prompt.ask("Novo Ponto de Interesse / Parque (opcional)", default=loc.poi).strip()
            GeoService.update_location(loc)
            console.print("[green]Ponto/Parque atualizado![/green]")
            time.sleep(1.2)
        elif sub_choice == "4":
            loc.suburb = Prompt.ask("Novo bairro (opcional)", default=loc.suburb).strip()
            GeoService.update_location(loc)
            console.print("[green]Bairro atualizado![/green]")
            time.sleep(1.2)
        elif sub_choice == "5":
            loc.city = Prompt.ask("Nova cidade/município", default=loc.city).strip()
            GeoService.update_location(loc)
            console.print("[green]Cidade atualizada![/green]")
            time.sleep(1.2)
        elif sub_choice == "6":
            loc.state = Prompt.ask("Novo estado por extenso", default=loc.state).strip()
            GeoService.update_location(loc)
            console.print("[green]Estado atualizado![/green]")
            time.sleep(1.2)
        elif sub_choice == "7":
            loc.country = Prompt.ask("Novo país", default=loc.country).strip()
            GeoService.update_location(loc)
            console.print("[green]País atualizado![/green]")
            time.sleep(1.2)
        elif sub_choice == "8":
            acc_str = Prompt.ask("Novo raio de precisão (metros)", default=str(int(loc.accuracy_m)))
            try:
                loc.accuracy_m = float(acc_str)
                GeoService.update_location(loc)
                console.print("[green]Precisão atualizada![/green]")
            except ValueError:
                console.print("[red]Valor numérico inválido![/red]")
            time.sleep(1.2)
        elif sub_choice == "P":
            GeoService.set_default_location_id(loc.id)
            console.print(f"[bold green]✔ Local '{loc.label}' definido como padrão global![/bold green]")
            time.sleep(1.5)
        elif sub_choice == "X":
            locs = GeoService.get_locations()
            if len(locs) <= 1:
                console.print("[red]Não é possível excluir o único local cadastrado no sistema.[/red]")
                time.sleep(2)
                continue
            confirm = Confirm.ask(f"[bold red]Tem certeza que deseja excluir o local '{loc.label}' ({loc.id})?[/bold red]", default=False)
            if confirm:
                GeoService.delete_location(loc.id)
                console.print("[green]Local excluído com sucesso![/green]")
                time.sleep(1.5)
                break


def _set_default_location_flow(console: Console, locations: List[GeoLocation]):
    """Fluxo para definir rapidamente o local padrão global."""
    console.print("\n[bold cyan]Selecione o novo local padrão global:[/bold cyan]")
    for i, loc in enumerate(locations, 1):
        console.print(f"  [{i}] {loc.label}")
    choice = Prompt.ask("\nNúmero do local", default="1")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(locations):
            GeoService.set_default_location_id(locations[idx].id)
            console.print(f"[bold green]✔ Local padrão atualizado para: {locations[idx].label}[/bold green]")
        else:
            console.print("[red]Opção inválida![/red]")
    except ValueError:
        console.print("[red]Opção inválida![/red]")
    time.sleep(1.5)


def _delete_location_flow(console: Console, locations: List[GeoLocation]):
    """Fluxo para selecionar e excluir um local predefinido diretamente."""
    if len(locations) <= 1:
        console.print("[red]Não é possível excluir o único local cadastrado no sistema.[/red]")
        time.sleep(2)
        return

    console.print("\n[bold red]Excluir Geolocalização Cadastrada[/bold red]")
    for i, loc in enumerate(locations, 1):
        console.print(f"  [{i}] {loc.label} [dim]({loc.id})[/dim]")
    choice = Prompt.ask("\nDigite o número do local a excluir (ou 0 para cancelar)", default="0").strip()
    if choice == "0":
        return
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(locations):
            target_loc = locations[idx]
            confirmed = Confirm.ask(f"[bold red]Tem certeza que deseja excluir o local '{target_loc.label}' ({target_loc.id})?[/bold red]", default=False)
            if confirmed:
                GeoService.delete_location(target_loc.id)
                console.print(f"[bold green]✔ Local '{target_loc.label}' excluído com sucesso![/bold green]")
                time.sleep(1.5)
        else:
            console.print("[red]Opção inválida![/red]")
            time.sleep(1)
    except ValueError:
        console.print("[red]Opção inválida![/red]")
        time.sleep(1)


def _menu_geolocation(console: Console):
    """Sub-menu: Cadastro e Gerenciamento de Geolocalizações Predefinidas."""
    while True:
        console.clear()
        console.print(Panel(
            "[bold yellow]Configurações: Geolocalizações & Metadados GPS[/bold yellow]\n"
            "[dim]Pontos predefinidos, marcação em fotos e tokens de coordenadas em nomes[/dim]",
            expand=False,
            border_style="yellow"
        ))

        locations = GeoService.get_locations()
        default_id = GeoService.get_default_location_id()
        tag_media = config.get("geo.tag_media", True)
        filename_token = config.get("geo.filename_token", True)

        table = Table(title="Locais Predefinidos Cadastrados", border_style="cyan")
        table.add_column("Opção", style="cyan", justify="center")
        table.add_column("Rótulo", style="bold white")
        table.add_column("Status", style="bold yellow")

        for i, loc in enumerate(locations, 1):
            is_def = "[bold green]★ PADRÃO[/bold green]" if loc.id == default_id else ""
            table.add_row(str(i), loc.label, is_def)

        console.print(table)

        conf_table = Table(title="Opções Gerais de Geotag & Metadados")
        conf_table.add_column("Atalho", style="cyan", justify="center")
        conf_table.add_column("Parâmetro", style="bold white")
        conf_table.add_column("Valor Atual", style="green")
        conf_table.add_column("Descrição", style="dim")

        tag_display = "[green]Sim[/green]" if tag_media else "[red]Não[/red]"
        token_display = "[green]Sim[/green]" if filename_token else "[red]Não[/red]"

        conf_table.add_row("T", "Gravar tags GPS em fotos sem coordenadas", tag_display, "Injeta GPS em JPG/PNG/WebP/TIFF no pipeline")
        conf_table.add_row("F", "Inserir token GPS no nome dos arquivos", token_display, "Adiciona _{gps} (ex: S20-4569_W45-4383) no nome")
        console.print(conf_table)

        console.print("\n[bold]Ações disponíveis:[/bold]")
        console.print(f"  [cyan][1-{len(locations)}][/cyan] Ver / Editar detalhes do local")
        console.print("  [cyan]+ ou A[/cyan]  :heavy_plus_sign: Cadastrar novo local")
        console.print("  [cyan]- ou X[/cyan]  :wastebasket: Excluir um local cadastrado")
        console.print("  [cyan]D[/cyan]       :star: Definir local padrão global")
        console.print("  [cyan]T[/cyan]       :camera: Alternar gravação de tags GPS em fotos")
        console.print("  [cyan]F[/cyan]       :label: Alternar token GPS no nome dos arquivos")
        console.print("  [cyan]0[/cyan]       :arrow_left: Voltar")

        choice = Prompt.ask("\nEscolha uma opção", default="0").strip().upper()
        if choice == "0":
            break
        elif choice in ["+", "A"]:
            _add_location_flow(console)
        elif choice in ["-", "X"]:
            _delete_location_flow(console, locations)
        elif choice == "D":
            _set_default_location_flow(console, locations)
        elif choice == "T":
            config.set("geo.tag_media", not tag_media)
            console.print("[green]Configuração salva![/green]")
            time.sleep(1)
        elif choice == "F":
            config.set("geo.filename_token", not filename_token)
            console.print("[green]Configuração salva![/green]")
            time.sleep(1)
        else:
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(locations):
                    _edit_location_flow(console, locations[idx])
                else:
                    console.print("[red]Opção inválida![/red]")
                    time.sleep(1)
            except ValueError:
                console.print("[red]Opção inválida![/red]")
                time.sleep(1)

