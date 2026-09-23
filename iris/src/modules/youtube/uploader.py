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

def find_client_secrets_file() -> Optional[Path]:
    """Busca o client_secrets.json nas pastas de segredos conhecidas."""
    candidates = [
        Path("secrets/client_secrets.json"),
        Path("iris/secrets/client_secrets.json"),
        Path("c:/code/IRIS/secrets/client_secrets.json"),
        Path("c:/code/IRIS/iris/secrets/client_secrets.json"),
        Path("C:/code/FOTOGRAFIA/timelapse/secrets/client_secrets.json")
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None

def find_token_file() -> Path:
    """Retorna o caminho preferencial para token.json."""
    candidates = [
        Path("secrets/token.json"),
        Path("iris/secrets/token.json"),
        Path("c:/code/IRIS/secrets/token.json"),
        Path("c:/code/IRIS/iris/secrets/token.json"),
        Path("C:/code/FOTOGRAFIA/timelapse/secrets/token.json")
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    
    # Se não existe em nenhum lugar, salvar em c:/code/IRIS/secrets/token.json
    default_path = Path("c:/code/IRIS/secrets/token.json")
    default_path.parent.mkdir(parents=True, exist_ok=True)
    return default_path

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

def build_timelapse_youtube_metadata(
    video_path: Path,
    tl_record: Dict[str, Any],
    yt_config: Dict[str, Any]
) -> Dict[str, Any]:
    """Compila título e descrição rica para envio ao YouTube."""
    privacy = yt_config.get("privacy_status", "unlisted")
    category_id = str(yt_config.get("category_id", "22"))

    first_dt_str = None
    last_dt_str = None
    name = video_path.name

    # Tenta extrair datas do nome do arquivo
    # Ex: 2016-05-14_22h15m-22h28m_...
    parts = name.split('_')
    date_part = parts[0] if len(parts) > 0 else datetime.now().strftime('%Y-%m-%d')
    time_part = parts[1] if len(parts) > 1 else ""

    if "-" in time_part:
        t1, t2 = time_part.split("-", 1)
        t1_clean = t1.replace('h', ':').replace('m', '')
        t2_clean = t2.replace('h', ':').replace('m', '')
        title = f"{date_part} ({t1_clean} - {t2_clean}) - Timelapse 4K UHD"
    else:
        title = f"{date_part} - Timelapse 4K UHD"

    photo_count = tl_record.get("photo_count", 0)
    dur_sec = tl_record.get("duration_seconds", 0)
    speedup = tl_record.get("speedup_factor", 1)
    encoder = tl_record.get("encoder", "FFmpeg")
    fps = tl_record.get("fps", 60)
    res = tl_record.get("resolution", "3840x2160")

    description = f"""Vídeo Timelapse renderizado em alta definição 4K UHD ({res}) a {fps} FPS.

⚙️ DADOS TÉCNICOS:
• Data de Captura: {date_part}
• Fotos da Sequência: {photo_count:,} fotos
• Duração do Vídeo: {dur_sec:.1f} segundos
• Fator de Aceleração: {speedup}x
• Processamento: IRIS Timelapse Studio ({encoder})
• Resolução: 4K UHD (3840x2160) - 16:9

Automação completa via IRIS (Integrated Recording and Ingestion System).
"""

    tags = ["timelapse", "4k", "uhd", "60fps", "natureza", "fotografia", "iris", date_part]

    return {
        "title": title[:100],
        "description": description[:5000],
        "tags": tags,
        "category_id": category_id,
        "privacy_status": privacy
    }
