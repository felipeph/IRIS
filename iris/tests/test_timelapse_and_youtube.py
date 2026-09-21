import pytest
from pathlib import Path
from datetime import datetime

from src.core.project import Project, create_project
from src.core.pipeline import PipelineRunner
from src.modules.timelapse.encoder import detect_ffmpeg_encoder
from src.modules.timelapse.namer import generate_timelapse_video_name, resolve_produced_output_path
from src.modules.timelapse.sequence import prepare_numbered_sequence, clean_sequence_dir
from src.modules.timelapse.stage import get_stage as get_timelapse_stage
from src.modules.youtube.stage import get_stage as get_youtube_stage
from src.modules.youtube.uploader import build_timelapse_youtube_metadata

def test_detect_ffmpeg_encoder():
    label, args = detect_ffmpeg_encoder()
    assert isinstance(label, str) and len(label) > 0
    assert "-c:v" in args

def test_generate_timelapse_video_name():
    d1 = datetime(2026, 8, 17, 16, 55, 0)
    d2 = datetime(2026, 8, 17, 18, 30, 0)
    name = generate_timelapse_video_name(
        first_dt=d1,
        last_dt=d2,
        camera_model="Canon PowerShot SX60 HS",
        orig_w=4608,
        orig_h=3456,
        total_photos=1000,
        fps=60,
        fpi=1,
        target_height=2160,
        is_test=False
    )
    assert name.startswith("2026-08-17_16h55m-18h30m_Canon-PowerShot-SX60-HS_4608x3456_4K_60fps_1fpi_")
    assert name.endswith("_timelapse.mp4")

def test_resolve_produced_output_path(tmp_path):
    d1 = datetime(2026, 9, 21, 10, 0, 0)
    video_name = "test_timelapse.mp4"
    out_path = resolve_produced_output_path(tmp_path, d1, video_name)
    expected = tmp_path / "6_Produzidos" / "2026" / "09" / "21" / "test_timelapse.mp4"
    assert out_path == expected
    assert out_path.parent.exists()

def test_prepare_and_clean_sequence(tmp_path):
    src_dir = tmp_path / "photos"
    src_dir.mkdir()
    p1 = src_dir / "IMG_0001.JPG"
    p2 = src_dir / "IMG_0002.JPG"
    p1.write_bytes(b"dummy image 1")
    p2.write_bytes(b"dummy image 2")

    ok, temp_dir, sorted_photos = prepare_numbered_sequence([p1, p2], src_dir)
    assert ok is True
    assert temp_dir.exists()
    assert (temp_dir / "000001.jpg").exists()
    assert (temp_dir / "000002.jpg").exists()
    assert len(sorted_photos) == 2

    clean_sequence_dir(temp_dir)
    assert not temp_dir.exists()

def test_pipeline_runner_includes_new_stages():
    runner = PipelineRunner()
    stage_ids = [s.stage_id for s in runner.stages]
    assert "timelapse" in stage_ids
    assert "youtube" in stage_ids

def test_empty_project_stages_graceful_pass(tmp_path):
    proj_name = f"test_empty_tl_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    proj = create_project(proj_name, str(tmp_path))
    tl_stage = get_timelapse_stage("timelapse", "Render")
    yt_stage = get_youtube_stage("youtube", "Upload")

    assert tl_stage.run(proj) is True
    assert yt_stage.run(proj, interactive=False) is True

def test_project_timelapse_db_persistence(tmp_path):
    proj_name = f"test_db_tl_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    proj = create_project(proj_name, str(tmp_path))
    record = {
        "sequence_dir": str(tmp_path / "seq"),
        "output_video_path": str(tmp_path / "out.mp4"),
        "photo_count": 300,
        "fps": 60,
        "frames_per_image": 1,
        "resolution": "3840x2160",
        "crop_mode": "bottom",
        "encoder": "libx264",
        "duration_seconds": 5.0,
        "speedup_factor": 60,
        "status": "rendered"
    }
    proj.save_timelapse(record)
    
    tls = proj.get_timelapses(status="rendered")
    assert len(tls) == 1
    assert tls[0]["output_video_path"] == str(tmp_path / "out.mp4")

    # Update with YouTube info
    proj.update_timelapse_youtube(str(tmp_path / "out.mp4"), "test_yt_id", "https://youtu.be/test_yt_id")
    tls_up = proj.get_timelapses(status="uploaded")
    assert len(tls_up) == 1
    assert tls_up[0]["youtube_video_id"] == "test_yt_id"
    assert tls_up[0]["youtube_url"] == "https://youtu.be/test_yt_id"


def test_build_timelapse_youtube_metadata():
    vpath = Path("2026-08-17_16h55m-18h30m_Canon_4608x3456_4K_60fps_1fpi_50x_00m10s_timelapse.mp4")
    record = {
        "photo_count": 600,
        "duration_seconds": 10.0,
        "speedup_factor": 50,
        "encoder": "h264_qsv",
        "fps": 60,
        "resolution": "3840x2160"
    }
    yt_config = {"privacy_status": "unlisted", "category_id": "22"}
    meta = build_timelapse_youtube_metadata(vpath, record, yt_config)

    assert "2026-08-17" in meta["title"]
    assert "16:55 - 18:30" in meta["title"]
    assert "4K UHD" in meta["title"]
    assert "600" in meta["description"]
    assert meta["privacy_status"] == "unlisted"
    assert "timelapse" in meta["tags"]
