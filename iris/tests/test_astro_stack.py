"""Testes unitários para os módulos Astro Stack (PSS) e Astro Sharpen."""

import numpy as np
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.modules.astro_stack.namer import (
    resolve_astro_stack_dir,
    build_stack_filename,
    build_preview_filename,
    build_report_filename,
)
from src.modules.astro_sharpen.namer import (
    resolve_astro_sharpen_dir,
    build_sharpened_filenames,
)
from src.modules.astro_stack.preprocessor import (
    moon_bounds,
    centred_crop,
    calculate_sequence_gain,
)
from src.modules.astro_stack.runner import find_astro_python, AstroStackRunner
from src.modules.astro_stack.stage import AstroStackStage, get_stage as get_stack_stage
from src.modules.astro_sharpen.stage import AstroSharpenStage, get_stage as get_sharpen_stage
from src.core.project import (
    Project,
    init_central_db,
    save_central_astro_stack,
    list_central_astro_stacks,
    save_central_astro_sharpen,
    list_central_astro_sharpens,
)


# ==============================================================================
# Testes de Naming e Estrutura de Diretórios
# ==============================================================================

def test_stack_namer_paths():
    dest_root = Path("X:/Workspace/Organizado")
    session_rel = Path("5_Astrofotografia/Lua/2026/10/12/sessao_18-30-00")

    out_dir = resolve_astro_stack_dir(session_rel, dest_root)
    expected_dir = dest_root / "8_Astro_Stack" / "Lua" / "2026" / "10" / "12" / "sessao_18-30-00"
    assert out_dir == expected_dir

    filename = build_stack_filename("2026-10-12", "18-30-00", "Canon SX60", 25)
    assert filename == "2026-10-12_18-30-00_Canon-SX60_stack25p_mono16.tiff"

    preview = build_preview_filename("2026-10-12", "18-30-00", "Canon SX60")
    assert preview == "2026-10-12_18-30-00_Canon-SX60_preview.png"

    report = build_report_filename("2026-10-12", "18-30-00", "Canon SX60")
    assert report == "2026-10-12_18-30-00_Canon-SX60_report.json"


def test_sharpen_namer_paths():
    dest_root = Path("X:/Workspace/Organizado")
    stack_dir = dest_root / "8_Astro_Stack" / "Lua" / "2026" / "10" / "12" / "sessao_18-30-00"

    out_dir = resolve_astro_sharpen_dir(stack_dir, dest_root)
    expected_dir = dest_root / "9_Astro_Sharpening" / "Lua" / "2026" / "10" / "12" / "sessao_18-30-00"
    assert out_dir == expected_dir

    stem = "2026-10-12_18-30-00_Canon-SX60_stack25p_mono16"
    tif_name, png_name = build_sharpened_filenames(stem, "moderado")
    assert tif_name == "2026-10-12_18-30-00_Canon-SX60_stack25p_moderado.tiff"
    assert png_name == "2026-10-12_18-30-00_Canon-SX60_stack25p_moderado.png"


# ==============================================================================
# Testes de Pré-Processamento e Geometria da Lua
# ==============================================================================

def test_moon_bounds_and_centred_crop():
    # Cria matriz 300x300 com fundo preto e disco centrado em (150, 150) com raio 40
    img = np.zeros((300, 300), dtype=np.uint16)
    y, x = np.ogrid[:300, :300]
    dist_from_center = np.sqrt((x - 150)**2 + (y - 150)**2)
    img[dist_from_center <= 40] = 45000

    bx, by, bw, bh = moon_bounds(img)
    assert abs((bx + bw / 2) - 150) < 5
    assert abs((by + bh / 2) - 150) < 5

    # Teste de recorte centrado sem distorção (tamanho 160)
    cropped = centred_crop(img, size=160)
    assert cropped.shape == (160, 160)
    assert cropped.dtype == np.uint16
    # O centro do crop deve conter o pico brilhante
    assert cropped[80, 80] == 45000


def test_calculate_sequence_gain():
    gain = calculate_sequence_gain(30000.0)
    assert gain == pytest.approx(2.0, rel=1e-3)

    gain_zero = calculate_sequence_gain(0.0)
    assert gain_zero == 1.0


# ==============================================================================
# Testes de Descoberta de Ambiente Astro
# ==============================================================================

def test_find_astro_python():
    py_path = find_astro_python()
    if py_path:
        assert isinstance(py_path, Path)
        assert py_path.name.lower().startswith("python")


# ==============================================================================
# Testes de Persistência em SQLite (Project & Central DB)
# ==============================================================================

