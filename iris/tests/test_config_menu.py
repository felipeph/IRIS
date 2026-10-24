import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from rich.console import Console
from src.core.config import config
from src.core.config_menu import (
    show_config_menu,
    _menu_storage_ingestion,
    _menu_organization_classification,
    _menu_timelapse,
    _menu_timelapse_long_exposure,
    _menu_video_edit,
    _menu_youtube_notifications,
    _menu_bird_id,
    _menu_geolocation,
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
        _menu_timelapse_long_exposure(mock_console)
        _menu_video_edit(mock_console)
        _menu_youtube_notifications(mock_console)
        _menu_bird_id(mock_console)
        _menu_geolocation(mock_console)

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
        ("8", "_menu_bird_id"),
        ("9", "_menu_geolocation"),
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

def test_organization_classification_burst_options_edit(mock_console):
    """Testa edição das opções 10 (toggle burst) e 11 (intervalo de rajada) em Organização & Classificação."""
    orig_burst = config.get("classification.enable_burst_detection", True)
    orig_int = config.get("classification.burst_interval_seconds", 1.5)
    try:
        # Testa opção 10 com Confirm.ask -> False
        with patch("src.core.config_menu.Prompt.ask", side_effect=["10", "0"]), \
             patch("src.core.config_menu.Confirm.ask", return_value=False), \
             patch("src.core.config_menu.time.sleep"):
            _menu_organization_classification(mock_console)
            assert config.get("classification.enable_burst_detection") is False

        # Testa opção 11 com Prompt.ask -> 2.5
        with patch("src.core.config_menu.Prompt.ask", side_effect=["11", "2.5", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_organization_classification(mock_console)
            assert config.get("classification.burst_interval_seconds") == 2.5
    finally:
        config.set("classification.enable_burst_detection", orig_burst)
        config.set("classification.burst_interval_seconds", orig_int)

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

def test_timelapse_long_exposure_fpi_edit(mock_console):
    """Testa edição da opção 8 (FPI - Frames por Foto) em Timelapses de Longa Exposição."""
    original_fpi = config.get("modules.timelapse_long_exposure.frames_per_image", 1)
    try:
        # Escolhe opção 8 (FPI) -> "3", depois 0 para sair
        with patch("src.core.config_menu.Prompt.ask", side_effect=["8", "3", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_timelapse_long_exposure(mock_console)
            assert config.get("modules.timelapse_long_exposure.frames_per_image") == 3
    finally:
        config.set("modules.timelapse_long_exposure.frames_per_image", original_fpi)


def test_bird_id_menu_edit(mock_console):
    """Testa edição do limiar de alta certeza, prior geográfico, recortes de vídeo e pasta IRIS no menu de aves."""
    original_conf = config.get("modules.bird_id.min_species_confidence", 0.70)
    original_lat = config.get("modules.bird_id.inaturalist.default_lat", -19.92)
    original_max_crops = config.get("modules.bird_id.video_max_crops", 5)
    original_iris_crops = config.get("modules.bird_id.iris_crops_folder", "10_Aves/Recortes")
    try:
        # Opção 3 -> 0.85, Opção 8 -> 8, Opção 10 -> -20.50, Opção 14 -> "Custom_Aves/Crops", 0 para sair
        with patch("src.core.config_menu.Prompt.ask", side_effect=["3", "0.85", "8", "8", "10", "-20.50", "14", "Custom_Aves/Crops", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_bird_id(mock_console)
            assert config.get("modules.bird_id.min_species_confidence") == 0.85
            assert config.get("modules.bird_id.video_max_crops") == 8
            assert config.get("modules.bird_id.inaturalist.default_lat") == -20.50
            assert config.get("modules.bird_id.iris_crops_folder") == "Custom_Aves/Crops"
    finally:
        config.set("modules.bird_id.min_species_confidence", original_conf)
        config.set("modules.bird_id.video_max_crops", original_max_crops)
        config.set("modules.bird_id.inaturalist.default_lat", original_lat)
        config.set("modules.bird_id.iris_crops_folder", original_iris_crops)



def test_config_manager_sanitize_mojibake():
    """Valida se ConfigManager corrige mojibake double-encoded e preserva strings limpas."""
    from src.core.config import ConfigManager

    clean_str = "Ingestão de Arquivos (SD -> SSD)"
    dirty_str = "IngestÃ£o de Arquivos (SD -> SSD)"

    # Limpo deve permanecer inalterado
    assert ConfigManager._sanitize_mojibake(clean_str) == clean_str

    # Mojibake deve ser corrigido para UTF-8 válido
    assert ConfigManager._sanitize_mojibake(dirty_str) == clean_str

    # Estruturas aninhadas (dicionários e listas)
    nested = {
        "title": "PublicaÃ§Ã£o de VÃ­deos",
        "stages": ["SanitizaÃ§Ã£o", clean_str],
    }
    sanitized = ConfigManager._sanitize_mojibake(nested)
    assert sanitized["title"] == "Publicação de Vídeos"
    assert sanitized["stages"][0] == "Sanitização"
    assert sanitized["stages"][1] == clean_str


def test_config_manager_auto_migrates_missing_stages(tmp_path: Path):
    """Garante que ConfigManager insere astro_stack e astro_sharpen em configurações legadas."""
    import yaml
    from src.core.config import ConfigManager

    test_cfg_file = tmp_path / "legacy_config.yaml"
    legacy_data = {
        "general": {"theme": "light"},
        "pipeline": {
            "stages": [
                {"id": "ingestion", "name": "Ingestão", "enabled": True},
                {"id": "organize", "name": "Organização", "enabled": True},
                {"id": "timelapse", "name": "Timelapse", "enabled": True},
            ]
        },
        "modules": {
            "timelapse": {"enabled": True}
        }
    }
    with open(test_cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(legacy_data, f)

    with patch("src.core.config.CONFIG_FILE", test_cfg_file):
        cm = ConfigManager()
        cm.load()

        stages = cm.get("pipeline.stages")
        stage_ids = [s["id"] for s in stages]
        assert "astro_stack" in stage_ids
        assert "astro_sharpen" in stage_ids
        
        # Garante ordem correta: após organize e antes de timelapse
        org_idx = stage_ids.index("organize")
        stack_idx = stage_ids.index("astro_stack")
        sharpen_idx = stage_ids.index("astro_sharpen")
        tl_idx = stage_ids.index("timelapse")
        assert org_idx < stack_idx < sharpen_idx < tl_idx

        # Garante que os módulos foram criados
        assert cm.get("modules.astro_stack.enabled") is True
        assert cm.get("modules.astro_sharpen.enabled") is True


def test_config_manager_auto_migrates_long_exposure_fpi(tmp_path: Path):
    """Garante que ConfigManager insere frames_per_image em módulos legados de timelapse_long_exposure."""
    import yaml
    from src.core.config import ConfigManager

    test_cfg_file = tmp_path / "legacy_le_config.yaml"
    legacy_data = {
        "modules": {
            "timelapse_long_exposure": {
                "enabled": True,
                "fps": 30
            }
        }
    }
    with open(test_cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(legacy_data, f)

    with patch("src.core.config.CONFIG_FILE", test_cfg_file):
        cm = ConfigManager()
        cm.load()
        assert cm.get("modules.timelapse_long_exposure.frames_per_image") == 1


def test_bird_id_menu_burst_consensus_edit(mock_console):
    """Testa edição das opções 18 (toggle consenso rajada) e 19 (concordância mínima) no menu de aves."""
    from unittest.mock import patch
    orig_consensus = config.get("modules.bird_id.enable_burst_consensus", True)
    orig_ratio = config.get("modules.bird_id.burst_min_agreement_ratio", 0.50)
    try:
        # Testa opção 18 com Confirm.ask -> False
        with patch("src.core.config_menu.Prompt.ask", side_effect=["18", "0"]), \
             patch("src.core.config_menu.Confirm.ask", return_value=False), \
             patch("src.core.config_menu.time.sleep"):
            _menu_bird_id(mock_console)
            assert config.get("modules.bird_id.enable_burst_consensus") is False

        # Testa opção 19 com Prompt.ask -> 0.75
        with patch("src.core.config_menu.Prompt.ask", side_effect=["19", "0.75", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_bird_id(mock_console)
            assert config.get("modules.bird_id.burst_min_agreement_ratio") == 0.75
    finally:
        config.set("modules.bird_id.enable_burst_consensus", orig_consensus)
        config.set("modules.bird_id.burst_min_agreement_ratio", orig_ratio)


def test_bird_id_menu_burst_early_exit_edit(mock_console):
    """Testa edição das opções 20 (toggle early exit) e 21 (confirmações mínimas) no menu de aves."""
    from unittest.mock import patch
    orig_ee = config.get("modules.bird_id.enable_burst_early_exit", True)
    orig_confirms = config.get("modules.bird_id.burst_early_exit_confirmations", 3)
    try:
        # Testa opção 20 com Confirm.ask -> False
        with patch("src.core.config_menu.Prompt.ask", side_effect=["20", "0"]), \
             patch("src.core.config_menu.Confirm.ask", return_value=False), \
             patch("src.core.config_menu.time.sleep"):
            _menu_bird_id(mock_console)
            assert config.get("modules.bird_id.enable_burst_early_exit") is False

        # Testa opção 21 com Prompt.ask -> 4
        with patch("src.core.config_menu.Prompt.ask", side_effect=["21", "4", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_bird_id(mock_console)
            assert config.get("modules.bird_id.burst_early_exit_confirmations") == 4
    finally:
        config.set("modules.bird_id.enable_burst_early_exit", orig_ee)
        config.set("modules.bird_id.burst_early_exit_confirmations", orig_confirms)


def test_config_manager_auto_migrates_burst_consensus(tmp_path: Path):
    """Garante que ConfigManager insere configurações de consenso e early exit em configs legadas."""
    import yaml
    from src.core.config import ConfigManager

    test_cfg_file = tmp_path / "legacy_bird_config.yaml"
    legacy_data = {
        "modules": {
            "bird_id": {
                "enabled": True,
                "classifier_type": "inaturalist"
            }
        }
    }
    with open(test_cfg_file, "w", encoding="utf-8") as f:
        yaml.dump(legacy_data, f)

    with patch("src.core.config.CONFIG_FILE", test_cfg_file):
        cm = ConfigManager()
        cm.load()
        assert cm.get("modules.bird_id.enable_burst_consensus") is True
        assert cm.get("modules.bird_id.burst_min_agreement_ratio") == 0.50
        assert cm.get("modules.bird_id.enable_burst_early_exit") is True
        assert cm.get("modules.bird_id.burst_early_exit_confirmations") == 3


def test_geolocation_menu_toggles(mock_console):
    """Testa alternância de gravação de tags e token de nome no menu de geolocalização."""
    orig_tag = config.get("geo.tag_media", True)
    orig_tok = config.get("geo.filename_token", True)
    try:
        # Alterna tag_media com 'T' e sai com '0'
        with patch("src.core.config_menu.Prompt.ask", side_effect=["T", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_geolocation(mock_console)
            assert config.get("geo.tag_media") is not orig_tag

        # Alterna filename_token com 'F' e sai com '0'
        with patch("src.core.config_menu.Prompt.ask", side_effect=["F", "0"]), \
             patch("src.core.config_menu.time.sleep"):
            _menu_geolocation(mock_console)
            assert config.get("geo.filename_token") is not orig_tok
    finally:
        config.set("geo.tag_media", orig_tag)
        config.set("geo.filename_token", orig_tok)


