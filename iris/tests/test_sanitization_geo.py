import pytest
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.core.project import Project, ProjectItem, create_project
from src.core.geo import GeoLocation, GeoService
from src.modules.sanitization.stage import SanitizationStage

@pytest.fixture
def mock_geo_loc():
    loc = GeoLocation(
        id="test-formiga",
        label="Bairro São Luiz - Formiga - MG",
        lat=-20.456887,
        lng=-45.438307,
        accuracy_m=25000.0,
        city="Formiga",
        state="Minas Gerais",
        country="Brasil"
    )
    GeoService.add_location(loc, set_as_default=True)
    return loc

def test_sanitization_geo_workflow(tmp_path, monkeypatch, mock_geo_loc):
    project = create_project("test_sanit_geo", str(tmp_path / "source"), geo_location_id="test-formiga")

    # Arquivo 1: JPEG com GPS nativo
    jpg_native = tmp_path / "native.jpg"
    jpg_native.write_bytes(b"content_native_jpg")
    item1 = ProjectItem(
        original_path=str(jpg_native),
        staging_path=str(jpg_native),
        status="copied",
        file_size_bytes=len(b"content_native_jpg"),
        file_hash="hash1"
    )

    # Arquivo 2: JPEG sem GPS
    jpg_no_gps = tmp_path / "no_gps.jpg"
    jpg_no_gps.write_bytes(b"content_no_gps_jpg")
    item2 = ProjectItem(
        original_path=str(jpg_no_gps),
        staging_path=str(jpg_no_gps),
        status="copied",
        file_size_bytes=len(b"content_no_gps_jpg"),
        file_hash="hash2"
    )

    # Arquivo 3: RAW sem GPS (ex: .CR2)
    raw_no_gps = tmp_path / "no_gps.CR2"
    raw_no_gps.write_bytes(b"content_raw_data")
    item3 = ProjectItem(
        original_path=str(raw_no_gps),
        staging_path=str(raw_no_gps),
        status="copied",
        file_size_bytes=len(b"content_raw_data"),
        file_hash="hash3"
    )

    # Arquivo 4: Vídeo sem GPS (ex: .mp4)
    video_no_gps = tmp_path / "no_gps.mp4"
    video_no_gps.write_bytes(b"content_video_data")
    item4 = ProjectItem(
        original_path=str(video_no_gps),
        staging_path=str(video_no_gps),
        status="copied",
        file_size_bytes=len(b"content_video_data"),
        file_hash="hash4"
    )

    with project.transaction():
        project.save_item(item1)
        project.save_item(item2)
        project.save_item(item3)
        project.save_item(item4)

    # Mock de read_gps_batch: item1 tem GPS nativo, os demais não
    mock_gps_return = {
        str(jpg_native.resolve()): (-20.1000, -45.1000, 10.0),
        str(jpg_no_gps.resolve()): (None, None, None),
        str(raw_no_gps.resolve()): (None, None, None),
        str(video_no_gps.resolve()): (None, None, None),
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""

    executed_cmds = []
    def fake_subprocess_run(cmd, **kwargs):
        executed_cmds.append(list(cmd))
        return mock_proc

    with patch("src.modules.sanitization.stage.read_gps_batch", return_value=mock_gps_return), \
         patch("src.modules.sanitization.stage.shutil.which", return_value="exiftool"), \
         patch("subprocess.run", side_effect=fake_subprocess_run):

        stage = SanitizationStage("sanitization", "Sanitização de Metadados EXIF e Geotag")
        success = stage.run(project)
        assert success is True

    items = {Path(it.staging_path).name: it for it in project.get_items()}

    # 1. Item nativo deve ter mantido as coordenadas nativas e geo_source='native'
    it_native = items["native.jpg"]
    assert it_native.geo_source == "native"
    assert pytest.approx(it_native.meta_latitude) == -20.1000
    assert pytest.approx(it_native.meta_longitude) == -45.1000
    assert it_native.geo_written is False

    # 2. Item JPEG sem GPS deve ter recebido as coordenadas do preset e sido gravado
    it_no_gps = items["no_gps.jpg"]
    assert it_no_gps.geo_source == "preset"
    assert pytest.approx(it_no_gps.meta_latitude) == -20.456887
    assert pytest.approx(it_no_gps.meta_longitude) == -45.438307
    assert it_no_gps.geo_written is True

    # 3. Item RAW sem GPS NÃO pode ter sido gravado via ExifTool (apenas no nome)
    it_raw = items["no_gps.CR2"]
    assert it_raw.geo_source == "preset"
    assert pytest.approx(it_raw.meta_latitude) == -20.456887
    assert pytest.approx(it_raw.meta_longitude) == -45.438307
    assert it_raw.geo_written is False

    # 4. Item Vídeo sem GPS NÃO pode ter sido gravado via ExifTool (apenas no nome)
    it_video = items["no_gps.mp4"]
    assert it_video.geo_source == "preset"
    assert pytest.approx(it_video.meta_latitude) == -20.456887
    assert pytest.approx(it_video.meta_longitude) == -45.438307
    assert it_video.geo_written is False

    # Garante que nenhum comando do ExifTool continha caminho do vídeo ou do RAW
    for cmd in executed_cmds:
        cmd_str = " ".join(cmd)
        assert "no_gps.CR2" not in cmd_str
        assert "no_gps.mp4" not in cmd_str
