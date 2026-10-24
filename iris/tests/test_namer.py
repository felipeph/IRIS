from pathlib import Path
from datetime import datetime
from src.core.metadata import MediaMetadata
from src.core.namer import generate_target_filename, sanitize_filename

def test_sanitize_filename():
    assert sanitize_filename('test:file*name?_f1.8') == 'test-file-name_f1-8'
    assert sanitize_filename('clean_name') == 'clean_name'

def test_generate_photo_filename():
    meta = MediaMetadata(
        file_path=Path("IMG_9821.JPG"),
        is_video=False,
        date_str="2026-09-06",
        time_str="14-25-30",
        timestamp=datetime(2026, 9, 6, 14, 25, 30),
        camera_model="SX60",
        camera_make="Canon",
        focal_length_equiv=1365.0,
        focal_str="1365mm",
        aperture_str="f6-5",
        shutter_str="1-1000s",
        iso_str="ISO400",
        resolution_str="16MP",
        width=4608,
        height=3456,
        fps_str="",
        duration_str="",
        original_stem="IMG_9821",
        extension="JPG",
        is_raw=False,
    )
    res = generate_target_filename(meta)
    assert "2026-09-06_14-25-30" in res
    assert "SX60" in res
    assert "16MP" in res
    assert "4608x3456" in res
    assert "1365mm" in res
    assert res.endswith(".jpg")

def test_generate_video_filename():
    meta = MediaMetadata(
        file_path=Path("MVI_0012.MP4"),
        is_video=True,
        date_str="2026-09-06",
        time_str="15-10-00",
        timestamp=datetime(2026, 9, 6, 15, 10, 0),
        camera_model="SX60",
        camera_make="Canon",
        focal_length_equiv=None,
        focal_str="",
        aperture_str="",
        shutter_str="",
        iso_str="",
        resolution_str="1080p",
        width=1920,
        height=1080,
        fps_str="60fps",
        duration_str="12s",
        original_stem="MVI_0012",
        extension="MP4",
        is_raw=False,
    )
    res = generate_target_filename(meta)
    assert "2026-09-06_15-10-00" in res
    assert "1080p" in res
    assert "1920x1080" in res
    assert "60fps" in res
    assert res.endswith(".mp4")

def test_generate_filename_with_gps_token():
    meta = MediaMetadata(
        file_path=Path("IMG_0001.JPG"),
        is_video=False,
        date_str="2026-10-24",
        time_str="12-00-00",
        timestamp=datetime(2026, 10, 24, 12, 0, 0),
        camera_model="SX60",
        camera_make="Canon",
        focal_length_equiv=1365.0,
        focal_str="1365mm",
        aperture_str="f6-5",
        shutter_str="1-1000s",
        iso_str="ISO400",
        resolution_str="16MP",
        width=4608,
        height=3456,
        fps_str="",
        duration_str="",
        original_stem="IMG_0001",
        extension="JPG",
        latitude=-20.456887,
        longitude=-45.438307,
    )
    res = generate_target_filename(meta)
    assert "S20-4569_W45-4383" in res

    # Vídeo com GPS
    meta_vid = MediaMetadata(
        file_path=Path("MVI_0001.MP4"),
        is_video=True,
        date_str="2026-10-24",
        time_str="12-00-00",
        timestamp=datetime(2026, 10, 24, 12, 0, 0),
        camera_model="SX60",
        camera_make="Canon",
        resolution_str="1080p",
        width=1920,
        height=1080,
        fps_str="60fps",
        duration_str="10s",
        original_stem="MVI_0001",
        extension="MP4",
        latitude=-20.456887,
        longitude=-45.438307,
    )
    res_vid = generate_target_filename(meta_vid)
    assert "S20-4569_W45-4383" in res_vid

def test_generate_filename_gps_fallback_project_and_idempotence():
    meta = MediaMetadata(
        file_path=Path("IMG_0001.JPG"),
        is_video=False,
        date_str="2026-10-24",
        time_str="12-00-00",
        timestamp=datetime(2026, 10, 24, 12, 0, 0),
        camera_model="SX60",
        camera_make="Canon",
        resolution_str="16MP",
        width=4608,
        height=3456,
        original_stem="IMG_0001_S20-4569_W45-4383", # já continha token
        extension="JPG",
    )
    # Sem meta.latitude/longitude, mas com project_geo_lat/lng no config
    cfg = {"project_geo_lat": -19.9667, "project_geo_lng": -43.9500}
    res = generate_target_filename(meta, config=cfg)
    # Deve conter o novo token do projeto e não duplicar o antigo
    assert "S19-9667_W43-9500" in res
    assert res.count("S20-4569") == 0
    assert "__" not in res

