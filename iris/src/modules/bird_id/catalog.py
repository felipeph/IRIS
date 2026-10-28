"""
Catálogo Global e Serviço de Espécies de Aves (IRIS Bird ID).
Gerencia a persistência centralizada de todas as espécies conhecidas no SQLite central (iris_central.db),
incluindo seed da lista regional com curadoria (br_mg_aves.csv), higienização de mojibake histórico,
contadores de uso (frequência) e busca flexível sem acentos / case-insensitive.
"""

import csv
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.core.config import ConfigManager
import src.core.project as p_mod

DEFAULT_SEED_CSV = Path(__file__).resolve().parent / "species_lists" / "br_mg_aves.csv"


def get_central_db_path(db_path: Optional[Path] = None) -> Path:
    """Retorna o caminho do banco central atual (suporta patching dinâmico em testes)."""
    return db_path if db_path is not None else p_mod.CENTRAL_DB_PATH



def normalize_ascii_lower(text: str) -> str:
    """Normaliza texto para ASCII minúsculo sem acentos para comparações tolerantes."""
    if not text:
        return ""
    clean = unicodedata.normalize("NFKD", str(text).strip())
    clean = clean.encode("ascii", "ignore").decode("utf-8")
    return clean.lower()


def clean_bird_text(text: str) -> str:
    """Higieniza string de espécie corrigindo mojibake e espaços excedentes."""
    if not text:
        return ""
    sanitized = ConfigManager._sanitize_mojibake(str(text).strip())
    # Remove caracteres de substituição unicode restantes se houver
    sanitized = sanitized.replace("\ufffd", "")
    return re.sub(r"\s+", " ", sanitized).strip()


