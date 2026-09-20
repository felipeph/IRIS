import pytest
import os
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.project import Project, ProjectItem, init_central_db
from src.modules.ingestion.stage import IngestionStage

@pytest.fixture
def ingestion_env(tmp_path):
    """Cria um ambiente de arquivos temporários para teste de cópia."""
    src_dir = tmp_path / "DCIM"
    dest_root = tmp_path / "IRIS"
    src_dir.mkdir()
    dest_root.mkdir()
    
    # Criar alguns arquivos dummy
    (src_dir / "foto1.jpg").write_text("dummy image content")
    (src_dir / "video1.mp4").write_text("dummy video content")
    (src_dir / "not_media.txt").write_text("text") # Não deve ser copiado
    
    # Setup DB paths for tests
    with patch("src.core.project.PROJECTS_DIR", tmp_path), \
         patch("src.core.project.CENTRAL_DB_PATH", tmp_path / "iris_central.db"):
        init_central_db()
        yield src_dir, dest_root

@patch("src.modules.ingestion.stage.config")
def test_ingestion_basic_copy(mock_config, ingestion_env):
    """Garante que apenas mídias são copiadas e o projeto é atualizado com hash."""
    src_dir, dest_root = ingestion_env
    mock_config.get.return_value = str(dest_root)
    
    project = Project("test_ingest", str(src_dir))
    project._init_project_db()
    
    with patch("src.core.project.Project.save_item") as mock_save_item:
        stage = IngestionStage("ingest", "Ingestão")
        success = stage.run(project)
        
        assert success is True
        
        # Verifica se foram copiados para o lugar certo
        dest_dir = dest_root / "1_Entrada" / "test_ingest" / "raw"
        assert (dest_dir / "foto1.jpg").exists()
        assert (dest_dir / "video1.mp4").exists()
        assert not (dest_dir / "not_media.txt").exists()
        
        # O save_item deve ter sido chamado para cada arquivo com verified=True
        assert mock_save_item.call_count == 2
        item_saved = mock_save_item.call_args[0][0]
        assert item_saved.status == "copied"
        assert item_saved.verified is True
        assert item_saved.file_hash != ""

@patch("src.modules.ingestion.stage.config")
def test_ingestion_resume(mock_config, ingestion_env):
    """Testa a retomada (pulando arquivos já copiados e verificados)."""
    src_dir, dest_root = ingestion_env
    mock_config.get.return_value = str(dest_root)
    
    dest_dir = dest_root / "1_Entrada" / "test_resume" / "raw"
    dest_dir.mkdir(parents=True)
    
    # Simula que foto1.jpg já foi copiado antes e verificado
    foto1_src = src_dir / "foto1.jpg"
    foto1_dest = dest_dir / "foto1.jpg"
    foto1_dest.write_text("dummy image content")
    
    project = Project("test_resume", str(src_dir))
    project._init_project_db()
    item = ProjectItem(
        original_path=str(foto1_src.resolve()), 
        staging_path=str(foto1_dest.resolve()), 
        status="copied", 
        file_size_bytes=foto1_src.stat().st_size,
        file_hash="fakehash",
        verified=True
    )
    project.save_item(item)
    
    with patch("src.modules.ingestion.stage.copy_and_verify") as mock_copy:
        # Mock para o arquivo que faltou (video1.mp4)
        mock_copy.return_value = (True, "fakehash2")
        
        stage = IngestionStage("ingest", "Ingestão")
        stage.run(project)
        
        # O copy_and_verify só deve ser chamado para o video1.mp4
        assert mock_copy.call_count == 1
        args, kwargs = mock_copy.call_args
        assert "video1.mp4" in str(args[0])

@patch("src.modules.ingestion.stage.config")
def test_ingestion_invalid_source(mock_config):
    """Garante falha graciosa se a origem não existir."""
    project = Project("test", "X:\\non_existent_dir")
    stage = IngestionStage("ingest", "Ingestão")
    assert stage.run(project) is False
