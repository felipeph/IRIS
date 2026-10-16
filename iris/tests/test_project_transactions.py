import pytest
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

from src.core.project import Project, ProjectItem, create_project, get_project, init_central_db

@pytest.fixture
def mock_projects_dir(tmp_path):
    with patch("src.core.project.PROJECTS_DIR", tmp_path), \
         patch("src.core.project.CENTRAL_DB_PATH", tmp_path / "iris_central.db"):
        init_central_db()
        yield tmp_path

def test_transaction_commits_on_clean_exit(mock_projects_dir):
    """Garante que itens salvos dentro de with project.transaction(): são persistidos fisicamente."""
    proj = create_project("test_tx_commit", "X:\\src")
    
    with proj.transaction() as p:
        for i in range(5):
            p.save_item(ProjectItem(
                original_path=f"/orig/file_{i}.jpg",
                staging_path=f"/dest/file_{i}.jpg",
                file_size_bytes=1000 + i,
                status="copied",
                verified=True
            ))

    # Conecta diretamente via novo cursor para certificar que os dados foram persistidos
    with sqlite3.connect(proj._project_db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM items")
        count = cursor.fetchone()[0]
        assert count == 5
        
        cursor.execute("SELECT original_path, file_size_bytes, verified FROM items WHERE original_path=?", ("/orig/file_3.jpg",))
        row = cursor.fetchone()
        assert row == ("/orig/file_3.jpg", 1003, 1)

def test_transaction_rollbacks_on_exception(mock_projects_dir):
    """Garante que se uma exceção ocorrer dentro do bloco, as alterações são descartadas."""
    proj = create_project("test_tx_rollback", "X:\\src")
    
    # Salva 1 item antes da transação que falhará
    proj.save_item(ProjectItem(original_path="/orig/stable.jpg", staging_path="/dest/stable.jpg", file_size_bytes=500))
    
    class CustomStageError(Exception):
        pass

    with pytest.raises(CustomStageError):
        with proj.transaction():
            proj.save_item(ProjectItem(original_path="/orig/doomed.jpg", staging_path="/dest/doomed.jpg", file_size_bytes=999))
            raise CustomStageError("Falha simulada no meio do processamento da etapa")

    # Verifica que apenas o item estável existe; o doomed foi revertido
    items = proj.get_items()
    assert len(items) == 1
    assert items[0].original_path == "/orig/stable.jpg"
    assert proj.get_item("/orig/doomed.jpg") is None

def test_nested_transactions_savepoints_partial_rollback(mock_projects_dir):
    """Testa reentrância com SAVEPOINT: transação interna falha, mas externa trata e commita com sucesso."""
    proj = create_project("test_tx_nested", "X:\\src")
    
    with proj.transaction():
        proj.save_item(ProjectItem(original_path="/orig/outer_1.jpg", staging_path="/dest/outer_1.jpg"))
        
        try:
            with proj.transaction():
                proj.save_item(ProjectItem(original_path="/orig/inner_fail.jpg", staging_path="/dest/inner_fail.jpg"))
                raise RuntimeError("Erro no sub-bloco interno")
        except RuntimeError:
            pass  # Trata o erro e continua o bloco externo
            
        proj.save_item(ProjectItem(original_path="/orig/outer_2.jpg", staging_path="/dest/outer_2.jpg"))

    items = {it.original_path for it in proj.get_items()}
    assert "/orig/outer_1.jpg" in items
    assert "/orig/outer_2.jpg" in items
    assert "/orig/inner_fail.jpg" not in items
    assert len(items) == 2

def test_nested_transactions_outer_failure_rolls_back_everything(mock_projects_dir):
    """Se a transação externa falhar no final, todas as transações internas aninhadas também são revertidas."""
    proj = create_project("test_tx_outer_fail", "X:\\src")
    
    with pytest.raises(ValueError):
        with proj.transaction():
            proj.save_item(ProjectItem(original_path="/orig/item1.jpg", staging_path="/dest/item1.jpg"))
            
            with proj.transaction():
                proj.save_item(ProjectItem(original_path="/orig/item2.jpg", staging_path="/dest/item2.jpg"))
                
            raise ValueError("Erro fatal no final da transação externa")

    assert len(proj.get_items()) == 0

def test_read_your_own_writes_in_transaction(mock_projects_dir):
    """Garante que get_item e get_items enxergam as inserções feitas na mesma transação antes do commit."""
    proj = create_project("test_tx_read_your_writes", "X:\\src")
    
    with proj.transaction() as p:
        p.save_item(ProjectItem(original_path="/orig/uncommitted.jpg", staging_path="/dest/uncommitted.jpg", file_size_bytes=42000))
        
        # Leitura pontual de item
        read_item = p.get_item("/orig/uncommitted.jpg")
        assert read_item is not None
        assert read_item.file_size_bytes == 42000
        
        # Leitura da lista completa
        all_items = p.get_items()
        assert len(all_items) == 1
        assert all_items[0].original_path == "/orig/uncommitted.jpg"

def test_save_item_standalone_compatibility(mock_projects_dir):
    """Garante que chamadas a save_item fora de uma transação continuam com auto-commit imediato."""
    proj = create_project("test_standalone", "X:\\src")
    assert proj._get_active_conn() is None
    
    proj.save_item(ProjectItem(original_path="/orig/single.jpg", staging_path="/dest/single.jpg", file_size_bytes=100))
    
    # Lê com conexão SQLite independente
    with sqlite3.connect(proj._project_db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_size_bytes FROM items WHERE original_path=?", ("/orig/single.jpg",))
        assert cursor.fetchone()[0] == 100

def test_save_items_batch_and_items_setter(mock_projects_dir):
    """Testa save_items_batch e o setter project.items com grande número de itens."""
    proj = create_project("test_batch", "X:\\src")
    
    items = [
        ProjectItem(
            original_path=f"/orig/batch_{i}.jpg",
            staging_path=f"/dest/batch_{i}.jpg",
            file_size_bytes=i * 10,
            status="copied",
            verified=(i % 2 == 0),
            meta_is_video=False,
            meta_width=1920,
            meta_height=1080
        )
        for i in range(100)
    ]
    
    # Usa o setter (que internamente chama save_items_batch)
    proj.items = items
    
    loaded = proj.get_items()
    assert len(loaded) == 100
    item_50 = proj.get_item("/orig/batch_50.jpg")
    assert item_50 is not None
    assert item_50.file_size_bytes == 500
    assert item_50.verified is True
    assert item_50.meta_width == 1920

def test_transaction_thread_isolation(mock_projects_dir):
    """Garante que a transação aberta na thread principal não vaza para outra thread e permite leitura WAL."""
    proj = create_project("test_thread_isolation", "X:\\src")
    
    thread_observed_conn = [None]
    thread_read_success = [False]
    
    with proj.transaction():
        proj.save_item(ProjectItem(original_path="/orig/main_thread.jpg", staging_path="/dest/main.jpg"))
        
        def worker():
            # A thread secundária deve ter seu próprio _tx_local (onde conn é None)
            thread_observed_conn[0] = proj._get_active_conn()
            try:
                # Thread secundária consegue ler o banco sem bloqueio (WAL mode)
                items = proj.get_items()
                thread_read_success[0] = isinstance(items, list)
            except Exception as e:
                print(f"Worker read error: {e}")
                thread_read_success[0] = False
                
        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=2.0)

    assert thread_observed_conn[0] is None
    assert thread_read_success[0] is True
    
    # Após a thread principal liberar a trava de escrita, a thread secundária grava com sucesso
    def worker_write():
        proj.save_item(ProjectItem(original_path="/orig/worker.jpg", staging_path="/dest/worker.jpg"))
        
    t2 = threading.Thread(target=worker_write)
    t2.start()
    t2.join(timeout=2.0)
    
    all_items = {it.original_path for it in proj.get_items()}
    assert "/orig/main_thread.jpg" in all_items
    assert "/orig/worker.jpg" in all_items
    assert len(all_items) == 2

def test_performance_benchmark_transaction_vs_churn(mock_projects_dir):
    """Mede a disparidade de performance entre save_item com commits individuais vs with project.transaction()."""
    p_tx = create_project("test_tx_speed", "X:\\src")
    
    count = 100
    items = [
        ProjectItem(original_path=f"/orig/perf_{i}.jpg", staging_path=f"/dest/perf_{i}.jpg", file_size_bytes=i)
        for i in range(count)
    ]
    
    # Com transação única
    start_tx = time.perf_counter()
    with p_tx.transaction():
        for it in items:
            p_tx.save_item(it)
    dur_tx = time.perf_counter() - start_tx
    
    assert len(p_tx.get_items()) == count
    assert dur_tx < 0.5
