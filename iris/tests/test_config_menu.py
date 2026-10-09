import pytest
from unittest.mock import patch, MagicMock
from rich.console import Console
from src.core.config import config
from src.core.config_menu import (
    show_config_menu,
    _menu_storage_ingestion,
    _menu_organization_classification,
    _menu_timelapse,
    _menu_video_edit,
    _menu_youtube_notifications
)

@pytest.fixture
def mock_console():
    return Console(force_terminal=False, width=80)

def test_config_menu_subpages_exit(mock_console):
    """Verifica se cada subpágina sai corretamente quando a opção '0' é fornecida."""
    with patch("src.core.config_menu.Prompt.ask", return_value="0"), \
         patch("src.core.config_menu.time.sleep"):
        _menu_storage_ingestion(mock_console)
        _menu_organization_classification(mock_console)
        _menu_timelapse(mock_console)
        _menu_video_edit(mock_console)
        _menu_youtube_notifications(mock_console)

def test_show_config_menu_hub(mock_console):
    """Testa a navegação no menu hub principal saindo com 0."""
    with patch("src.core.config_menu.Prompt.ask", return_value="0"), \
         patch("src.core.config_menu.time.sleep"):
        show_config_menu(mock_console)

def test_show_config_menu_routes_to_subpages(mock_console):
    """Testa se o hub chama as subpáginas correspondentes."""
    for opt, target_func in [
        ("1", "_menu_storage_ingestion"),
        ("2", "_menu_organization_classification"),
        ("3", "_menu_timelapse"),
        ("4", "_menu_video_edit"),
        ("5", "_menu_youtube_notifications"),
    ]:
        with patch("src.core.config_menu.Prompt.ask", side_effect=[opt, "0"]), \
             patch(f"src.core.config_menu.{target_func}") as mock_sub, \
             patch("src.core.config_menu.time.sleep"):
            show_config_menu(mock_console)
            assert mock_sub.called

def test_storage_ingestion_edit(mock_console):
    """Testa edição de valor em Armazenamento & Ingestão."""
    original = config.get("general.log_level", "INFO")
    try:
        # Escolhe opção 3 (Nível de Log) -> "DEBUG", depois 0 para sair
        with patch("src.core.config_menu.Prompt.ask", side_effect=["3", "DEBUG", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_storage_ingestion(mock_console)
            assert config.get("general.log_level") == "DEBUG"
    finally:
        config.set("general.log_level", original)

def test_organization_classification_edit(mock_console):
    """Testa edição de valor em Organização & Classificação."""
    original = config.get("classification.moon_zoom_threshold_mm", 1000.0)
    try:
        # Escolhe opção 3 (Zoom Lua) -> "1250.0", depois 0 para sair
        with patch("src.core.config_menu.Prompt.ask", side_effect=["3", "1250.0", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_organization_classification(mock_console)
            assert config.get("classification.moon_zoom_threshold_mm") == 1250.0
    finally:
        config.set("classification.moon_zoom_threshold_mm", original)

def test_timelapse_edit(mock_console):
    """Testa edição de valor em Timelapse 4K."""
    original_fps = config.get("modules.timelapse.fps", 60)
    try:
        # Escolhe opção 2 (FPS Timelapse) -> "30", depois 0 para sair
        with patch("src.core.config_menu.Prompt.ask", side_effect=["2", "30", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_timelapse(mock_console)
            assert config.get("modules.timelapse.fps") == 30
    finally:
        config.set("modules.timelapse.fps", original_fps)

def test_video_edit_menu(mock_console):
    """Testa edição de valor em Edição de Vídeo 4K."""
    original_speed = config.get("modules.video_edit.speed", 1.0)
    try:
        # Escolhe opção 3 (Velocidade) -> "2.0", depois 0 para sair
        with patch("src.core.config_menu.Prompt.ask", side_effect=["3", "2.0", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_video_edit(mock_console)
            assert config.get("modules.video_edit.speed") == 2.0
    finally:
        config.set("modules.video_edit.speed", original_speed)

def test_youtube_notifications_edit(mock_console):
    """Testa edição de valor em YouTube & Notificações."""
    original_playlist = config.get("modules.youtube.playlist", "Timelapses")
    try:
        # Escolhe opção 2 (Playlist Timelapses) -> "Meus Timelapses", depois 0 para sair
        with patch("src.core.config_menu.Prompt.ask", side_effect=["2", "Meus Timelapses", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_youtube_notifications(mock_console)
            assert config.get("modules.youtube.playlist") == "Meus Timelapses"
    finally:
        config.set("modules.youtube.playlist", original_playlist)
