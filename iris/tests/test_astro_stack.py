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
    process_and_save_frame,
    process_single_frame,
    scale_single_frame,
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

    # Teste de recorte rápido com bounds pré-calculados (otimização de performance)
    cropped_fast = centred_crop(img, size=160, bounds=(bx, by, bw, bh))
    np.testing.assert_array_equal(cropped, cropped_fast)


def test_calculate_sequence_gain():
    gain = calculate_sequence_gain(30000.0)
    assert gain == pytest.approx(2.0, rel=1e-3)

    gain_zero = calculate_sequence_gain(0.0)
    assert gain_zero == 1.0


def test_process_and_scale_single_frame(tmp_path: Path):
    import cv2
    from src.modules.astro_stack.preprocessor import _read_tiff, _write_tiff

    # Cria imagem sintética e salva em disco como TIFF
    test_raw = tmp_path / "synthetic_moon.tiff"
    img = np.zeros((300, 300), dtype=np.uint16)
    y, x = np.ogrid[:300, :300]
    dist = np.sqrt((x - 150)**2 + (y - 150)**2)
    img[dist <= 40] = 30000
    _write_tiff(test_raw, img)

    # 1. Processamento isolado (process_single_frame)
    temp_out = tmp_path / "raw_cropped.tiff"
    meta = process_single_frame(test_raw, crop_size=160, output_tiff_path=temp_out, fast_demosaic=True)

    assert meta["filename"] == "synthetic_moon.tiff"
    assert meta["peak"] == 30000.0
    assert temp_out.exists()

    cropped_data = _read_tiff(temp_out)
    assert cropped_data.shape == (160, 160)
    assert cropped_data[80, 80] == 30000

    # 2. Normalização com ganho linear (scale_single_frame)
    final_out = tmp_path / "final_frame.tiff"
    scale_single_frame(temp_out, final_out, gain=2.0)

    assert final_out.exists()
    final_data = _read_tiff(final_out)
    assert final_data.shape == (160, 160)
    assert final_data[80, 80] == 60000


def test_process_and_save_frame_single_pass(tmp_path: Path):
    from src.modules.astro_stack.preprocessor import _read_tiff, _write_tiff

    # Cria imagem sintética e salva em disco como TIFF
    test_raw = tmp_path / "synthetic_moon_direct.tiff"
    img = np.zeros((300, 300), dtype=np.uint16)
    y, x = np.ogrid[:300, :300]
    dist = np.sqrt((x - 150)**2 + (y - 150)**2)
    img[dist <= 40] = 25000
    _write_tiff(test_raw, img)

    # Processamento em passo único direto
    direct_out = tmp_path / "subfolder" / "direct_frame.tiff"
    meta = process_and_save_frame(test_raw, crop_size=160, gain=2.0, output_tiff_path=direct_out, fast_demosaic=True)

    assert meta["success"] is True
    assert meta["filename"] == "synthetic_moon_direct.tiff"
    assert meta["peak"] == 25000.0
    assert direct_out.exists()

    result_data = _read_tiff(direct_out)
    assert result_data.shape == (160, 160)
    assert result_data[80, 80] == 50000


def test_process_and_save_frame_edge_skipped(tmp_path: Path):
    from src.modules.astro_stack.preprocessor import _write_tiff

    # Cria imagem sintética onde a lua toca a borda inferior (y=299)
    test_raw = tmp_path / "synthetic_moon_border.tiff"
    img = np.zeros((300, 300), dtype=np.uint16)
    y, x = np.ogrid[:300, :300]
    dist = np.sqrt((x - 150)**2 + (y - 280)**2)
    img[dist <= 40] = 25000
    _write_tiff(test_raw, img)

    direct_out = tmp_path / "subfolder" / "direct_border.tiff"
    meta = process_and_save_frame(test_raw, crop_size=160, gain=2.0, output_tiff_path=direct_out, fast_demosaic=True)

    # Não deve quebrar com exceção não tratada e deve indicar success=False
    assert meta["success"] is False
    assert "toca a borda" in meta["error"]
    assert not direct_out.exists()




# ==============================================================================
# Testes de Descoberta de Ambiente Astro
# ==============================================================================

