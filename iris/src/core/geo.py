import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any, Tuple
from rich.panel import Panel
from src.core.config import config

# Extensões com suporte seguro a gravação de metadados sem perigo de corrupção ou overhead massivo
# Conforme requisitos estritos do usuário:
# - NUNCA regravar RAWs (ex: .cr2, .cr3, .arw, .nef, .dng, etc.)
# - NUNCA regravar Vídeos (ex: .mp4, .mov, etc.)
# Para esses formatos, as coordenadas GPS são inseridas EXCLUSIVAMENTE no nome do arquivo.
GEO_WRITABLE_EXTS = {
    ".jpg", ".jpeg",
    ".png", ".webp",
    ".tif", ".tiff",
    ".heic"
}

@dataclass
class GeoLocation:
    id: str
    label: str
    lat: float
    lng: float
    accuracy_m: float = 25000.0
    city: str = ""
    state: str = ""
    country: str = "Brasil"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "lat": float(self.lat),
            "lng": float(self.lng),
            "accuracy_m": float(self.accuracy_m),
            "city": self.city,
            "state": self.state,
            "country": self.country,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeoLocation":
        return cls(
            id=str(data.get("id", "")).strip(),
            label=str(data.get("label", "")).strip(),
            lat=float(data.get("lat", 0.0)),
            lng=float(data.get("lng", 0.0)),
            accuracy_m=float(data.get("accuracy_m", 25000.0)),
            city=str(data.get("city", "")).strip(),
            state=str(data.get("state", "")).strip(),
            country=str(data.get("country", "Brasil")).strip(),
        )


def parse_coords(text: str) -> Tuple[float, float]:
    """
    Analisa uma string de coordenadas e retorna (latitude, longitude).
    Suporta:
    - Decimal separado por vírgula ou espaço: "-20.456887, -45.438307" ou "-20.456887 -45.438307"
    - Formatos com direções cardeais: "20.456887S, 45.438307W" ou "20.456887 S 45.438307 W"
    """
    clean = text.strip()
    if not clean:
        raise ValueError("Coordenadas vazias.")

    # Substitui vírgula entre números por espaço caso seja separador decimal em pt-br ou delimitador
    # Padrão típico Google Maps: -20.456887, -45.438307
    pattern = r"^\s*([+-]?\d+(?:\.\d+)?)\s*([NSEWnsew]?)\s*[,;\s/]\s*([+-]?\d+(?:\.\d+)?)\s*([NSEWnsew]?)\s*$"
    m = re.match(pattern, clean)
    if m:
        val1, ref1, val2, ref2 = m.groups()
        lat_val = float(val1)
        lng_val = float(val2)

        ref1 = ref1.upper()
        ref2 = ref2.upper()

        if ref1 == "S":
            lat_val = -abs(lat_val)
        elif ref1 == "N":
            lat_val = abs(lat_val)

        if ref2 == "W":
            lng_val = -abs(lng_val)
        elif ref2 == "E":
            lng_val = abs(lng_val)

        if not (-90.0 <= lat_val <= 90.0):
            raise ValueError(f"Latitude inválida ({lat_val}). Deve estar entre -90 e 90.")
        if not (-180.0 <= lng_val <= 180.0):
            raise ValueError(f"Longitude inválida ({lng_val}). Deve estar entre -180 e 180.")

        return lat_val, lng_val

    # Tenta split simples
    parts = re.split(r"[,;\s]+", clean)
    if len(parts) == 2:
        lat_val = float(parts[0])
        lng_val = float(parts[1])
        if not (-90.0 <= lat_val <= 90.0):
            raise ValueError(f"Latitude inválida ({lat_val}). Deve estar entre -90 e 90.")
        if not (-180.0 <= lng_val <= 180.0):
            raise ValueError(f"Longitude inválida ({lng_val}). Deve estar entre -180 e 180.")
        return lat_val, lng_val

    raise ValueError(f"Formato de coordenadas não reconhecido: '{text}'")


def format_gps_token(lat: float, lng: float) -> str:
    """
    Formata latitude e longitude para o token de arquivo:
    Ex: -20.456887, -45.438307 -> "S20-4569_W45-4383"
    Usa 4 casas decimais, hífen no lugar do ponto e N/S/E/W no lugar do sinal.
    """
    lat_ref = "N" if lat >= 0 else "S"
    lng_ref = "E" if lng >= 0 else "W"
    lat_part = f"{lat_ref}{abs(lat):.4f}".replace(".", "-")
    lng_part = f"{lng_ref}{abs(lng):.4f}".replace(".", "-")
    return f"{lat_part}_{lng_part}"


