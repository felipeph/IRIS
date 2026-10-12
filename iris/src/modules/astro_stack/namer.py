"""Gerador de nomes e caminhos padronizados para o empilhamento lunar (8_Astro_Stack)."""
from pathlib import Path
from typing import Union


def resolve_astro_stack_dir(session_rel_dir: Union[str, Path], dest_root: Union[str, Path]) -> Path:
    """Resolve o diretório físico definitivo na raiz 8_Astro_Stack.
    
    Exemplo:
        session_rel_dir: 5_Astrofotografia/Lua/2026/08/28/sessao_19-05-55
        retorna: dest_root / 8_Astro_Stack / Lua / 2026 / 08 / 28 / sessao_19-05-55
    """
    rel_path = Path(session_rel_dir)
    parts = list(rel_path.parts)
    
    # Substitui 5_Astrofotografia por 8_Astro_Stack
    if parts and parts[0] == "5_Astrofotografia":
        parts[0] = "8_Astro_Stack"
    elif parts and parts[0] != "8_Astro_Stack":
        parts = ["8_Astro_Stack"] + parts

    return Path(dest_root).joinpath(*parts)


def build_stack_filename(
    date_str: str,
    time_str: str,
    camera_model: str,
    keep_percent: int,
    ext: str = "tiff"
) -> str:
    """Gera o nome de arquivo oficial do TIFF empilhado.
    
    Exemplo:
        2026-08-28_19-05-55_Canon-SX60_stack25p_mono16.tiff
    """
    cam = camera_model.replace(" ", "-").replace("_", "-") if camera_model else "Astro"
    # Remove caracteres inválidos para nomes de arquivos
    cam = "".join(c for c in cam if c.isalnum() or c in ("-", "."))
    return f"{date_str}_{time_str}_{cam}_stack{keep_percent}p_mono16.{ext}"


def build_preview_filename(
    date_str: str,
    time_str: str,
    camera_model: str
) -> str:
    """Gera o nome da imagem de prévia 8-bit normalizada."""
    cam = camera_model.replace(" ", "-").replace("_", "-") if camera_model else "Astro"
    cam = "".join(c for c in cam if c.isalnum() or c in ("-", "."))
    return f"{date_str}_{time_str}_{cam}_preview.png"


def build_report_filename(
    date_str: str,
    time_str: str,
    camera_model: str
) -> str:
    """Gera o nome do relatório JSON de metadados da sessão."""
    cam = camera_model.replace(" ", "-").replace("_", "-") if camera_model else "Astro"
    cam = "".join(c for c in cam if c.isalnum() or c in ("-", "."))
    return f"{date_str}_{time_str}_{cam}_report.json"
