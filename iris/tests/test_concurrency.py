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

def test_project_lock_corrupt_empty_file_auto_recovery(tmp_path, monkeypatch):
    """Garante que um arquivo .lock vazio (0 bytes) ou corrompido é limpo e recuperado com sucesso."""
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    proj_name = "test_corrupt_lock"
    lock_file = tmp_path / f"{proj_name}.lock"
    
    # Simula arquivo de lock vazio deixado por crash anterior
    lock_file.write_text("", encoding="utf-8")
    assert lock_file.exists()
    assert lock_file.stat().st_size == 0
    
    lock = ProjectLock(proj_name)
    assert lock.acquire() is True
    assert lock_file.exists()
    
    # O arquivo deve agora conter JSON válido com o PID atual
    with open(lock_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["pid"] == os.getpid()
        assert data["project_name"] == proj_name
        
    lock.release()
    assert not lock_file.exists()

def test_project_lock_write_failure_leaves_no_garbage(tmp_path, monkeypatch):
    """Garante que, se a escrita do JSON falhar, o arquivo parcial é removido imediatamente."""
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    proj_name = "test_write_fail"
    lock_file = tmp_path / f"{proj_name}.lock"
    
    def mock_dump_fail(*args, **kwargs):
        raise OSError("Simulação de disco cheio ou erro de I/O na escrita do lock")
        
    monkeypatch.setattr("json.dump", mock_dump_fail)
    
    lock = ProjectLock(proj_name)
    with pytest.raises(OSError, match="Simulação de disco cheio"):
        lock.acquire()
        
    # O arquivo parcial deve ter sido apagado pelo bloco except
    assert not lock_file.exists()

def test_get_lock_info_retry_on_empty_content(tmp_path, monkeypatch):
    """Garante que get_lock_info retenta ler quando o arquivo está temporariamente vazio."""
    monkeypatch.setattr("src.core.lock.PROJECTS_DIR", tmp_path)
    proj_name = "test_retry_read"
    lock = ProjectLock(proj_name)
    
    # Arquivo inexistente retorna None imediatamente
    assert lock.get_lock_info() is None
    
    # Arquivo vazio retorna None após esgotar as retentativas rápidas
    lock.lock_file.write_text("", encoding="utf-8")
    assert lock.get_lock_info(retries=2, retry_delay=0.01) is None

def test_project_lock_real_multiprocess_collision(tmp_path):
    """
    Testa exclusão mútua atômica real entre processos distintos do SO via subprocess.
    Valida que exatamente um processo adquire o lock e os demais recebem ProjectLockedError.
    """
    import subprocess
    import sys
    
    proj_name = "multiprocess_test_proj"
    
    worker_code = """
import sys
import time
from pathlib import Path
from src.core.lock import ProjectLock, ProjectLockedError
import src.core.lock as lock_mod

lock_mod.PROJECTS_DIR = Path(sys.argv[1])
proj = sys.argv[2]
lock = ProjectLock(proj)
try:
    if lock.acquire():
        # Mantém a posse por 400ms para que os concorrentes colidam
        time.sleep(0.4)
        lock.release()
        sys.exit(0)
    sys.exit(1)
except ProjectLockedError:
    # 42 indica que foi devidamente barrado por trava ativa de outro PID
    sys.exit(42)
except Exception:
    sys.exit(99)
"""

    cmd = [sys.executable, "-c", worker_code, str(tmp_path), proj_name]
    
    # Dispara 3 processos simultâneos disputando exatamente o mesmo projeto
    processes = [subprocess.Popen(cmd) for _ in range(3)]
    exit_codes = [p.wait(timeout=10) for p in processes]
    
    exit_codes.sort()
    # Exatamente um deve obter sucesso (0) e os outros dois devem ser bloqueados (42)
    assert exit_codes == [0, 42, 42]

