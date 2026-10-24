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
