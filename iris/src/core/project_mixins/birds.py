"""
ProjectBirdsMixin.
Gerencia persistência e consultas de identificação taxonômica de espécies de aves (YOLO + BioCLIP),
com suporte a dual-write atômico no banco local e central (RFC 08 / 09).
"""

import json
import sqlite3
from typing import List, Dict, Any, Optional


def _sanitize_meta_dict(val: Any) -> Any:
    """Garante recursivamente que dicionários e listas contenham apenas tipos serializáveis em JSON."""
    if isinstance(val, dict):
        return {k: _sanitize_meta_dict(v) for k, v in val.items() if k not in ("pil_img", "bgr_img")}
    elif isinstance(val, (list, tuple)):
        return [_sanitize_meta_dict(item) for item in val]
    elif hasattr(val, "item"):
        return val.item()
    elif isinstance(val, (str, int, float, bool)) or val is None:
        return val
    else:
        return str(val)


class ProjectBirdsMixin:
    """Mixin com operações relativas à identificação e classificação de espécies de aves."""

    def add_bird_identification(self, record: Dict[str, Any]):
        """Registra uma identificação de ave no banco do projeto e no central atomicamente."""
        self._ensure_db_initialized()
        record_copy = dict(record)
        record_copy["project_name"] = self.name

        meta_val = dict(record_copy.get("metadata_json", {})) if isinstance(record_copy.get("metadata_json"), dict) else {}
        if record_copy.get("species_common_en"):
            meta_val["species_common_en"] = record_copy["species_common_en"]
        if record_copy.get("family"):
            meta_val["family"] = record_copy["family"]
        if record_copy.get("order"):
            meta_val["order"] = record_copy["order"]

        # Mescla metadados e recortes anteriores se já existirem (ex: video_crops da Etapa 1)
        existing = self.get_bird_identification(record_copy.get("item_path", ""))
        if existing:
            if not record_copy.get("crop_saved_path") and existing.get("crop_saved_path"):
                record_copy["crop_saved_path"] = existing["crop_saved_path"]
            old_meta = existing.get("metadata_json", {})
            if isinstance(old_meta, dict):
                merged_meta = dict(old_meta)
                merged_meta.update(meta_val)
                meta_val = merged_meta

        meta_val = _sanitize_meta_dict(meta_val)
        meta_json_str = json.dumps(meta_val, default=str)

        params = (
            self.name,
            str(record_copy.get("item_path", "")),
            1 if record_copy.get("is_video", False) else 0,
            record_copy.get("species_common", ""),
            record_copy.get("species_scientific", ""),
            float(record_copy.get("confidence", 0.0)),
            record_copy.get("top2_common", ""),
            record_copy.get("top2_scientific", ""),
            float(record_copy.get("top2_confidence", 0.0)),
            record_copy.get("top3_common", ""),
            record_copy.get("top3_scientific", ""),
            float(record_copy.get("top3_confidence", 0.0)),
            1 if record_copy.get("needs_review", False) else 0,
            str(record_copy.get("crop_saved_path", "")),
            meta_json_str
        )

        sql_main = """
            INSERT INTO main.bird_identifications (
                project_name, item_path, is_video, species_common, species_scientific,
                confidence, top2_common, top2_scientific, top2_confidence,
                top3_common, top3_scientific, top3_confidence, needs_review,
                crop_saved_path, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_name, item_path) DO UPDATE SET
                is_video=excluded.is_video,
                species_common=excluded.species_common,
                species_scientific=excluded.species_scientific,
                confidence=excluded.confidence,
                top2_common=excluded.top2_common,
                top2_scientific=excluded.top2_scientific,
                top2_confidence=excluded.top2_confidence,
                top3_common=excluded.top3_common,
                top3_scientific=excluded.top3_scientific,
                top3_confidence=excluded.top3_confidence,
                needs_review=excluded.needs_review,
                crop_saved_path=CASE WHEN excluded.crop_saved_path != '' THEN excluded.crop_saved_path ELSE main.bird_identifications.crop_saved_path END,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
        """
        sql_central = sql_main.replace("main.bird_identifications", "central.bird_identifications")
        self._execute_dual_write(sql_main, params, sql_central, params)

    def save_bird_detection(self, record: Dict[str, Any]):
        """
        Registra a detecção física e caminhos de recortes de uma ave (Etapa 1: bird_detect).
        Salva ou atualiza os caminhos dos recortes e metadados no SQLite sem sobrescrever taxonomia pré-existente.
        """
        self._ensure_db_initialized()
        record_copy = dict(record)
        record_copy["project_name"] = self.name

        meta_val = record_copy.get("metadata_json", {})
        if isinstance(meta_val, dict):
            meta_val = _sanitize_meta_dict(meta_val)
            meta_json_str = json.dumps(meta_val, default=str)
        else:
            meta_json_str = str(meta_val)

        params = (
            self.name,
            str(record_copy.get("item_path", "")),
            1 if record_copy.get("is_video", False) else 0,
            str(record_copy.get("crop_saved_path", "")),
            meta_json_str
        )

        sql_main = """
            INSERT INTO main.bird_identifications (
                project_name, item_path, is_video, species_common, species_scientific,
                confidence, top2_common, top2_scientific, top2_confidence,
                top3_common, top3_scientific, top3_confidence, needs_review,
                crop_saved_path, metadata_json
            ) VALUES (?, ?, ?, '', '', 0.0, '', '', 0.0, '', '', 0.0, 1, ?, ?)
            ON CONFLICT(project_name, item_path) DO UPDATE SET
                is_video=excluded.is_video,
                crop_saved_path=excluded.crop_saved_path,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
        """
        sql_central = sql_main.replace("main.bird_identifications", "central.bird_identifications")
        self._execute_dual_write(sql_main, params, sql_central, params)

    def update_bird_identification_path(self, old_path: str, new_path: str):
        """Atualiza a referência do caminho do item após renomeação/movimentação física."""
        self._ensure_db_initialized()
        sql_main = """
            UPDATE main.bird_identifications
            SET item_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE project_name = ? AND item_path = ?
        """
        sql_central = sql_main.replace("main.bird_identifications", "central.bird_identifications")
        params = (str(new_path), self.name, str(old_path))
        self._execute_dual_write(sql_main, params, sql_central, params)

    def list_bird_identifications(self) -> List[Dict[str, Any]]:
        """Retorna todas as identificações de aves registradas no banco do projeto."""
        self._ensure_db_initialized()
        query = """
            SELECT id, project_name, item_path, is_video, species_common, species_scientific,
                   confidence, top2_common, top2_scientific, top2_confidence,
                   top3_common, top3_scientific, top3_confidence, needs_review,
                   crop_saved_path, metadata_json, created_at, updated_at
            FROM bird_identifications
            WHERE project_name = ?
            ORDER BY created_at ASC
        """
        import src.core.project as p_mod
        active_conn = self._get_active_conn()
        if active_conn is not None:
            active_conn.row_factory = sqlite3.Row
            cursor = active_conn.cursor()
            cursor.execute(query, (self.name,))
            rows = cursor.fetchall()
        else:
            with p_mod.get_db_connection(self._project_db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, (self.name,))
                rows = cursor.fetchall()

        res = []
        for r in rows:
            d = dict(r)
            d["is_video"] = bool(d["is_video"])
            d["needs_review"] = bool(d["needs_review"])
            try:
                d["metadata_json"] = json.loads(d["metadata_json"])
            except Exception:
                d["metadata_json"] = {}
            if isinstance(d["metadata_json"], dict):
                d["species_common_en"] = d["metadata_json"].get("species_common_en") or d["metadata_json"].get("common_en", "")
                d["family"] = d["metadata_json"].get("family", "")
                d["order"] = d["metadata_json"].get("order", "")
            else:
                d["species_common_en"] = ""
                d["family"] = ""
                d["order"] = ""
            res.append(d)
        return res

    def get_bird_identification(self, item_path: str) -> Optional[Dict[str, Any]]:
        """Retorna o registro de identificação de ave para um item específico."""
        self._ensure_db_initialized()
        query = """
            SELECT id, project_name, item_path, is_video, species_common, species_scientific,
                   confidence, top2_common, top2_scientific, top2_confidence,
                   top3_common, top3_scientific, top3_confidence, needs_review,
                   crop_saved_path, metadata_json, created_at, updated_at
            FROM bird_identifications
            WHERE project_name = ? AND item_path = ?
            LIMIT 1
        """
        import src.core.project as p_mod
        active_conn = self._get_active_conn()
        if active_conn is not None:
            active_conn.row_factory = sqlite3.Row
            cursor = active_conn.cursor()
            cursor.execute(query, (self.name, str(item_path)))
            r = cursor.fetchone()
        else:
            with p_mod.get_db_connection(self._project_db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(query, (self.name, str(item_path)))
                r = cursor.fetchone()

        if not r:
            return None
        d = dict(r)
        d["is_video"] = bool(d["is_video"])
        d["needs_review"] = bool(d["needs_review"])
        try:
            d["metadata_json"] = json.loads(d["metadata_json"])
        except Exception:
            d["metadata_json"] = {}
        if isinstance(d["metadata_json"], dict):
            d["species_common_en"] = d["metadata_json"].get("species_common_en") or d["metadata_json"].get("common_en", "")
            d["family"] = d["metadata_json"].get("family", "")
            d["order"] = d["metadata_json"].get("order", "")
        else:
            d["species_common_en"] = ""
            d["family"] = ""
            d["order"] = ""
        return d

    def get_bird_identifications_count(self) -> int:
        """Retorna a contagem total de identificações de aves no projeto com custo O(1)."""
        self._ensure_db_initialized()
        query = "SELECT COUNT(*) FROM bird_identifications WHERE project_name = ?"
        import src.core.project as p_mod
        active_conn = self._get_active_conn()
        if active_conn is not None:
            cursor = active_conn.cursor()
            cursor.execute(query, (self.name,))
            row = cursor.fetchone()
            return row[0] if row else 0
        else:
            with p_mod.get_db_connection(self._project_db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(query, (self.name,))
                row = cursor.fetchone()
                return row[0] if row else 0

    def list_known_species(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """Retorna espécies registradas no catálogo global ordenadas por uso."""
        from src.modules.bird_id.catalog import list_species
        return list_species(limit=limit, offset=offset, db_path=getattr(self, "_central_db_file", None))

    def search_known_species(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Busca flexível no catálogo global de espécies sem acentos."""
        from src.modules.bird_id.catalog import search_species
        return search_species(query=query, limit=limit, db_path=getattr(self, "_central_db_file", None))

    def get_known_species(self, scientific_or_common: str) -> Optional[Dict[str, Any]]:
        """Localiza uma espécie no catálogo global por nome científico ou comum."""
        from src.modules.bird_id.catalog import get_species
        return get_species(scientific_or_common=scientific_or_common, db_path=getattr(self, "_central_db_file", None))

    def register_known_species(
        self,
        common: str,
        scientific: str,
        common_en: str = "",
        family: str = "",
        order_name: str = "",
        source: str = "manual"
    ) -> Dict[str, Any]:
        """Registra ou atualiza uma espécie no catálogo global."""
        from src.modules.bird_id.catalog import register_or_increment_species
        return register_or_increment_species(
            common=common,
            scientific=scientific,
            common_en=common_en,
            family=family,
            order_name=order_name,
            source=source,
            db_path=getattr(self, "_central_db_file", None)
        )

    def correct_bird_identification(
        self,
        item_path: str,
        new_species: Dict[str, Any],
        apply_physical_move: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Corrige formalmente a identificação de uma ave no banco local e central,
        redefinindo confidence=1.0, needs_review=0 e registrando metadados de auditoria.
        Se apply_physical_move for True e o projeto já tiver organizado os arquivos,
        renomeia e move para a subpasta da nova espécie, atualizando as tags EXIF/IPTC.
        """
        self._ensure_db_initialized()
        existing = self.get_bird_identification(item_path)
        if not existing:
            try:
                from pathlib import Path
                existing = self.get_bird_identification(str(Path(item_path).resolve()))
            except Exception:
                pass
        if not existing:
            return None

        from datetime import datetime
        from pathlib import Path
        from src.modules.bird_id.catalog import register_or_increment_species

        comm_pt = str(new_species.get("species_common") or "").strip()
        sci = str(new_species.get("species_scientific") or "").strip()
        comm_en = str(new_species.get("species_common_en") or "").strip()
        family = str(new_species.get("family") or "").strip()
        order_name = str(new_species.get("order") or new_species.get("order_name") or "").strip()

        if not comm_pt and not sci:
            raise ValueError("Ao menos o nome comum ou científico deve ser fornecido para correção.")
        if not comm_pt:
            comm_pt = sci
        if not sci:
            sci = comm_pt

        # Incrementa / atualiza no catálogo global
        register_or_increment_species(
            common=comm_pt,
            scientific=sci,
            common_en=comm_en,
            family=family,
            order_name=order_name,
            source="manual_correction",
            count_increment=1,
            db_path=getattr(self, "_central_db_file", None)
        )

        old_meta = existing.get("metadata_json", {})
        if not isinstance(old_meta, dict):
            old_meta = {}

        new_meta = dict(old_meta)
        new_meta["manual_correction"] = True
        new_meta["corrected_at"] = datetime.now().isoformat()
        new_meta["previous_species"] = {
            "species_common": existing.get("species_common", ""),
            "species_scientific": existing.get("species_scientific", ""),
            "confidence": existing.get("confidence", 0.0),
            "needs_review": existing.get("needs_review", False),
        }
        if comm_en:
            new_meta["species_common_en"] = comm_en
        if family:
            new_meta["family"] = family
        if order_name:
            new_meta["order"] = order_name

        new_meta = _sanitize_meta_dict(new_meta)
        meta_json_str = json.dumps(new_meta, default=str)

        old_db_path = existing.get("item_path", item_path)

        sql_main = """
            UPDATE main.bird_identifications
            SET species_common = ?,
                species_scientific = ?,
                confidence = 1.0,
                needs_review = 0,
                metadata_json = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE project_name = ? AND item_path = ?
        """
        sql_central = sql_main.replace("main.bird_identifications", "central.bird_identifications")
        params = (comm_pt, sci, meta_json_str, self.name, old_db_path)
        self._execute_dual_write(sql_main, params, sql_central, params)

        updated_record = dict(existing)
        updated_record["species_common"] = comm_pt
        updated_record["species_scientific"] = sci
        updated_record["species_common_en"] = comm_en
        updated_record["family"] = family
        updated_record["order"] = order_name
        updated_record["confidence"] = 1.0
        updated_record["needs_review"] = False
        updated_record["metadata_json"] = new_meta

        # Se solicitado e o arquivo já tiver sido organizado fisicamente anteriormente
        if apply_physical_move:
            try:
                from src.core.config import config
                from src.modules.bird_id.action import apply_bird_physical_move, apply_bird_metadata
                item = None
                for it in self.get_items():
                    for p in [it.organized_path, it.staging_path, it.original_path]:
                        if p and (p == old_db_path or Path(p).resolve() == Path(old_db_path).resolve()):
                            item = it
                            break
                    if item:
                        break

                if item:
                    bird_cfg = dict(config.get("modules.bird_id", {}))
                    # Só move fisicamente se já passou pela etapa de organização física (ex: já está em organized_path)
                    if item.organized_path and Path(item.organized_path).exists():
                        new_path = apply_bird_physical_move(item, self, updated_record, bird_cfg)
                        if new_path.exists() and bool(bird_cfg.get("write_exif_tags", True)):
                            apply_bird_metadata(new_path, updated_record)
            except Exception:
                pass

        return updated_record


