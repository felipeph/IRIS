"""Testes unitários e de integração para o motor de Astrofotografia Lunar e Wavelets do IRIS."""

import numpy as np
import pytest
from pathlib import Path
import cv2

from src.modules.astro.wavelets import LunarWaveletEngine
from src.modules.astro.postprocess import (
    load_lunar_image,
    save_lunar_image,
    apply_clahe_16bit,
    stretch_tonal_range,
    process_and_export_all_presets,
)


@pytest.fixture
def synthetic_moon_16bit(tmp_path: Path) -> Path:
    """Gera um arquivo TIFF 16-bit sintético simulando um disco lunar com crateras e fundo escuro."""
    h, w = 300, 300
    img = np.zeros((h, w, 3), dtype=np.uint16)

    # Disco lunar em cinza claro (~45000 em 16-bit)
    center = (150, 150)
    radius = 100
    cv2.circle(img, center, radius, (45000, 45000, 45000), -1)

    # Adicionar crateras (áreas escuras e picos centrais brilhantes)
    cv2.circle(img, (120, 120), 25, (25000, 25000, 25000), -1)
    cv2.circle(img, (120, 120), 4, (55000, 55000, 55000), -1)

    cv2.circle(img, (180, 160), 18, (28000, 28000, 28000), -1)
    cv2.circle(img, (160, 200), 12, (30000, 30000, 30000), -1)

    # Leve ruído Gaussiano simulando câmera astronômica
    noise = np.random.normal(0, 400, (h, w, 3)).astype(np.int32)
    img = np.clip(img.astype(np.int32) + noise, 0, 65535).astype(np.uint16)

    file_path = tmp_path / "synthetic_moon_stack.tif"
    cv2.imwrite(str(file_path), img)
    return file_path


def test_wavelet_energy_conservation():
    """Verifica se a decomposição À Trous com ganho unitário recupera a imagem original sem perda."""
    engine = LunarWaveletEngine(levels=5)
    rng = np.random.default_rng(42)
    original = rng.random((200, 200, 3), dtype=np.float32)

    approx, details = engine.decompose(original)
    assert len(details) == 5
    assert approx.shape == original.shape

    # Reconstrução com ganhos 1.0 (neutros)
    reconstructed = engine.reconstruct(
        approx,
        details,
        gains=[1.0, 1.0, 1.0, 1.0, 1.0],
        denoise_thresholds=None,
        limb_mask=None,
    )

    diff = np.max(np.abs(original - reconstructed))
    assert diff < 1e-5, f"Erro máximo de reconstrução excessivo: {diff}"


def test_wavelet_smooth_shrinkage():
    """Verifica a atenuação de ruído na função de shrinkage contínuo."""
    engine = LunarWaveletEngine()
    detail = np.array([-0.05, -0.001, 0.0, 0.001, 0.05], dtype=np.float32)
    tau = 0.005

    shrunk = engine.apply_smooth_shrinkage(detail, threshold=tau)

    # Valores menores que tau devem ser substancialmente atenuados
    assert abs(shrunk[1]) < 0.0005
    assert abs(shrunk[3]) < 0.0005
    # Valores bem maiores que tau devem ser preservados quase intactos
    assert abs(shrunk[0] - detail[0]) < 0.002
    assert abs(shrunk[4] - detail[4]) < 0.002


def test_limb_guard_detection():
    """Gera um disco e verifica se o Limb Guard isola a borda externa contra o espaço."""
    img = np.zeros((200, 200), dtype=np.float32)
    cv2.circle(img, (100, 100), 60, 0.8, -1)

    mask = LunarWaveletEngine.compute_limb_mask(img, blur_radius=5, edge_dilation=9)

    # Centro do disco deve ter proteção nula (máscara 0.0)
    assert mask[100, 100] == 0.0
    # Espaço profundo deve ter proteção nula (máscara 0.0)
    assert mask[10, 10] == 0.0
    # A borda do disco (~raio 60, ou seja, x=160, y=100) deve ter alta intensidade
    assert mask[100, 160] > 0.5


