"""Submenu de configurações: Eventos/Álbuns (nome do evento, participantes e catálogo de pessoas)."""

from rich.console import Console
from rich.prompt import Prompt, Confirm

from src.core.event import (
    EventInfo, PeopleCatalog, apply_event_tags, parse_names, normalize_names, project_event,
)


def prompt_event_dialog(console: Console, initial: EventInfo | None = None) -> EventInfo | None:
    """Pergunta nome do evento e participantes (com sugestões do catálogo global)."""
    initial = initial or EventInfo()
    name = Prompt.ask("Nome do evento", default=initial.name or "").strip()
    if not name:
        return None

    frequent = PeopleCatalog.list(limit=15)
    chosen = list(initial.participants)
    if frequent:
        console.print("[bold cyan]Pessoas frequentes:[/bold cyan]")
        for i, person in enumerate(frequent, 1):
            console.print(f"  [cyan]{i}.[/cyan] {person}")
        console.print("[dim]Digite números e/ou nomes novos separados por vírgula (ex.: 1, 3, Maria Souza).[/dim]")
    default_txt = ", ".join(chosen)
    raw = Prompt.ask("Participantes", default=default_txt)
    for token in [t.strip() for t in raw.replace(";", ",").split(",")]:
        if token.isdigit() and 1 <= int(token) <= len(frequent):
            chosen.append(frequent[int(token) - 1])
        elif token:
            chosen.append(token)
    event = EventInfo(name, normalize_names(chosen))
    return event


def _edit_project_event_flow(console: Console, proj_name: str):
    from src.core.project import get_project
    project = get_project(proj_name)
    if not project:
        console.print("[red]Projeto não encontrado.[/red]")
        return

    previous = project_event(project) if project.is_event else None
    console.print(f"\n[bold]Projeto:[/bold] {proj_name}")
    if previous and previous.name:
        console.print(f"  Evento: [green]{previous.name}[/green]")
        console.print(f"  Participantes: {', '.join(previous.participants) or '(nenhum)'}")
    else:
        console.print("  [dim]Este projeto não é de evento.[/dim]")

    console.print("\n  [cyan]1.[/cyan] Editar evento e participantes")
    console.print("  [cyan]2.[/cyan] Desmarcar como evento")
    console.print("  [cyan]3.[/cyan] Reaplicar tags agora")
    console.print("  [cyan]0.[/cyan] Voltar")
    choice = Prompt.ask("Opção", default="0")

    if choice == "1":
        event = prompt_event_dialog(console, previous)
        if not event:
            console.print("[yellow]Nome vazio: nada alterado.[/yellow]")
            return
        project.is_event = True
        project.event_name = event.name
        project.event_participants = list(event.participants)
        project.save()
        PeopleCatalog.register(event.participants)
        console.print("[green]Evento atualizado.[/green]")
        if Confirm.ask("Reaplicar as tags nas fotos já organizadas agora?", default=True):
            n = apply_event_tags(project, previous=previous, console=console)
            console.print(f"[green]Tags aplicadas em {n} arquivo(s).[/green]")
    elif choice == "2":
        if Confirm.ask("Desmarcar este projeto como evento? (as tags já gravadas nos arquivos não são removidas)", default=False):
            project.is_event = False
            project.save()
            console.print("[green]Projeto desmarcado.[/green]")
    elif choice == "3":
        if not (previous and previous.name):
            console.print("[yellow]Projeto sem evento.[/yellow]")
            return
        n = apply_event_tags(project, previous=previous, console=console)
        console.print(f"[green]Tags aplicadas em {n} arquivo(s).[/green]")


def _manage_people_catalog_flow(console: Console):
    while True:
        people = PeopleCatalog.list(limit=200)
        console.print("\n[bold cyan]Catálogo de pessoas[/bold cyan]")
        for i, p in enumerate(people, 1):
            console.print(f"  [cyan]{i}.[/cyan] {p}")
        if not people:
            console.print("  [dim](vazio)[/dim]")
        console.print("\n  [cyan]A.[/cyan] Adicionar  [cyan]R.[/cyan] Renomear  [cyan]E.[/cyan] Excluir  [cyan]0.[/cyan] Voltar")
        opt = Prompt.ask("Opção", default="0").upper()
        if opt == "0":
            return
        if opt == "A":
            PeopleCatalog.register(parse_names(Prompt.ask("Nomes (separados por vírgula)", default="")))
        elif opt in ("R", "E") and people:
            idx = Prompt.ask("Número da pessoa", default="")
            if idx.isdigit() and 1 <= int(idx) <= len(people):
                target = people[int(idx) - 1]
                if opt == "R":
                    PeopleCatalog.rename(target, Prompt.ask("Novo nome", default=target))
                elif Confirm.ask(f"Excluir '{target}' do catálogo?", default=False):
                    PeopleCatalog.delete(target)


def _menu_events(console: Console):
    """Hub de eventos: editar evento de um projeto e gerenciar catálogo de pessoas."""
    from src.core.project import list_open_projects
    while True:
        console.print("\n[bold yellow]🎉 Eventos & Álbuns[/bold yellow]")
        console.print("  [cyan]1.[/cyan] Editar evento de um projeto")
        console.print("  [cyan]2.[/cyan] Catálogo de pessoas frequentes")
        console.print("  [cyan]0.[/cyan] Voltar")
        choice = Prompt.ask("Opção", default="0")
        if choice == "0":
            return
        if choice == "2":
            _manage_people_catalog_flow(console)
        elif choice == "1":
            from src.core.project import get_project
            names = list_open_projects()
            if not names:
                console.print("[yellow]Nenhum projeto encontrado.[/yellow]")
                continue
            for i, n in enumerate(names, 1):
                p = get_project(n)
                tag = f" [green]🎉 {p.event_name}[/green]" if p and p.is_event else ""
                console.print(f"  [cyan]{i}.[/cyan] {n}{tag}")
            idx = Prompt.ask("Número do projeto", default="")
            if idx.isdigit() and 1 <= int(idx) <= len(names):
                _edit_project_event_flow(console, names[int(idx) - 1])
