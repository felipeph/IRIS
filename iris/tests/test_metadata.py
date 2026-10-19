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
