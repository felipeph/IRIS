"""
Módulo de Ações Físicas e Metadados de Aves (IRIS Bird ID).
Executa as ações de alta certeza:
1. Renomeação tripla: [Nome_Popular_PT]_[Nome_Científico]_[Nome_Popular_EN]
2. Movimentação para subpasta da espécie dentro da categoria (ex: 2_AlbunsDatas/.../{Nome_PT}/)
3. Injeção de metadados taxonômicos EXIF/IPTC/XMP via ExifTool
4. Sincronização atômica do estado no SQLite do projeto
"""

import unicodedata
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List

from src.core.config import config
from src.core.project import Project, ProjectItem
from src.core.cleanup import clean_empty_parent_dirs


def sanitize_bird_token(name: str) -> str:
    """
    Higieniza um token de nome de ave para uso seguro em pastas e arquivos em qualquer SO:
    - Remove acentos e diacríticos (ASCII limpo: ex: Sabiá -> Sabia)
    - Substitui caracteres inválidos e pontuações por hífen
    - Converte espaços em hífens
    - Remove múltiplos hífens ou traços consecutivos
    """
    if not name:
        return ""
    # Remove acentuação mantendo os caracteres base
    clean = unicodedata.normalize("NFKD", name.strip()).encode("ascii", "ignore").decode("utf-8")
    # Substitui caracteres inválidos e pontuações por hífen
    clean = re.sub(r'[\\/*?:"<>|.,;()\[\]{}]', "-", clean)
    # Converte espaços em hífens
    clean = re.sub(r"\s+", "-", clean)
    # Remove múltiplos hífens ou traços consecutivos
    clean = re.sub(r"-+", "-", clean)
    return clean.strip("-_ ")


def build_bird_filename(current_name: str, common_pt: str, scientific: str, common_en: str = "") -> str:
    """
    Constrói o nome de arquivo enriquecido com taxonomia segura (apenas _ e sem acentos/espaços),
    posicionando o nome popular em português e científico logo após a data e hora e antes
    das demais informações técnicas:
    {Data}_{Hora}_{Nome_Popular_PT}_{Nome_Cientifico}_{Info_Tecnica}.{ext}
    Exemplo: 2026-09-06_15-10-00_Beija-flor-de-fronte-violeta_Thalurania-glaucopis_Canon-SX60_16MP_IMG_1234.JPG
    """
    p = Path(current_name)
    stem = p.stem
    ext = p.suffix

    t_pt = sanitize_bird_token(common_pt)
    t_sci = sanitize_bird_token(scientific)

    tokens = [t for t in [t_pt, t_sci] if t]
    if not tokens:
        return current_name

    bird_tag = "_".join(tokens)

    # Expressões regulares para localizar prefixo temporal (data + hora ou data)
    dt_pattern = r"^(\d{4}[-_]?\d{2}[-_]?\d{2}[-_]\d{2}[-_]?\d{2}[-_]?\d{2})(?:_(.*))?$"
    d_pattern = r"^(\d{4}[-_]?\d{2}[-_]?\d{2})(?:_(.*))?$"

    m = re.match(dt_pattern, stem) or re.match(d_pattern, stem)
    if m:
        prefix = m.group(1)
        rest = m.group(2) or ""

        # Se já estiver com a tag taxonômica logo após o prefixo, é idempotente
        if rest == bird_tag or rest.startswith(f"{bird_tag}_"):
            return current_name

        # Limpar tokens taxonômicos pré-existentes de rest (migração do padrão antigo com sufixo)
        clean_rest = rest
        for tok in [bird_tag, t_pt, t_sci]:
            if tok:
                clean_rest = clean_rest.replace(tok, "")
        clean_rest = re.sub(r"[-_]{2,}", "_", clean_rest).strip("-_")

        if clean_rest:
            new_stem = f"{prefix}_{bird_tag}_{clean_rest}"
        else:
            new_stem = f"{prefix}_{bird_tag}"
        return f"{new_stem}{ext}"
    else:
        # Sem prefixo de data/hora: insere a tag no início do stem antes dos nomes de câmera/originais
        if stem == bird_tag or stem.startswith(f"{bird_tag}_"):
            return current_name
        clean_stem = stem
        for tok in [bird_tag, t_pt, t_sci]:
            if tok:
                clean_stem = clean_stem.replace(tok, "")
        clean_stem = re.sub(r"[-_]{2,}", "_", clean_stem).strip("-_")
        if clean_stem:
            return f"{bird_tag}_{clean_stem}{ext}"
        return f"{bird_tag}{ext}"