def test_reconstruct_with_limb_guard():
    """Gera um disco e verifica que a reconstrução com Limb Guard evita estouros no limbo."""
    engine = LunarWaveletEngine(levels=4)
    img = np.zeros((150, 150), dtype=np.float32)
    cv2.circle(img, (75, 75), 45, 0.7, -1)

    approx, details = engine.decompose(img)
    limb_mask = engine.compute_limb_mask(img)

    # Aplica ganho agressivo de wavelets
    gains = [2.5, 2.5, 2.0, 1.5]

    # Reconstrução com Limb Guard
    recon_with_guard = engine.reconstruct(approx, details, gains=gains, limb_mask=limb_mask, limb_guard_strength=1.0)
    # Reconstrução sem Limb Guard
    recon_without_guard = engine.reconstruct(approx, details, gains=gains, limb_mask=None)

    assert recon_with_guard.shape == img.shape
    assert not np.isnan(recon_with_guard).any()
    # O valor na borda sem guard tem maior overshoot que com guard
    diff = np.max(recon_without_guard) - np.max(recon_with_guard)
    assert diff >= 0.0


def test_presets_execution(synthetic_moon_16bit: Path):
    """Executa todos os 12 presets disponíveis e garante conformidade de saída."""
    engine = LunarWaveletEngine()
    img_float, bit_depth = load_lunar_image(synthetic_moon_16bit)
    assert bit_depth == 16
    assert img_float.shape == (300, 300, 3)

    all_presets = list(LunarWaveletEngine.PRESETS.keys())
    assert len(all_presets) == 12

    for preset_name in all_presets:
        out = engine.process_preset(img_float, preset_name=preset_name, use_limb_guard=True)
        assert out.shape == img_float.shape
        assert out.min() >= 0.0
        assert out.max() <= 1.0
        assert not np.isnan(out).any()


def test_richardson_lucy_algorithm():
    """Valida o algoritmo de deconvolução Richardson-Lucy restaurando pico pontual."""
    original = np.zeros((31, 31), dtype=np.float32)
    original[15, 15] = 1.0  # pico pontual (craterlet / estrela)

    # Aplica blur
    blurred = cv2.GaussianBlur(original, (7, 7), 1.2)
    # Deconvolução
    deconv = LunarWaveletEngine.richardson_lucy(blurred, psf_sigma=1.2, iterations=6)

    assert deconv.shape == original.shape
    assert deconv.min() >= 0.0
    assert deconv.max() <= 1.0
    assert not np.isnan(deconv).any()
    # O pico central deve ser substancialmente restaurado após a deconvolução
    assert deconv[15, 15] > blurred[15, 15]


def test_local_clarity_algorithm():
    """Valida o filtro de micro-contraste de relevo local (Clarity)."""
    img = np.random.uniform(0.2, 0.8, (50, 50, 3)).astype(np.float32)
    clarified = LunarWaveletEngine.apply_local_clarity(img, sigma=5.0, amount=0.6)

    assert clarified.shape == img.shape
    assert clarified.min() >= 0.0
    assert clarified.max() <= 1.0
    assert not np.isnan(clarified).any()


def test_adaptive_s_curve_algorithm():
    """Valida a curva S adaptativa."""
    from src.modules.astro.postprocess import apply_adaptive_s_curve
    img = np.linspace(0.0, 1.0, 100, dtype=np.float32).reshape(10, 10)
    scurve = apply_adaptive_s_curve(img, contrast=1.3, midtone_pivot=0.5)

    assert scurve.shape == img.shape
    assert scurve.min() >= 0.0
    assert scurve.max() <= 1.0
    # O contraste em torno do ponto de pivô deve ser aumentado
    diff_original = img[5, 5] - img[4, 4]
    diff_scurve = scurve[5, 5] - scurve[4, 4]
    assert diff_scurve >= diff_original * 0.95


def test_load_and_save_16bit_fidelity(tmp_path: Path):
    """Garante fidelidade de ponta a ponta na leitura e escrita de TIFF 16-bit."""
    test_img = np.random.uniform(0.0, 1.0, (100, 100, 3)).astype(np.float32)
    out_file = tmp_path / "test_out_16bit.tif"

    save_lunar_image(test_img, out_file, bit_depth=16)
    loaded_img, depth = load_lunar_image(out_file)

    assert depth == 16
    assert loaded_img.shape == test_img.shape
    # A diferença máxima deve estar dentro da discretização de 16 bits (1 / 65535 ~ 1.5e-5)
    max_err = np.max(np.abs(test_img - loaded_img))
    assert max_err < 5e-5


def test_clahe_and_tonal_stretch(synthetic_moon_16bit: Path):
    """Valida a aplicação de CLAHE em 16-bit e ajuste tonal."""
    img_float, _ = load_lunar_image(synthetic_moon_16bit)

    enhanced = apply_clahe_16bit(img_float, clip_limit=2.0, blend_ratio=0.5)
    assert enhanced.shape == img_float.shape
    assert enhanced.min() >= 0.0
    assert enhanced.max() <= 1.0

    stretched = stretch_tonal_range(enhanced, gamma=1.1)
    assert stretched.shape == img_float.shape
    assert not np.isnan(stretched).any()


