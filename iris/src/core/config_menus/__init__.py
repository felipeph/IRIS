"""
Pacote de submenus interativos de configuração do IRIS.
Divide as responsabilidades de `src.core.config_menu` por domínio funcional.
"""

from .storage_org import _menu_storage_ingestion, _menu_organization_classification
from .timelapse import _menu_timelapse, _menu_timelapse_long_exposure
from .video_youtube import _menu_video_edit, _menu_youtube_notifications
from .astro import _menu_astro
from .bird_id import _menu_bird_id
from .geolocation import (
    _add_location_flow,
    _edit_location_flow,
    _set_default_location_flow,
    _delete_location_flow,
    _menu_geolocation,
)

__all__ = [
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
