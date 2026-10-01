"""Módulo de Astrofotografia Lunar do IRIS.

Oferece motor de wavelets à trous multiescala com proteção de limbo (Limb Guard),
pós-processamento adaptativo (CLAHE 16-bit, curvas tonais) e CLI autônomo para
substituir o fluxo manual de ferramentas legadas (RegiStax).
"""

from .wavelets import LunarWaveletEngine
from .postprocess import (
    load_lunar_image,
    save_lunar_image,
    process_and_export_all_presets,
    apply_clahe_16bit,
    apply_dual_scale_clahe,
    apply_adaptive_s_curve,
)

__all__ = [
    "LunarWaveletEngine",
    "load_lunar_image",
    "save_lunar_image",
    "process_and_export_all_presets",
    "apply_clahe_16bit",
    "apply_dual_scale_clahe",
    "apply_adaptive_s_curve",
]
