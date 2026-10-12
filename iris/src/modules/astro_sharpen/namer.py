"""Gerador de nomes e caminhos padronizados para o aprimoramento lunar (9_Astro_Sharpening)."""
from pathlib import Path
from typing import Union, Tuple


def resolve_astro_sharpen_dir(stack_dir_or_path: Union[str, Path], dest_root: Union[str, Path]) -> Path:
    """Resolve o diretório físico definitivo na raiz 9_Astro_Sharpening.
    
    Exemplo:
        8_Astro_Stack/Lua/2026/08/28/sessao_19-05-55
        -> dest_root / 9_Astro_Sharpening / Lua / 2026 / 08 / 28 / sessao_19-05-55
    """
    p = Path(stack_dir_or_path)
    if p.is_file():
        p = p.parent

    dest_root_p = Path(dest_root)
    # Tenta obter relativo ao dest_root
    try:
        rel_p = p.relative_to(dest_root_p)
    except ValueError:
        rel_p = p

    parts = list(rel_p.parts)
    if parts and parts[0] == "8_Astro_Stack":
        parts[0] = "9_Astro_Sharpening"
    elif parts and parts[0] != "9_Astro_Sharpening":
        parts = ["9_Astro_Sharpening"] + parts

    return dest_root_p.joinpath(*parts)


def build_sharpened_filenames(stack_stem: str, preset: str) -> Tuple[str, str]:
    """Gera os nomes de arquivo TIFF e PNG correspondentes ao preset aplicado.
    
    Exemplo:
        stack_stem: 2026-08-28_19-05-55_Canon-SX60_stack25p_mono16
        preset: registax_fiel
        retorna: (2026-08-28_19-05-55_Canon-SX60_stack25p_registax_fiel.tiff, ...png)
    """
    base = stack_stem.replace("_mono16", "")
    tiff_name = f"{base}_{preset}.tiff"
    png_name = f"{base}_{preset}.png"
    return tiff_name, png_name