def test_project_and_central_db_astro_records(tmp_path: Path):
    central_db = tmp_path / "central.db"
    with patch("src.core.project.CENTRAL_DB_PATH", central_db), \
         patch("src.core.project.PROJECTS_DIR", tmp_path):
        init_central_db()

        # Cria projeto
        proj = Project("lunar_proj", str(tmp_path / "src"))
        proj.save_metadata()

        # Adiciona astro stack
        stack_record = {
            "project_name": "lunar_proj",
            "session_dir": "5_Astrofotografia/Lua/sessao_1",
            "output_dir": "8_Astro_Stack/Lua/sessao_1",
            "raw_count": 20,
            "keep_percents": [10, 25],
            "status": "completed",
            "crop_size": 1800,
            "shared_gain": 1.5,
            "elapsed_seconds": 12.5,
        }
        proj.add_astro_stack(stack_record)

        stacks = proj.get_astro_stacks()
        assert len(stacks) == 1
        assert stacks[0]["raw_count"] == 20
        assert stacks[0]["status"] == "completed"
        assert proj.is_astro_session_stacked("5_Astrofotografia/Lua/sessao_1")

        # Salva central DB
        save_central_astro_stack(stack_record)
        c_stacks = list_central_astro_stacks()
        assert len(c_stacks) == 1
        assert c_stacks[0]["project_name"] == "lunar_proj"

        # Adiciona astro sharpen
        sharpen_record = {
            "project_name": "lunar_proj",
            "source_stack_path": "8_Astro_Stack/Lua/sessao_1/stack_10pct.tif",
            "preset": "moderado",
            "output_tiff_path": "9_Astro_Sharpening/Lua/sessao_1/stack_10pct_moderado.tiff",
            "output_png_path": "9_Astro_Sharpening/Lua/sessao_1/stack_10pct_moderado.png",
            "status": "completed",
            "elapsed_seconds": 2.3,
        }
        proj.add_astro_sharpen(sharpen_record)
        sharpens = proj.get_astro_sharpens()
        assert len(sharpens) == 1
        assert sharpens[0]["preset"] == "moderado"

        save_central_astro_sharpen(sharpen_record)
        c_sharpens = list_central_astro_sharpens()
        assert len(c_sharpens) == 1
        assert c_sharpens[0]["preset"] == "moderado"


# ==============================================================================
# Testes de Estágios do Pipeline
# ==============================================================================

def test_pipeline_stages_instantiation():
    s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")
    assert isinstance(s_stack, AstroStackStage)
    assert s_stack.stage_id == "astro_stack"
    assert "Empilhamento" in s_stack.name

    s_sharpen = get_sharpen_stage("astro_sharpen", "Aprimoramento de Astrofotografia")
    assert isinstance(s_sharpen, AstroSharpenStage)
    assert s_sharpen.stage_id == "astro_sharpen"
    assert "Aprimoramento" in s_sharpen.name


def test_stage_run_empty_project(tmp_path: Path):
    proj = Project("empty_astro_proj", str(tmp_path / "src"))
    s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")
    # Sem imagens na sessão, o stage deve completar com sucesso (retorna True)
    res_stack = s_stack.run(proj)
    assert res_stack is True

    s_sharpen = get_sharpen_stage("astro_sharpen", "Aprimoramento de Astrofotografia")
    res_sharpen = s_sharpen.run(proj)
    assert res_sharpen is True


def test_namer_with_absolute_windows_paths():
    dest_root = Path("C:/IRIS")
    abs_session = Path("C:/1/TESTES/5_Astrofotografia/Lua/2026/06/02/sessao_20-22-39")
    
    out_dir = resolve_astro_stack_dir(abs_session, dest_root)
    assert out_dir == dest_root / "8_Astro_Stack" / "Lua" / "2026" / "06" / "02" / "sessao_20-22-39"

    abs_stack = Path("C:/1/TESTES/8_Astro_Stack/Lua/2026/06/02/sessao_20-22-39/stack10p.tiff")
    sharpen_dir = resolve_astro_sharpen_dir(abs_stack, dest_root)
    assert sharpen_dir == dest_root / "9_Astro_Sharpening" / "Lua" / "2026" / "06" / "02" / "sessao_20-22-39"


def test_stage_source_path_session_discovery(tmp_path: Path):
    sess_dir = tmp_path / "5_Astrofotografia" / "Lua" / "2026" / "06" / "02" / "sessao_20-22-39"
    sess_dir.mkdir(parents=True, exist_ok=True)
    # Cria 2 arquivos simulados
    (sess_dir / "frame1.cr2").write_bytes(b"\x00" * 100)
    (sess_dir / "frame2.cr2").write_bytes(b"\x00" * 100)

    proj = Project("src_path_astro_proj", str(sess_dir))
    s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")

    # Com runner simulado para não disparar o subprocesso PSS
    with patch("src.modules.astro_stack.stage.AstroStackRunner") as mock_runner_cls:
        mock_runner = MagicMock()
        mock_runner.is_available.return_value = True
        mock_runner.run_session.return_value = {
            "output_tiff_paths": {"10": str(tmp_path / "test.tiff")},
            "crop_size": 200,
            "shared_gain": 1.5,
        }
        mock_runner_cls.return_value = mock_runner

        with patch("src.modules.astro_stack.stage.send_windows_toast"):
            with patch("src.modules.astro_stack.stage.send_ntfy_notification"):
                success = s_stack.run(proj, force=True)
                assert success is True
                assert mock_runner.run_session.called