def maps_url(lat: float, lng: float) -> str:
    """Retorna URL de visualização no Google Maps."""
    return f"https://www.google.com/maps?q={lat:.6f},{lng:.6f}"


def build_location_panel(
    loc: GeoLocation,
    title: str = "📍 \\[LOCALIZAÇÃO ATIVA DO PROJETO\\]",
    border_style: str = "yellow"
) -> Panel:
    """Gera um painel vertical padronizado com as informações detalhadas da localização (uma por linha)."""
    gps_token = format_gps_token(loc.lat, loc.lng)
    gmaps = maps_url(loc.lat, loc.lng)
    reg_parts = [p for p in [loc.city, loc.state, loc.country] if p]
    reg_str = ", ".join(reg_parts) if reg_parts else "Brasil"

    clean_title = title.replace("[", "\\[") if "\\[" not in title else title
    loc_text = (
        f"[bold yellow]{clean_title}[/bold yellow]\n"
        f"  [dim]• Rótulo:[/dim]       [bold white]{loc.label}[/bold white]\n"
        f"  [dim]• Região:[/dim]       {reg_str}\n"
        f"  [dim]• Coordenadas:[/dim]  {loc.lat:.6f}, {loc.lng:.6f} [dim](Token: {gps_token})[/dim]\n"
        f"  [dim]• Precisão:[/dim]     Raio de {int(loc.accuracy_m):,}m [dim](Usado no iNaturalist)[/dim]\n"
        f"  [dim]• Google Maps:[/dim]  [link={gmaps}]{gmaps}[/link]"
    )
    return Panel(loc_text, expand=False, border_style=border_style)


def build_exiftool_geo_args(loc: GeoLocation, is_video: bool = False, ext: str = "") -> List[str]:
    """
    Gera argumentos de linha de comando para o ExifTool para injeção de GPS e IPTC/XMP.
    Atenção: Apenas chamado para mídias graváveis (GEO_WRITABLE_EXTS).
    Vídeos e RAWs nunca recebem chamada de escrita do ExifTool.
    """
    ext_lower = ext.lower()
    if is_video or ext_lower not in GEO_WRITABLE_EXTS:
        return []

    lat = loc.lat
    lng = loc.lng
    lat_ref = "N" if lat >= 0 else "S"
    lng_ref = "E" if lng >= 0 else "W"
    abs_lat = abs(lat)
    abs_lng = abs(lng)

    args = [
        f"-GPSLatitude={abs_lat:.6f}",
        f"-GPSLatitudeRef={lat_ref}",
        f"-GPSLongitude={abs_lng:.6f}",
        f"-GPSLongitudeRef={lng_ref}",
        f"-XMP:GPSLatitude={lat:.6f}",
        f"-XMP:GPSLongitude={lng:.6f}",
    ]

    if loc.city:
        args.append(f"-IPTC:City={loc.city}")
        args.append(f"-XMP-photoshop:City={loc.city}")
    if loc.state:
        args.append(f"-IPTC:Province-State={loc.state}")
        args.append(f"-XMP-photoshop:State={loc.state}")
    if loc.country:
        args.append(f"-IPTC:Country-PrimaryLocationName={loc.country}")
        args.append(f"-XMP-photoshop:Country={loc.country}")
    if loc.label:
        args.append(f"-IPTC:Sub-location={loc.label}")
        args.append(f"-XMP-iptcCore:Location={loc.label}")

    args.extend([
        "-IPTC:CodedCharacterSet=UTF8",
        "-charset", "iptc=UTF8",
        "-charset", "filename=utf8",
    ])

    return args


