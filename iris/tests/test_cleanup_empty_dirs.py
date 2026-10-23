import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.cleanup import (
    is_dir_empty,
    clean_empty_parent_dirs,
    clean_empty_directories,
    prune_empty_dirs_upward,
    OS_JUNK_FILES
)
from src.core.config import config
from src.core.project import create_project, ProjectItem
from src.modules.organize.stage import OrganizeStage
from src.modules.youtube.cleaner import execute_post_upload_cleanup
from src.modules.bird_id.organize_stage import BirdOrganizeStage
from src.core.pipeline import PipelineRunner


def test_is_dir_empty_basic(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert is_dir_empty(empty_dir) is True

    non_empty_dir = tmp_path / "non_empty"
    non_empty_dir.mkdir()
    (non_empty_dir / "file.txt").write_text("hello")
    assert is_dir_empty(non_empty_dir) is False

    assert is_dir_empty(tmp_path / "does_not_exist") is False


def test_is_dir_empty_with_os_junk_files(tmp_path):
    junk_dir = tmp_path / "junk_only"
    junk_dir.mkdir()
    (junk_dir / "Thumbs.db").write_bytes(b"cache")
    (junk_dir / "desktop.ini").write_text("[Shell]")
    (junk_dir / ".DS_Store").write_bytes(b"macos")

    # Com ignore_junk_files=True (default), arquivos de lixo são descartados e a pasta é considerada vazia
    assert is_dir_empty(junk_dir, ignore_junk_files=True) is True
    assert not (junk_dir / "Thumbs.db").exists()
    assert not (junk_dir / "desktop.ini").exists()
    assert not (junk_dir / ".DS_Store").exists()

    # Pasta com junk file E arquivo real
    mixed_dir = tmp_path / "mixed"
    mixed_dir.mkdir()
    (mixed_dir / "Thumbs.db").write_bytes(b"cache")
    real_file = mixed_dir / "photo.jpg"
    real_file.write_bytes(b"image")

    assert is_dir_empty(mixed_dir, ignore_junk_files=True) is False
    assert real_file.exists()


def test_clean_empty_parent_dirs_prunes_to_stop_at_dir(tmp_path):
    dest_root = tmp_path / "IRIS"
    dest_root.mkdir()

    category_dir = dest_root / "1_Entrada"
    proj_dir = category_dir / "proj_test"
    sub_dir = proj_dir / "subfolder"
    sub_dir.mkdir(parents=True)

    # Inicia poda a partir do sub_dir até dest_root
    removed = clean_empty_parent_dirs(sub_dir, stop_at_dir=dest_root)
    assert removed == 3  # subfolder, proj_test, 1_Entrada
    assert not category_dir.exists()
    assert not proj_dir.exists()
    assert not sub_dir.exists()
    assert dest_root.exists()  # Raiz do IRIS estritamente preservada!


def test_clean_empty_parent_dirs_from_file_path(tmp_path):
    dest_root = tmp_path / "IRIS"
    category_dir = dest_root / "6_Produzidos"
    day_dir = category_dir / "2026" / "10" / "22"
    day_dir.mkdir(parents=True)

    video_file = day_dir / "video.mp4"
    # Quando o arquivo é excluído
    removed = clean_empty_parent_dirs(video_file, stop_at_dir=dest_root)
    assert removed == 4  # 22, 10, 2026, 6_Produzidos
    assert not category_dir.exists()
    assert dest_root.exists()


def test_clean_empty_parent_dirs_stops_at_non_empty(tmp_path):
    dest_root = tmp_path / "IRIS"
    category_dir = dest_root / "2_AlbunsDatas"
    day1_dir = category_dir / "2026" / "10" / "20"
    day2_dir = category_dir / "2026" / "10" / "21"
    day1_dir.mkdir(parents=True)
    day2_dir.mkdir(parents=True)

    (day2_dir / "foto_preservada.jpg").write_text("foto")

    # Poda a partir de day1_dir (vazia)
    removed = clean_empty_parent_dirs(day1_dir, stop_at_dir=dest_root)
    assert removed == 1  # Apenas a pasta '20' removida
    assert not day1_dir.exists()
    assert (category_dir / "2026" / "10").exists()
    assert day2_dir.exists()


def test_clean_empty_directories_recursive(tmp_path):
    dest_root = tmp_path / "IRIS"
    (dest_root / "empty_cat1" / "sub1" / "sub2").mkdir(parents=True)
    (dest_root / "empty_cat2").mkdir(parents=True)
    cat_with_file = dest_root / "cat_real" / "data"
    cat_with_file.mkdir(parents=True)
    (cat_with_file / "data.csv").write_text("1,2,3")

    removed = clean_empty_directories(dest_root, preserve_root=True)
    assert removed == 4  # sub2, sub1, empty_cat1, empty_cat2
    assert not (dest_root / "empty_cat1").exists()
    assert not (dest_root / "empty_cat2").exists()
    assert cat_with_file.exists()
    assert dest_root.exists()


def test_organize_stage_prunes_empty_1_entrada(tmp_path, monkeypatch):
    dest_root = tmp_path / "IRIS"
    dest_root.mkdir()
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: str(dest_root) if k in ("general.destination_root", "storage.destination_root") else orig_get(k, d))

    staging_dir = dest_root / "1_Entrada" / "test_proj"
    staging_dir.mkdir(parents=True)
    test_file = staging_dir / "photo.jpg"
    test_file.write_bytes(b"content_123456")

    from src.modules.organize.stage import compute_file_hash
    f_hash = compute_file_hash(test_file)

    project = create_project("test_proj", str(tmp_path / "origem"))
    item = ProjectItem(
        original_path=str(test_file.resolve()),
        staging_path=str(test_file.resolve()),
        relative_dest_dir="2_AlbunsDatas/2026/10/22",
        target_filename="photo_final.jpg",
        category="avulsa",
        status="copied",
        verified=True,
        file_size_bytes=len(b"content_123456"),
        file_hash=f_hash
    )
    project.save_item(item)

    stage = OrganizeStage("organize", "Organização Física")
    success = stage.run(project, interactive=False)
    assert success is True

    # Valida que o arquivo foi movido para o destino final
    final_file = dest_root / "2_AlbunsDatas" / "2026" / "10" / "22" / "photo_final.jpg"
    assert final_file.exists()

    # Valida que 1_Entrada/test_proj E 1_Entrada foram podadas pois ficaram vazias
    assert not (dest_root / "1_Entrada" / "test_proj").exists()
    assert not (dest_root / "1_Entrada").exists()


