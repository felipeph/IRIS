import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import xxhash
from src.core.project import Project, ProjectItem, init_central_db
from src.modules.organize.stage import OrganizeStage, compute_file_hash, clean_empty_directories

@pytest.fixture
def organize_env(tmp_path):
    """Cria um ambiente temporário com staging e dest_root."""
    dest_root = tmp_path / "IRIS"
    dest_root.mkdir()
    
    with patch("src.core.project.PROJECTS_DIR", tmp_path), \
         patch("src.core.project.CENTRAL_DB_PATH", tmp_path / "iris_central.db"):
        init_central_db()
        yield dest_root

def test_organize_empty_project(organize_env):
    dest_root = organize_env
    project = Project("empty_proj")
    project._init_project_db()
    
    with patch("src.modules.organize.stage.config") as mock_config:
        mock_config.get.return_value = str(dest_root)
        stage = OrganizeStage("organize", "Organização")
        assert stage.run(project, interactive=False) is True

def test_organize_successful_move(organize_env):
    dest_root = organize_env
    project = Project("proj_move")
    project._init_project_db()

    # Criar arquivos no staging
    staging_dir = dest_root / "1_Entrada" / "proj_move" / "raw"
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    f1 = staging_dir / "IMG_001.JPG"
    f1.write_bytes(b"photo content 12345")
    hash1 = compute_file_hash(f1)
    
    f2 = staging_dir / "VID_002.MP4"
    f2.write_bytes(b"video content 67890")
    hash2 = compute_file_hash(f2)

    item1 = ProjectItem(
        original_path="G:/DCIM/IMG_001.JPG",
        staging_path=str(f1),
        status="copied",
        verified=True,
        file_size_bytes=len(b"photo content 12345"),
        file_hash=hash1,
        category="avulsa",
        relative_dest_dir="2_AlbunsDatas/2026/09/20",
        target_filename="2026-09-20_photo1.jpg"
    )
    item2 = ProjectItem(
        original_path="G:/DCIM/VID_002.MP4",
        staging_path=str(f2),
        status="copied",
        verified=True,
        file_size_bytes=len(b"video content 67890"),
        file_hash=hash2,
        category="video",
        relative_dest_dir="3_Videos/2026/09/20",
        target_filename="2026-09-20_video1.mp4"
    )
    project.save_item(item1)
    project.save_item(item2)

    with patch("src.modules.organize.stage.config") as mock_config:
        mock_config.get.return_value = str(dest_root)
        stage = OrganizeStage("organize", "Organização")
        success = stage.run(project, interactive=False)
        assert success is True

    # 1. Arquivos movidos para o destino correto
    final_p1 = dest_root / "2_AlbunsDatas" / "2026" / "09" / "20" / "2026-09-20_photo1.jpg"
    final_p2 = dest_root / "3_Videos" / "2026" / "09" / "20" / "2026-09-20_video1.mp4"
    assert final_p1.exists()
    assert final_p1.read_bytes() == b"photo content 12345"
    assert final_p2.exists()
    assert final_p2.read_bytes() == b"video content 67890"

    # 2. Arquivos de staging não existem mais
    assert not f1.exists()
    assert not f2.exists()

    # 3. Diretórios de staging vazios foram removidos
    proj_staging_root = dest_root / "1_Entrada" / "proj_move"
    assert not proj_staging_root.exists()

    # 4. Status atualizado no banco
    updated_items = {it.original_path: it for it in project.items}
    assert updated_items["G:/DCIM/IMG_001.JPG"].status == "organized"
    assert updated_items["G:/DCIM/IMG_001.JPG"].organized_path == str(final_p1.resolve())
    assert updated_items["G:/DCIM/VID_002.MP4"].status == "organized"
    assert updated_items["G:/DCIM/VID_002.MP4"].organized_path == str(final_p2.resolve())

