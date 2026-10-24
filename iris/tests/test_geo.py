import pytest
from src.core.geo import GeoLocation, parse_coords, format_gps_token, maps_url, build_exiftool_geo_args, GeoService
from src.core.config import config

def test_parse_coords_valid():
    # Decimal com vírgula
    lat, lng = parse_coords("-20.456887, -45.438307")
    assert pytest.approx(lat) == -20.456887
    assert pytest.approx(lng) == -45.438307

    # Decimal com espaço
    lat, lng = parse_coords("-20.456887 -45.438307")
    assert pytest.approx(lat) == -20.456887
    assert pytest.approx(lng) == -45.438307

    # Com cardinal S e W
    lat, lng = parse_coords("20.456887S, 45.438307W")
    assert pytest.approx(lat) == -20.456887
    assert pytest.approx(lng) == -45.438307

    # Positivo (N e E)
    lat, lng = parse_coords("10.5N, 20.2E")
    assert pytest.approx(lat) == 10.5
    assert pytest.approx(lng) == 20.2

def test_parse_coords_invalid():
    with pytest.raises(ValueError):
        parse_coords("invalido")

    with pytest.raises(ValueError):
        parse_coords("-95.0, -45.0")

    with pytest.raises(ValueError):
        parse_coords("-20.0, 190.0")

def test_format_gps_token():
    token = format_gps_token(-20.456887, -45.438307)
    assert token == "S20-4569_W45-4383"

    token_pos = format_gps_token(12.3456, 45.6789)
    assert token_pos == "N12-3456_E45-6789"

def test_maps_url():
    url = maps_url(-20.456887, -45.438307)
    assert url == "https://www.google.com/maps?q=-20.456887,-45.438307"

def test_build_exiftool_geo_args_image():
    loc = GeoLocation(
        id="test-loc",
        label="Bairro Teste",
        lat=-20.456887,
        lng=-45.438307,
        city="Formiga",
        state="Minas Gerais",
        country="Brasil"
    )
    args = build_exiftool_geo_args(loc, is_video=False, ext=".jpg")
    assert any("GPSLatitudeRef=S" in a for a in args)
    assert any("GPSLongitudeRef=W" in a for a in args)
    assert "-IPTC:City=Formiga" in args
    assert "-IPTC:Province-State=Minas Gerais" in args
    assert "-IPTC:Country-PrimaryLocationName=Brasil" in args
    assert "-IPTC:Sub-location=Bairro Teste" in args

def test_build_exiftool_geo_args_video_or_raw():
    loc = GeoLocation(
        id="test-loc",
        label="Bairro Teste",
        lat=-20.456887,
        lng=-45.438307,
        city="Formiga",
        state="Minas Gerais",
        country="Brasil"
    )
    # Vídeo NÃO deve gerar args de escrita ExifTool
    assert build_exiftool_geo_args(loc, is_video=True, ext=".mp4") == []
    # RAW NÃO deve gerar args de escrita ExifTool
    assert build_exiftool_geo_args(loc, is_video=False, ext=".cr2") == []
    assert build_exiftool_geo_args(loc, is_video=False, ext=".dng") == []

def test_geo_service_crud(tmp_path, monkeypatch):
    test_loc = GeoLocation(
        id="custom-1",
        label="Ponto Personalizado",
        lat=-20.1234,
        lng=-45.5678,
        city="Cidade A",
        state="Minas Gerais",
        country="Brasil"
    )
    GeoService.add_location(test_loc, set_as_default=True)
    assert GeoService.get_default_location_id() == "custom-1"

    retrieved = GeoService.get_location("custom-1")
    assert retrieved is not None
    assert retrieved.label == "Ponto Personalizado"
    assert pytest.approx(retrieved.lat) == -20.1234

    test_loc.label = "Ponto Modificado"
    GeoService.update_location(test_loc)
    assert GeoService.get_location("custom-1").label == "Ponto Modificado"

    deleted = GeoService.delete_location("custom-1")
    assert deleted is True
    assert GeoService.get_location("custom-1") is None


def test_geo_service_delete_protection():
    orig_locs = config.get("geo.locations", [])
    try:
        config.set("geo.locations", [{"id": "unico", "label": "Unico", "lat": 0, "lng": 0}])
        assert GeoService.delete_location("unico") is False
    finally:
        config.set("geo.locations", orig_locs)


