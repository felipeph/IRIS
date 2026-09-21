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
    assert "60fps" in res
    assert res.endswith(".mp4")
