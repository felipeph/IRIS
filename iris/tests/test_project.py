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

def test_init_project_db_does_not_drop_table_if_metadata_json_present(mock_projects_dir):
    """Garante que a migração não é destrutiva mesmo se metadata_json existir na tabela."""
    p = create_project("test_no_drop", "X:\\src")
    p.items = [ProjectItem(original_path="/orig/photo1.jpg", staging_path="/dest/photo1.jpg", file_size_bytes=1000)]
    
    # Simula a adição da coluna metadata_json (ou existência prévia da coluna)
    with sqlite3.connect(p._project_db_file) as conn:
        conn.execute("ALTER TABLE items ADD COLUMN metadata_json TEXT DEFAULT '{}'")
        conn.commit()
        
    # Re-executa _init_project_db forçando nova verificação
    p._init_project_db(force=True)
    
    # Verifica que a tabela items NÃO foi deletada e os registros permanecem íntegros
    items = p.items
    assert len(items) == 1
    assert items[0].original_path == "/orig/photo1.jpg"
    assert items[0].file_size_bytes == 1000

def test_user_version_and_indexes_created(mock_projects_dir):
    """Verifica que PRAGMA user_version é gravado e os índices são criados."""
    p = create_project("test_versioning", "X:\\src")
    
    with sqlite3.connect(p._project_db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        ver = cursor.fetchone()[0]
        assert ver == 1
        
        # Verifica criação dos índices
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='items'")
        indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_items_status" in indexes
        assert "idx_items_category" in indexes
        assert "idx_items_status_verified" in indexes
        
    with sqlite3.connect(mock_projects_dir / "iris_central.db") as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        ver = cursor.fetchone()[0]
        assert ver == 1

def test_db_initialized_caching(mock_projects_dir):
    """Testa se o cache de inicialização em memória evita re-execuções redundantes."""
    p = create_project("test_caching", "X:\\src")
    assert p._db_initialized is True
    
    # Chamar novamente _init_project_db não deve quebrar nem recalcular schema
    p._init_project_db()
    assert p._db_initialized is True

def test_has_items_and_get_items_count_empty_project(mock_projects_dir):
    """Testa has_items e get_items_count com projeto inexistente e sem itens."""
    p_non_existent = Project("empty_non_existent")
    assert p_non_existent.has_items() is False
    assert p_non_existent.get_items_count() == 0
    assert p_non_existent.get_items() == []

    p_created = create_project("empty_created", "X:\\src")
    assert p_created.has_items() is False
    assert p_created.get_items_count() == 0
    assert p_created.get_items() == []

def test_has_items_and_get_items_count_with_filters(mock_projects_dir):
    """Testa has_items e get_items_count com filtros específicos de status, category e verified."""
    p = create_project("test_filters", "X:\\src")
    items = [
        ProjectItem(original_path="/p1.jpg", staging_path="/dest/p1.jpg", status="copied", category="timelapse", verified=True),
        ProjectItem(original_path="/p2.jpg", staging_path="/dest/p2.jpg", status="copied", category="timelapse", verified=False),
        ProjectItem(original_path="/p3.jpg", staging_path="/dest/p3.jpg", status="organized", category="timelapse", verified=True),
        ProjectItem(original_path="/v1.mp4", staging_path="/dest/v1.mp4", status="copied", category="video", verified=True),
        ProjectItem(original_path="/f1.jpg", staging_path="/dest/f1.jpg", status="copied", category="foto_unica", verified=True),
    ]
    p.save_items_batch(items)

    # Contagens gerais e existência
    assert p.has_items() is True
    assert p.get_items_count() == 5

    # Filtros por status
    assert p.has_items(status="copied") is True
    assert p.get_items_count(status="copied") == 4
    assert p.has_items(status="organized") is True
    assert p.get_items_count(status="organized") == 1
    assert p.has_items(status="non_existent") is False
    assert p.get_items_count(status="non_existent") == 0

    # Filtros por category
    assert p.has_items(category="timelapse") is True
    assert p.get_items_count(category="timelapse") == 3
    assert p.has_items(category="video") is True
    assert p.get_items_count(category="video") == 1
    assert p.has_items(category="astro_lua") is False
    assert p.get_items_count(category="astro_lua") == 0

    # Filtros por verified
    assert p.get_items_count(verified=True) == 4
    assert p.get_items_count(verified=False) == 1

    # Filtros combinados
    assert p.has_items(status="copied", verified=True) is True
    assert p.get_items_count(status="copied", verified=True) == 3
    assert p.get_items_count(status="copied", category="timelapse", verified=True) == 1
    assert p.get_items_count(status="organized", category="video") == 0

def test_get_items_filtered_and_by_category(mock_projects_dir):
    """Testa get_items com parâmetros de filtragem e get_items_by_category."""
    p = create_project("test_get_filtered", "X:\\src")
    items = [
        ProjectItem(original_path="/t1.jpg", staging_path="/dest/t1.jpg", status="copied", category="timelapse", verified=True),
        ProjectItem(original_path="/t2.jpg", staging_path="/dest/t2.jpg", status="copied", category="timelapse", verified=False),
        ProjectItem(original_path="/v1.mp4", staging_path="/dest/v1.mp4", status="copied", category="video", verified=True),
    ]
    p.save_items_batch(items)

    # get_items sem filtros retorna todos
    assert len(p.get_items()) == 3

    # get_items filtrado por categoria
    tl_items = p.get_items(category="timelapse")
    assert len(tl_items) == 2
    assert {it.original_path for it in tl_items} == {"/t1.jpg", "/t2.jpg"}

    # get_items_by_category
    v_items = p.get_items_by_category("video")
    assert len(v_items) == 1
    assert v_items[0].original_path == "/v1.mp4"

    # get_items filtrado por status e verified
    verified_copied = p.get_items(status="copied", verified=True)
    assert len(verified_copied) == 2
    assert {it.original_path for it in verified_copied} == {"/t1.jpg", "/v1.mp4"}


def test_atomic_dual_write_and_reconciliation(mock_projects_dir):
    """Testa se a gravação dupla é consistente e se a reconciliação recupera registros faltantes (RFC 08)."""
    from src.core.project import (
        list_central_timelapses,
        list_central_edited_videos,
        reconcile_project_with_central,
        reconcile_all_projects_with_central,
    )
    
    p = create_project("test_dual_write", "X:\\src")
    
    # Salvar timelapse via Project grava no local e no central
    tl_record = {
        "sequence_dir": "2026-10-19_TL",
        "photo_count": 120,
        "fps": 24,
        "output_video_path": "/exports/tl1.mp4",
        "metadata_json": {"test": 123}
    }
    p.save_timelapse(tl_record)
    
    # Verifica que está no banco local
    local_tls = p.get_timelapses()
    assert len(local_tls) == 1
    assert local_tls[0]["output_video_path"] == "/exports/tl1.mp4"
    
    # Verifica que está no banco central
    central_tls = list_central_timelapses("test_dual_write")
    assert len(central_tls) == 1
    assert central_tls[0]["output_video_path"] == "/exports/tl1.mp4"
    
    # Atualiza YouTube
    p.update_timelapse_youtube("/exports/tl1.mp4", "yt_123", "https://youtu.be/yt_123")
    assert p.get_timelapses()[0]["youtube_video_id"] == "yt_123"
    assert list_central_timelapses("test_dual_write")[0]["youtube_video_id"] == "yt_123"
    
    # Simula um registro criado apenas no banco local (desincronizado manualmente)
    with sqlite3.connect(p._project_db_file) as conn:
        conn.execute("""
            INSERT INTO timelapses (project_name, sequence_dir, photo_count, fps, output_video_path)
            VALUES (?, ?, ?, ?, ?)
        """, ("test_dual_write", "sess2", 200, 30, "/exports/tl2_orphan.mp4"))
        conn.commit()
        
    # No central, deve continuar tendo apenas 1
    assert len(list_central_timelapses("test_dual_write")) == 1
    
    # Executa a reconciliação
    stats = reconcile_project_with_central("test_dual_write")
    assert stats["timelapses"] >= 1
    
    # Agora o central deve ter 2 timelapses
    updated_central_tls = list_central_timelapses("test_dual_write")
    assert len(updated_central_tls) == 2
    paths = {t["output_video_path"] for t in updated_central_tls}
    assert "/exports/tl2_orphan.mp4" in paths
    
    # Testa reconcile_all_projects_with_central
    all_stats = reconcile_all_projects_with_central()
    assert "test_dual_write" in all_stats