class GeoService:
    """Gerencia a lista de locais predefinidos e o local padrão em config.yaml."""

    DEFAULT_LOCATIONS: List[Dict[str, Any]] = [
        {
            "id": "formiga-sao-luiz",
            "label": "Bairro São Luiz - Formiga - MG",
            "lat": -20.456887,
            "lng": -45.438307,
            "accuracy_m": 25000.0,
            "city": "Formiga",
            "state": "Minas Gerais",
            "country": "Brasil"
        },
        {
            "id": "bh-belvedere",
            "label": "Bairro Belvedere - Belo Horizonte - MG",
            "lat": -19.9667,
            "lng": -43.9500,
            "accuracy_m": 15000.0,
            "city": "Belo Horizonte",
            "state": "Minas Gerais",
            "country": "Brasil"
        },
        {
            "id": "ouro-preto-sao-bartolomeu",
            "label": "São Bartolomeu - Ouro Preto - MG",
            "lat": -20.3167,
            "lng": -43.5833,
            "accuracy_m": 20000.0,
            "city": "Ouro Preto",
            "state": "Minas Gerais",
            "country": "Brasil"
        }
    ]

    @classmethod
    def ensure_defaults(cls) -> None:
        """Garante que existam locais configurados e local padrão migrado."""
        locations_data = config.get("geo.locations")
        if not locations_data or not isinstance(locations_data, list):
            # Tenta migrar a partir de modules.bird_id.inaturalist.default_lat/lng se existir
            inat_lat = config.get("modules.bird_id.inaturalist.default_lat")
            inat_lng = config.get("modules.bird_id.inaturalist.default_lng")
            defaults = [dict(loc) for loc in cls.DEFAULT_LOCATIONS]
            if inat_lat is not None and inat_lng is not None:
                defaults[0]["lat"] = float(inat_lat)
                defaults[0]["lng"] = float(inat_lng)
            config.set("geo.locations", defaults)

        if not config.get("geo.default_location"):
            locs = config.get("geo.locations", [])
            default_id = locs[0]["id"] if locs and isinstance(locs[0], dict) and "id" in locs[0] else "formiga-sao-luiz"
            config.set("geo.default_location", default_id)

        if config.get("geo.tag_media") is None:
            config.set("geo.tag_media", True)

        if config.get("geo.filename_token") is None:
            config.set("geo.filename_token", True)

    @classmethod
    def get_locations(cls) -> List[GeoLocation]:
        cls.ensure_defaults()
        raw = config.get("geo.locations", [])
        locs: List[GeoLocation] = []
        for item in raw:
            if isinstance(item, dict) and "id" in item:
                try:
                    locs.append(GeoLocation.from_dict(item))
                except Exception:
                    pass
        return locs

    @classmethod
    def get_location(cls, loc_id: str) -> Optional[GeoLocation]:
        if not loc_id:
            return None
        for loc in cls.get_locations():
            if loc.id == loc_id:
                return loc
        return None

    @classmethod
    def get_default_location_id(cls) -> str:
        cls.ensure_defaults()
        return str(config.get("geo.default_location", "")).strip()

    @classmethod
    def get_default_location(cls) -> Optional[GeoLocation]:
        def_id = cls.get_default_location_id()
        loc = cls.get_location(def_id)
        if not loc:
            locs = cls.get_locations()
            if locs:
                return locs[0]
        return loc

    @classmethod
    def add_location(cls, loc: GeoLocation, set_as_default: bool = False) -> None:
        locs = cls.get_locations()
        # Se já existe ID, atualiza
        updated = False
        new_list = []
        for existing in locs:
            if existing.id == loc.id:
                new_list.append(loc.to_dict())
                updated = True
            else:
                new_list.append(existing.to_dict())
        if not updated:
            new_list.append(loc.to_dict())

        config.set("geo.locations", new_list)
        if set_as_default or len(new_list) == 1:
            cls.set_default_location_id(loc.id)

    @classmethod
    def update_location(cls, loc: GeoLocation) -> None:
        cls.add_location(loc, set_as_default=False)

    @classmethod
    def delete_location(cls, loc_id: str) -> bool:
        locs = cls.get_locations()
        if len(locs) <= 1:
            return False
        new_list = [l.to_dict() for l in locs if l.id != loc_id]
        if len(new_list) == len(locs):
            return False

        config.set("geo.locations", new_list)
        if cls.get_default_location_id() == loc_id:
            if new_list:
                cls.set_default_location_id(new_list[0]["id"])
            else:
                cls.set_default_location_id("")
        return True

    @classmethod
    def set_default_location_id(cls, loc_id: str) -> None:
        config.set("geo.default_location", loc_id)
