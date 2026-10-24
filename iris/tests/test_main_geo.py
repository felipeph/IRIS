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


def test_select_location_dialog_delete(mock_console):
    """Testa exclusão interativa com atalho '-' no diálogo de seleção."""
    temp_loc = GeoLocation(
        id="sitio-exclusao-teste",
        label="Sítio Para Excluir - Sabará - MG",
        lat=-19.88,
        lng=-43.80,
        city="Sabará",
        state="Minas Gerais"
    )
    GeoService.add_location(temp_loc)
    locs = GeoService.get_locations()
    target_idx = next(i for i, l in enumerate(locs, 1) if l.id == temp_loc.id)

    # Escolhe '-' para excluir, fornece target_idx, confirma com True, depois escolhe '1'
    with patch("main.Prompt.ask", side_effect=["-", str(target_idx), "1"]), \
         patch("main.Confirm.ask", return_value=True), \
         patch("main.time.sleep"):
        loc = select_location_dialog(mock_console)
        assert loc is not None

    remaining_ids = [l.id for l in GeoService.get_locations()]
    assert temp_loc.id not in remaining_ids


def test_select_location_dialog_delete_cancel(mock_console):
    """Testa cancelamento de exclusão (0) no diálogo de seleção."""
    before_count = len(GeoService.get_locations())
    with patch("main.Prompt.ask", side_effect=["-", "0", "1"]), \
         patch("main.time.sleep"):
        loc = select_location_dialog(mock_console)
        assert loc is not None
    assert len(GeoService.get_locations()) == before_count