def test_youtube_cleanup_prunes_empty_produzidos_to_dest_root(tmp_path, monkeypatch):
    dest_root = tmp_path / "IRIS"
    dest_root.mkdir()
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: str(dest_root) if k in ("general.destination_root", "storage.destination_root") else orig_get(k, d))

    prod_dir = dest_root / "6_Produzidos" / "2026" / "10" / "22"
    prod_dir.mkdir(parents=True)
    video_file = prod_dir / "timelapse.mp4"
    video_file.write_bytes(b"mp4_content")

    project = create_project("test_yt_proj", str(tmp_path / "origem"))
    project.save_timelapse({
        "output_video_path": str(video_file.resolve()),
        "status": "uploaded",
        "youtube_video_id": "yt_video_999"
    })

    mock_yt = MagicMock()
    with patch("src.modules.youtube.cleaner.verify_youtube_upload_status", return_value=(True, "Upload verificado")):
        success = execute_post_upload_cleanup(
            project=project,
            video_path=video_file,
            video_id="yt_video_999",
            job_type="timelapse",
            youtube=mock_yt,
            interactive=False
        )
        assert success is True

    # O vídeo local foi deletado
    assert not video_file.exists()

    # 6_Produzidos e as subpastas de data foram podadas até dest_root
    assert not (dest_root / "6_Produzidos").exists()
    assert dest_root.exists()


def test_bird_organize_prunes_empty_source_dirs(tmp_path, monkeypatch):
    dest_root = tmp_path / "IRIS"
    dest_root.mkdir()
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: str(dest_root) if k in ("general.destination_root", "storage.destination_root") else orig_get(k, d))

    # Cria foto em 2_AlbunsDatas
    source_day = dest_root / "2_AlbunsDatas" / "2026" / "10" / "22"
    source_day.mkdir(parents=True)
    photo_file = source_day / "IMG_001.jpg"
    photo_file.write_bytes(b"bird_jpeg")

    project = create_project("test_bird_clean_proj", str(tmp_path / "origem"))
    item = ProjectItem(
        original_path=str(photo_file.resolve()),
        staging_path=str(photo_file.resolve()),
        organized_path=str(photo_file.resolve()),
        category="avulsa",
        status="organized",
        verified=True,
        file_size_bytes=len(b"bird_jpeg")
    )
    project.save_item(item)

    # Identificação com alta certeza
    record = {
        "item_path": str(photo_file.resolve()),
        "confidence": 0.95,
        "needs_review": False,
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_en": "Great Kiskadee"
    }
    project.add_bird_identification(record)

    stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves")
    success = stage.run(project)
    assert success is True

    # Foto foi movida para subpasta da espécie
    assert not photo_file.exists()
    dest_species_dir = dest_root / "2_AlbunsDatas" / "2026" / "10" / "22" / "Bem-te-vi"
    moved_files = list(dest_species_dir.glob("*.jpg"))
    assert len(moved_files) == 1
    assert "Bem-te-vi" in moved_files[0].name

    # A pasta source_day não está vazia porque contém a subpasta 'Bem-te-vi'
    assert source_day.exists()


def test_pipeline_runner_sweep_empty_directories(tmp_path, monkeypatch):
    dest_root = tmp_path / "IRIS"
    (dest_root / "temp_empty" / "nested").mkdir(parents=True)
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: str(dest_root) if k in ("general.destination_root", "storage.destination_root") else orig_get(k, d))

    runner = PipelineRunner()
    runner._sweep_empty_directories()

    assert not (dest_root / "temp_empty").exists()
    assert dest_root.exists()
