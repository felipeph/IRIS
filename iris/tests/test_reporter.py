import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.reporter import ProgressReporter, SilentReporter, RichConsoleReporter
from src.modules.ingestion.strategies.copy_strategy import copy_and_verify
from src.modules.organize.stage import OrganizeStage
from src.modules.cleanup.stage import CleanupStage
from src.core.project import create_project, ProjectItem, init_central_db


def test_silent_reporter_contract():
    """Testa se o SilentReporter implementa a interface e armazena logs/updates sem IO."""
    reporter = SilentReporter(default_confirm_response=True)
    reporter.start_stage("TEST_STAGE", total_units=1000, mode="bytes")
    reporter.update(increment=100, current_item="file1.jpg", status_msg="Processando")
    reporter.log("Mensagem de teste", level="info")
    reporter.end_stage(success=True)

    assert len(reporter.updates) == 1
    assert reporter.updates[0]["increment"] == 100
    assert reporter.updates[0]["item"] == "file1.jpg"
    assert len(reporter.logs) == 1
    assert reporter.logs[0] == ("info", "Mensagem de teste")
    assert reporter.confirm("Deseja continuar?") is True


def test_silent_reporter_confirm_false():
    """Verifica se SilentReporter com default_confirm_response=False rejeita confirmações."""
    reporter = SilentReporter(default_confirm_response=False)
    assert reporter.confirm("Apagar?") is False


def test_copy_and_verify_with_silent_reporter(tmp_path):
    """Testa copy_and_verify usando SilentReporter sem nenhuma interface Rich."""
    src_file = tmp_path / "src.dat"
    dest_file = tmp_path / "dest.dat"
    data = b"Hello, IRIS world!" * 1024
    src_file.write_bytes(data)

    reporter = SilentReporter()
    success, fhash = copy_and_verify(src_file, dest_file, reporter=reporter)

    assert success is True
    assert len(fhash) > 0
    assert dest_file.exists()
    assert dest_file.read_bytes() == data
    # Verifica que reporter recebeu updates de progresso
    assert len(reporter.updates) >= 2


def test_organize_stage_with_silent_reporter_cancel(tmp_path):
    """Testa se OrganizeStage cancela a execução quando reporter.confirm() retorna False."""
    with patch("src.core.project.PROJECTS_DIR", tmp_path), \
         patch("src.core.project.CENTRAL_DB_PATH", tmp_path / "iris_central.db"):
        init_central_db()
        p = create_project("test_org_cancel", str(tmp_path))
        
        # Item copiado pronto para organização
        item = ProjectItem(
            original_path=str(tmp_path / "orig.jpg"),
            staging_path=str(tmp_path / "orig.jpg"),
            category="foto_unica",
            relative_dest_dir="Fotos",
            status="copied",
            verified=True,
            file_size_bytes=10
        )
        p.save_item(item)
        
        # SilentReporter que recusa confirmação
        reporter = SilentReporter(default_confirm_response=False)
        stage = OrganizeStage("organize", "Organização")
        result = stage.run(p, interactive=True, reporter=reporter)
        
        # Deve ter sido cancelado pelo usuário
        assert result is False
        assert any("cancelada" in msg for _, msg in reporter.logs)


def test_cleanup_stage_with_silent_reporter_cancel(tmp_path):
    """Testa se CleanupStage cancela a limpeza quando reporter.confirm() retorna False."""
    with patch("src.core.project.PROJECTS_DIR", tmp_path), \
         patch("src.core.project.CENTRAL_DB_PATH", tmp_path / "iris_central.db"):
        init_central_db()
        
        src_file = tmp_path / "sd_card" / "orig.jpg"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_bytes(b"12345")
        
        p = create_project("test_clean_cancel", str(tmp_path / "sd_card"), auto_cleanup=False)
        item = ProjectItem(
            original_path=str(src_file),
            staging_path=str(tmp_path / "dest.jpg"),
            status="copied",
            verified=True,
            file_size_bytes=5
        )
        p.save_item(item)
        
        reporter = SilentReporter(default_confirm_response=False)
        stage = CleanupStage("cleanup", "Limpeza")
        result = stage.run(p, auto_clean=False, reporter=reporter)
        
        # Deve retornar True (operação abortada/preservada de forma segura) e arquivo intacto
        assert result is True
        assert src_file.exists()
        assert any("cancelada" in msg for _, msg in reporter.logs)