def test_find_astro_python_real_environment():
    """Garante que find_astro_python localiza um interpretador funcional no ambiente local."""
    py_path = find_astro_python()
    assert py_path is not None, "find_astro_python() deve encontrar o ambiente .venv_astro ou candidato válido"
    assert isinstance(py_path, Path)
    assert py_path.name.lower().startswith("python")
    assert py_path.exists()
    runner = AstroStackRunner(py_path)
    assert runner.is_available() is True


def test_resolve_python_exe(tmp_path: Path):
    """Testa a resolução de executáveis a partir de arquivos diretos ou diretórios de venv."""
    import sys
    from src.modules.astro_stack.runner import _resolve_python_exe

    # 1. Entrada nula ou auto
    assert _resolve_python_exe(None) is None
    assert _resolve_python_exe("auto") is None
    assert _resolve_python_exe("   ") is None

    # 2. Arquivo direto
    dummy_exe = tmp_path / "custom_python.exe"
    dummy_exe.touch()
    assert _resolve_python_exe(dummy_exe) == dummy_exe
    assert _resolve_python_exe(str(dummy_exe)) == dummy_exe

    # 3. Diretório de venv
    scripts_dir = tmp_path / "fake_venv" / ("Scripts" if sys.platform == "win32" else "bin")
    scripts_dir.mkdir(parents=True)
    venv_exe = scripts_dir / ("python.exe" if sys.platform == "win32" else "python")
    venv_exe.touch()

    assert _resolve_python_exe(tmp_path / "fake_venv") == venv_exe


