from pathlib import Path
from datetime import datetime, timedelta

from src.core.metadata import MediaMetadata
from src.core.classifier import classify_media_batch
from src.core.event import (
    EventInfo, PeopleCatalog, ALBUM_SKIPPED_STAGE_IDS, build_exiftool_event_args, parse_names,
)
from src.core.project import create_project, get_project


def _meta(i, ext="JPG", video=False, raw=False, focal=None, seconds=0):
    ts = datetime(2026, 9, 6, 15, 0, 0) + timedelta(seconds=seconds)
    return MediaMetadata(
        file_path=Path(f"IMG_{i:04d}.{ext}"), is_video=video,
        date_str=ts.strftime("%Y-%m-%d"), time_str=ts.strftime("%H-%M-%S"), timestamp=ts,
        camera_model="X", camera_make="Canon", focal_length_equiv=focal,
        original_stem=f"IMG_{i:04d}", extension=ext, is_raw=raw,
    )


def test_event_info_normalizes_names():
    ev = EventInfo("  Aniversário   da Ana ", ["Ana", "ana", " João ", "", "Maria"])
    assert ev.name == "Aniversário da Ana"
    assert ev.participants == ["Ana", "João", "Maria"]
    assert ev.keywords[0] == "Aniversário da Ana"
    assert "Pessoa|João" in ev.hierarchical and "Evento|Aniversário da Ana" in ev.hierarchical


def test_parse_names():
    assert parse_names("Ana, João; ana , Maria") == ["Ana", "João", "Maria"]


def test_event_args_only_for_writable_formats():
    ev = EventInfo("Festa", ["Ana"])
    assert build_exiftool_event_args(ev, ext=".cr2") == []
    assert build_exiftool_event_args(ev, ext=".mp4") == []
    args = build_exiftool_event_args(ev, ext=".jpg")
    assert "-Keywords+=Festa" in args and "-Subject+=Ana" in args
    assert "-XMP-lr:HierarchicalSubject+=Pessoa|Ana" in args
    assert "-XMP-dc:Title=Festa" in args


def test_event_args_remove_previous_values():
    args = build_exiftool_event_args(EventInfo("Novo", []), previous=EventInfo("Antigo", ["Ana"]), ext=".jpg")
    assert "-Keywords-=Antigo" in args and "-Keywords-=Ana" in args
    assert args.index("-Keywords-=Antigo") < args.index("-Keywords+=Novo")


def test_album_mode_treats_everything_as_avulsa():
    # Cadência de timelapse (200 fotos a cada 5s), RAW de lua e vídeo
    items = [_meta(i, seconds=i * 5) for i in range(200)]
    items.append(_meta(500, ext="CR2", raw=True, focal=1500.0, seconds=2000))
    items.append(_meta(501, ext="MP4", video=True, seconds=2100))
    out = classify_media_batch(items, album_mode=True, event_name="Festa / Ana")
    assert len(out) == 202
    assert {c.category for c in out} == {"avulsa", "album_video"}
    assert all(c.burst_id == "" for c in out)
    dirs = {str(c.relative_dest_dir).replace("\\", "/") for c in out}
    assert len(dirs) == 1
    only_dir = next(iter(dirs))
    assert only_dir.startswith("2_AlbunsDatas/") and only_dir.endswith("/2026/09/06")
    assert "5_Astrofotografia" not in only_dir


def test_album_mode_splits_multiple_days():
    day1 = _meta(1, seconds=0)
    day2 = _meta(2, seconds=86400)  # 2026-09-07
    out = classify_media_batch([day2, day1], album_mode=True, event_name="Viagem")
    dirs = [str(c.relative_dest_dir).replace("\\", "/") for c in out]
    assert dirs == [
        "2_AlbunsDatas/Viagem/2026/09/06",
        "2_AlbunsDatas/Viagem/2026/09/07",
    ]


def test_normal_mode_unchanged_for_bursts():
    items = [_meta(1, seconds=0), _meta(2, seconds=1)]
    out = classify_media_batch(items)
    assert {c.category for c in out} == {"rajada"}


def test_album_skips_expected_stages():
    for sid in ("bird_id", "astro_stack", "timelapse", "video_edit", "youtube"):
        assert sid in ALBUM_SKIPPED_STAGE_IDS
    assert "sanitization" not in ALBUM_SKIPPED_STAGE_IDS


def test_project_event_persistence_and_default():
    p = create_project("evt_proj", "C:/src", event=EventInfo("Casamento", ["Ana", "Beto"]))
    loaded = get_project("evt_proj")
    assert loaded.is_event and loaded.event_name == "Casamento"
    assert loaded.event_participants == ["Ana", "Beto"]

    create_project("plain_proj", "C:/src")
    plain = get_project("plain_proj")
    assert plain.is_event is False and plain.event_participants == []


def test_people_catalog_roundtrip():
    PeopleCatalog.register(["Ana", "ana", "Beto"])
    assert PeopleCatalog.list()[0] == "Ana"
    assert set(PeopleCatalog.list()) == {"Ana", "Beto"}
    assert PeopleCatalog.rename("Beto", "Roberto")
    assert PeopleCatalog.delete("Ana")
    assert PeopleCatalog.list() == ["Roberto"]