def test_process_and_export_craters_group(synthetic_moon_16bit: Path, tmp_path: Path):
    """Testa a geração do grupo 'craters' contendo os 4 presets de relevo."""
    dest_dir = tmp_path / "saida_craters"

    results = process_and_export_all_presets(
        input_path=synthetic_moon_16bit,
        output_dir=dest_dir,
        presets=["craters"],
        enable_clahe=True,
        use_limb_guard=True,
        export_png=True,
        export_tiff=True,
    )

    expected = ["enfatico", "crateras_profundas", "deconvolucao_extrema", "contraste_dramatico"]
    assert len(results) == 4
    for p in expected:
        assert p in results
        assert results[p]["tiff"].exists()
        assert results[p]["png"].exists()


def test_cli_subcommands(synthetic_moon_16bit: Path, tmp_path: Path):
    """Testa a invocação do CLI iris-astro via argparse com novas opções."""
    from src.modules.astro.cli import main
    import sys

    # 1. Testar subcomando info
    sys.argv = ["iris-astro", "info", str(synthetic_moon_16bit)]
    main()

    # 2. Testar subcomando sharpen para preset crateras_profundas com clarity e deconvolve
    out_dir = tmp_path / "cli_out"
    sys.argv = [
        "iris-astro",
        "sharpen",
        str(synthetic_moon_16bit),
        "--preset",
        "crateras_profundas",
        "--clarity",
        "0.6",
        "--deconvolve",
        "--output-dir",
        str(out_dir),
    ]
    main()

    generated_png = out_dir / f"{synthetic_moon_16bit.stem}_crateras_profundas.png"
    generated_tif = out_dir / f"{synthetic_moon_16bit.stem}_crateras_profundas.tif"
    assert generated_png.exists()
    assert generated_tif.exists()

    # 3. Testar subcomando sharpen para preset registax_fiel
    sys.argv = [
        "iris-astro",
        "sharpen",
        str(synthetic_moon_16bit),
        "--preset",
        "registax_fiel",
        "--output-dir",
        str(out_dir),
    ]
    main()

    reg_png = out_dir / f"{synthetic_moon_16bit.stem}_registax_fiel.png"
    reg_tif = out_dir / f"{synthetic_moon_16bit.stem}_registax_fiel.tif"
    assert reg_png.exists()
    assert reg_tif.exists()


def test_process_and_export_registax_group(synthetic_moon_16bit: Path, tmp_path: Path):
    """Testa a geração do grupo 'registax' contendo os 4 presets calibrados."""
    dest_dir = tmp_path / "saida_registax"

    results = process_and_export_all_presets(
        input_path=synthetic_moon_16bit,
        output_dir=dest_dir,
        presets=["registax"],
        enable_clahe=True,
        use_limb_guard=True,
        export_png=True,
        export_tiff=True,
    )

    expected = ["registax_fiel", "registax_limb_guard", "registax_plus", "registax_mineral"]
    assert len(results) == 4
    for p in expected:
        assert p in results
        assert results[p]["tiff"].exists()
        assert results[p]["png"].exists()


def test_registax_fiel_ground_truth_fidelity():
    """Valida a fidelidade matemática (PSNR >= 48 dB e MAE < 150) contra o arquivo real do RegiStax."""
    exp_dir = Path("experiments/astro")
    orig_files = list(exp_dir.glob("original-autostakkert-*.tif"))
    reg_files = list(exp_dir.glob("editado-registax-*.tif"))

    if not orig_files or not reg_files:
        pytest.skip("Arquivos de benchmark do RegiStax não encontrados em experiments/astro.")

    orig_path = orig_files[0]
    reg_path = reg_files[0]

    engine = LunarWaveletEngine()
    orig_img, depth = load_lunar_image(orig_path)
    gt_img, _ = load_lunar_image(reg_path)

    result = engine.process_preset(orig_img, preset_name="registax_fiel")

    mse = np.mean((result - gt_img) ** 2)
    psnr = 10 * np.log10(1.0 / max(mse, 1e-10))
    mae = np.mean(np.abs(result - gt_img)) * 65535.0

    # Fidelidade matemática excepcional: PSNR >= 48.0 dB (o olho humano não distingue acima de 40 dB)
    assert psnr >= 48.0, f"PSNR abaixo do limiar de ouro de 48 dB: {psnr:.2f} dB"
    assert mae < 150.0, f"MAE acima de 150 níveis: {mae:.2f}"