def ensure_catalog_table(conn: sqlite3.Connection):
    """Garante que a tabela species_catalog e seus índices existam na conexão fornecida."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS species_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            species_common TEXT NOT NULL,
            species_scientific TEXT NOT NULL UNIQUE,
            species_common_en TEXT DEFAULT '',
            family TEXT DEFAULT '',
            order_name TEXT DEFAULT '',
            use_count INTEGER DEFAULT 1,
            source TEXT DEFAULT 'historical',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_species_catalog_names ON species_catalog(species_common, species_scientific)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_species_catalog_usage ON species_catalog(use_count DESC)")
    conn.commit()


def sync_species_catalog(
    central_db_path: Optional[Path] = None,
    seed_csv_path: Optional[Path] = None,
    project_db_path: Optional[Path] = None
) -> int:
    """
    Sincroniza e pré-popula o catálogo de espécies em iris_central.db:
    1. Importa a lista curada de espécies regionais de MG/Brasil (br_mg_aves.csv).
    2. Lê todas as identificações históricas de bird_identifications em iris_central.db.
    3. Higieniza caracteres e associa nomes científicos padronizados.
    4. Atualiza os contadores de frequência (use_count).
    Retorna o total de espécies cadastradas no catálogo.
    """
    c_path = get_central_db_path(central_db_path)
    c_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path = seed_csv_path or DEFAULT_SEED_CSV

    species_map: Dict[str, Dict[str, Any]] = {}

    # 1. Carrega base de referência com curadoria (br_mg_aves.csv)
    if seed_path.exists():
        with open(seed_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sci = (row.get("scientific_name") or "").strip()
                if not sci:
                    continue
                comm_pt = clean_bird_text(row.get("common_name_pt") or "")
                comm_en = clean_bird_text(row.get("common_name_en") or "")
                fam = clean_bird_text(row.get("family") or "")
                ord_name = clean_bird_text(row.get("order") or "")

                species_map[sci] = {
                    "species_common": comm_pt,
                    "species_scientific": sci,
                    "species_common_en": comm_en,
                    "family": fam,
                    "order_name": ord_name,
                    "use_count": 1,
                    "source": "seed_csv"
                }

    # 2. Coleta identificações históricas de iris_central.db
    with p_mod.get_db_connection(c_path) as conn:
        ensure_catalog_table(conn)
        cursor = conn.cursor()

        # Coletar estatísticas de bird_identifications na central
        try:
            cursor.execute("""
                SELECT species_common, species_scientific, COUNT(*) as cnt
                FROM bird_identifications
                WHERE species_scientific IS NOT NULL AND trim(species_scientific) != ''
                GROUP BY species_scientific
            """)
            rows = cursor.fetchall()
            for comm_raw, sci_raw, count_val in rows:
                sci = str(sci_raw).strip()
                if not sci:
                    continue
                clean_comm = clean_bird_text(comm_raw)

                if sci in species_map:
                    # Se já existe na base de sementes, mantemos o nome curado em português e somamos as ocorrências
                    species_map[sci]["use_count"] += int(count_val)
                    species_map[sci]["source"] = "historical_plus_seed"
                else:
                    species_map[sci] = {
                        "species_common": clean_comm or sci,
                        "species_scientific": sci,
                        "species_common_en": "",
                        "family": "",
                        "order_name": "",
                        "use_count": int(count_val),
                        "source": "historical"
                    }
        except sqlite3.OperationalError:
            pass

        # Se fornecido um banco de projeto específico, mescla identificações dele também
        if project_db_path and project_db_path.exists() and project_db_path.resolve() != c_path.resolve():
            try:
                with p_mod.get_db_connection(project_db_path) as pconn:
                    pcursor = pconn.cursor()
                    pcursor.execute("""
                        SELECT species_common, species_scientific, COUNT(*) as cnt
                        FROM bird_identifications
                        WHERE species_scientific IS NOT NULL AND trim(species_scientific) != ''
                        GROUP BY species_scientific
                    """)
                    for p_comm, p_sci, p_cnt in pcursor.fetchall():
                        sci = str(p_sci).strip()
                        if not sci:
                            continue
                        clean_comm = clean_bird_text(p_comm)
                        if sci in species_map:
                            species_map[sci]["use_count"] = max(species_map[sci]["use_count"], int(p_cnt))
                        else:
                            species_map[sci] = {
                                "species_common": clean_comm or sci,
                                "species_scientific": sci,
                                "species_common_en": "",
                                "family": "",
                                "order_name": "",
                                "use_count": int(p_cnt),
                                "source": "project_db"
                            }
            except Exception:
                pass

        # 3. Grava no species_catalog via UPSERT
        for item in species_map.values():
            cursor.execute("""
                INSERT INTO species_catalog (
                    species_common, species_scientific, species_common_en, family, order_name, use_count, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(species_scientific) DO UPDATE SET
                    species_common = CASE
                        WHEN excluded.source IN ('seed_csv', 'historical_plus_seed') THEN excluded.species_common
                        WHEN species_catalog.species_common LIKE '%\\ufffd%' THEN excluded.species_common
                        ELSE species_catalog.species_common
                    END,
                    species_common_en = CASE WHEN excluded.species_common_en != '' THEN excluded.species_common_en ELSE species_catalog.species_common_en END,
                    family = CASE WHEN excluded.family != '' THEN excluded.family ELSE species_catalog.family END,
                    order_name = CASE WHEN excluded.order_name != '' THEN excluded.order_name ELSE species_catalog.order_name END,
                    use_count = max(species_catalog.use_count, excluded.use_count),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                item["species_common"],
                item["species_scientific"],
                item["species_common_en"],
                item["family"],
                item["order_name"],
                item["use_count"],
                item["source"]
            ))

        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM species_catalog")
        total = cursor.fetchone()[0]
        return total


def list_species(
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Retorna espécies do catálogo ordenadas prioritariamente por maior uso e nome popular."""
    c_path = get_central_db_path(db_path)
    with p_mod.get_db_connection(c_path) as conn:
        ensure_catalog_table(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, species_common, species_scientific, species_common_en, family, order_name, use_count, source
            FROM species_catalog
            ORDER BY use_count DESC, species_common ASC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        return [dict(r) for r in cursor.fetchall()]


def get_species(
    scientific_or_common: str,
    db_path: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """Localiza uma espécie por correspondência exata em nome científico ou popular."""
    if not scientific_or_common:
        return None
    target = scientific_or_common.strip()
    c_path = get_central_db_path(db_path)
    with p_mod.get_db_connection(c_path) as conn:
        ensure_catalog_table(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, species_common, species_scientific, species_common_en, family, order_name, use_count, source
            FROM species_catalog
            WHERE lower(species_scientific) = lower(?) OR lower(species_common) = lower(?)
            LIMIT 1
        """, (target, target))
        row = cursor.fetchone()
        return dict(row) if row else None


