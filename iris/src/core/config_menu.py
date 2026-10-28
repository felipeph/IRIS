"""
Hub principal do menu interativo de configurações do IRIS.
As subpáginas temáticas estão modularizadas em `src.core.config_menus` e re-exportadas
aqui para total retrocompatibilidade de imports e mocks de testes.
"""

import time
import re
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
    format_gps_token,
    maps_url,
    build_location_panel,
    interactive_add_location_flow,
    reverse_geocode,
)
from src.core.config_menus import (
    _menu_storage_ingestion,
    _menu_organization_classification,
    _menu_timelapse,
    _menu_timelapse_long_exposure,
    _menu_video_edit,
    _menu_youtube_notifications,
    _menu_astro,
    _menu_bird_id,
    _add_location_flow,
    _edit_location_flow,
    _set_default_location_flow,
    _delete_location_flow,
    _menu_geolocation,
)


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
        console.print("  [cyan]9.[/cyan] 📍 Geolocalizações & Metadados GPS [dim](Pontos pré-definidos, GPS em Tags e Nomes)[/dim]")
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
        elif choice == "9":
            _menu_geolocation(console)
        else:
            console.print("[red]Opção inválida.[/red]")
            time.sleep(1)


__all__ = [
    "show_config_menu",
    "_menu_storage_ingestion",
    "_menu_organization_classification",
    "_menu_timelapse",
    "_menu_timelapse_long_exposure",
    "_menu_video_edit",
    "_menu_youtube_notifications",
    "_menu_astro",
    "_menu_bird_id",
    "_add_location_flow",
    "_edit_location_flow",
    "_set_default_location_flow",
    "_delete_location_flow",
    "_menu_geolocation",
]
