import os
import sys
import json
import time
import socket
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional, List

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube"
]

_GEOCODE_CACHE = {}

SECRETS_DIR = Path(__file__).resolve().parents[3] / "secrets"

def find_client_secrets_file() -> Optional[Path]:
    """Retorna o client_secrets.json em iris/secrets/, se existir."""
    path = SECRETS_DIR / "client_secrets.json"
    return path if path.exists() else None

def find_token_file() -> Path:
    """Retorna o caminho de token.json em iris/secrets/ (criando a pasta se preciso)."""
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    return SECRETS_DIR / "token.json"

def save_token_atomic(token_path: Path, creds: Credentials):
    """Salva credenciais em token_path de forma atômica."""
    temp_path = token_path.with_suffix(f".tmp.{os.getpid()}")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        os.replace(temp_path, token_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)

def get_authenticated_service():
    """Autentica na YouTube Data API v3 usando OAuth 2.0 e renova/gera o token.json."""
    creds = None
    token_path = find_token_file()

    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                save_token_atomic(token_path, creds)
            except Exception:
                creds = None

        if not creds:
            client_secrets = find_client_secrets_file()
            if not client_secrets:
                return None
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
            creds = flow.run_local_server(port=0, prompt='consent')
            save_token_atomic(token_path, creds)

    return build("youtube", "v3", credentials=creds)

def reverse_geocode_coordinates(lat: float, lon: float, timeout: float = 4.0) -> Dict[str, str]:
    """Geocodificação reversa usando OpenStreetMap Nominatim."""
    key = (round(lat, 4), round(lon, 4))
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]

    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=14&addressdetails=1"
    headers = {"User-Agent": "IRIS-MediaStudio/1.0"}

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                address = data.get("address", {})
                city = address.get("city") or address.get("town") or address.get("municipality") or address.get("suburb") or ""
                state = address.get("state") or address.get("region") or ""
                country = address.get("country") or ""
                parts = [p for p in [city, state, country] if p]
                formatted = ", ".join(parts) if parts else data.get("display_name", "")
                res = {
                    "city": city,
                    "state": state,
                    "country": country,
                    "formatted_address": formatted
                }
                _GEOCODE_CACHE[key] = res
                return res
    except Exception:
        pass
    return {"city": "", "state": "", "country": "", "formatted_address": ""}

def add_video_to_playlist(youtube, video_id: str, playlist_name_or_id: str, privacy: str = "unlisted") -> Tuple[bool, Optional[str], Optional[str]]:
    """Adiciona o vídeo à playlist do canal (cria a playlist automaticamente se não existir)."""
    if not youtube or not video_id or not playlist_name_or_id:
        return False, None, None

    playlist_target = str(playlist_name_or_id).strip()
    playlist_id = None
    playlist_title = playlist_target

    try:
        if playlist_target.startswith("PL") and len(playlist_target) >= 16:
            playlist_id = playlist_target
        else:
            next_page = None
            while True:
                req = youtube.playlists().list(part="snippet", mine=True, maxResults=50, pageToken=next_page)
                resp = req.execute()
                for item in resp.get("items", []):
                    item_title = item.get("snippet", {}).get("title", "")
                    if item_title.strip().lower() == playlist_target.lower():
                        playlist_id = item["id"]
                        playlist_title = item_title
                        break
                if playlist_id or not resp.get("nextPageToken"):
                    break
                next_page = resp.get("nextPageToken")

            if not playlist_id:
                create_privacy = privacy.lower() if privacy in ["public", "unlisted", "private"] else "unlisted"
                new_pl = youtube.playlists().insert(
                    part="snippet,status",
                    body={
                        "snippet": {"title": playlist_target, "description": "Timelapses 4K UHD gerados pelo IRIS."},
                        "status": {"privacyStatus": create_privacy}
                    }
                ).execute()
                playlist_id = new_pl.get("id")
                playlist_title = new_pl.get("snippet", {}).get("title", playlist_target)

        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id}
                }
            }
        ).execute()
        return True, playlist_id, playlist_title

    except Exception:
        return False, None, None

from src.modules.youtube.describer import (
    build_rich_youtube_description,
    build_youtube_title,
    build_youtube_tags,
)

def build_timelapse_youtube_metadata(
    video_path: Path,
    tl_record: Dict[str, Any],
    yt_config: Dict[str, Any],
    project: Optional[Any] = None
) -> Dict[str, Any]:
    """Compila título e descrição rica para envio ao YouTube."""
    privacy = yt_config.get("privacy_status", "unlisted")
    category_id = str(yt_config.get("category_id", "22"))

    record_copy = dict(tl_record)
    project_name = getattr(project, "name", "") if project else record_copy.get("project_name", "")

    # Se metadata_json não existe ou está vazio, monta fallback a partir do nome ou items do projeto
    meta = record_copy.get("metadata_json")
    if not isinstance(meta, dict) or not meta:
        meta = {}
        # Tenta extrair dados do nome do arquivo
        # Ex: 2016-05-14_22h15m-22h28m_Canon_4608x3456_4K_60fps_1fpi_50x_00m10s_timelapse.mp4
        parts = video_path.name.split('_')
        if len(parts) > 0:
            meta["date_str"] = parts[0]
        if len(parts) > 2 and not parts[2].startswith("timelapse") and "x" not in parts[2]:
            meta["camera_model"] = parts[2]
        
        # Se houver itens do projeto correspondentes à sequência
        seq_dir = record_copy.get("sequence_dir")
        if project and hasattr(project, "items") and seq_dir:
            matched_items = [
                it for it in project.items 
                if it.organized_path and Path(it.organized_path).parent.resolve() == Path(seq_dir).resolve()
            ]
            if matched_items:
                first_it = matched_items[0]
                meta["camera_make"] = first_it.meta_camera_make or "Cam"
                meta["camera_model"] = first_it.meta_camera_model or meta.get("camera_model", "Camera")
                meta["orig_width"] = first_it.meta_width or 0
                meta["orig_height"] = first_it.meta_height or 0
                meta["total_orig_size_bytes"] = sum(it.file_size_bytes for it in matched_items if it.file_size_bytes)
                meta["orig_formats"] = sorted(list({it.meta_extension.upper().lstrip('.') for it in matched_items if it.meta_extension}))
                meta["apertures"] = [it.meta_aperture_str for it in matched_items if it.meta_aperture_str]
                meta["shutters"] = [it.meta_shutter_str for it in matched_items if it.meta_shutter_str]
                meta["isos"] = [it.meta_iso_str for it in matched_items if it.meta_iso_str]
                meta["focals"] = [it.meta_focal_str for it in matched_items if it.meta_focal_str]
                if first_it.meta_focal_length_equiv:
                    meta["focal_equiv_summary"] = f"{first_it.meta_focal_length_equiv:.0f}mm"
                if first_it.meta_timestamp:
                    meta["first_dt_iso"] = first_it.meta_timestamp
                if matched_items[-1].meta_timestamp:
                    meta["last_dt_iso"] = matched_items[-1].meta_timestamp

        record_copy["metadata_json"] = meta

    # Atualiza tamanho do vídeo se existir no disco e não estiver preenchido
    if video_path.exists() and "video_size_bytes" not in record_copy["metadata_json"]:
        record_copy["metadata_json"]["video_size_bytes"] = video_path.stat().st_size

    title = build_youtube_title(video_path, record_copy)
    description = build_rich_youtube_description(record_copy, project_name=project_name)
    tags = build_youtube_tags(record_copy)

    return {
        "title": title[:100],
        "description": description[:5000],
        "tags": tags,
        "category_id": category_id,
        "privacy_status": privacy
    }