def test_geolocation_suburb_poi_and_tags():
    loc = GeoLocation(
        id="mangabeiras",
        label="Meu Ponto",
        lat=-19.9547,
        lng=-43.9056,
        city="Belo Horizonte",
        state="Minas Gerais",
        country="Brasil",
        suburb="Mangabeiras",
        poi="Parque das Mangabeiras"
    )
    d = loc.to_dict()
    assert d["suburb"] == "Mangabeiras"
    assert d["poi"] == "Parque das Mangabeiras"

    rebuilt = GeoLocation.from_dict(d)
    assert rebuilt.suburb == "Mangabeiras"
    assert rebuilt.poi == "Parque das Mangabeiras"

    tags = rebuilt.get_tags()
    assert "Parque das Mangabeiras" in tags
    assert "Mangabeiras" in tags
    assert "Belo Horizonte" in tags
    assert "Minas Gerais" in tags
    assert "Brasil" in tags
    assert "Meu Ponto" in tags


def test_build_exiftool_geo_args_with_tags():
    loc = GeoLocation(
        id="mangabeiras",
        label="Observatório",
        lat=-19.9547,
        lng=-43.9056,
        city="Belo Horizonte",
        state="Minas Gerais",
        country="Brasil",
        suburb="Mangabeiras",
        poi="Parque das Mangabeiras"
    )
    args = build_exiftool_geo_args(loc, is_video=False, ext=".jpg")

    assert "-IPTC:City=Belo Horizonte" in args
    assert "-IPTC:Province-State=Minas Gerais" in args
    assert "-IPTC:Country-PrimaryLocationName=Brasil" in args
    assert "-IPTC:Sub-location=Parque das Mangabeiras" in args
    assert "-XMP-iptcCore:Location=Parque das Mangabeiras" in args

    assert "-Keywords+=Parque das Mangabeiras" in args
    assert "-Keywords+=Mangabeiras" in args
    assert "-Keywords+=Belo Horizonte" in args
    assert "-Keywords+=Minas Gerais" in args
    assert "-Keywords+=Brasil" in args

    assert "-Subject+=Parque das Mangabeiras" in args
    assert "-Subject+=Mangabeiras" in args

    assert any(a.startswith("-XPKeywords=") and "Parque das Mangabeiras" in a for a in args)


def test_build_location_panel_content():
    from src.core.geo import build_location_panel
    loc = GeoLocation(
        id="teste-panel",
        label="Entrada Principal",
        lat=-19.95,
        lng=-43.90,
        city="Belo Horizonte",
        state="Minas Gerais",
        country="Brasil",
        suburb="Mangabeiras",
        poi="Parque das Mangabeiras"
    )
    panel = build_location_panel(loc)
    render_text = str(panel.renderable)
    assert "Entrada Principal" in render_text
    assert "Parque das Mangabeiras" in render_text
    assert "Mangabeiras" in render_text
    assert "Belo Horizonte" in render_text


def test_reverse_geocode_nominatim_success():
    from unittest.mock import patch, MagicMock
    from src.core.geo import reverse_geocode

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "category": "leisure",
        "type": "park",
        "name": "Parque das Mangabeiras",
        "address": {
            "park": "Parque das Mangabeiras",
            "suburb": "Mangabeiras",
            "city": "Belo Horizonte",
            "state": "Minas Gerais",
            "country": "Brasil"
        }
    }

    with patch("requests.get", return_value=mock_resp):
        info = reverse_geocode(-19.9547, -43.9056)
        assert info["city"] == "Belo Horizonte"
        assert info["state"] == "Minas Gerais"
        assert info["country"] == "Brasil"
        assert info["suburb"] == "Mangabeiras"
        assert info["poi"] == "Parque das Mangabeiras"
        assert info["source"] == "nominatim"


def test_reverse_geocode_fallback_bigdatacloud():
    from unittest.mock import patch, MagicMock
    from src.core.geo import reverse_geocode

    # Primeiro request (Nominatim) falha com timeout
    mock_bdc = MagicMock()
    mock_bdc.status_code = 200
    mock_bdc.json.return_value = {
        "city": "Formiga",
        "principalSubdivision": "Minas Gerais",
        "countryName": "Brasil",
        "localityInfo": {
            "administrative": [
                {"name": "Brasil", "adminLevel": 2},
                {"name": "Minas Gerais", "adminLevel": 4},
                {"name": "Formiga", "adminLevel": 8},
                {"name": "São Luiz", "adminLevel": 10}
            ]
        }
    }

    def side_effect(url, **kwargs):
        if "nominatim" in url:
            raise Exception("Nominatim Timeout")
        return mock_bdc

    with patch("requests.get", side_effect=side_effect):
        info = reverse_geocode(-20.456887, -45.438307)
        assert info["city"] == "Formiga"
        assert info["state"] == "Minas Gerais"
        assert info["country"] == "Brasil"
        assert info["suburb"] == "São Luiz"
        assert info["source"] == "bigdatacloud"


