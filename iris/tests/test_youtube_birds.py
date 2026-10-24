import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock

from src.modules.youtube.describer import (
    sanitize_hashtag,
    resolve_bird_identification,
    build_bird_youtube_title,
    format_bird_taxonomy_block,
    build_bird_hashtags,
    resolve_bird_target_playlists,
    build_edited_video_youtube_metadata,
    build_edited_video_youtube_title
)
from src.modules.youtube.uploader import (
    build_timelapse_youtube_metadata,
    add_video_to_playlists,
    clear_playlist_cache,
    _PLAYLIST_CACHE
)


def test_sanitize_hashtag():
    assert sanitize_hashtag("Bem-te-vi") == "BemTeVi"
    assert sanitize_hashtag("Pitangus sulphuratus") == "PitangusSulphuratus"
    assert sanitize_hashtag("Great Kiskadee") == "GreatKiskadee"
    assert sanitize_hashtag("Beija-flor-de-fronte-violeta") == "BeijaFlorDeFronteVioleta"
    assert sanitize_hashtag("Observação de Aves!") == "ObservacaoDeAves"
    assert sanitize_hashtag("") == ""


def test_build_bird_youtube_title_standard():
    p = Path("2026-10-23_14h30m_Canon-SX60_video_editado.mp4")
    record = {
        "duration_seconds": 35.0,
        "metadata_json": {}
    }
    bird_info = {
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee"
    }

    title = build_bird_youtube_title(p, record, bird_info)
    assert "Bem-te-vi (Pitangus sulphuratus) - Great Kiskadee" in title
    assert "2026-10-23" in title
    assert "(14:30)" in title
    assert "Vídeo 4K UHD" not in title
    assert "4K UHD" not in title
    assert len(title) <= 100


def test_build_bird_youtube_title_without_english():
    p = Path("2026-10-23_14h30m_video.mp4")
    record = {"duration_seconds": 10.0, "metadata_json": {}}
    bird_info = {
        "species_common": "Sabiá-laranjeira",
        "species_scientific": "Turdus rufiventris",
        "species_common_en": ""
    }

    title = build_bird_youtube_title(p, record, bird_info)
    assert title.startswith("Sabiá-laranjeira (Turdus rufiventris) | 2026-10-23")
    assert "Vídeo 4K UHD" not in title
    assert len(title) <= 100


def test_build_bird_youtube_title_long_name_compression():
    p = Path("2026-10-23_14h30m-16h45m_Super-Long-Camera-Name_4K_video.mp4")
    record = {"duration_seconds": 120.0, "metadata_json": {}}
    bird_info = {
        "species_common": "Beija-flor-de-gravata-vermelha-da-mata-atlantica",
        "species_scientific": "Augastes scutatus grandis extremus",
        "species_common_en": "Atlantic Forest Red-throated Giant Hummingbird"
    }

    title = build_bird_youtube_title(p, record, bird_info)
    assert "Vídeo 4K UHD" not in title
    assert len(title) <= 100
    assert "Beija-flor" in title


def test_format_bird_taxonomy_block():
    bird_info = {
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "family": "Tyrannidae",
        "order": "Passeriformes",
        "confidence": 0.954,
        "taxon_id": 16045
    }

    block = format_bird_taxonomy_block(bird_info)
    assert "🐦 IDENTIFICAÇÃO TAXONÔMICA (AVES):" in block
    assert "• Espécie (Nome Popular): Bem-te-vi" in block
    assert "• Nome em Inglês: Great Kiskadee" in block
    assert "• Nome Científico: Pitangus sulphuratus" in block
    assert "• Família: Tyrannidae" in block
    assert "• Ordem: Passeriformes" in block
    assert "• Classe: Aves" in block
    assert "• Reino: Animalia" in block
    assert "• Grau de Certeza: 95.4% (Visão Computacional iNaturalist)" in block
    assert "• Ficha da Espécie no iNaturalist: https://www.inaturalist.org/taxa/16045" in block


def test_build_bird_hashtags():
    bird_info = {
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "family": "Tyrannidae",
        "order": "Passeriformes"
    }

    hts = build_bird_hashtags(bird_info)
    assert "#BemTeVi" in hts
    assert "#PitangusSulphuratus" in hts
    assert "#GreatKiskadee" in hts
    assert "#Tyrannidae" in hts
    assert "#Passeriformes" in hts
    assert "#Aves" in hts
    assert "#Birdwatching" in hts
    assert "#Ornitologia" in hts


def test_resolve_bird_target_playlists_full():
    bird_info = {
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee"
    }
    yt_cfg = {
        "bird_playlist": "Birds 4K",
        "bird_playlists": {
            "general": True,
            "scientific_name": True,
            "common_name_pt": True,
            "common_name_en": True
        }
    }

    pls = resolve_bird_target_playlists(bird_info, yt_cfg)
    assert pls == ["Birds 4K", "Pitangus sulphuratus", "Bem-te-vi", "Great Kiskadee"]


def test_resolve_bird_target_playlists_filtered_by_config():
    bird_info = {
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee"
    }
    yt_cfg = {
        "bird_playlist": "Aves do Brasil",
        "bird_playlists": {
            "general": True,
            "scientific_name": True,
            "common_name_pt": False,
            "common_name_en": False
        }
    }

    pls = resolve_bird_target_playlists(bird_info, yt_cfg)
    assert pls == ["Aves do Brasil", "Pitangus sulphuratus"]