def write_bird_exif_tags(
    file_path: Path,
    common_pt: str,
    scientific: str,
    common_en: str = "",
    family: str = "",
    order: str = "",
    extra_keywords: Optional[List[str]] = None
) -> bool:
    """
    Injeta metadados taxonômicos (IPTC, XMP e EXIF) no arquivo usando ExifTool sem recodificar pixels.
    Utiliza argfile temporário com codificação UTF-8 explícita para compatibilidade universal
    e preservação perfeita de acentuação e espaços no Google Fotos, Apple Fotos, Lightroom e Windows.
    """
    env_exif = os.getenv("IRIS_EXIFTOOL_PATH")
    exiftool_bin = env_exif if env_exif else shutil.which("exiftool")
    if not exiftool_bin:
        return False

    keywords = ["Aves"]
    if extra_keywords:
        for ek in extra_keywords:
            clean_ek = str(ek or "").strip()
            if clean_ek and clean_ek not in keywords:
                keywords.append(clean_ek)
    for kw in [common_pt, scientific, common_en, family, order]:
        if kw and kw not in keywords:
            keywords.append(kw)

    title = f"{common_pt} ({scientific})" if scientific else common_pt
    title_parts = [common_pt]
    if scientific:
        title_parts.append(f"({scientific})")
    if common_en and common_en.lower() != common_pt.lower():
        title_parts.append(f"- {common_en}")
    caption = " ".join(title_parts)

    lines = [
        "-overwrite_original",
        "-charset", "UTF8",
        "-charset", "iptc=UTF8",
        "-charset", "filename=UTF8",
        "-codedcharacterset=utf8",
    ]

    for kw in keywords:
        lines.append(f"-Keywords+={kw}")
        lines.append(f"-Subject+={kw}")

    if common_pt and scientific:
        hier = f"Fauna|Aves|{family or 'Outros'}|{scientific}|{common_pt}"
        lines.append(f"-HierarchicalSubject+={hier}")

    # Descrições e Legendas (Google Fotos, Flickr, DigiKam)
    lines.append(f"-Caption-Abstract={caption}")
    lines.append(f"-Description={caption}")
    lines.append(f"-ImageDescription={caption}")

    # Títulos e Nomes de Objeto
    lines.append(f"-Title={title}")
    lines.append(f"-ObjectName={title}")

    # Tags nativas do Windows Explorer (UTF-16LE / UTF-8)
    lines.append(f"-XPTitle={title}")
    lines.append(f"-XPComment={caption}")
    lines.append(f"-XPKeywords={';'.join(keywords)}")

    lines.append(str(file_path.resolve()))

    argfile = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
            argfile = f.name

        cmd = [exiftool_bin, "-charset", "UTF8", "-@", argfile]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return proc.returncode == 0
    except Exception:
        return False
    finally:
        if argfile:
            try:
                os.unlink(argfile)
            except OSError:
                pass


def apply_bird_metadata(
    file_path: Path,
    record: Dict[str, Any],
    extra_keywords: Optional[List[str]] = None
) -> bool:
    """
    Aplica metadados taxonômicos EXIF/IPTC/XMP ao arquivo indicado com base no registro.
    Suporta inclusão de palavras-chave extras (ex: tags de geolocalização).
    """
    if not file_path.exists():
        return False

    common_pt = record.get("species_common", "")
    sci = record.get("species_scientific", "")
    meta_dict = record.get("metadata_json", {}) if isinstance(record.get("metadata_json"), dict) else {}
    common_en = record.get("species_common_en", "") or meta_dict.get("species_common_en", "") or meta_dict.get("common_en", "")
    family = record.get("family", "") or meta_dict.get("family", "")
    order = record.get("order", "") or meta_dict.get("order", "")

    return write_bird_exif_tags(file_path, common_pt, sci, common_en, family, order, extra_keywords=extra_keywords)


