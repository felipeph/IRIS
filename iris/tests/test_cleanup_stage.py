import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.project import Project, ProjectItem
from src.modules.cleanup.stage import CleanupStage, is_removable_media
from src.modules.ingestion.strategies.base import compute_file_hash

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
    hash1 = compute_file_hash(dest_file1)
    
    # Arquivo 2
    src_file2 = source_dir / "subfolder" / "IMG_002.JPG"
    src_file2.parent.mkdir()
    src_file2.write_bytes(b"anothercontent")
    dest_file2 = staging_dir / "subfolder" / "IMG_002.JPG"
    dest_file2.parent.mkdir()
    dest_file2.write_bytes(b"anothercontent")
    hash2 = compute_file_hash(dest_file2)
    
    project = Project("test_cleanup_proj", str(source_dir))
    
    item1 = ProjectItem(
        original_path=str(src_file1),
        staging_path=str(dest_file1),
        status="copied",
        file_size_bytes=len(b"content12345"),
        file_hash=hash1,
        verified=True
    )
    item2 = ProjectItem(
        original_path=str(src_file2),
        staging_path=str(dest_file2),
        status="copied",
        file_size_bytes=len(b"anothercontent"),
        file_hash=hash2,
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
    """Garante que com auto_clean=True em mídia normal o Confirm.ask não é chamado e send2trash é executado."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=False), \
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
         patch("src.modules.cleanup.stage.is_removable_media", return_value=False), \
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
         patch("src.modules.cleanup.stage.is_removable_media", return_value=False), \
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
         patch("src.modules.cleanup.stage.is_removable_media", return_value=False), \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        # Nenhum arquivo deve ter sido enviado para a lixeira por falha no double-check
        mock_trash.assert_not_called()

def test_cleanup_stage_hash_guard_protects_divergent_hash(cleanup_env):
    """Garante que se o arquivo de destino no SSD tiver o mesmo tamanho mas hash divergente (corrupção), a origem é preservada."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    # Altera o conteúdo mantendo exatamente o mesmo tamanho (12 bytes)
    cleanup_env["dest_file1"].write_bytes(b"corrupted123")
    assert len(b"corrupted123") == len(b"content12345")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=False), \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        # Apenas dest_file2 deve ser deletado; dest_file1 deve ser preservado pelo hash guard
        assert mock_trash.call_count == 1
        mock_trash.assert_called_once_with(str(cleanup_env["src_file2"]))

def test_cleanup_stage_when_files_already_moved(cleanup_env):
    """Garante que quando os arquivos já foram movidos na ingestão, a etapa cleanup conclui com sucesso sem erros."""
    project = cleanup_env["project"]
    stage = CleanupStage("cleanup", "Limpeza da Origem")

    cleanup_env["src_file1"].unlink()
    cleanup_env["src_file2"].unlink()

    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:

        success = stage.run(project, auto_clean=True)
        assert success is True
        mock_trash.assert_not_called()

def test_cleanup_stage_removable_drive_interactive_refusal(cleanup_env):
    """Garante que em mídia removível interativa, se o usuário recusar a exclusão permanente, nada é apagado."""
    project = cleanup_env["project"]
    project.auto_cleanup = False
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=True), \
         patch("src.modules.cleanup.stage.Confirm.ask", return_value=False) as mock_confirm, \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=False)
        assert success is True
        mock_confirm.assert_called_once()
        mock_trash.assert_not_called()
        assert cleanup_env["src_file1"].exists()
        assert cleanup_env["src_file2"].exists()

def test_cleanup_stage_removable_drive_interactive_approval_unlinks(cleanup_env):
    """Garante que em mídia removível interativa, se o usuário confirmar, unlink é feito com hash guard após send2trash falhar."""
    project = cleanup_env["project"]
    project.auto_cleanup = False
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=True), \
         patch("src.modules.cleanup.stage.Confirm.ask", return_value=True) as mock_confirm, \
         patch("src.modules.cleanup.stage.send2trash", side_effect=OSError("Recycle bin not supported")):
        
        success = stage.run(project, auto_clean=False)
        assert success is True
        mock_confirm.assert_called_once()
        assert not cleanup_env["src_file1"].exists()
        assert not cleanup_env["src_file2"].exists()