def test_build_edited_video_youtube_metadata_with_bird(tmp_path):
    vid = tmp_path / "2026-10-23_14h30m_Canon-SX60_video_editado.mp4"
    vid.write_bytes(b"dummy")

    rec = {
        "output_video_path": str(vid),
        "source_video_paths": ["C:/fake/clip1.mp4"],
        "metadata_json": {
            "camera_model": "Canon PowerShot SX60 HS",
            "camera_make": "Canon",
            "first_dt_formatted": "23/10/2026 às 14:30:00",
            "bird_identification": {
                "species_common": "Bem-te-vi",
                "species_scientific": "Pitangus sulphuratus",
                "species_common_en": "Great Kiskadee",
                "family": "Tyrannidae",
                "order": "Passeriformes",
                "confidence": 0.962,
                "taxon_id": 16045
            }
        }
    }
    yt_cfg = {
        "bird_playlist": "Birds 4K",
        "privacy_status": "unlisted"
    }

    meta = build_edited_video_youtube_metadata(vid, rec, yt_cfg)
    assert "Bem-te-vi (Pitangus sulphuratus) - Great Kiskadee" in meta["title"]
    assert "Vídeo 4K UHD" not in meta["title"]
    assert "Registro em altíssima definição de Bem-te-vi" in meta["description"]
    assert "🐦 IDENTIFICAÇÃO TAXONÔMICA (AVES):" in meta["description"]
    assert "Tyrannidae" in meta["description"]
    assert "#BemTeVi" in meta["description"]
    assert "#PitangusSulphuratus" in meta["description"]
    assert "Pitangus sulphuratus" in meta["tags"]
    assert "Great Kiskadee" in meta["tags"]
    assert meta["playlists"] == ["Birds 4K", "Pitangus sulphuratus", "Bem-te-vi", "Great Kiskadee"]
    assert meta["bird_info"] is not None


def test_build_edited_video_youtube_metadata_without_bird(tmp_path):
    vid = tmp_path / "2026-10-23_14h30m_Canon-SX60_video_editado.mp4"
    vid.write_bytes(b"dummy")

    rec = {
        "output_video_path": str(vid),
        "source_video_paths": ["C:/fake/paisagem.mp4"],
        "metadata_json": {
            "camera_model": "Canon PowerShot SX60 HS",
            "camera_make": "Canon",
            "first_dt_formatted": "23/10/2026 às 14:30:00"
        }
    }
    yt_cfg = {
        "video_playlist": "Natureza 4K UHD",
        "privacy_status": "unlisted"
    }

    meta = build_edited_video_youtube_metadata(vid, rec, yt_cfg)
    assert "- Vídeo 4K UHD" in meta["title"]
    assert "🐦 IDENTIFICAÇÃO TAXONÔMICA" not in meta["description"]
    assert meta["playlists"] == ["Natureza 4K UHD"]
    assert meta["bird_info"] is None


def test_build_timelapse_youtube_metadata_with_bird(tmp_path):
    vid = tmp_path / "2026-10-23_14h30m_Canon_timelapse.mp4"
    vid.write_bytes(b"dummy")

    rec = {
        "output_video_path": str(vid),
        "sequence_dir": "C:/fake/seq",
        "metadata_json": {
            "camera_model": "Canon SX60",
            "camera_make": "Canon",
            "date_str": "2026-10-23",
            "bird_identification": {
                "species_common": "Tucano-toco",
                "species_scientific": "Ramphastos toco",
                "species_common_en": "Toco Toucan",
                "family": "Ramphastidae",
                "order": "Piciformes",
                "confidence": 0.985
            }
        }
    }
    yt_cfg = {
        "bird_playlist": "Birds 4K",
        "privacy_status": "unlisted"
    }

    meta = build_timelapse_youtube_metadata(vid, rec, yt_cfg)
    assert "Tucano-toco (Ramphastos toco) - Toco Toucan" in meta["title"]
    assert "Vídeo 4K UHD" not in meta["title"]
    assert "🐦 IDENTIFICAÇÃO TAXONÔMICA (AVES):" in meta["description"]
    assert "#TucanoToco" in meta["description"]
    assert meta["playlists"] == ["Birds 4K", "Ramphastos toco", "Tucano-toco", "Toco Toucan"]


def test_add_video_to_playlists_mocked():
    clear_playlist_cache()
    mock_youtube = MagicMock()

    # Simula resposta de listagem sem playlists existentes
    mock_youtube.playlists().list().execute.return_value = {"items": [], "nextPageToken": None}
    # Simula criação de playlists
    mock_youtube.playlists().insert().execute.side_effect = [
        {"id": "PL_BIRDS_4K", "snippet": {"title": "Birds 4K"}},
        {"id": "PL_BEM_TE_VI", "snippet": {"title": "Bem-te-vi"}}
    ]
    # Simula inserção dos itens
    mock_youtube.playlistItems().insert().execute.return_value = {"id": "ITEM_1"}

    pls = ["Birds 4K", "Bem-te-vi"]
    res = add_video_to_playlists(mock_youtube, "VID_123", pls)

    assert len(res) == 2
    assert res[0] == (True, "PL_BIRDS_4K", "Birds 4K")
    assert res[1] == (True, "PL_BEM_TE_VI", "Bem-te-vi")

    # Verifica se foram cacheadas
    assert "birds 4k" in _PLAYLIST_CACHE
    assert "bem-te-vi" in _PLAYLIST_CACHE

    clear_playlist_cache()
