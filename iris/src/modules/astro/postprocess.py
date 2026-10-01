"""Módulo de Pós-Processamento e Gerenciamento de Imagens Lunares de Alta Resolução.

Manipula leitura e escrita de imagens TIFF 16-bit e 32-bit com preservação estrita de
alcance dinâmico, realce adaptativo de contraste local (CLAHE em 16-bit no espaço de luminância),
calibração de histograma e exportação automatizada para presets.
"""

from pathlib import Path
from typing import Tuple, Optional, Dict, List, Union
import numpy as np
import cv2

from .wavelets import LunarWaveletEngine


def load_lunar_image(path: Union[str, Path]) -> Tuple[np.ndarray, int]:
    """
    Carrega uma imagem lunar (TIFF, PNG, etc.) preservando o número original de bits por canal.
    Normaliza a saída para float32 no intervalo [0.0, 1.0] e padroniza a ordem de cores para RGB.

    Args:
        path: Caminho do arquivo no disco.

    Returns:
        Tupla (image_float, original_bit_depth), onde:
            image_float: array float32 em [0.0, 1.0], formato (H, W) ou (H, W, 3) em RGB.
            original_bit_depth: 8, 16 ou 32.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    # cv2.IMREAD_UNCHANGED preserva a profundidade de 16-bit se presente
    raw_img = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if raw_img is None:
        raise ValueError(f"Não foi possível ler a imagem: {path}. Formato inválido ou corrompido.")

    dtype = raw_img.dtype
    if dtype == np.uint16:
        original_bit_depth = 16
        image_float = raw_img.astype(np.float32) / 65535.0
    elif dtype == np.uint8:
        original_bit_depth = 8
        image_float = raw_img.astype(np.float32) / 255.0
    elif dtype in (np.float32, np.float64):
        original_bit_depth = 32
        image_float = np.clip(raw_img.astype(np.float32), 0.0, 1.0)
    else:
        original_bit_depth = 8
        image_float = np.clip(raw_img.astype(np.float32) / 255.0, 0.0, 1.0)

    # Padronizar para RGB se tiver 3 canais (OpenCV lê em BGR)
    if image_float.ndim == 3 and image_float.shape[2] == 3:
        image_float = cv2.cvtColor(image_float, cv2.COLOR_BGR2RGB)
    elif image_float.ndim == 3 and image_float.shape[2] == 4:
        # Descartar canal alpha se presente
        image_float = cv2.cvtColor(image_float[:, :, :3], cv2.COLOR_BGR2RGB)

    return image_float, original_bit_depth


def apply_clahe_16bit(
    image_float: np.ndarray,
    clip_limit: float = 1.5,
    tile_grid_size: Tuple[int, int] = (8, 8),
    blend_ratio: float = 0.6,
) -> np.ndarray:
    """
    Aplica equalização de histograma adaptativa (CLAHE) mantendo a precisão de 16-bit e
    atuando apenas no canal de luminância (para evitar desvio de matiz de cor).

    Args:
        image_float: Imagem float32 em [0.0, 1.0].
        clip_limit: Limite de contraste local do CLAHE (1.0 a 3.0 recomendado para relevo lunar).
        tile_grid_size: Tamanho dos blocos locais (padrão 8x8).
        blend_ratio: Fração de mistura com a imagem original (0.0 = sem efeito, 1.0 = CLAHE total).

    Returns:
        Imagem float32 processada em [0.0, 1.0].
    """
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)

    if image_float.ndim == 2:
        # Imagem monocromática
        u16 = np.clip(image_float * 65535.0, 0, 65535).astype(np.uint16)
        enhanced_u16 = clahe.apply(u16)
        enhanced_float = enhanced_u16.astype(np.float32) / 65535.0
        return np.clip(image_float * (1.0 - blend_ratio) + enhanced_float * blend_ratio, 0.0, 1.0)

    # Imagem colorida (RGB): converter para LAB em float32 para desacoplar L (luminância) de A e B (cor)
    lab = cv2.cvtColor(image_float, cv2.COLOR_RGB2LAB)
    l_channel = lab[:, :, 0]  # L em OpenCV float varia de 0.0 a 100.0

    # Escalar L para uint16 para usar a implementação acelerada de CLAHE
    l_u16 = np.clip((l_channel / 100.0) * 65535.0, 0, 65535).astype(np.uint16)
    enhanced_l_u16 = clahe.apply(l_u16)
    enhanced_l = (enhanced_l_u16.astype(np.float32) / 65535.0) * 100.0

    blended_l = l_channel * (1.0 - blend_ratio) + enhanced_l * blend_ratio
    lab[:, :, 0] = np.clip(blended_l, 0.0, 100.0)

    enhanced_rgb = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return np.clip(enhanced_rgb, 0.0, 1.0)


def stretch_tonal_range(
    image_float: np.ndarray,
    black_clip_pct: float = 0.02,
    white_clip_pct: float = 99.98,
    gamma: float = 1.0,
) -> np.ndarray:
    """
    Realiza o esticamento de histograma (black/white point stretch) e ajuste de curva gama.
    Descarta uma fração ínfima de ruído de fundo para ancorar o espaço em preto puro e
    aproveita todo o alcance dinâmico para os picos das crateras.
    """
    result = image_float.copy()

    # Calcular percentis sobre valores positivos
    positives = result[result > 0.002]
    if len(positives) > 100:
        b_val = float(np.percentile(positives, black_clip_pct))
        w_val = float(np.percentile(positives, white_clip_pct))
    else:
        b_val = float(np.min(result))
        w_val = float(np.max(result))

    if w_val > b_val:
        result = (result - b_val) / (w_val - b_val)
        result = np.clip(result, 0.0, 1.0)

    if gamma != 1.0 and gamma > 0.0:
        result = np.power(result, 1.0 / gamma)

    return np.clip(result, 0.0, 1.0)


def save_lunar_image(
    image_float: np.ndarray,
    output_path: Union[str, Path],
    bit_depth: int = 16,
) -> Path:
    """
    Salva uma imagem lunar em disco na profundidade de bits desejada (8 ou 16 bits).

    Args:
        image_float: Array float32 em [0.0, 1.0].
        output_path: Caminho de saída desejado (.tif, .png, etc.).
        bit_depth: 8 ou 16 (padrão: 16).

    Returns:
        Path do arquivo salvo.
    """
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    # Converter de RGB para BGR para escrita pelo OpenCV se for colorida
    if image_float.ndim == 3 and image_float.shape[2] == 3:
        to_write = cv2.cvtColor(image_float, cv2.COLOR_RGB2BGR)
    else:
        to_write = image_float

    if bit_depth == 16:
        data_u16 = np.clip(to_write * 65535.0, 0, 65535).astype(np.uint16)
        success = cv2.imwrite(str(out_p), data_u16)
    else:
        data_u8 = np.clip(to_write * 255.0, 0, 255).astype(np.uint8)
        success = cv2.imwrite(str(out_p), data_u8)

    if not success:
        raise IOError(f"Falha ao salvar a imagem em: {out_p}")

    return out_p


def apply_adaptive_s_curve(
    image_float: np.ndarray,
    contrast: float = 1.25,
    midtone_pivot: float = 0.35,
) -> np.ndarray:
    """
    Aplica uma curva S adaptativa centrada na meia-luz lunar, aumentando
    o gradiente tonal e a profundidade de sombras projetadas por crateras.
    """
    if contrast <= 1.0:
        return image_float

    if image_float.ndim == 2:
        x = image_float - midtone_pivot
        s = np.sign(x) * (np.abs(x) ** (1.0 / contrast)) + midtone_pivot
        return np.clip(s, 0.0, 1.0)

    # Em RGB, atua no canal de luminância L para não distorcer o balanço de cores
    lab = cv2.cvtColor(image_float, cv2.COLOR_RGB2LAB)
    l_norm = lab[:, :, 0] / 100.0
    x = l_norm - midtone_pivot
    s = np.sign(x) * (np.abs(x) ** (1.0 / contrast)) + midtone_pivot
    lab[:, :, 0] = np.clip(s, 0.0, 1.0) * 100.0
    return np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0.0, 1.0)


def apply_dual_scale_clahe(
    image_float: np.ndarray,
    fine_grid: Tuple[int, int] = (16, 16),
    coarse_grid: Tuple[int, int] = (6, 6),
    blend_ratio: float = 0.65,
) -> np.ndarray:
    """
    Aplica equalização de histograma adaptativa em dupla escala (fina para microcrateras
    e ampla para distinção entre mares e terras altas).
    """
    fine_enh = apply_clahe_16bit(image_float, clip_limit=1.6, tile_grid_size=fine_grid, blend_ratio=blend_ratio)
    coarse_enh = apply_clahe_16bit(fine_enh, clip_limit=1.2, tile_grid_size=coarse_grid, blend_ratio=0.5)
    return coarse_enh


def process_and_export_all_presets(
    input_path: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    presets: Optional[List[str]] = None,
    enable_clahe: bool = True,
    use_limb_guard: bool = True,
    export_png: bool = True,
    export_tiff: bool = True,
    custom_gamma: float = 1.0,
    custom_contrast: Optional[float] = None,
    custom_clarity: Optional[float] = None,
    custom_deconvolve: Optional[bool] = None,
) -> Dict[str, Dict[str, Path]]:
    """
    Fluxo completo e autônomo de pós-processamento:
    Carrega o TIFF empilhado, processa cada preset de wavelets com Limb Guard,
    aplica CLAHE (simples ou dual-scale), curvas S de relevo e esticamento dinâmico.

    Args:
        input_path: Caminho do TIFF empilhado original (ex: saída do AutoStakkert!).
        output_dir: Diretório de destino. Se None, cria subpasta 'processado_iris'.
        presets: Lista de presets ou grupos ('all', 'craters', 'classic').
        enable_clahe: Se True, aplica realce adaptativo de relevo 16-bit.
        use_limb_guard: Se True, ativa proteção de borda no limbo.
        export_png: Se True, gera PNG de 8-bit com alta qualidade.
        export_tiff: Se True, gera TIFF de 16-bit master.
        custom_gamma: Fator de correção de gama tonal.
        custom_contrast: Fator opcional para sobrescrever o contraste da curva S.
        custom_clarity: Fator opcional para sobrescrever o micro-contraste (Clarity).
        custom_deconvolve: Força ativação/desativação da Deconvolução Richardson-Lucy.

    Returns:
        Dicionário mapeando nome do preset aos arquivos gerados.
    """
    in_file = Path(input_path)
    if not in_file.exists():
        raise FileNotFoundError(f"Arquivo de entrada não encontrado: {input_path}")

    target_dir = Path(output_dir) if output_dir else in_file.parent / f"{in_file.stem}_processado_iris"
    target_dir.mkdir(parents=True, exist_ok=True)

    # Resolução de grupos de presets
    all_available = list(LunarWaveletEngine.PRESETS.keys())
    craters_group = ["enfatico", "crateras_profundas", "deconvolucao_extrema", "contraste_dramatico"]
    classic_group = ["suave", "equilibrado", "enfatico", "mineral"]

    resolved_presets: List[str] = []
    if presets is None or "all" in presets:
        resolved_presets = all_available
    elif "craters" in presets:
        resolved_presets = craters_group
    elif "classic" in presets:
        resolved_presets = classic_group
    else:
        for p in presets:
            if p in all_available and p not in resolved_presets:
                resolved_presets.append(p)

    if not resolved_presets:
        resolved_presets = all_available

    engine = LunarWaveletEngine(levels=5)
    img_float, original_depth = load_lunar_image(in_file)

    results: Dict[str, Dict[str, Path]] = {}

    for preset_name in resolved_presets:
        p_cfg = LunarWaveletEngine.PRESETS[preset_name]

        # 1. Aplicação de Wavelets com Deconvolução, Limb Guard e Clarity
        sharpened = engine.process_preset(
            img_float,
            preset_name=preset_name,
            use_limb_guard=use_limb_guard,
            override_deconvolve=custom_deconvolve,
            override_clarity=custom_clarity,
        )

        # 2. Realce de Relevo Local (CLAHE Simples ou Dual-Scale)
        if enable_clahe:
            if p_cfg.get("dual_clahe", False):
                clahe_enhanced = apply_dual_scale_clahe(sharpened)
            else:
                ratio = 0.4 if preset_name == "suave" else 0.65
                clahe_enhanced = apply_clahe_16bit(sharpened, clip_limit=1.5, blend_ratio=ratio)
        else:
            clahe_enhanced = sharpened

        # 3. Curva S Adaptativa para Esculpir Crateras e Terminador
        contrast_factor = custom_contrast if custom_contrast is not None else p_cfg.get("s_curve_contrast", 1.0)
        tonal_sculpted = apply_adaptive_s_curve(clahe_enhanced, contrast=contrast_factor)

        # 4. Calibração Tonal Final (Esticamento Dinâmico)
        final_img = stretch_tonal_range(tonal_sculpted, gamma=custom_gamma)

        # 5. Exportação dos formatos solicitados
        preset_files: Dict[str, Path] = {}
        base_name = f"{in_file.stem}_{preset_name}"

        if export_tiff:
            tiff_path = target_dir / f"{base_name}.tif"
            save_lunar_image(final_img, tiff_path, bit_depth=16)
            preset_files["tiff"] = tiff_path

        if export_png:
            png_path = target_dir / f"{base_name}.png"
            save_lunar_image(final_img, png_path, bit_depth=8)
            preset_files["png"] = png_path

        results[preset_name] = preset_files

    return results
