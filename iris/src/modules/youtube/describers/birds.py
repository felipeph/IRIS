import json
from pathlib import Path
from typing import Dict, Any, List, Optional

from .formatting import _extract_temporal_context, sanitize_hashtag
from .geo import resolve_project_geolocation


def _normalize_bird_record(b: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza o dicionário de identificação de ave garantindo acesso aos campos fundamentais."""
    d = dict(b)
    meta = d.get("metadata_json") or {}
    if not isinstance(meta, dict):
        meta = {}

    c_pt = (d.get("species_common") or meta.get("species_common") or "").strip()
    sci = (d.get("species_scientific") or meta.get("species_scientific") or "").strip()
    c_en = (d.get("species_common_en") or meta.get("species_common_en") or meta.get("common_en") or "").strip()
    fam = (d.get("family") or meta.get("family") or "").strip()
    order = (d.get("order") or meta.get("order") or "").strip()
    conf = float(d.get("confidence") or meta.get("confidence") or 0.0)
    taxon_id = d.get("taxon_id") or meta.get("taxon_id")

    return {
        "species_common": c_pt,
        "species_scientific": sci,
        "species_common_en": c_en,
        "family": fam,
        "order": order,
        "confidence": conf,
        "taxon_id": taxon_id,
        "metadata_json": meta
    }


def resolve_bird_identification(record: Dict[str, Any], project: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """
    Localiza o registro consolidado de identificação de ave para o vídeo (ou timelapse):
    1. No próprio record["metadata_json"]["bird_identification"]
    2. Consultando project.get_bird_identification(...) para cada caminho de origem
    3. Casamento por itens do projeto ou nome de arquivo na tabela bird_identifications
    Retorna dicionário normalizado ou None se não houver espécie de ave identificada.
    """
    meta = record.get("metadata_json") or {}
    if isinstance(meta, dict) and meta.get("bird_identification"):
        b_info = dict(meta["bird_identification"])
        if b_info.get("species_common") or b_info.get("species_scientific"):
            return _normalize_bird_record(b_info)

    if not project:
        return None

    # Tenta obter caminhos de origem
    raw_paths = record.get("source_video_paths") or record.get("source_files") or []
    if isinstance(raw_paths, str):
        try:
            src_paths = json.loads(raw_paths)
        except Exception:
            src_paths = [raw_paths] if raw_paths else []
    elif isinstance(raw_paths, (list, tuple)):
        src_paths = list(raw_paths)
    else:
        src_paths = []

    if record.get("output_video_path"):
        src_paths.append(record["output_video_path"])
    if record.get("sequence_dir"):
        src_paths.append(record["sequence_dir"])
    if record.get("item_path"):
        src_paths.append(record["item_path"])

    # 1. Consulta direta por item_path no banco
    if hasattr(project, "get_bird_identification"):
        for p in src_paths:
            if not p:
                continue
            rec_id = project.get_bird_identification(str(p))
            if not rec_id:
                try:
                    rec_id = project.get_bird_identification(str(Path(p).resolve()))
                except Exception:
                    pass
            if rec_id and (rec_id.get("species_common") or rec_id.get("species_scientific")):
                return _normalize_bird_record(rec_id)

    # 2. Varredura em list_bird_identifications()
    if hasattr(project, "list_bird_identifications"):
        all_birds = project.list_bird_identifications()
        if all_birds:
            src_names = {Path(p).name.lower() for p in src_paths if p}
            for b in all_birds:
                b_path_str = b.get("item_path", "")
                b_name = Path(b_path_str).name.lower()
                if b_name and b_name in src_names:
                    return _normalize_bird_record(b)

            seq_dir = record.get("sequence_dir")
            if seq_dir:
                seq_p = Path(seq_dir).resolve()
                for b in all_birds:
                    b_p = Path(b.get("item_path", "")).resolve()
                    if b_p.parent == seq_p:
                        return _normalize_bird_record(b)

    return None


def build_bird_youtube_title(
    video_path: Path,
    record: Dict[str, Any],
    bird_info: Dict[str, Any],
    project: Optional[Any] = None,
    loc: Optional[Any] = None
) -> str:
    """
    Gera título específico para vídeos de aves no YouTube:
    {Data} ({Hora}) | {Nome_PT} ({Nome_Cientifico}) - {Nome_EN} | {Cidade}, {UF}
    - NUNCA inclui 'Vídeo 4K UHD' no título.
    - Data e hora primeiro, seguidos da espécie e da cidade/UF.
    - Adapta progressivamente para nunca ultrapassar o limite estrito de 100 caracteres.
    """
    c_pt = bird_info.get("species_common", "").strip()
    sci = bird_info.get("species_scientific", "").strip()
    c_en = bird_info.get("species_common_en", "").strip()

    if sci and c_pt:
        bird_taxon = f"{c_pt} ({sci})"
    elif c_pt:
        bird_taxon = c_pt
    else:
        bird_taxon = sci or "Aves da Natureza"

    if c_en and c_en.lower() != c_pt.lower() and c_en.lower() != sci.lower():
        bird_header = f"{bird_taxon} - {c_en}"
    else:
        bird_header = bird_taxon

    date_part, time_str = _extract_temporal_context(video_path, record)
    temporal_full = f"{date_part} {time_str}".strip() if time_str else date_part

    if loc is None:
        loc = resolve_project_geolocation(record, project)

    loc_str = ""
    if loc and getattr(loc, "city", None):
        loc_str = f"{loc.city}, {loc.state}" if getattr(loc, "state", None) else loc.city

    # 1. Formato completo: Data (Hora) | Nome PT (Científico) - EN | Cidade, UF
    elements = [temporal_full, bird_header]
    if loc_str:
        elements.append(loc_str)
    candidate = " | ".join(elements)
    if len(candidate) <= 100:
        return candidate

    # 2. Formato condensado (sem nome em inglês): Data (Hora) | Nome PT (Científico) | Cidade, UF
    if bird_header != bird_taxon:
        elements_no_en = [temporal_full, bird_taxon]
        if loc_str:
            elements_no_en.append(loc_str)
        cand_no_en = " | ".join(elements_no_en)
        if len(cand_no_en) <= 100:
            return cand_no_en

    # 3. Formato sem Cidade se exceder: Data (Hora) | Nome PT (Científico) - EN
    cand_no_loc = f"{temporal_full} | {bird_header}"
    if len(cand_no_loc) <= 100:
        return cand_no_loc

    # 4. Apenas Data (Hora) | Nome PT (Científico)
    cand_minimal = f"{temporal_full} | {bird_taxon}"
    if len(cand_minimal) <= 100:
        return cand_minimal

    # 5. Truncamento seguro
    return candidate[:97] + "..."


def format_bird_taxonomy_block(bird_info: Dict[str, Any]) -> str:
    """Gera bloco de texto dedicado com a ficha taxonômica completa da ave."""
    c_pt = bird_info.get("species_common", "").strip() or "Espécie não informada"
    c_en = bird_info.get("species_common_en", "").strip()
    sci = bird_info.get("species_scientific", "").strip() or "Indeterminado"
    fam = bird_info.get("family", "").strip() or "Não informada"
    order = bird_info.get("order", "").strip() or "Não informada"
    conf = float(bird_info.get("confidence", 0.0))
    conf_pct = f"{conf * 100:.1f}%" if conf > 0.0 else "Classificação confirmada"
    taxon_id = bird_info.get("taxon_id")

    lines = [
        "🐦 IDENTIFICAÇÃO TAXONÔMICA (AVES):",
        f"• Espécie (Nome Popular): {c_pt}",
    ]
    if c_en and c_en.lower() != c_pt.lower():
        lines.append(f"• Nome em Inglês: {c_en}")
    lines.append(f"• Nome Científico: {sci}")
    lines.append(f"• Família: {fam}")
    lines.append(f"• Ordem: {order}")
    lines.append("• Classe: Aves")
    lines.append("• Reino: Animalia")
    lines.append(f"• Grau de Certeza: {conf_pct} (Visão Computacional iNaturalist)")
    if taxon_id:
        lines.append(f"• Ficha da Espécie no iNaturalist: https://www.inaturalist.org/taxa/{taxon_id}")

    return "\n".join(lines)


def build_bird_hashtags(bird_info: Dict[str, Any]) -> List[str]:
    """Gera lista de hashtags limpas para a ave (sem acentos, sem espaços, PascalCase)."""
    hashtags = []

    c_pt = sanitize_hashtag(bird_info.get("species_common", ""))
    sci = sanitize_hashtag(bird_info.get("species_scientific", ""))
    c_en = sanitize_hashtag(bird_info.get("species_common_en", ""))
    fam = sanitize_hashtag(bird_info.get("family", ""))
    order = sanitize_hashtag(bird_info.get("order", ""))

    for tag in [c_pt, sci, c_en, fam, order]:
        if tag and f"#{tag}" not in hashtags:
            hashtags.append(f"#{tag}")

    default_bird_tags = [
        "#Aves", "#Birdwatching", "#ObservacaoDeAves",
        "#Ornitologia", "#Passarinhada", "#FaunaSilvestre"
    ]
    for d in default_bird_tags:
        if d not in hashtags:
            hashtags.append(d)

    return hashtags


def resolve_bird_target_playlists(
    bird_info: Dict[str, Any],
    yt_config: Dict[str, Any],
    loc: Optional[Any] = None
) -> List[str]:
    """
    Determina todas as playlists do YouTube onde o vídeo da ave deve ser publicado.
    Suporta multi-playlists simultâneas:
    1. Playlist geral de aves (ex: 'Birds 4K')
    2. Playlist de Pássaros da Cidade (ex: 'Pássaros de Passos - MG') se loc disponível
    3. Playlist do Nome Científico (ex: 'Pitangus sulphuratus')
    4. Playlist do Nome Popular em PT (ex: 'Bem-te-vi')
    5. Playlist do Nome Popular em EN (ex: 'Great Kiskadee')
    """
    bp_cfg = yt_config.get("bird_playlists") or {}
    general_pl = yt_config.get("bird_playlist", "Birds 4K")
    include_general = bp_cfg.get("general", True)
    include_sci = bp_cfg.get("scientific_name", True)
    include_pt = bp_cfg.get("common_name_pt", True)
    include_en = bp_cfg.get("common_name_en", True)
    include_geo = bp_cfg.get("by_city", True)

    targets: List[str] = []
    seen = set()

    def _add(pl_name: str):
        clean = pl_name.strip()
        if clean and clean.lower() not in seen:
            seen.add(clean.lower())
            targets.append(clean)

    if include_general and general_pl:
        _add(general_pl)

    if include_geo and loc and getattr(loc, "city", None):
        city_name = loc.city.strip()
        state_name = getattr(loc, "state", "").strip()
        if city_name:
            geo_pl = f"Pássaros de {city_name} - {state_name}" if state_name else f"Pássaros de {city_name}"
            _add(geo_pl)

    if include_sci:
        sci = bird_info.get("species_scientific", "").strip()
        if sci:
            _add(sci)

    if include_pt:
        c_pt = bird_info.get("species_common", "").strip()
        if c_pt:
            _add(c_pt)

    if include_en:
        c_en = bird_info.get("species_common_en", "").strip()
        if c_en:
            _add(c_en)

    if not targets:
        _add(yt_config.get("video_playlist", "Natureza 4K UHD"))

    return targets