def apply_bird_physical_move(
    item: ProjectItem,
    project: Project,
    record: Dict[str, Any],
    bird_cfg: Dict[str, Any]
) -> Path:
    """
    Aplica exclusivamente a movimentação física e renomeação taxonômica no disco e SQLite:
    1. Renomeação segura: {stem}_{Nome_PT}_{Nome_Cientifico}.{ext}
    2. Subpasta sanitizada (sem espaço e sem acento): {Nome_PT}/ ou {Nome_PT}/rajada_HH-MM-SS/
    3. Sincronização atômica no SQLite
    """
    current_path = Path(item.organized_path or item.staging_path or item.original_path)
    if not current_path.exists():
        return current_path

    min_confidence = float(bird_cfg.get("min_species_confidence", 0.70))
    confidence = float(record.get("confidence", 0.0))
    needs_review = bool(record.get("needs_review", False))
    meta_dict = record.get("metadata_json", {}) if isinstance(record.get("metadata_json"), dict) else {}
    is_early_exit = bool(meta_dict.get("burst_early_exit", False))

    # Filtro estrito de alta certeza (Abordagem B: early exit com needs_review == False é aceito)
    if needs_review:
        return current_path

    if confidence < min_confidence and not is_early_exit:
        return current_path

    rename_files = bool(bird_cfg.get("rename_files", True))
    organize_subfolder = bool(bird_cfg.get("organize_in_subfolders", True))

    common_pt = record.get("species_common", "")
    sci = record.get("species_scientific", "")
    meta_dict = record.get("metadata_json", {}) if isinstance(record.get("metadata_json"), dict) else {}
    common_en = record.get("species_common_en", "") or meta_dict.get("species_common_en", "") or meta_dict.get("common_en", "")

    # 1. Determina nome de arquivo
    if rename_files and (common_pt or sci):
        new_filename = build_bird_filename(current_path.name, common_pt, sci, common_en)
    else:
        new_filename = current_path.name

    # 2. Determina diretório de destino
    if organize_subfolder and common_pt:
        sub_dir_name = sanitize_bird_token(common_pt)
        parent_name = current_path.parent.name.lower()

        if parent_name.startswith("rajada"):
            # Caso de foto em rajada: organizamos dentro da pasta da espécie daquela data:
            # ex: 2_AlbunsDatas/YYYY/MM/DD/{Nome_PT}/rajada_HH-MM-SS/
            if current_path.parent.parent.name.lower() == sub_dir_name.lower():
                # Idempotência: já está dentro de {Nome_PT}/rajada_...
                target_dir = current_path.parent
            else:
                if current_path.parent.parent.name.isdigit():
                    date_dir = current_path.parent.parent
                else:
                    date_dir = current_path.parent.parent.parent
                target_dir = date_dir / sub_dir_name / current_path.parent.name
        else:
            # Caso de foto avulsa ou vídeo: 2_AlbunsDatas/YYYY/MM/DD/{Nome_PT}/
            if parent_name == sub_dir_name.lower():
                target_dir = current_path.parent
            elif current_path.parent.name.isdigit():
                target_dir = current_path.parent / sub_dir_name
            else:
                target_dir = current_path.parent.parent / sub_dir_name
    else:
        target_dir = current_path.parent

    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / new_filename

    # 3. Movimentação / Renomeação Física no Disco
    old_parent = current_path.parent

    if target_path.resolve() != current_path.resolve():
        if target_path.exists():
            # Se colidir com arquivo pré-existente
            target_path = target_dir / f"{target_path.stem}_1{target_path.suffix}"
        shutil.move(str(current_path), str(target_path))

        # Se a pasta de origem ficou vazia, realiza poda ascendente até a raiz do IRIS
        dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
        if old_parent.resolve() != target_dir.resolve() and old_parent.exists():
            clean_empty_parent_dirs(old_parent, stop_at_dir=dest_root)

    # 4. Atualização Atômica no SQLite
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


def apply_bird_organization(
    item: ProjectItem,
    project: Project,
    record: Dict[str, Any],
    bird_cfg: Dict[str, Any]
) -> Path:
    """
    Função retrocompatível que executa a movimentação física e, opcionalmente,
    a injeção de metadados EXIF caso 'write_exif_tags' esteja ativo no bird_cfg.
    """
    target_path = apply_bird_physical_move(item, project, record, bird_cfg)
    write_exif = bool(bird_cfg.get("write_exif_tags", False))
    if write_exif and target_path.exists():
        apply_bird_metadata(target_path, record)
    return target_path