def test_reverse_geocode_offline_graceful():
    from unittest.mock import patch
    from src.core.geo import reverse_geocode

    with patch("requests.get", side_effect=Exception("No internet connection")):
        info = reverse_geocode(-20.456887, -45.438307)
        assert info["city"] == ""
        assert info["country"] == "Brasil"
        assert info["source"] == "offline"


def test_interactive_add_location_flow_save_quick():
    from unittest.mock import patch
    from rich.console import Console
    from src.core.geo import interactive_add_location_flow

    mock_console = Console(record=True)
    coords = "-19.9547, -43.9056"
    label = "Parque das Mangabeiras BH"

    mock_geo = {
        "city": "Belo Horizonte",
        "state": "Minas Gerais",
        "country": "Brasil",
        "suburb": "Mangabeiras",
        "poi": "Parque das Mangabeiras",
        "source": "nominatim"
    }

    with patch("src.core.geo.reverse_geocode", return_value=mock_geo), \
         patch("rich.prompt.Prompt.ask", side_effect=[coords, label, "S"]):
        loc = interactive_add_location_flow(mock_console, set_as_default=False)
        assert loc is not None
        assert loc.label == label
        assert loc.city == "Belo Horizonte"
        assert loc.suburb == "Mangabeiras"
        assert loc.poi == "Parque das Mangabeiras"
        # Cleanup
        GeoService.delete_location(loc.id)


def test_interactive_add_location_flow_cancel():
    from unittest.mock import patch
    from rich.console import Console
    from src.core.geo import interactive_add_location_flow

    mock_console = Console(record=True)
    coords = "-19.9547, -43.9056"
    label = "Ponto Cancelado"

    with patch("src.core.geo.reverse_geocode", return_value={"city": "BH", "country": "Brasil"}), \
         patch("rich.prompt.Prompt.ask", side_effect=[coords, label, "C"]):
        loc = interactive_add_location_flow(mock_console)
        assert loc is None


def test_exiftool_geo_args_accents_utf8(tmp_path):
    import shutil
    import subprocess
    import json
    import os
    import tempfile
    from PIL import Image

    exiftool_bin = shutil.which("exiftool")
    if not exiftool_bin:
        pytest.skip("ExifTool não encontrado no ambiente")

    test_img = tmp_path / "test_accent.jpg"
    img = Image.new("RGB", (10, 10), color="blue")
    img.save(test_img, "JPEG")

    loc = GeoLocation(
        id="suica",
        label="Praça São Luiz - Nova Suíça",
        lat=-19.9234,
        lng=-43.9876,
        city="Belo Horizonte",
        state="Minas Gerais",
        country="Brasil",
        suburb="Nova Suíça",
        poi="Praça São Luiz"
    )

    geo_args = build_exiftool_geo_args(loc, is_video=False, ext=".jpg")

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write("-MPF:all=\n")
        f.write("-trailer:all=\n")
        f.write("-MakerNotes:all=\n")
        f.write("-PreviewImage=\n")
        f.write("-overwrite_original\n")
        f.write("-P\n")
        for arg in geo_args:
            f.write(f"{arg}\n")
        f.write(f"{test_img.resolve()}\n")
        argfile = f.name

    try:
        cmd = [exiftool_bin, "-charset", "UTF8", "-@", argfile]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        assert proc.returncode == 0
        assert "Malformed UTF-8" not in proc.stderr

        read_cmd = [exiftool_bin, "-charset", "UTF8", "-json", "-G", str(test_img.resolve())]
        read_proc = subprocess.run(read_cmd, capture_output=True, text=True, encoding="utf-8")
        assert read_proc.returncode == 0
        data = json.loads(read_proc.stdout)[0]

        assert data.get("IPTC:Sub-location") == "Praça São Luiz"
        assert data.get("XMP:Location") == "Praça São Luiz"
        assert data.get("EXIF:XPKeywords") == "Praça São Luiz;Nova Suíça;Belo Horizonte;Minas Gerais;Brasil;Praça São Luiz - Nova Suíça"
        keywords = data.get("IPTC:Keywords")
        if isinstance(keywords, str):
            keywords = [keywords]
        assert "Nova Suíça" in keywords
        assert "Praça São Luiz" in keywords
    finally:
        if os.path.exists(argfile):
            os.unlink(argfile)