def search_species(
    query: str,
    limit: int = 25,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Busca inteligente no catálogo por nome comum, científico, inglês ou família.
    Suporta busca tolerante a acentuação (ex: 'suir' ou 'sabia').
    Ranqueia por relevância:
    - Correspondência exata no início > substring > use_count.
    """
    clean_q = normalize_ascii_lower(query)
    c_path = get_central_db_path(db_path)

    with p_mod.get_db_connection(c_path) as conn:
        ensure_catalog_table(conn)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        if not clean_q:
            cursor.execute("""
                SELECT id, species_common, species_scientific, species_common_en, family, order_name, use_count, source
                FROM species_catalog
                ORDER BY use_count DESC, species_common ASC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cursor.fetchall()]

        # Carregar todas as espécies para ordenação com normalização sem acentos em Python
        cursor.execute("""
            SELECT id, species_common, species_scientific, species_common_en, family, order_name, use_count, source
            FROM species_catalog
        """)
        all_rows = [dict(r) for r in cursor.fetchall()]

    scored: List[tuple[int, int, Dict[str, Any]]] = []
    for r in all_rows:
        comm_norm = normalize_ascii_lower(r["species_common"])
        sci_norm = normalize_ascii_lower(r["species_scientific"])
        en_norm = normalize_ascii_lower(r.get("species_common_en", ""))
        fam_norm = normalize_ascii_lower(r.get("family", ""))

        score = 0
        if comm_norm == clean_q or sci_norm == clean_q:
            score = 1000
        elif comm_norm.startswith(clean_q) or sci_norm.startswith(clean_q):
            score = 500
        elif f" {clean_q}" in comm_norm or f"-{clean_q}" in comm_norm or f" {clean_q}" in sci_norm:
            score = 250
        elif clean_q in comm_norm:
            score = 150
        elif clean_q in sci_norm:
            score = 120
        elif clean_q in en_norm or clean_q in fam_norm:
            score = 80

        if score > 0:
            scored.append((score, int(r.get("use_count", 1)), r))

    # Ordena decrescente por score de matching e depois por frequência de uso
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in scored[:limit]]


def register_or_increment_species(
    common: str,
    scientific: str,
    common_en: str = "",
    family: str = "",
    order_name: str = "",
    source: str = "manual",
    count_increment: int = 1,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Registra uma nova espécie no catálogo ou incrementa sua contagem de uso se já existir.
    Garante que nomes não fiquem vazios ou com mojibake.
    """
    c_path = get_central_db_path(db_path)
    clean_comm = clean_bird_text(common)
    clean_sci = str(scientific).strip()
    clean_en = clean_bird_text(common_en)
    clean_fam = clean_bird_text(family)
    clean_ord = clean_bird_text(order_name)

    if not clean_sci:
        raise ValueError("O nome científico da espécie é obrigatório para cadastro no catálogo.")
    if not clean_comm:
        clean_comm = clean_sci

    with p_mod.get_db_connection(c_path) as conn:
        ensure_catalog_table(conn)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO species_catalog (
                species_common, species_scientific, species_common_en, family, order_name, use_count, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(species_scientific) DO UPDATE SET
                species_common = CASE WHEN excluded.species_common != '' THEN excluded.species_common ELSE species_catalog.species_common END,
                species_common_en = CASE WHEN excluded.species_common_en != '' THEN excluded.species_common_en ELSE species_catalog.species_common_en END,
                family = CASE WHEN excluded.family != '' THEN excluded.family ELSE species_catalog.family END,
                order_name = CASE WHEN excluded.order_name != '' THEN excluded.order_name ELSE species_catalog.order_name END,
                use_count = species_catalog.use_count + excluded.use_count,
                updated_at = CURRENT_TIMESTAMP
        """, (clean_comm, clean_sci, clean_en, clean_fam, clean_ord, max(1, count_increment), source))
        conn.commit()

        return get_species(clean_sci, db_path=c_path) or {
            "species_common": clean_comm,
            "species_scientific": clean_sci,
            "species_common_en": clean_en,
            "family": clean_fam,
            "order_name": clean_ord,
            "use_count": max(1, count_increment),
            "source": source
        }
