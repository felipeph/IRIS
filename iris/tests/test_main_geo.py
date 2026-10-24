import pytest
from unittest.mock import patch, MagicMock
from rich.console import Console
from src.core.geo import GeoService, GeoLocation
from main import select_location_dialog

@pytest.fixture
def mock_console():
    return Console(force_terminal=False, width=80)

def test_select_location_dialog_default(mock_console):
    """Testa seleção direta por ENTER (opção padrão)."""
    locations = GeoService.get_locations()
    assert len(locations) >= 1
    default_id = GeoService.get_default_location_id()

    with patch("main.Prompt.ask", return_value="1"):
        loc = select_location_dialog(mock_console, default_id=default_id)
        assert loc.id == locations[0].id

def test_select_location_dialog_select_second(mock_console):
    """Testa seleção do segundo local da lista."""
    locations = GeoService.get_locations()
    if len(locations) >= 2:
        with patch("main.Prompt.ask", return_value="2"):
            loc = select_location_dialog(mock_console)
            assert loc.id == locations[1].id

def test_select_location_dialog_add_quick(mock_console):
    """Testa fluxo rápido de cadastro '+' no diálogo de seleção."""
    locations_before = len(GeoService.get_locations())
    coords = "-20.123456, -44.654321"
    label = "Sítio Teste - Nova Lima - MG"

    with patch("main.Prompt.ask", side_effect=["+", coords, label, "Nova Lima", "Minas Gerais"]):
        loc = select_location_dialog(mock_console)
        assert loc.label == label
        assert loc.lat == pytest.approx(-20.123456)
        assert loc.lng == pytest.approx(-44.654321)
        assert loc.city == "Nova Lima"
        assert loc.state == "Minas Gerais"

    locations_after = len(GeoService.get_locations())
    assert locations_after == locations_before + 1

    # Cleanup
    GeoService.delete_location(loc.id)