def test_find_astro_python_configured_priorities(tmp_path: Path):
    """Testa que caminhos configurados via python_path, venv_path ou IRIS_ASTRO_PYTHON têm precedência."""
    import sys
    from src.modules.astro_stack.runner import find_astro_python

    dummy_py = tmp_path / "priority_python.exe"
    dummy_py.touch()

    # Prioridade 1: IRIS_ASTRO_PYTHON
    with patch.dict("os.environ", {"IRIS_ASTRO_PYTHON": str(dummy_py)}):
        assert find_astro_python() == dummy_py

    # Prioridade 2: modules.astro_stack.python_path
    with patch.dict("os.environ", {"IRIS_ASTRO_PYTHON": ""}):
        with patch("src.modules.astro_stack.runner.config.get", side_effect=lambda k, default=None: str(dummy_py) if k == "modules.astro_stack.python_path" else default):
            assert find_astro_python() == dummy_py

    # Prioridade 3: modules.astro_stack.venv_path apontando para arquivo ou pasta
    fake_venv = tmp_path / "custom_venv"
    scripts = fake_venv / ("Scripts" if sys.platform == "win32" else "bin")
    scripts.mkdir(parents=True)
    venv_py = scripts / ("python.exe" if sys.platform == "win32" else "python")
    venv_py.touch()

    with patch.dict("os.environ", {"IRIS_ASTRO_PYTHON": ""}):
        with patch("src.modules.astro_stack.runner.config.get", side_effect=lambda k, default=None: str(fake_venv) if k == "modules.astro_stack.venv_path" else default):
            assert find_astro_python() == venv_py


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
    empty_dst = tmp_path / "dst"
    empty_dst.mkdir(parents=True, exist_ok=True)
    proj = Project("empty_astro_proj", str(tmp_path / "src"))
    s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")

    with patch("src.core.config.config.get", side_effect=lambda k, d=None: empty_dst if k in ("storage.destination_root", "general.destination_root") else d):
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

    dest_root = tmp_path / "dest"
    proj = Project("src_path_astro_proj", str(sess_dir))
    s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")

    # Com runner simulado para não disparar o subprocesso PSS
    with patch("src.core.config.config.get", side_effect=lambda k, d=None: dest_root if "destination_root" in k else d):
        with patch("src.modules.astro_stack.stage.AstroStackRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.is_available.return_value = True
            mock_runner.run_session.return_value = {
                "output_tiff_paths": {"10": str(dest_root / "test.tiff")},
                "crop_size": 200,
                "shared_gain": 1.5,
            }
            mock_runner_cls.return_value = mock_runner

            with patch("src.modules.astro_stack.stage.send_windows_toast"):
                with patch("src.modules.astro_stack.stage.send_ntfy_notification"):
                    success = s_stack.run(proj, force=True)
                    assert success is True
                    assert mock_runner.run_session.called


def test_astro_stack_ignores_dest_root_sessions(tmp_path: Path):
    """Garante que sessões históricas em dest_root não sejam empilhadas se não pertencerem ao projeto."""
    dest_root = tmp_path / "dest"
    old_session = dest_root / "5_Astrofotografia" / "Lua" / "2026" / "09" / "02" / "sessao_23-55-59"
    old_session.mkdir(parents=True, exist_ok=True)
    (old_session / "moon1.cr2").write_bytes(b"\x00" * 100)
    (old_session / "moon2.cr2").write_bytes(b"\x00" * 100)

    with patch("src.core.project.PROJECTS_DIR", tmp_path):
        proj = Project("timelapse_proj", str(tmp_path / "src"))
        from src.core.project import ProjectItem
        tl_item = ProjectItem(
            original_path=str(tmp_path / "src" / "tl_001.jpg"),
            staging_path=str(tmp_path / "staging" / "tl_001.jpg"),
            relative_dest_dir="4_Timelapses/GoPro/2026/10/12/timelapse_18-00-00",
            target_filename="tl_001.jpg",
            category="timelapse",
            status="organized",
            verified=True,
        )
        proj.items = [tl_item]

        s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")

        with patch("src.core.config.config.get", side_effect=lambda k, d=None: dest_root if "destination_root" in k else d):
            with patch("src.modules.astro_stack.stage.AstroStackRunner") as mock_runner_cls:
                mock_runner = MagicMock()
                mock_runner_cls.return_value = mock_runner
                res = s_stack.run(proj)
                assert res is True
                # Runner NÃO deve ser chamado pois as fotos de old_session não pertencem ao projeto!
                assert not mock_runner.run_session.called


def test_astro_sharpen_ignores_dest_root_stacks(tmp_path: Path):
    """Garante que stacks TIFF históricos em dest_root não sejam aprimorados se não pertencerem ao projeto."""
    dest_root = tmp_path / "dest"
    old_stack_dir = dest_root / "8_Astro_Stack" / "Lua" / "2026" / "09" / "02" / "sessao_23-55-59"
    old_stack_dir.mkdir(parents=True, exist_ok=True)
    (old_stack_dir / "old_stack.tiff").write_bytes(b"\x00" * 100)

    with patch("src.core.project.PROJECTS_DIR", tmp_path):
        proj = Project("timelapse_proj", str(tmp_path / "src"))
        from src.core.project import ProjectItem
        tl_item = ProjectItem(
            original_path=str(tmp_path / "src" / "tl_001.jpg"),
            staging_path=str(tmp_path / "staging" / "tl_001.jpg"),
            relative_dest_dir="4_Timelapses/GoPro/2026/10/12/timelapse_18-00-00",
            target_filename="tl_001.jpg",
            category="timelapse",
            status="organized",
            verified=True,
        )
        proj.items = [tl_item]

        s_sharpen = get_sharpen_stage("astro_sharpen", "Aprimoramento de Astrofotografia")

        with patch("src.core.config.config.get", side_effect=lambda k, d=None: dest_root if "destination_root" in k else d):
            with patch("src.modules.astro_sharpen.stage.process_and_export_all_presets") as mock_sharpen:
                res = s_sharpen.run(proj)
                assert res is True
                assert not mock_sharpen.called


def test_astro_stack_processes_project_lunar_items(tmp_path: Path):
    """Garante que fotos de astrofotografia lunar pertencentes ao projeto sejam processadas normalmente."""
    dest_root = tmp_path / "dest"
    lunar_dir = dest_root / "5_Astrofotografia" / "Lua" / "2026" / "10" / "13" / "sessao_20-00-00"
    lunar_dir.mkdir(parents=True, exist_ok=True)
    f1 = lunar_dir / "moon1.cr2"
    f2 = lunar_dir / "moon2.cr2"
    f1.write_bytes(b"\x00" * 100)
    f2.write_bytes(b"\x00" * 100)

    with patch("src.core.project.PROJECTS_DIR", tmp_path):
        proj = Project("lunar_valid_proj", str(tmp_path / "src"))
        from src.core.project import ProjectItem
        it1 = ProjectItem(
            original_path=str(f1),
            staging_path=str(f1),
            organized_path=str(f1),
            relative_dest_dir="5_Astrofotografia/Lua/2026/10/13/sessao_20-00-00",
            target_filename="moon1.cr2",
            category="astro_lua",
            status="organized",
            verified=True,
        )
        it2 = ProjectItem(
            original_path=str(f2),
            staging_path=str(f2),
            organized_path=str(f2),
            relative_dest_dir="5_Astrofotografia/Lua/2026/10/13/sessao_20-00-00",
            target_filename="moon2.cr2",
            category="astro_lua",
            status="organized",
            verified=True,
        )
        proj.items = [it1, it2]

        s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")

        with patch("src.core.config.config.get", side_effect=lambda k, d=None: dest_root if "destination_root" in k else d):
            with patch("src.modules.astro_stack.stage.AstroStackRunner") as mock_runner_cls:
                mock_runner = MagicMock()
                mock_runner.is_available.return_value = True
                mock_runner.run_session.return_value = {
                    "output_tiff_paths": {"10": str(dest_root / "out.tiff")},
                    "crop_size": 200,
                    "shared_gain": 1.5,
                }
                mock_runner_cls.return_value = mock_runner
                with patch("src.modules.astro_stack.stage.send_windows_toast"), \
                     patch("src.modules.astro_stack.stage.send_ntfy_notification"):
                    res = s_stack.run(proj, force=True)
                    assert res is True
                    assert mock_runner.run_session.called


def test_astro_stack_prunes_empty_output_dir_on_failure(tmp_path: Path):
    dest_root = tmp_path / "dest"
    sess_dir = tmp_path / "src" / "5_Astrofotografia" / "Lua" / "2026" / "10" / "18" / "sessao_fail"
    sess_dir.mkdir(parents=True, exist_ok=True)
    (sess_dir / "frame1.cr2").write_bytes(b"\x00" * 100)
    (sess_dir / "frame2.cr2").write_bytes(b"\x00" * 100)

    proj = Project("fail_proj", str(sess_dir))
    s_stack = get_stack_stage("astro_stack", "Empilhamento Lunar")

    with patch("src.core.config.config.get", side_effect=lambda k, d=None: dest_root if "destination_root" in k else d):
        with patch("src.modules.astro_stack.stage.AstroStackRunner") as mock_runner_cls:
            mock_runner = MagicMock()
            mock_runner.is_available.return_value = True
            mock_runner.run_session.side_effect = RuntimeError("Falha PSS simulada")
            mock_runner_cls.return_value = mock_runner

            res = s_stack.run(proj, force=True)
            assert res is True
            expected_out_dir = dest_root / "8_Astro_Stack" / "Lua" / "2026" / "10" / "18" / "sessao_fail"
            assert not expected_out_dir.exists()


def test_astro_sharpen_prunes_empty_output_dir_on_failure(tmp_path: Path):
    dest_root = tmp_path / "dest"
    stack_file = tmp_path / "src" / "8_Astro_Stack" / "Lua" / "2026" / "10" / "18" / "sessao_fail" / "stack.tiff"
    stack_file.parent.mkdir(parents=True, exist_ok=True)
    stack_file.write_bytes(b"\x00" * 100)

    proj = Project("sharpen_fail_proj", str(tmp_path / "src"))
    s_sharpen = get_sharpen_stage("astro_sharpen", "Aprimoramento")

    with patch("src.core.config.config.get", side_effect=lambda k, d=None: dest_root if "destination_root" in k else d):
        with patch("src.modules.astro_sharpen.stage.process_and_export_all_presets") as mock_presets:
            mock_presets.side_effect = RuntimeError("Falha Wavelets simulada")
            res = s_sharpen.run(proj)
            assert res is True
            expected_out_dir = dest_root / "9_Astro_Sharpening" / "Lua" / "2026" / "10" / "18" / "sessao_fail"
            assert not expected_out_dir.exists()


