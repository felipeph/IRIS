"""
ProjectAstroMixin (RFC 09).
Gerencia persistência e consultas de astrofotografia lunar (empilhamentos e wavelets),
com suporte a dual-write atômico no banco local e central.
"""

import json
import sqlite3
from typing import List, Dict, Any, Optional


class ProjectAstroMixin:
    """Mixin com operações relativas a astrofotografia (empilhamentos PSS e aprimoramento por wavelets)."""

    def add_astro_stack(self, record: Dict[str, Any]):
        """Registra uma sessão de empilhamento lunar no banco do projeto e no central atomicamente (RFC 08)."""
        self._ensure_db_initialized()
        record_copy = dict(record)
        record_copy["project_name"] = self.name
        
        keep_percents = record_copy.get("keep_percents", [])
        keep_percents_str = json.dumps(list(keep_percents)) if isinstance(keep_percents, (list, tuple)) else str(keep_percents)
        out_paths = record_copy.get("output_tiff_paths_json", {})
        out_paths_str = json.dumps(out_paths) if isinstance(out_paths, (dict, list)) else str(out_paths)
        meta_val = record_copy.get("metadata_json", {})
        meta_json_str = json.dumps(meta_val) if isinstance(meta_val, dict) else str(meta_val)

        params = (
            self.name,
            record_copy.get("session_dir", ""),
            record_copy.get("raw_count", 0),
            keep_percents_str,
            record_copy.get("output_dir", ""),
            out_paths_str,
            record_copy.get("crop_size", 0),
            record_copy.get("shared_gain", 1.0),
            record_copy.get("status", "stacked"),
            meta_json_str,
            record_copy.get("elapsed_seconds", 0.0)
        )
        sql_main = """
            INSERT INTO main.astro_stacks (
                project_name, session_dir, raw_count, keep_percents, output_dir,
                output_tiff_paths_json, crop_size, shared_gain, status, metadata_json, elapsed_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_name, session_dir) DO UPDATE SET
                raw_count=excluded.raw_count,
                keep_percents=excluded.keep_percents,
                output_dir=excluded.output_dir,
                output_tiff_paths_json=excluded.output_tiff_paths_json,
                crop_size=excluded.crop_size,
                shared_gain=excluded.shared_gain,
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                elapsed_seconds=excluded.elapsed_seconds,
                updated_at=CURRENT_TIMESTAMP
        """
        sql_central = sql_main.replace("main.astro_stacks", "central.astro_stacks")
        self._execute_dual_write(sql_main, params, sql_central, params)

    def get_astro_stacks(self, session_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera sessões de empilhamento registradas no projeto."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        import src.core.project as p_mod
        with p_mod.get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if session_dir:
                cursor.execute("SELECT * FROM astro_stacks WHERE project_name=? AND session_dir=? ORDER BY created_at DESC", (self.name, session_dir))
            else:
                cursor.execute("SELECT * FROM astro_stacks WHERE project_name=? ORDER BY created_at DESC", (self.name,))
            for row in cursor.fetchall():
                d = dict(row)
                for json_col in ("keep_percents", "output_tiff_paths_json", "metadata_json"):
                    val = d.get(json_col)
                    if isinstance(val, str) and val:
                        try:
                            d[json_col] = json.loads(val)
                        except Exception:
                            pass
                results.append(d)
        return results

    def has_astro_stacks(self) -> bool:
        """Verifica se existem sessões de empilhamento concluídas no projeto."""
        stacks = self.get_astro_stacks()
        return any(s.get("status") in ("stacked", "done", "success", "completed") for s in stacks)

    def is_astro_session_stacked(self, session_dir: str) -> bool:
        """Verifica se uma sessão de astrofotografia já foi empilhada com sucesso."""
        stacks = self.get_astro_stacks(session_dir)
        return any(s.get("status") in ("stacked", "done", "success", "completed") for s in stacks)

    def add_astro_sharpen(self, record: Dict[str, Any]):
        """Registra uma imagem aprimorada por wavelets no banco do projeto e no central atomicamente (RFC 08)."""
        self._ensure_db_initialized()
        record_copy = dict(record)
        record_copy["project_name"] = self.name
        
        meta_val = record_copy.get("metadata_json", {})
        meta_json_str = json.dumps(meta_val) if isinstance(meta_val, dict) else str(meta_val)

        params = (
            self.name,
            record_copy.get("source_stack_path", ""),
            record_copy.get("preset", ""),
            record_copy.get("output_tiff_path", ""),
            record_copy.get("output_png_path", ""),
            record_copy.get("status", "sharpened"),
            meta_json_str,
            record_copy.get("elapsed_seconds", 0.0)
        )
        sql_main = """
            INSERT INTO main.astro_sharpens (
                project_name, source_stack_path, preset, output_tiff_path, output_png_path,
                status, metadata_json, elapsed_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(output_tiff_path) DO UPDATE SET
                preset=excluded.preset,
                output_png_path=excluded.output_png_path,
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                elapsed_seconds=excluded.elapsed_seconds,
                updated_at=CURRENT_TIMESTAMP
        """
        sql_central = sql_main.replace("main.astro_sharpens", "central.astro_sharpens")
        self._execute_dual_write(sql_main, params, sql_central, params)

    def get_astro_sharpens(self, source_stack_path: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera imagens com sharpening registradas no projeto."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        import src.core.project as p_mod
        with p_mod.get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if source_stack_path:
                cursor.execute("SELECT * FROM astro_sharpens WHERE project_name=? AND source_stack_path=? ORDER BY created_at DESC", (self.name, source_stack_path))
            else:
                cursor.execute("SELECT * FROM astro_sharpens WHERE project_name=? ORDER BY created_at DESC", (self.name,))
            for row in cursor.fetchall():
                d = dict(row)
                val = d.get("metadata_json")
                if isinstance(val, str) and val:
                    try:
                        d["metadata_json"] = json.loads(val)
                    except Exception:
                        pass
                results.append(d)
        return results

    def has_astro_sharpens(self) -> bool:
        """Verifica se existem imagens com sharpening concluídas no projeto."""
        sharpens = self.get_astro_sharpens()
        return any(s.get("status") in ("sharpened", "done", "success", "completed") for s in sharpens)

    def is_astro_sharpen_done(self, source_stack_path: str, preset: str = "") -> bool:
        """Verifica se uma imagem de stack já possui sharpening concluído."""
        sharpens = self.get_astro_sharpens(source_stack_path)
        if preset:
            return any(s.get("preset") == preset and s.get("status") in ("sharpened", "done", "success", "completed") for s in sharpens)
        return any(s.get("status") in ("sharpened", "done", "success", "completed") for s in sharpens)