def test_organize_collision_same_hash(organize_env):
    dest_root = organize_env
    project = Project("proj_col_same")
    project._init_project_db()

    staging_dir = dest_root / "1_Entrada" / "proj_col_same" / "raw"
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    f1 = staging_dir / "IMG_001.JPG"
    f1.write_bytes(b"identical photo content")
    h1 = compute_file_hash(f1)

    # Pre-criar arquivo idêntico no destino
    dest_dir = dest_root / "2_AlbunsDatas" / "2026" / "09" / "20"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing_dest = dest_dir / "2026-09-20_photo1.jpg"
    existing_dest.write_bytes(b"identical photo content")

    item = ProjectItem(
        original_path="G:/DCIM/IMG_001.JPG",
        staging_path=str(f1),
        status="copied",
        verified=True,
        file_size_bytes=len(b"identical photo content"),
        file_hash=h1,
        category="avulsa",
        relative_dest_dir="2_AlbunsDatas/2026/09/20",
        target_filename="2026-09-20_photo1.jpg"
    )
    project.save_item(item)

    with patch("src.modules.organize.stage.config") as mock_config:
        mock_config.get.return_value = str(dest_root)
        stage = OrganizeStage("organize", "Organização")
        success = stage.run(project, interactive=False)
        assert success is True

    # Não deve ter criado photo1_1.jpg
    assert not (dest_dir / "2026-09-20_photo1_1.jpg").exists()
    assert existing_dest.exists()
    assert not f1.exists()

    it = project.get_item("G:/DCIM/IMG_001.JPG")
    assert it.status == "organized"
    assert it.organized_path == str(existing_dest.resolve())

def test_organize_collision_different_hash(organize_env):
    dest_root = organize_env
    project = Project("proj_col_diff")
    project._init_project_db()

    staging_dir = dest_root / "1_Entrada" / "proj_col_diff" / "raw"
    staging_dir.mkdir(parents=True, exist_ok=True)
    
    f1 = staging_dir / "IMG_001.JPG"
    f1.write_bytes(b"new different content")
    h1 = compute_file_hash(f1)

    # Pre-criar arquivo diferente no destino
    dest_dir = dest_root / "2_AlbunsDatas" / "2026" / "09" / "20"
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing_dest = dest_dir / "2026-09-20_photo1.jpg"
    existing_dest.write_bytes(b"old content")

    item = ProjectItem(
        original_path="G:/DCIM/IMG_001.JPG",
        staging_path=str(f1),
        status="copied",
        verified=True,
        file_size_bytes=len(b"new different content"),
        file_hash=h1,
        category="avulsa",
        relative_dest_dir="2_AlbunsDatas/2026/09/20",
        target_filename="2026-09-20_photo1.jpg"
    )
    project.save_item(item)

    with patch("src.modules.organize.stage.config") as mock_config:
        mock_config.get.return_value = str(dest_root)
        stage = OrganizeStage("organize", "Organização")
        success = stage.run(project, interactive=False)
        assert success is True

    # Deve ter criado sufixo _1
    suffixed_dest = dest_dir / "2026-09-20_photo1_1.jpg"
    assert existing_dest.read_bytes() == b"old content"
    assert suffixed_dest.exists()
    assert suffixed_dest.read_bytes() == b"new different content"
    assert not f1.exists()

    it = project.get_item("G:/DCIM/IMG_001.JPG")
    assert it.status == "organized"
    assert it.organized_path == str(suffixed_dest.resolve())

