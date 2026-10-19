"""
ProjectMediaMixin (RFC 09).
Gerencia operações CRUD e persistência de timelapses e vídeos editados,
com suporte a dual-write atômico no banco local e central.
"""

import json
import sqlite3
from typing import List, Dict, Any, Optional


class ProjectMediaMixin:
    """Mixin com operações relativas a mídias processadas (timelapses e vídeos editados)."""

    def save_timelapse(self, record: dict):
        """Salva ou atualiza um timelapse no banco do projeto e sincroniza atomicamente no central via ATTACH (RFC 08)."""
        self._ensure_db_initialized()
        record_copy = dict(record)
        record_copy["project_name"] = self.name
        
        raw_meta = record_copy.get("metadata_json", {})
        if isinstance(raw_meta, (dict, list)):
            meta_json_str = json.dumps(raw_meta, ensure_ascii=False)
        elif isinstance(raw_meta, str):
            meta_json_str = raw_meta
        else:
            meta_json_str = "{}"
        
        params = (
            self.name,
            record_copy.get("sequence_dir", ""),
            record_copy.get("output_video_path", ""),
            record_copy.get("photo_count", 0),
            record_copy.get("fps", 60),
            record_copy.get("frames_per_image", 1),
            record_copy.get("resolution", "3840x2160"),
            record_copy.get("crop_mode", "bottom"),
            record_copy.get("encoder", ""),
            record_copy.get("duration_seconds", 0.0),
            record_copy.get("speedup_factor", 1),
            record_copy.get("youtube_video_id", ""),
            record_copy.get("youtube_url", ""),
            record_copy.get("youtube_privacy", "unlisted"),
            record_copy.get("status", "rendered"),
            meta_json_str
        )
        sql_main = """
            INSERT INTO main.timelapses (
                project_name, sequence_dir, output_video_path, photo_count,
                fps, frames_per_image, resolution, crop_mode, encoder,
                duration_seconds, speedup_factor, youtube_video_id, youtube_url,
                youtube_privacy, status, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(output_video_path) DO UPDATE SET
                photo_count=excluded.photo_count,
                fps=excluded.fps,
                frames_per_image=excluded.frames_per_image,
                resolution=excluded.resolution,
                crop_mode=excluded.crop_mode,
                encoder=excluded.encoder,
                duration_seconds=excluded.duration_seconds,
                speedup_factor=excluded.speedup_factor,
                youtube_video_id=COALESCE(excluded.youtube_video_id, timelapses.youtube_video_id),
                youtube_url=COALESCE(excluded.youtube_url, timelapses.youtube_url),
                youtube_privacy=COALESCE(excluded.youtube_privacy, timelapses.youtube_privacy),
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
        """
        sql_central = sql_main.replace("main.timelapses", "central.timelapses")
        self._execute_dual_write(sql_main, params, sql_central, params)

    def get_timelapses(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera todos os timelapses do projeto (opcionalmente filtrando por status)."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        import src.core.project as p_mod
        with p_mod.get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM timelapses WHERE status=? ORDER BY created_at ASC", (status,))
            else:
                cursor.execute("SELECT * FROM timelapses ORDER BY created_at ASC")
            for row in cursor.fetchall():
                d = dict(row)
                d["local_file_deleted"] = bool(d.get("local_file_deleted", 0))
                val = d.get("metadata_json")
                if isinstance(val, str) and val:
                    try:
                        d["metadata_json"] = json.loads(val)
                    except Exception:
                        pass
                results.append(d)
        return results

    def has_timelapses(self) -> bool:
        """Verifica se existem timelapses renderizados ou registrados."""
        tls = self.get_timelapses()
        return any(t.get("status") in ("rendered", "done", "success") for t in tls)

    def update_timelapse_youtube(self, video_path: str, video_id: str, url: str):
        """Atualiza metadados do YouTube tanto no banco do projeto quanto no banco central atomicamente (RFC 08)."""
        sql_main = """
            UPDATE main.timelapses
            SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """
        sql_central = sql_main.replace("main.timelapses", "central.timelapses")
        params = (video_id, url, video_path)
        self._execute_dual_write(sql_main, params, sql_central, params)

    def mark_timelapse_local_deleted(self, video_path: str):
        """Marca o vídeo renderizado como apagado localmente no banco do projeto e no central atomicamente (RFC 08)."""
        sql_main = """
            UPDATE main.timelapses
            SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """
        sql_central = sql_main.replace("main.timelapses", "central.timelapses")
        params = (video_path,)
        self._execute_dual_write(sql_main, params, sql_central, params)

    def save_edited_video(self, record: dict):
        """Salva ou atualiza um vídeo editado no banco do projeto e sincroniza atomicamente no central via ATTACH (RFC 08)."""
        self._ensure_db_initialized()
        record_copy = dict(record)
        record_copy["project_name"] = self.name

        raw_meta = record_copy.get("metadata_json", {})
        if isinstance(raw_meta, (dict, list)):
            meta_json_str = json.dumps(raw_meta, ensure_ascii=False)
        elif isinstance(raw_meta, str):
            meta_json_str = raw_meta
        else:
            meta_json_str = "{}"

        src_paths = record_copy.get("source_video_paths", record_copy.get("source_files", []))
        if isinstance(src_paths, (list, tuple)):
            src_paths_str = json.dumps(list(src_paths), ensure_ascii=False)
        elif isinstance(src_paths, str):
            src_paths_str = src_paths
        else:
            src_paths_str = "[]"

        speed = record_copy.get("speed_factor", record_copy.get("speed", 1.0))
        target_res = record_copy.get("target_resolution", record_copy.get("resolution", ""))
        audio_stripped = 1 if (record_copy.get("audio_stripped", False) or record_copy.get("has_audio") == 0) else 0

        params = (
            self.name,
            src_paths_str,
            record_copy.get("output_video_path", ""),
            record_copy.get("mode", "single"),
            record_copy.get("clip_count", 1),
            speed,
            record_copy.get("orig_fps", 0.0),
            record_copy.get("target_fps", 0.0),
            record_copy.get("orig_resolution", ""),
            target_res,
            record_copy.get("trim_start_sec", record_copy.get("trim_seconds", 0.0)),
            record_copy.get("trim_end_sec", 0.0),
            audio_stripped,
            record_copy.get("duration_seconds", 0.0),
            record_copy.get("encoder", ""),
            record_copy.get("youtube_video_id", ""),
            record_copy.get("youtube_url", ""),
            record_copy.get("youtube_privacy", "unlisted"),
            record_copy.get("status", "rendered"),
            meta_json_str
        )
        sql_main = """
            INSERT INTO main.edited_videos (
                project_name, source_video_paths, output_video_path, mode,
                clip_count, speed_factor, orig_fps, target_fps, orig_resolution,
                target_resolution, trim_start_sec, trim_end_sec, audio_stripped,
                duration_seconds, encoder, youtube_video_id, youtube_url,
                youtube_privacy, status, metadata_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(output_video_path) DO UPDATE SET
                source_video_paths=excluded.source_video_paths,
                mode=excluded.mode,
                clip_count=excluded.clip_count,
                speed_factor=excluded.speed_factor,
                orig_fps=excluded.orig_fps,
                target_fps=excluded.target_fps,
                orig_resolution=excluded.orig_resolution,
                target_resolution=excluded.target_resolution,
                trim_start_sec=excluded.trim_start_sec,
                trim_end_sec=excluded.trim_end_sec,
                audio_stripped=excluded.audio_stripped,
                duration_seconds=excluded.duration_seconds,
                encoder=excluded.encoder,
                youtube_video_id=COALESCE(excluded.youtube_video_id, edited_videos.youtube_video_id),
                youtube_url=COALESCE(excluded.youtube_url, edited_videos.youtube_url),
                youtube_privacy=COALESCE(excluded.youtube_privacy, edited_videos.youtube_privacy),
                status=excluded.status,
                metadata_json=excluded.metadata_json,
                updated_at=CURRENT_TIMESTAMP
        """
        sql_central = sql_main.replace("main.edited_videos", "central.edited_videos")
        self._execute_dual_write(sql_main, params, sql_central, params)

    def get_edited_videos(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera todos os vídeos editados do projeto (opcionalmente filtrando por status)."""
        if not self._project_db_file.exists():
            return []
        self._init_project_db()
        results = []
        import src.core.project as p_mod
        with p_mod.get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status:
                cursor.execute("SELECT * FROM edited_videos WHERE status=? ORDER BY created_at ASC", (status,))
            else:
                cursor.execute("SELECT * FROM edited_videos ORDER BY created_at ASC")
            for row in cursor.fetchall():
                d = dict(row)
                d["local_file_deleted"] = bool(d.get("local_file_deleted", 0))
                d["speed"] = d.get("speed_factor", 1.0)
                d["resolution"] = d.get("target_resolution", "")
                d["has_audio"] = 0 if d.get("audio_stripped", 0) else 1
                val = d.get("metadata_json")
                if isinstance(val, str) and val:
                    try:
                        d["metadata_json"] = json.loads(val)
                    except Exception:
                        pass
                raw_src = d.get("source_video_paths")
                if isinstance(raw_src, str) and raw_src:
                    try:
                        d["source_video_paths"] = json.loads(raw_src)
                    except Exception:
                        d["source_video_paths"] = [raw_src]
                results.append(d)
        return results

    def has_edited_videos(self) -> bool:
        """Verifica se existem vídeos editados com status renderizado."""
        evs = self.get_edited_videos()
        return any(v.get("status") in ("rendered", "done", "success") for v in evs)

    def update_edited_video_youtube(self, video_path: str, video_id: str, url: str):
        """Atualiza metadados do YouTube de vídeo editado no banco local e no central atomicamente (RFC 08)."""
        sql_main = """
            UPDATE main.edited_videos
            SET youtube_video_id=?, youtube_url=?, status='uploaded', updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """
        sql_central = sql_main.replace("main.edited_videos", "central.edited_videos")
        params = (video_id, url, video_path)
        self._execute_dual_write(sql_main, params, sql_central, params)

    def mark_edited_video_local_deleted(self, video_path: str):
        """Marca o vídeo editado como apagado localmente no banco do projeto e no central atomicamente (RFC 08)."""
        sql_main = """
            UPDATE main.edited_videos
            SET local_file_deleted=1, updated_at=CURRENT_TIMESTAMP
            WHERE output_video_path=?
        """
        sql_central = sql_main.replace("main.edited_videos", "central.edited_videos")
        params = (video_path,)
        self._execute_dual_write(sql_main, params, sql_central, params)
