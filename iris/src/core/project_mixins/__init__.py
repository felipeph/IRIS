"""
Pacote de Mixins e submódulos para decomposição do módulo Project (RFC 09).
"""

from .schema import CURRENT_SCHEMA_VERSION, SHARED_TABLES_DDL
from .base import ProjectBase, _ProjectTransactionContext
from .items import ProjectItemsMixin
from .media import ProjectMediaMixin
from .astro import ProjectAstroMixin
from .birds import ProjectBirdsMixin
from .central_db import (
    list_open_projects,
    get_last_active_project,
    save_central_timelapse,
    update_central_timelapse_youtube,
    update_central_timelapse_local_deleted,
    list_central_timelapses,
    save_central_edited_video,
    update_central_edited_video_youtube,
    update_central_edited_video_local_deleted,
    list_central_edited_videos,
    save_central_astro_stack,
    list_central_astro_stacks,
    save_central_astro_sharpen,
    list_central_astro_sharpens,
    reconcile_project_with_central,
    reconcile_all_projects_with_central,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "SHARED_TABLES_DDL",
    "ProjectBase",
    "_ProjectTransactionContext",
    "ProjectItemsMixin",
    "ProjectMediaMixin",
    "ProjectAstroMixin",
    "ProjectBirdsMixin",
    "list_open_projects",
    "get_last_active_project",
    "save_central_timelapse",
    "update_central_timelapse_youtube",
    "update_central_timelapse_local_deleted",
    "list_central_timelapses",
    "save_central_edited_video",
    "update_central_edited_video_youtube",
    "update_central_edited_video_local_deleted",
    "list_central_edited_videos",
    "save_central_astro_stack",
    "list_central_astro_stacks",
    "save_central_astro_sharpen",
    "list_central_astro_sharpens",
    "reconcile_project_with_central",
    "reconcile_all_projects_with_central",
]
