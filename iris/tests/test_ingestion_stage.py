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

def test_strategy_factory():
    """Garante que a fábrica seleciona MoveStrategy ou CopyStrategy com base no config."""
    from src.modules.ingestion.strategies import MoveStrategy, CopyStrategy

    stage = IngestionStage("ingest", "Ingestão")

    with patch("src.modules.ingestion.stage.config.get") as mock_get:
        mock_get.side_effect = lambda k, default=None: "copy" if "strategy" in k else 4
        strat = stage.get_strategy()
        assert isinstance(strat, CopyStrategy)

    with patch("src.modules.ingestion.stage.config.get") as mock_get:
        mock_get.side_effect = lambda k, default=None: "move" if "strategy" in k else 8
        strat = stage.get_strategy()
        assert isinstance(strat, MoveStrategy)
        assert strat.max_workers == 8

def test_move_strategy_basic(ingestion_env, tmp_path):
    """Garante movimentação nativa dos arquivos, remoção da origem, hash e limpeza de pastas."""
    from src.modules.ingestion.strategies import MoveStrategy

    src_dir, dest_root = ingestion_env
    dest_dir = dest_root / "1_Entrada" / "test_move" / "raw"

    # Criar subpasta na origem para testar remoção de pasta vazia
    sub_origem = src_dir / "100CANON"
    sub_origem.mkdir()
    (sub_origem / "sub_foto.jpg").write_text("sub photo data")

    project = Project("test_move", str(src_dir))
    project._init_project_db()

    strategy = MoveStrategy(max_workers=2)
    success = strategy.execute(project, src_dir, dest_dir)

    assert success is True
    # Originais de mídia foram movidos (não devem mais existir na origem)
    assert not (src_dir / "foto1.jpg").exists()
    assert not (src_dir / "video1.mp4").exists()
    assert not (sub_origem / "sub_foto.jpg").exists()
    # Pasta vazia foi limpa
    assert not sub_origem.exists()
    # Arquivo não mídia foi preservado na origem
    assert (src_dir / "not_media.txt").exists()

    # Destino deve ter os arquivos com conteúdo íntegro
    assert (dest_dir / "foto1.jpg").exists()
    assert (dest_dir / "video1.mp4").exists()
    assert (dest_dir / "100CANON" / "sub_foto.jpg").exists()

    # Verifica itens salvos no banco
    items = project.get_items()
    assert len(items) == 3
    for it in items:
        assert it.status == "copied"
        assert it.verified is True
        assert len(it.file_hash) > 0

def test_move_strategy_collision_and_duplicate(ingestion_env):
    """Garante tratamento de colisão com sufixo e deduplicação de arquivo idêntico."""
    from src.modules.ingestion.strategies import MoveStrategy

    src_dir, dest_root = ingestion_env
    dest_dir = dest_root / "1_Entrada" / "test_collision" / "raw"
    dest_dir.mkdir(parents=True)

    # 1. Arquivo idêntico já presente no destino (mesmo nome, mesmo tamanho)
    foto1_dest = dest_dir / "foto1.jpg"
    foto1_dest.write_text("dummy image content") # exatamente o mesmo texto de foto1.jpg

    # 2. Arquivo com mesmo nome mas tamanho diferente no destino
    video1_dest = dest_dir / "video1.mp4"
    video1_dest.write_text("diferente e maior tamanho de conteudo")

    project = Project("test_collision", str(src_dir))
    project._init_project_db()

    strategy = MoveStrategy(max_workers=2)
    success = strategy.execute(project, src_dir, dest_dir)

    assert success is True

    # foto1 era idêntico: arquivo no destino preservado
    assert foto1_dest.exists()

    # video1 colidiu com tamanho diferente: destino deve conter video1.mp4 (original do destino)
    # e video1_1.mp4 (movido da origem com sufixo incremental)
    assert (dest_dir / "video1.mp4").exists()
    assert (dest_dir / "video1_1.mp4").exists()
    assert (dest_dir / "video1_1.mp4").read_text() == "dummy video content"

def test_move_strategy_legacy_extensions(tmp_path):
    """Garante que formatos de mídia legados e diversos são ingeridos."""
    from src.modules.ingestion.strategies import MoveStrategy

    src_dir = tmp_path / "DCIM_LEGACY"
    dest_dir = tmp_path / "DEST_RAW"
    src_dir.mkdir()
    dest_dir.mkdir()

    # Criar arquivos com formatos antigos e variados
    legacy_files = [
        "antigo.avi",
        "video.3gp",
        "camcorder.mts",
        "raw_canon.cr3",
        "iphone.heic",
        "bitmap.bmp",
        "anim.webp"
    ]
    for name in legacy_files:
        (src_dir / name).write_text(f"content of {name}")

    (src_dir / "documento.pdf").write_text("nao midia")

    project = Project("test_legacy", str(src_dir))
    project._init_project_db()

    strategy = MoveStrategy(max_workers=2)
    success = strategy.execute(project, src_dir, dest_dir)

    assert success is True
    for name in legacy_files:
        assert (dest_dir / name).exists()
        assert not (src_dir / name).exists()

    # PDF não deve ter sido movido
    assert (src_dir / "documento.pdf").exists()
    assert not (dest_dir / "documento.pdf").exists()

