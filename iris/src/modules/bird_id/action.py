"""
Módulo de Ações Físicas e Metadados de Aves (IRIS Bird ID).
Executa as ações de alta certeza:
1. Renomeação tripla: [Nome_Popular_PT]_[Nome_Científico]_[Nome_Popular_EN]
2. Movimentação para subpasta da espécie dentro da categoria (ex: 2_AlbunsDatas/.../{Nome_PT}/)
3. Injeção de metadados taxonômicos EXIF/IPTC/XMP via ExifTool
4. Sincronização atômica do estado no SQLite do projeto
"""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from src.core.config import config
from src.core.project import Project, ProjectItem


def sanitize_bird_token(name: str) -> str:
    """Higieniza um token de nome de ave para uso seguro em arquivos e pastas no Windows/Linux."""
    if not name:
        return ""
    # Substitui caracteres inválidos e pontuações por hífen
    clean = re.sub(r'[\\/*?:"<>|.]', "-", name.strip())
    # Converte espaços em hífens
    clean = re.sub(r"\s+", "-", clean)
    # Remove múltiplos hífens ou traços consecutivos
    clean = re.sub(r"-+", "-", clean)
    return clean.strip("-_ ")


def build_bird_filename(current_name: str, common_pt: str, scientific: str, common_en: str = "") -> str:
    """
    Constrói o nome de arquivo enriquecido com a taxonomia tripla da ave:
    {Stem_Original}_[{Nome_Popular_PT}]_[{Nome_Cientifico}]_[{Nome_Popular_EN}].{ext}
    """
    p = Path(current_name)
    stem = p.stem
    ext = p.suffix

    t_pt = sanitize_bird_token(common_pt)
    t_sci = sanitize_bird_token(scientific)
    t_en = sanitize_bird_token(common_en)

    tokens = []
    if t_pt:
        tokens.append(f"[{t_pt}]")
    if t_sci:
        tokens.append(f"[{t_sci}]")
    if t_en and t_en.lower() != t_pt.lower():
        tokens.append(f"[{t_en}]")

    if not tokens:
        return current_name

    bird_tag = "_".join(tokens)

    # Evita duplicação se o nome já contiver a tag
    if bird_tag in stem:
        return current_name

    return f"{stem}_{bird_tag}{ext}"


def write_bird_exif_tags(
    file_path: Path,
    common_pt: str,
    scientific: str,
    common_en: str = "",
    family: str = "",
    order: str = ""
) -> bool:
    """
    Injeta metadados taxonômicos (IPTC, XMP e EXIF) no arquivo usando ExifTool sem recodificar pixels.
    """
    env_exif = os.getenv("IRIS_EXIFTOOL_PATH")
    exiftool_bin = env_exif if env_exif else shutil.which("exiftool")
    if not exiftool_bin:
        return False

    keywords = ["Aves"]
    if common_pt:
        keywords.append(common_pt)
    if common_en and common_en.lower() != common_pt.lower():
        keywords.append(common_en)
    if scientific:
        keywords.append(scientific)
    if family:
        keywords.append(family)
    if order:
        keywords.append(order)

    args = [exiftool_bin, "-overwrite_original", "-charset", "iptc=UTF8", "-charset", "filename=UTF8"]

    for kw in set(keywords):
        args.append(f"-Keywords+={kw}")
        args.append(f"-Subject+={kw}")

    if common_pt and scientific:
        hier = f"Fauna|Aves|{family or 'Outros'}|{scientific}|{common_pt}"
        args.append(f"-HierarchicalSubject+={hier}")

    title_parts = [common_pt]
    if scientific:
        title_parts.append(f"({scientific})")
    if common_en:
        title_parts.append(f"- {common_en}")
    caption = " ".join(title_parts)
    args.append(f"-Caption-Abstract={caption}")
    args.append(f"-Description={caption}")

    args.append(str(file_path))

    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False


def apply_bird_organization(
    item: ProjectItem,
    project: Project,
    record: Dict[str, Any],
    bird_cfg: Dict[str, Any]
) -> Path:
    """
    Aplica a tripla ação de alta certeza (Renomeação + Subpasta + EXIF) em item identificado.
    Atualiza atomicamente o SQLite do projeto.
    """
    current_path = Path(item.organized_path or item.staging_path or item.original_path)
    if not current_path.exists():
        return current_path

    min_confidence = float(bird_cfg.get("min_species_confidence", 0.75))
    confidence = float(record.get("confidence", 0.0))
    needs_review = bool(record.get("needs_review", False))

    # Filtro estrito de alta certeza
    if confidence < min_confidence or needs_review:
        return current_path

    rename_files = bool(bird_cfg.get("rename_files", True))
    organize_subfolder = bool(bird_cfg.get("organize_in_subfolders", True))
    write_exif = bool(bird_cfg.get("write_exif_tags", True))

    common_pt = record.get("species_common", "")
    sci = record.get("species_scientific", "")
    meta_dict = record.get("metadata_json", {}) if isinstance(record.get("metadata_json"), dict) else {}
    common_en = record.get("species_common_en", "") or meta_dict.get("species_common_en", "") or meta_dict.get("common_en", "")
    family = record.get("family", "") or meta_dict.get("family", "")
    order = record.get("order", "") or meta_dict.get("order", "")

    # 1. Determina nome de arquivo
    if rename_files and (common_pt or sci):
        new_filename = build_bird_filename(current_path.name, common_pt, sci, common_en)
    else:
        new_filename = current_path.name

    # 2. Determina diretório de destino
    if organize_subfolder and common_pt:
        sub_dir_name = sanitize_bird_token(common_pt)
        # Se o parent já for a subpasta da espécie, não aninha novamente
        if current_path.parent.name.lower() == sub_dir_name.lower():
            target_dir = current_path.parent
        else:
            target_dir = current_path.parent / sub_dir_name
    else:
        target_dir = current_path.parent

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / new_filename

    # 3. Movimentação / Renomeação Física no Disco
    if target_path.resolve() != current_path.resolve():
        if target_path.exists():
            # Se colidir com arquivo pré-existente
            target_path = target_dir / f"{target_path.stem}_1{target_path.suffix}"
        shutil.move(str(current_path), str(target_path))

    # 4. Injeção de Metadados EXIF/IPTC
    if write_exif and target_path.exists():
        write_bird_exif_tags(target_path, common_pt, sci, common_en, family, order)

    # 5. Atualização Atômica no SQLite
    dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
    item.organized_path = str(target_path.resolve())
    item.target_filename = target_path.name
    try:
        item.relative_dest_dir = str(target_path.parent.relative_to(dest_root))
    except (ValueError, Exception):
        pass

    with project.transaction():
        project.save_item(item)
        if hasattr(project, "update_bird_identification_path"):
            project.update_bird_identification_path(str(current_path.resolve()), str(target_path.resolve()))
            if str(current_path) != str(current_path.resolve()):
                project.update_bird_identification_path(str(current_path), str(target_path.resolve()))

    return target_path
