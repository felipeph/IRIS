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
    argfile_contents = []
    def fake_subprocess_run(cmd, **kwargs):
        executed_cmds.append(list(cmd))
        if "-@" in cmd:
            idx = cmd.index("-@") + 1
            if idx < len(cmd):
                argfile = Path(cmd[idx])
                if argfile.exists():
                    argfile_contents.append(argfile.read_text(encoding="utf-8"))
        return mock_proc

    with patch("src.modules.sanitization.stage.read_gps_batch", return_value=mock_gps_return), \
         patch("src.modules.sanitization.stage.shutil.which", return_value="exiftool"), \
         patch("subprocess.run", side_effect=fake_subprocess_run):

        stage = SanitizationStage("sanitization", "Sanitização de Metadados EXIF e Geotag (Álbuns)")
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
    for content in argfile_contents:
        assert "no_gps.CR2" not in content
        assert "no_gps.mp4" not in content


def test_sanitization_selective_albums_and_timelapse_samples(tmp_path, mock_geo_loc):
    """
    Testa o comportamento seletivo pós-organização da Abordagem B1:
    - Frames mestres em 4_Timelapses/ e 5_Astrofotografia/ são ignorados pelo ExifTool (bit-perfect).
    - Amostras copiadas para 2_AlbunsDatas/ e fotos avulsas em 2_AlbunsDatas/ são sanitizadas.
    """
    project = create_project("test_sanit_selective", str(tmp_path / "source"), geo_location_id="test-formiga")

    dest_root = tmp_path / "IRIS"
    albums_dir = dest_root / "2_AlbunsDatas" / "2026" / "09" / "22"
    tl_dir = dest_root / "4_Timelapses" / "GoPro" / "2026" / "09" / "22" / "timelapse_12-00-00"
    astro_dir = dest_root / "5_Astrofotografia" / "Lua" / "2026" / "09" / "22" / "sessao_21-00-00"

    albums_dir.mkdir(parents=True, exist_ok=True)
    tl_dir.mkdir(parents=True, exist_ok=True)
    astro_dir.mkdir(parents=True, exist_ok=True)

    # 1. Foto avulsa organizada em 2_AlbunsDatas
    f_album = albums_dir / "2026-09-22_photo_album.jpg"
    f_album.write_bytes(b"content_album_photo")
    item_album = ProjectItem(
        original_path="G:/DCIM/IMG_01.JPG",
        staging_path=str(f_album),
        organized_path=str(f_album),
        relative_dest_dir="2_AlbunsDatas/2026/09/22",
        category="avulsa",
        status="organized",
        file_size_bytes=len(b"content_album_photo"),
        file_hash="hash_album"
    )

    # 2. Frame mestre de timelapse em 4_Timelapses com amostra extra em 2_AlbunsDatas
    f_tl_master = tl_dir / "2026-09-22_tl_0001.jpg"
    f_tl_master.write_bytes(b"content_timelapse_frame")

    f_tl_sample = albums_dir / "timelapse_amostras_12-00-00" / "2026-09-22_tl_0001.jpg"
    f_tl_sample.parent.mkdir(parents=True, exist_ok=True)
    f_tl_sample.write_bytes(b"content_timelapse_frame_sample")

    item_timelapse = ProjectItem(
        original_path="G:/DCIM/TL_0001.JPG",
        staging_path=str(f_tl_master),
        organized_path=str(f_tl_master),
        relative_dest_dir="4_Timelapses/GoPro/2026/09/22/timelapse_12-00-00",
        category="timelapse",
        status="organized",
        file_size_bytes=len(b"content_timelapse_frame"),
        file_hash="hash_tl_master",
        extra_organized_paths_json=json.dumps([str(f_tl_sample)])
    )

    # 3. Frame mestre de astrofotografia em 5_Astrofotografia (RAW ou JPEG)
    f_astro = astro_dir / "2026-09-22_astro_001.CR2"
    f_astro.write_bytes(b"content_astro_raw")
    item_astro = ProjectItem(
        original_path="G:/DCIM/ASTRO_001.CR2",
        staging_path=str(f_astro),
        organized_path=str(f_astro),
        relative_dest_dir="5_Astrofotografia/Lua/2026/09/22/sessao_21-00-00",
        category="astro_lua",
        status="organized",
        file_size_bytes=len(b"content_astro_raw"),
        file_hash="hash_astro"
    )

    with project.transaction():
        project.save_item(item_album)
        project.save_item(item_timelapse)
        project.save_item(item_astro)

    mock_gps_return = {
        str(f_album.resolve()): (None, None, None),
        str(f_tl_sample.resolve()): (None, None, None),
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = ""

    argfile_contents = []
    def fake_subprocess_run(cmd, **kwargs):
        if "-@" in cmd:
            idx = cmd.index("-@") + 1
            if idx < len(cmd):
                argfile = Path(cmd[idx])
                if argfile.exists():
                    argfile_contents.append(argfile.read_text(encoding="utf-8"))
        return mock_proc

    with patch("src.modules.sanitization.stage.read_gps_batch", return_value=mock_gps_return), \
         patch("src.modules.sanitization.stage.shutil.which", return_value="exiftool"), \
         patch("subprocess.run", side_effect=fake_subprocess_run):

        stage = SanitizationStage("sanitization", "Sanitização de Metadados e Geotag (Álbuns)")
        success = stage.run(project)
        assert success is True

    # Verifica o que foi escrito nos argfiles do ExifTool
    all_exiftool_targets = "\n".join(argfile_contents)

    # 1. Foto de álbum e amostra de timelapse DEVEM ter sido passadas ao ExifTool
    assert str(f_album.resolve()) in all_exiftool_targets
    assert str(f_tl_sample.resolve()) in all_exiftool_targets

    # 2. Frame mestre de timelapse e foto de astro NUNCA devem ter sido passados ao ExifTool
    assert str(f_tl_master.resolve()) not in all_exiftool_targets
    assert str(f_astro.resolve()) not in all_exiftool_targets
