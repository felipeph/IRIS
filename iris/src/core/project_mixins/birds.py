"""
ProjectBirdsMixin.
Gerencia persistência e consultas de identificação taxonômica de espécies de aves (YOLO + BioCLIP),
com suporte a dual-write atômico no banco local e central (RFC 08 / 09).
"""

import json
import sqlite3
from typing import List, Dict, Any, Optional


class ProjectBirdsMixin:
    """Mixin com operações relativas à identificação e classificação de espécies de aves."""

    def add_bird_identification(self, record: Dict[str, Any]):
        """Registra uma identificação de ave no banco do projeto e no central atomicamente."""
        self._ensure_db_initialized()
        record_copy = dict(record)
        record_copy["project_name"] = self.name

        meta_val = record_copy.get("metadata_json", {})
        meta_json_str = json.dumps(meta_val) if isinstance(meta_val, dict) else str(meta_val)

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
                crop_saved_path=excluded.crop_saved_path,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
        """
        sql_central = sql_main.replace("main.bird_identifications", "central.bird_identifications")
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

