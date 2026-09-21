from pathlib import Path
from datetime import datetime, timedelta
from src.core.metadata import MediaMetadata
from src.core.classifier import classify_media_batch, find_timelapse_segments

def test_classify_video():
    meta = MediaMetadata(
        file_path=Path("MVI_0012.MP4"),
        is_video=True,
        date_str="2026-09-06",
        time_str="15-10-00",
        timestamp=datetime(2026, 9, 6, 15, 10, 0),
        camera_model="SX60",
        camera_make="Canon",
        resolution_str="1080p",
        fps_str="60fps",
        duration_str="12s",
        original_stem="MVI_0012",
        extension="MP4",
        is_raw=False,
    )
    items = classify_media_batch([meta])
    assert len(items) == 1
    assert items[0].category == "video"
    assert "3_Videos" in str(items[0].relative_dest_dir)

def test_classify_moon_photo():
    meta = MediaMetadata(
        file_path=Path("IMG_9999.CR2"),
        is_video=False,
        date_str="2026-09-06",
        time_str="20-00-00",
        timestamp=datetime(2026, 9, 6, 20, 0, 0),
        camera_model="SX60",
        camera_make="Canon",
        focal_length_equiv=1365.0,
        focal_str="1365mm",
        original_stem="IMG_9999",
        extension="CR2",
        is_raw=True,
    )
    items = classify_media_batch([meta], class_config={"moon_zoom_threshold_mm": 1000.0})
    assert len(items) == 1
    assert items[0].category == "astro_lua"
    assert "5_Astrofotografia" in str(items[0].relative_dest_dir)

def test_classify_avulsa_photo():
    meta = MediaMetadata(
        file_path=Path("IMG_1234.JPG"),
        is_video=False,
        date_str="2026-09-06",
        time_str="12-00-00",
        timestamp=datetime(2026, 9, 6, 12, 0, 0),
        camera_model="T6",
        camera_make="Canon",
        focal_length_equiv=50.0,
        focal_str="50mm",
        original_stem="IMG_1234",
        extension="JPG",
        is_raw=False,
    )
    items = classify_media_batch([meta])
    assert len(items) == 1
    assert items[0].category == "avulsa"
    assert "2_AlbunsDatas" in str(items[0].relative_dest_dir)
