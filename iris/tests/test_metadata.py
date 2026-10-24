import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.core.metadata import (
    get_video_info_ffprobe,
    get_video_dimensions_ffprobe,
    get_video_duration_ffprobe,
    extract_metadata_batch,
    format_duration
)

def test_get_video_info_ffprobe_mocked(tmp_path):
    dummy_video = tmp_path / "sample.mp4"
    dummy_video.write_bytes(b"dummy_mp4_bytes")

    fake_ffprobe_output = {
        "streams": [
            {
                "width": 3840,
                "height": 2160,
                "r_frame_rate": "60/1"
            }
        ],
        "format": {
            "duration": "12.345"
        }
    }

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(fake_ffprobe_output)

    with patch("shutil.which", return_value="ffprobe"), \
         patch("subprocess.run", return_value=mock_proc) as mock_run:
        info = get_video_info_ffprobe(dummy_video)
        assert info["width"] == 3840
        assert info["height"] == 2160
        assert info["duration"] == 12.345
        assert info["r_frame_rate"] == "60/1"

        # Compatibilidade com getters específicos (deve reutilizar a mesma função)
        w, h = get_video_dimensions_ffprobe(dummy_video)
        assert w == 3840
        assert h == 2160
        dur = get_video_duration_ffprobe(dummy_video)
        assert dur == 12.345

        # Confere comando ffprobe emitido com -of json e -show_entries consolidado
        cmd = mock_run.call_args[0][0]
        assert "-of" in cmd
        assert "json" in cmd
        assert "-select_streams" in cmd

def test_extract_metadata_batch_consolidated_ffprobe(tmp_path):
    dummy_video = tmp_path / "vid.mp4"
    dummy_video.write_bytes(b"dummy")

    fake_ffprobe = {
        "width": 1920,
        "height": 1080,
        "duration": 45.0,
        "r_frame_rate": "30/1"
    }

    # Simula exiftool ausente ou retornando sem tags de vídeo
    with patch("src.core.metadata.shutil.which", side_effect=lambda x: "bin" if x == "ffprobe" else None), \
         patch("src.core.metadata.get_video_info_ffprobe", return_value=fake_ffprobe) as mock_ff:
        results = extract_metadata_batch([dummy_video])
        assert len(results) == 1
        meta = results[0]
        assert meta.is_video is True
        assert meta.width == 1920
        assert meta.height == 1080
        assert meta.duration_str == "45s"
        assert meta.resolution_str == "1080p"
        # Deve ter invocado o ffprobe apenas 1 vez para o arquivo
        assert mock_ff.call_count == 1

def test_format_focal_standard_35mm():
    from src.core.metadata import format_focal
    val, s = format_focal("50mm", "32mm")
    assert val == 50.0
    assert s == "50mm"

def test_format_focal_35efl_composite():
    from src.core.metadata import format_focal
    # Caso típico Canon SX60 HS onde FocalLengthIn35mmFormat é None, mas ExifTool fornece FocalLength35efl
    val, s = format_focal(None, "247.0 mm", focal_35efl=1385.84, scale_factor=5.61)
    assert val == 1385.84
    assert s == "1386mm"

def test_format_focal_scale_factor_fallback():
    from src.core.metadata import format_focal
    # Caso onde só há focal real e scale factor
    val, s = format_focal(None, "247.0 mm", focal_35efl=None, scale_factor=5.6107)
    assert round(val, 1) == 1385.8
    assert s == "1386mm"

def test_format_focal_real_only_fallback():
    from src.core.metadata import format_focal
    # Caso sem crop factor nem 35mm
    val, s = format_focal(None, "247.0 mm", focal_35efl=None, scale_factor=None)
    assert val == 247.0
    assert s == "247mm"

def test_format_focal_none():
    from src.core.metadata import format_focal
    val, s = format_focal(None, None)
    assert val == 0.0
    assert s == "0mm"

def test_extract_metadata_batch_canon_sx60_raw(tmp_path):
    dummy_cr2 = tmp_path / "IMG_4197.CR2"
    dummy_cr2.write_bytes(b"dummy_cr2")

    fake_exif = [
        {
            "SourceFile": str(dummy_cr2.resolve()),
            "DateTimeOriginal": "2026:10:18 20:41:09",
            "Make": "Canon",
            "Model": "Canon PowerShot SX60 HS",
            "FocalLength": "247.0 mm",
            "FocalLength35efl": 1385.84,
            "ScaleFactor35efl": 5.61,
            "FNumber": 6.5,
            "ExposureTime": "1/200",
            "ISO": 200,
            "ImageWidth": 2048,
            "ImageHeight": 1536
        }
    ]

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(fake_exif)

    with patch("src.core.metadata.shutil.which", return_value="exiftool"), \
         patch("subprocess.run", return_value=mock_proc) as mock_run:
        results = extract_metadata_batch([dummy_cr2])
        assert len(results) == 1
        meta = results[0]
        assert meta.is_raw is True
        assert meta.camera_make == "Canon"
        assert meta.camera_model == "PowerShot-SX60-HS"
        assert meta.focal_length_equiv == 1385.84
        assert meta.focal_str == "1386mm"
        assert meta.shutter_str == "1-200s"
        assert meta.aperture_str == "f6-5"
        assert meta.iso_str == "ISO200"

def test_parse_gps_from_raw_exif():
    from src.core.metadata import parse_gps_from_raw_exif
    # Formato EXIF tradicional com ref
    raw1 = {
        "GPSLatitude": 20.456887,
        "GPSLatitudeRef": "S",
        "GPSLongitude": 45.438307,
        "GPSLongitudeRef": "W",
        "GPSHPositioningError": 12.5
    }
    lat, lng, acc = parse_gps_from_raw_exif(raw1)
    assert lat == -20.456887
    assert lng == -45.438307
    assert acc == 12.5

    # Formato QuickTime video
    raw2 = {
        "GPSCoordinates": "-20.456887-045.438307+200.000/"
    }
    lat2, lng2, acc2 = parse_gps_from_raw_exif(raw2)
    assert lat2 == -20.456887
    assert lng2 == -45.438307
    assert acc2 is None

def test_extract_metadata_batch_with_gps(tmp_path):
    from src.core.metadata import extract_metadata_batch
    dummy_jpg = tmp_path / "GPS_IMG.JPG"
    dummy_jpg.write_bytes(b"dummy_jpg")

    fake_exif = [
        {
            "SourceFile": str(dummy_jpg.resolve()),
            "DateTimeOriginal": "2026:10:18 12:00:00",
            "Make": "Canon",
            "Model": "PowerShot",
            "GPSLatitude": 20.456887,
            "GPSLatitudeRef": "S",
            "GPSLongitude": 45.438307,
            "GPSLongitudeRef": "W",
            "GPSHPositioningError": 5.0
        }
    ]

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps(fake_exif)

    with patch("src.core.metadata.shutil.which", return_value="exiftool"), \
         patch("subprocess.run", return_value=mock_proc) as mock_run:
        results = extract_metadata_batch([dummy_jpg])
        assert len(results) == 1
        assert results[0].latitude == -20.456887
        assert results[0].longitude == -45.438307
        assert results[0].gps_accuracy == 5.0

        cmd = mock_run.call_args[0][0]
        assert "-GPSLatitude#" in cmd
        assert "-GPSLongitude#" in cmd
