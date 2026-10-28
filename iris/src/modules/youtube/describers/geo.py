import unicodedata
from typing import Dict, Any, List, Optional

from src.core.geo import GeoService, GeoLocation
from .formatting import sanitize_hashtag


BR_STATE_TO_UF = {
    "acre": "AC", "alagoas": "AL", "amapa": "AP", "amazonas": "AM",
    "bahia": "BA", "ceara": "CE", "distrito federal": "DF", "espirito santo": "ES",
    "goias": "GO", "maranhao": "MA", "mato grosso": "MT", "mato grosso do sul": "MS",
    "minas gerais": "MG", "para": "PA", "paraiba": "PB", "parana": "PR",
    "pernambuco": "PE", "piaui": "PI", "rio de janeiro": "RJ",
    "rio grande do norte": "RN", "rio grande do sul": "RS", "rondonia": "RO",
    "roraima": "RR", "santa catarina": "SC", "sao paulo": "SP", "sergipe": "SE", "tocantins": "TO"
}


def resolve_project_geolocation(record: Dict[str, Any], project: Optional[Any] = None) -> Optional[GeoLocation]:
    """Recupera o objeto GeoLocation associado ao vídeo ou projeto."""
    meta = record.get("metadata_json") or {}
    if isinstance(meta, dict) and meta.get("geo_location"):
        g_data = meta["geo_location"]
        if isinstance(g_data, dict) and (g_data.get("city") or g_data.get("lat")):
            return GeoLocation.from_dict(g_data)

    if project:
        if hasattr(project, "geo_location_id") and project.geo_location_id:
            loc = GeoService.get_location(project.geo_location_id)
            if loc:
                return loc
        return GeoService.get_default_location()

    return GeoService.get_default_location()


def format_location_block(loc: GeoLocation) -> str:
    """Gera bloco de texto dedicado com informações de localização e habitat."""
    if not loc:
        return ""

    parts = []
    if loc.city:
        parts.append(loc.city)
    if loc.state:
        parts.append(loc.state)
    if loc.country:
        parts.append(loc.country)

    loc_name = ", ".join(parts) if parts else (loc.label or "Localização Registrada")

    lines = [
        "📍 LOCALIZAÇÃO E HABITAT:",
        f"• Localidade: {loc_name}"
    ]

    ref = loc.poi or loc.suburb
    if ref:
        lines.append(f"• Ponto de Referência / Bairro: {ref}")

    if loc.lat != 0.0 or loc.lng != 0.0:
        lines.append(f"• Coordenadas Geográficas: {loc.lat:.6f}, {loc.lng:.6f}")
        lines.append(f"• Visualização no Google Maps: https://www.google.com/maps?q={loc.lat:.6f},{loc.lng:.6f}")

    return "\n".join(lines)


def build_geo_hashtags(loc: GeoLocation) -> List[str]:
    """Gera lista de hashtags geográficas limpas (#PassosMG, #Passos, #MinasGerais, #Brasil)."""
    if not loc:
        return []
    tags = []
    if loc.city and loc.state:
        norm_st = unicodedata.normalize('NFKD', loc.state).encode('ASCII', 'ignore').decode('utf-8').lower().strip()
        if norm_st in BR_STATE_TO_UF:
            uf = BR_STATE_TO_UF[norm_st]
            ht_uf = f"#{sanitize_hashtag(loc.city)}{uf}"
            if ht_uf not in tags:
                tags.append(ht_uf)
        tags.append(f"#{sanitize_hashtag(loc.city)}{sanitize_hashtag(loc.state)}")
    if loc.city:
        ht_city = f"#{sanitize_hashtag(loc.city)}"
        if ht_city not in tags:
            tags.append(ht_city)
    if loc.state:
        ht_state = f"#{sanitize_hashtag(loc.state)}"
        if ht_state not in tags:
            tags.append(ht_state)
    if loc.country and loc.country.lower() != "brasil":
        ht_country = f"#{sanitize_hashtag(loc.country)}"
        if ht_country not in tags:
            tags.append(ht_country)
    elif loc.country:
        if "#Brasil" not in tags:
            tags.append("#Brasil")
    return [t for t in tags if t]

