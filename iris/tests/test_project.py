import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from src.core.project import Project, ProjectItem, get_project, create_project, init_central_db

@pytest.fixture
def mock_projects_dir(tmp_path):
    # Patch the config.PROJECTS_DIR and core.project.PROJECTS_DIR constants
    with patch("src.core.project.PROJECTS_DIR", tmp_path), \
         patch("src.core.project.CENTRAL_DB_PATH", tmp_path / "iris_central.db"):
        init_central_db()
        yield tmp_path

def test_project_item_creation():
    """Testa se o modelo de dados de item funciona."""
    item = ProjectItem(original_path="/orig/a.jpg", staging_path="/dest/a.jpg", file_size_bytes=100)
    assert item.status == "pending"
    assert item.file_size_bytes == 100
    assert item.verified is False
    
    d = {"original_path": "/x", "staging_path": "/y", "status": "copied", "file_size_bytes": 50, "file_hash": "abc", "verified": True}
    item2 = ProjectItem.from_dict(d)
    assert item2.status == "copied"
    assert item2.verified is True
    assert item2.file_hash == "abc"

def test_project_save_and_load(mock_projects_dir):
    """Garante que salvar e carregar banco SQLite não perde dados."""
    p = create_project("test_save_load", "X:\\src")
    p.current_stage_id = "stage1"
    p.save_metadata()
    
    p.items = [ProjectItem("/orig", "/dest", file_hash="hash_123", verified=True)]
    
    assert (mock_projects_dir / "iris_central.db").exists()
    assert (mock_projects_dir / "test_save_load.db").exists()
    
    p2 = get_project("test_save_load")
    assert p2 is not None
    assert p2.source_path == "X:\\src"
    assert p2.current_stage_id == "stage1"
    
    items = p2.items
    assert len(items) == 1
    assert items[0].original_path == "/orig"
    assert items[0].file_hash == "hash_123"
    assert items[0].verified is True

def test_project_not_found(mock_projects_dir):
    p = Project("non_existent")
    assert p.load_metadata() is False
    assert get_project("non_existent") is None

def test_create_project(mock_projects_dir):
    p = create_project("new_proj", "Y:\\source")
    assert p.name == "new_proj"
    assert (mock_projects_dir / "iris_central.db").exists()
    assert (mock_projects_dir / "new_proj.db").exists()

def test_project_auto_cleanup_persistence(mock_projects_dir):
    """Testa persistência e recarregamento da flag auto_cleanup."""
    p = create_project("proj_cleanup_test", "Z:\\source", auto_cleanup=True)
    assert p.auto_cleanup is True
    
    p_loaded = get_project("proj_cleanup_test")
    assert p_loaded is not None
    assert p_loaded.auto_cleanup is True
    
    # Alterna para False e salva
    p_loaded.auto_cleanup = False
    p_loaded.save_metadata()
    
    p_reloaded = get_project("proj_cleanup_test")
    assert p_reloaded is not None
    assert p_reloaded.auto_cleanup is False

def test_create_project_inherits_global_config(mock_projects_dir):
    """Testa se novo projeto herda a configuração global."""
    from src.core.config import config
    
    with patch.object(config, "get", return_value=True):
        p1 = create_project("proj_inherited_true", "Z:\\source")
        assert p1.auto_cleanup is True
        
    with patch.object(config, "get", return_value=False):
        p2 = create_project("proj_inherited_false", "Z:\\source")
        assert p2.auto_cleanup is False

