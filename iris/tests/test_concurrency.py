import os
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.core.config import PROJECTS_DIR, config
from src.core.lock import ProjectLock, ProjectLockedError, is_pid_alive
from src.core.project import (
    create_project,
    get_project,
    get_last_active_project,
    get_db_connection,
    CENTRAL_DB_PATH
)
from src.modules.youtube.uploader import save_token_atomic

def test_is_pid_alive_current_process():
    assert is_pid_alive(os.getpid()) is True
    assert is_pid_alive(0) is False
    assert is_pid_alive(-1) is False
    # PID muito alto que certamente não existe
    assert is_pid_alive(9999999) is False

def test_project_lock_acquire_and_release(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    proj_name = "test_project_lock"
    
    lock = ProjectLock(proj_name)
    assert lock.acquire() is True
    
    lock_file = tmp_path / f"{proj_name}.lock"
    assert lock_file.exists()
    
    with open(lock_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["project_name"] == proj_name
        assert data["pid"] == os.getpid()
        
    lock.release()
    assert not lock_file.exists()

def test_project_lock_reentrant_same_pid(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    proj_name = "test_reentrant"
    
    lock1 = ProjectLock(proj_name)
    assert lock1.acquire() is True
    
    lock2 = ProjectLock(proj_name)
    # Mesmo PID deve permitir
    assert lock2.acquire() is True
    
    lock1.release()

def test_project_lock_blocks_different_active_pid(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    proj_name = "test_blocked"
    lock_file = tmp_path / f"{proj_name}.lock"
    
    # Simula lock criado por outro PID ativo
    fake_pid = 4  # System PID no Windows, sempre ativo
    lock_data = {
        "project_name": proj_name,
        "pid": fake_pid,
        "hostname": "test-host",
        "acquired_at": "2026-09-22T20:00:00"
    }
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump(lock_data, f)
        
    lock = ProjectLock(proj_name)
    with pytest.raises(ProjectLockedError) as exc_info:
        lock.acquire()
        
    assert exc_info.value.pid == fake_pid
    assert exc_info.value.project_name == proj_name

def test_project_lock_auto_recovers_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    proj_name = "test_stale"
    lock_file = tmp_path / f"{proj_name}.lock"
    
    # Simula lock criado por PID inexistente (morto)
    dead_pid = 9999999
    lock_data = {
        "project_name": proj_name,
        "pid": dead_pid,
        "hostname": "old-host",
        "acquired_at": "2026-09-20T10:00:00"
    }
    with open(lock_file, "w", encoding="utf-8") as f:
        json.dump(lock_data, f)
        
    lock = ProjectLock(proj_name)
    # Deve detectar que dead_pid não existe, limpar o lock órfão e adquirir
    assert lock.acquire() is True
    
    with open(lock_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["pid"] == os.getpid()
        
    lock.release()
    assert not lock_file.exists()

def test_different_projects_can_lock_simultaneously(tmp_path, monkeypatch):
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    
    lock_a = ProjectLock("project_alpha")
    lock_b = ProjectLock("project_beta")
    
    assert lock_a.acquire() is True
    assert lock_b.acquire() is True
    
    assert (tmp_path / "project_alpha.lock").exists()
    assert (tmp_path / "project_beta.lock").exists()
    
    lock_a.release()
    lock_b.release()
    
    assert not (tmp_path / "project_alpha.lock").exists()
    assert not (tmp_path / "project_beta.lock").exists()

def test_sqlite_wal_mode(tmp_path):
    test_db = tmp_path / "test_wal.db"
    conn = get_db_connection(test_db)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    conn.close()
    assert mode.lower() == "wal"

def test_get_last_active_project(tmp_path, monkeypatch):
    fake_central = tmp_path / "iris_central.db"
    monkeypatch.setattr("src.core.project.CENTRAL_DB_PATH", fake_central)
    
    p1 = create_project("Project_One", "C:/source1")
    p2 = create_project("Project_Two", "C:/source2")
    
    # Último criado/atualizado deve ser Project_Two
    assert get_last_active_project() == "Project_Two"
    
    # Atualiza Project_One
    p1.touch()
    assert get_last_active_project() == "Project_One"

def test_config_atomic_save(tmp_path, monkeypatch):
    fake_config = tmp_path / "config.yaml"
    monkeypatch.setattr("src.core.config.CONFIG_FILE", fake_config)
    
    config.set("general.theme", "light")
    assert fake_config.exists()
    assert not fake_config.with_suffix(".tmp").exists()
    assert config.get("general.theme") == "light"

def test_youtube_token_atomic_save(tmp_path):
    token_file = tmp_path / "token.json"
    mock_creds = MagicMock()
    mock_creds.to_json.return_value = '{"token": "xyz123"}'
    
    save_token_atomic(token_file, mock_creds)
    assert token_file.exists()
    assert '{"token": "xyz123"}' in token_file.read_text(encoding="utf-8")
