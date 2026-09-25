import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.project import Project, ProjectItem
from src.modules.cleanup.stage import CleanupStage

@pytest.fixture
def cleanup_env(tmp_path):
    source_dir = tmp_path / "source_sd"
    source_dir.mkdir(parents=True)
    staging_dir = tmp_path / "staging_ssd"
    staging_dir.mkdir(parents=True)
    
    # Arquivo 1
    src_file1 = source_dir / "IMG_001.JPG"
    src_file1.write_bytes(b"content12345")
    dest_file1 = staging_dir / "IMG_001.JPG"
    dest_file1.write_bytes(b"content12345")
    
    # Arquivo 2
    src_file2 = source_dir / "subfolder" / "IMG_002.JPG"
    src_file2.parent.mkdir()
    src_file2.write_bytes(b"anothercontent")
    dest_file2 = staging_dir / "subfolder" / "IMG_002.JPG"
    dest_file2.parent.mkdir()
    dest_file2.write_bytes(b"anothercontent")
    
    project = Project("test_cleanup_proj", str(source_dir))
    
    item1 = ProjectItem(
        original_path=str(src_file1),
        staging_path=str(dest_file1),
        status="copied",
        file_size_bytes=len(b"content12345"),
        file_hash="hash1",
        verified=True
    )
    item2 = ProjectItem(
        original_path=str(src_file2),
        staging_path=str(dest_file2),
        status="copied",
        file_size_bytes=len(b"anothercontent"),
        file_hash="hash2",
        verified=True
    )
    
    return {
        "source_dir": source_dir,
        "staging_dir": staging_dir,
        "src_file1": src_file1,
        "src_file2": src_file2,
        "dest_file1": dest_file1,
        "dest_file2": dest_file2,
        "project": project,
        "items": [item1, item2]
    }

def test_cleanup_stage_auto_clean_skips_confirmation_and_uses_trash(cleanup_env):
    """Garante que com auto_clean=True o Confirm.ask não é chamado e send2trash é executado."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.Confirm.ask") as mock_confirm, \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        mock_confirm.assert_not_called()
        assert mock_trash.call_count == 2
        mock_trash.assert_any_call(str(cleanup_env["src_file1"]))
        mock_trash.assert_any_call(str(cleanup_env["src_file2"]))

def test_cleanup_stage_manual_requires_confirmation_and_cancels_if_no(cleanup_env):
    """Garante que quando auto_clean=False a confirmação é solicitada e cancela se usuário disser não."""
    project = cleanup_env["project"]
    project.auto_cleanup = False
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.Confirm.ask", return_value=False) as mock_confirm, \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=False)
        assert success is True
        mock_confirm.assert_called_once()
        mock_trash.assert_not_called()

def test_cleanup_stage_manual_deletes_when_confirmed(cleanup_env):
    """Garante que quando auto_clean=False a confirmação é solicitada e executa se confirmada."""
    project = cleanup_env["project"]
    project.auto_cleanup = False
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.Confirm.ask", return_value=True) as mock_confirm, \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=False)
        assert success is True
        mock_confirm.assert_called_once()
        assert mock_trash.call_count == 2

def test_cleanup_stage_double_check_protects_unmatched_files(cleanup_env):
    """Garante que se o arquivo de destino não existir ou tiver tamanho diferente, a origem NÃO é apagada."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    # Destroi o destino do arquivo 1
    cleanup_env["dest_file1"].unlink()
    # Altera o tamanho do destino do arquivo 2
    cleanup_env["dest_file2"].write_bytes(b"mismatched_size")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        # Nenhum arquivo deve ter sido enviado para a lixeira por falha no double-check
        mock_trash.assert_not_called()