def test_organize_auto_recovery(organize_env):
    """Verifica que se o arquivo não estiver no staging mas já existir no destino com mesmo hash, auto-recupera."""
    dest_root = organize_env
    project = Project("proj_recover")
    project._init_project_db()

    dest_dir = dest_root / "3_Videos" / "2026" / "09" / "20"
    dest_dir.mkdir(parents=True, exist_ok=True)
    final_video = dest_dir / "2026-09-20_video1.mp4"
    final_video.write_bytes(b"recovered video bytes")
    h = compute_file_hash(final_video)

    # Staging path que NÃO existe
    non_existent_staging = dest_root / "1_Entrada" / "proj_recover" / "raw" / "non_existent.mp4"

    item = ProjectItem(
        original_path="G:/DCIM/VID_RECOVER.MP4",
        staging_path=str(non_existent_staging),
        status="copied",
        verified=True,
        file_size_bytes=len(b"recovered video bytes"),
        file_hash=h,
        category="video",
        relative_dest_dir="3_Videos/2026/09/20",
        target_filename="2026-09-20_video1.mp4"
    )
    project.save_item(item)

    with patch("src.modules.organize.stage.config") as mock_config:
        mock_config.get.return_value = str(dest_root)
        stage = OrganizeStage("organize", "Organização")
        success = stage.run(project, interactive=False)
        assert success is True

    it = project.get_item("G:/DCIM/VID_RECOVER.MP4")
    assert it.status == "organized"
    assert it.organized_path == str(final_video.resolve())

def test_organize_extra_dest_dirs(organize_env):
    dest_root = organize_env
    project = Project("proj_extra")
    project._init_project_db()

    staging_dir = dest_root / "1_Entrada" / "proj_extra" / "raw"
    staging_dir.mkdir(parents=True, exist_ok=True)
    f1 = staging_dir / "VID_EXTRA.MP4"
    f1.write_bytes(b"extra dir test video")
    h = compute_file_hash(f1)

    item = ProjectItem(
        original_path="G:/DCIM/VID_EXTRA.MP4",
        staging_path=str(f1),
        status="copied",
        verified=True,
        file_size_bytes=len(b"extra dir test video"),
        file_hash=h,
        category="video",
        relative_dest_dir="3_Videos/2026/09/20",
        target_filename="2026-09-20_extra.mp4",
        extra_dest_dirs_json=json.dumps(["ExtraFolder/BackupVideos"])
    )
    project.save_item(item)

    with patch("src.modules.organize.stage.config") as mock_config:
        mock_config.get.return_value = str(dest_root)
        stage = OrganizeStage("organize", "Organização")
        success = stage.run(project, interactive=False)
        assert success is True

    final_p = dest_root / "3_Videos" / "2026" / "09" / "20" / "2026-09-20_extra.mp4"
    extra_p = dest_root / "ExtraFolder" / "BackupVideos" / "2026-09-20_extra.mp4"

    assert final_p.exists()
    assert extra_p.exists()
    assert extra_p.read_bytes() == b"extra dir test video"

    it = project.get_item("G:/DCIM/VID_EXTRA.MP4")
    assert it.status == "organized"
    extras = json.loads(it.extra_organized_paths_json)
    assert len(extras) == 1
    assert extras[0] == str(extra_p.resolve())

def test_organize_interactive_cancellation(organize_env):
    dest_root = organize_env
    project = Project("proj_cancel")
    project._init_project_db()

    staging_dir = dest_root / "1_Entrada" / "proj_cancel" / "raw"
    staging_dir.mkdir(parents=True, exist_ok=True)
    f1 = staging_dir / "IMG.JPG"
    f1.write_bytes(b"test")
    h = compute_file_hash(f1)

    item = ProjectItem(
        original_path="G:/DCIM/IMG.JPG",
        staging_path=str(f1),
        status="copied",
        verified=True,
        file_size_bytes=4,
        file_hash=h,
        category="avulsa",
        relative_dest_dir="2_AlbunsDatas/2026/09/20",
        target_filename="img.jpg"
    )
    project.save_item(item)

    with patch("src.modules.organize.stage.config") as mock_config, \
         patch("rich.prompt.Confirm.ask", return_value=False):
        mock_config.get.return_value = str(dest_root)
        stage = OrganizeStage("organize", "Organização")
        success = stage.run(project, interactive=True)
        assert success is False

    # Arquivo não deve ter sido movido
    assert f1.exists()
    it = project.get_item("G:/DCIM/IMG.JPG")
    assert it.status == "copied"