def test_cleanup_stage_removable_drive_auto_clean_skips_when_flag_false(cleanup_env):
    """Garante que no modo automático em mídia removível com allow_permanent_sd_clean=False, a limpeza é pulada (Zero Data Loss)."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=True), \
         patch("src.modules.cleanup.stage.config.get", return_value=False), \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        mock_trash.assert_not_called()
        assert cleanup_env["src_file1"].exists()
        assert cleanup_env["src_file2"].exists()

def test_cleanup_stage_removable_drive_auto_clean_deletes_when_flag_true(cleanup_env):
    """Garante que no modo automático em mídia removível com allow_permanent_sd_clean=True, os arquivos são excluídos com segurança."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=True), \
         patch("src.modules.cleanup.stage.config.get", return_value=True), \
         patch("src.modules.cleanup.stage.send2trash", side_effect=OSError("Drive sem lixeira")):
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        assert not cleanup_env["src_file1"].exists()
        assert not cleanup_env["src_file2"].exists()

def test_cleanup_stage_trash_failure_falls_back_safely_when_not_allowed(cleanup_env):
    """Garante que se send2trash falhar e allow_permanent for False, unlink NÃO é chamado e arquivos são preservados."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    with patch.object(project, "get_items", return_value=cleanup_env["items"]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=False), \
         patch("src.modules.cleanup.stage.config.get", return_value=False), \
         patch("src.modules.cleanup.stage.send2trash", side_effect=PermissionError("Acesso negado à lixeira")):
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        # Como allow_permanent=False, os arquivos devem continuar existindo no SD
        assert cleanup_env["src_file1"].exists()
        assert cleanup_env["src_file2"].exists()

def test_cleanup_stage_supports_organized_path(cleanup_env):
    """Garante que se o arquivo já foi movido para organized_path pós-organize, o cleanup localiza e valida o hash no novo caminho."""
    project = cleanup_env["project"]
    project.auto_cleanup = True
    stage = CleanupStage("cleanup", "Limpeza da Origem")
    
    # Simula que o arquivo 1 foi movido do staging para organized_path
    organized_dir = cleanup_env["staging_dir"].parent / "organized"
    organized_dir.mkdir(parents=True)
    org_file1 = organized_dir / "IMG_001.JPG"
    cleanup_env["dest_file1"].rename(org_file1)
    
    item1 = cleanup_env["items"][0]
    item1.staging_path = str(cleanup_env["dest_file1"])  # não existe mais
    item1.organized_path = str(org_file1)                 # novo caminho existente
    
    with patch.object(project, "get_items", return_value=[item1]), \
         patch("src.modules.cleanup.stage.is_removable_media", return_value=False), \
         patch("src.modules.cleanup.stage.send2trash") as mock_trash:
        
        success = stage.run(project, auto_clean=True)
        assert success is True
        mock_trash.assert_called_once_with(str(cleanup_env["src_file1"]))

def test_is_removable_media_detection(tmp_path):
    """Testa a função auxiliar is_removable_media."""
    # Em sistema não-nt ou caminho inválido
    with patch("os.name", "posix"):
        assert is_removable_media(tmp_path) is False
        
    with patch("os.name", "nt"), \
         patch("ctypes.windll.kernel32.GetDriveTypeW", return_value=2):
        assert is_removable_media(Path("E:/DCIM/100CANON")) is True
        
    with patch("os.name", "nt"), \
         patch("ctypes.windll.kernel32.GetDriveTypeW", return_value=3):
        assert is_removable_media(Path("C:/IRIS")) is False
