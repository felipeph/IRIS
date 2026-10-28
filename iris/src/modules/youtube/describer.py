"""
Fachada do gerador de títulos, descrições, tags e roteamento de playlists do YouTube.
As implementações estão modularizadas por domínio em `src.modules.youtube.describers`.
"""

from src.core.geo import GeoService, GeoLocation
from src.core.metadata import parse_shutter_seconds

from .describers import (
    format_duration_human,
    format_bytes_human,
    _parse_shutter_value,
    _parse_iso_value,
    _parse_aperture_value,
    summarize_exposure_param,
    calculate_aspect_ratio,
    _extract_temporal_context,
    sanitize_hashtag,
    BR_STATE_TO_UF,
    resolve_project_geolocation,
    format_location_block,
    build_geo_hashtags,
    _normalize_bird_record,
    resolve_bird_identification,
    build_bird_youtube_title,
    format_bird_taxonomy_block,
    build_bird_hashtags,
    resolve_bird_target_playlists,
    build_youtube_title,
    build_youtube_tags,
    build_rich_youtube_description,
    build_edited_video_youtube_title,
    build_edited_video_youtube_metadata,
)

__all__ = [
    "GeoService",
    "GeoLocation",
    "parse_shutter_seconds",
    "format_duration_human",
    "format_bytes_human",
    "_parse_shutter_value",
    "_parse_iso_value",
    "_parse_aperture_value",
    "summarize_exposure_param",
    "calculate_aspect_ratio",
    "_extract_temporal_context",
    "sanitize_hashtag",
    "BR_STATE_TO_UF",
    "resolve_project_geolocation",
    "format_location_block",
    "build_geo_hashtags",
    "_normalize_bird_record",
    "resolve_bird_identification",
    "build_bird_youtube_title",
    "format_bird_taxonomy_block",
    "build_bird_hashtags",
    "resolve_bird_target_playlists",
    "build_youtube_title",
    "build_youtube_tags",
    "build_rich_youtube_description",
    "build_edited_video_youtube_title",
    "build_edited_video_youtube_metadata",
]
