import pytest
from pathlib import Path
from datetime import datetime

from src.core.project import (
    Project,
    ProjectItem,
    create_project,
    save_central_edited_video,
    update_central_edited_video_youtube,
    list_central_edited_videos
)
from src.core.pipeline import PipelineRunner
from src.modules.video_edit.namer import (
    generate_edited_video_name,
    resolve_edited_output_path,
    format_number_no_dot
)
from src.modules.video_edit.session import (
    group_videos_into_sessions,
    parse_item_datetime,
    parse_duration_seconds,
    get_item_source_folder
)
from src.modules.video_edit.renderer import build_atempo_chain, build_render_cmd, render_edited_video
from src.modules.video_edit.stage import get_stage as get_video_edit_stage
from src.modules.youtube.describer import (
    build_edited_video_youtube_metadata,
    build_edited_video_youtube_title
)


def test_format_number_no_dot():
    assert format_number_no_dot(1.0) == "1-0"
    assert format_number_no_dot(2) == "2-0"
    assert format_number_no_dot(2, precision=0) == "2"
    assert format_number_no_dot(0.5) == "0-5"
    assert format_number_no_dot(29.97, precision=2) == "29-97"
    assert format_number_no_dot("59.94", precision=2) == "59-94"


def test_generate_edited_video_name_individual_no_dots():
    start_dt = datetime(2026, 8, 17, 14, 30, 0)
    end_dt = datetime(2026, 8, 17, 14, 30, 30)
    
    name = generate_edited_video_name(
        first_dt=start_dt,
        last_dt=end_dt,
        camera_model="Canon PowerShot SX60 HS",
        clip_count=1,
        orig_w=1920,
        orig_h=1080,
        target_w=3840,
        target_h=2160,
        orig_fps=29.97,
        target_fps=60,
        speed=1.0,
        trim_seconds=2.0,
        has_audio=True,
        final_duration_s=26.0
    )
    
    # Assert extension is .mp4
    assert name.endswith(".mp4")
    # Assert body has absolutely no dots
    body = name[:-4]
    assert "." not in body, f"Body of filename contains dots: {body}"
    
    # Assert presence of key metadata components
    assert "2026-08-17_14h30m" in name
    assert "Canon-PowerShot-SX60-HS" in name
    assert "1clipe" in name
    assert "orig-1920x1080_to_4K-3840x2160" in name
    assert "orig29-97fps_to_60fps" in name
    assert "speed1-0x" in name
    assert "trim2-0s" in name
    assert "_audio_" in name
    assert "00m26s" in name
    assert "video_editado.mp4" in name


def test_generate_edited_video_name_joined_mute_no_dots():
    start_dt = datetime(2026, 8, 17, 14, 30, 0)
    end_dt = datetime(2026, 8, 17, 14, 48, 0)
    
    name = generate_edited_video_name(
        first_dt=start_dt,
        last_dt=end_dt,
        camera_model="Sony A7IV",
        clip_count=3,
        orig_w=1920,
        orig_h=1080,
        target_w=3840,
        target_h=2160,
        orig_fps=30.0,
        target_fps=60,
        speed=2.5,
        trim_seconds=0.0,
        has_audio=False,
        final_duration_s=125.4
    )
    
    assert name.endswith(".mp4")
    body = name[:-4]
    assert "." not in body, f"Body contains dots: {body}"
    
    assert "2026-08-17_14h30m-14h48m" in name
    assert "Sony-A7IV" in name
    assert "3clipes" in name
    assert "speed2-5x" in name
    assert "trim0s" in name
    assert "_mute_" in name
    assert "02m05s" in name


def test_resolve_edited_output_path(tmp_path):
    d = datetime(2026, 8, 17, 14, 30, 0)
    filename = "2026-08-17_14h30m_Canon_video_editado.mp4"
    out = resolve_edited_output_path(tmp_path, d, filename)
    expected = tmp_path / "7_Video_Editado_4K" / "2026" / "08" / "17" / filename
    assert out == expected
    assert out.parent.exists()


def test_session_grouping_individual():
    item1 = ProjectItem(
        original_path="/orig/v1.mp4",
        staging_path="/orig/v1.mp4",
        category="video",
        meta_camera_model="Canon SX60",
        meta_timestamp="2026-08-17T14:30:00",
        meta_duration_str="60s"
    )
    item2 = ProjectItem(
        original_path="/orig/v2.mp4",
        staging_path="/orig/v2.mp4",
        category="video",
        meta_camera_model="Canon SX60",
        meta_timestamp="2026-08-17T14:32:00",
        meta_duration_str="60s"
    )
    sessions = group_videos_into_sessions([item1, item2], mode="individual")
    assert len(sessions) == 2
    assert len(sessions[0]) == 1
    assert len(sessions[1]) == 1


def test_get_item_source_folder_normalization():
    # Caminho com original_path
    it1 = ProjectItem(original_path=r"C:\SD_CARD\DCIM\100CANON\MVI_0001.MP4", staging_path="")
    assert "100canon" in get_item_source_folder(it1).lower()

    # Fallback para staging_path
    it2 = ProjectItem(original_path="", staging_path=r"C:\IRIS\1_Entrada\Passaros\video.mp4")
    assert "passaros" in get_item_source_folder(it2).lower()

    # Vazio
    it3 = ProjectItem(original_path="", staging_path="")
    assert get_item_source_folder(it3) == ""


def test_session_grouping_joined_source_folder_and_camera():
    # 2 clipes na mesma pasta A (Canon SX60) em horários próximos
    c1 = ProjectItem(
        original_path="/orig/folder_a/c1.mp4",
        staging_path="/orig/folder_a/c1.mp4",
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-08-17T09:00:00",
        meta_duration_str="60s"
    )
    c2 = ProjectItem(
        original_path="/orig/folder_a/c2.mp4",
        staging_path="/orig/folder_a/c2.mp4",
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-08-17T09:05:00",
        meta_duration_str="60s"
    )
    # 1 clipe na mesma pasta A (Canon SX60), mas 6 horas depois (deve ser concatenado junto!)
    c3 = ProjectItem(
        original_path="/orig/folder_a/c3.mp4",
        staging_path="/orig/folder_a/c3.mp4",
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-08-17T15:00:00",
        meta_duration_str="60s"
    )
    # 1 clipe na mesma pasta A, mas câmera diferente (GoPro) -> sessão separada para proteger concat
    c4 = ProjectItem(
        original_path="/orig/folder_a/c4.mp4",
        staging_path="/orig/folder_a/c4.mp4",
        category="video",
        meta_camera_make="GoPro",
        meta_camera_model="Hero 11",
        meta_timestamp="2026-08-17T09:10:00",
        meta_duration_str="60s"
    )
    # 1 clipe em pasta diferente B (Canon SX60), gravado no mesmo minuto de c1 -> sessão separada
    c5 = ProjectItem(
        original_path="/orig/folder_b/c5.mp4",
        staging_path="/orig/folder_b/c5.mp4",
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-08-17T09:00:30",
        meta_duration_str="60s"
    )

    sessions = group_videos_into_sessions([c1, c2, c3, c4, c5], mode="joined")
    assert len(sessions) == 3
    
    # Sessão 1: folder_a Canon SX60 (c1, c2, c3 juntos, mesmo com 6 horas de diferença)
    assert len(sessions[0]) == 3
    assert sessions[0][0].original_path == "/orig/folder_a/c1.mp4"
    assert sessions[0][1].original_path == "/orig/folder_a/c2.mp4"
    assert sessions[0][2].original_path == "/orig/folder_a/c3.mp4"
    assert sessions[0][0].meta_camera_model == "SX60"
    
    # Sessão 2: folder_b Canon SX60 (c5 isolado pela pasta de origem)
    assert len(sessions[1]) == 1
    assert sessions[1][0].original_path == "/orig/folder_b/c5.mp4"
    
    # Sessão 3: folder_a GoPro (c4 isolado pela câmera)
    assert len(sessions[2]) == 1
    assert sessions[2][0].original_path == "/orig/folder_a/c4.mp4"
    assert sessions[2][0].meta_camera_model == "Hero 11"


def test_build_atempo_chain():
    assert build_atempo_chain(1.0) == ""
    assert build_atempo_chain(1.5) == "atempo=1.5000"
    assert build_atempo_chain(2.0) == "atempo=2.0000"
    assert build_atempo_chain(0.5) == "atempo=0.5000"
    
    # 4.0x speed requires chaining atempo=2.0,atempo=2.0
    chain_4x = build_atempo_chain(4.0)
    assert "atempo=2.0000,atempo=2.0000" in chain_4x

    # 0.2x speed requires chaining atempo=0.5,atempo=0.5,atempo=0.8000
    chain_slow = build_atempo_chain(0.2)
    assert "atempo=0.5000" in chain_slow


def test_project_edited_video_db_persistence(tmp_path):
    proj_name = f"test_db_ve_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    proj = create_project(proj_name, str(tmp_path))
    
    rec = {
        "output_video_path": str(tmp_path / "out_4k.mp4"),
        "source_files": '["/orig/c1.mp4"]',
        "clip_count": 1,
        "mode": "individual",
        "speed": 1.0,
        "target_fps": 60,
        "trim_seconds": 2.0,
        "has_audio": 1,
        "resolution": "3840x2160",
        "orig_resolution": "1920x1080",
        "orig_fps": 30.0,
        "camera_model": "Canon SX60",
        "duration_seconds": 26.0,
        "encoder": "libx264",
        "status": "rendered"
    }
    proj.save_edited_video(rec)
    
    res = proj.get_edited_videos(status="rendered")
    assert len(res) == 1
    assert res[0]["output_video_path"] == str(tmp_path / "out_4k.mp4")
    assert res[0]["clip_count"] == 1
    assert res[0]["speed"] == 1.0
    
    # Update YouTube status
    proj.update_edited_video_youtube(
        str(tmp_path / "out_4k.mp4"),
        "yt_vid_999",
        "https://youtu.be/yt_vid_999"
    )
    
    res_up = proj.get_edited_videos(status="uploaded")
    assert len(res_up) == 1
    assert res_up[0]["youtube_video_id"] == "yt_vid_999"


def test_central_edited_video_persistence(tmp_path):
    out_video = str(tmp_path / f"central_{datetime.now().strftime('%Y%m%d%H%M%S%f')}.mp4")
    rec = {
        "output_video_path": out_video,
        "project_name": "central_test_proj",
        "source_files": '["/v1.mp4"]',
        "clip_count": 1,
        "mode": "individual",
        "speed": 2.0,
        "target_fps": 60,
        "trim_seconds": 2.0,
        "has_audio": 0,
        "resolution": "3840x2160",
        "orig_resolution": "1920x1080",
        "orig_fps": 30.0,
        "camera_model": "Canon SX60",
        "duration_seconds": 15.0,
        "encoder": "h264_nvenc",
        "status": "rendered"
    }
    save_central_edited_video(rec)
    
    all_central = list_central_edited_videos()
    matched = [c for c in all_central if c["output_video_path"] == out_video]
    assert len(matched) == 1
    assert matched[0]["speed"] == 2.0
    
    update_central_edited_video_youtube(
        out_video,
        "cent_yt_123",
        "https://youtu.be/cent_yt_123"
    )
    
    all_central2 = list_central_edited_videos()
    matched2 = [c for c in all_central2 if c["output_video_path"] == out_video]
    assert matched2[0]["status"] == "uploaded"
    assert matched2[0]["youtube_video_id"] == "cent_yt_123"


def test_pipeline_runner_includes_video_edit():
    runner = PipelineRunner()
    stage_ids = [s.stage_id for s in runner.stages]
    assert "video_edit" in stage_ids
    assert "timelapse" in stage_ids
    assert "youtube" in stage_ids
    # video_edit must be before youtube
    ve_idx = stage_ids.index("video_edit")
    yt_idx = stage_ids.index("youtube")
    assert ve_idx < yt_idx


def test_video_edit_stage_empty_project(tmp_path):
    proj_name = f"test_empty_ve_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    proj = create_project(proj_name, str(tmp_path))
    ve_stage = get_video_edit_stage("video_edit", "Edição de Vídeo")
    # Empty project without video items should pass cleanly
    assert ve_stage.run(proj, interactive=False) is True


def test_build_edited_video_youtube_metadata(tmp_path):
    vid_path = tmp_path / "2026-08-17_14h30m_Canon-SX60_orig-1920x1080_to_4K-3840x2160_speed2-0x_mute_video_editado.mp4"
    vid_path.write_bytes(b"dummy video data")
    
    rec = {
        "output_video_path": str(vid_path),
        "camera_model": "Canon PowerShot SX60 HS",
        "clip_count": 2,
        "mode": "joined",
        "orig_resolution": "1920x1080",
        "target_resolution": "3840x2160",
        "orig_fps": 30.0,
        "target_fps": 60,
        "speed_factor": 2.0,
        "trim_start_sec": 2.0,
        "audio_stripped": 1,
        "duration_seconds": 45.0,
        "encoder": "h264_nvenc",
        "metadata_json": {
            "camera_model": "Canon PowerShot SX60 HS",
            "camera_make": "Canon",
            "first_dt_formatted": "17/08/2026 às 14:30:00"
        }
    }
    yt_cfg = {
        "video_playlist": "Natureza 4K UHD",
        "privacy_status": "unlisted"
    }
    
    meta = build_edited_video_youtube_metadata(vid_path, rec, yt_cfg)
    assert "title" in meta
    assert "description" in meta
    assert "tags" in meta
    assert "2026-08-17" in meta["title"]
    assert "14:30" in meta["title"]
    assert "Vídeo 4K UHD" in meta["title"]
    assert "Canon PowerShot SX60 HS" not in meta["title"]
    assert "Canon PowerShot SX60 HS" in meta["description"]
    
    desc = meta["description"]
    assert "TEMPO, CAPTURA E VELOCIDADE" in desc
    assert "EQUIPAMENTO E ARQUIVO ORIGINAL" in desc
    assert "PROCESSAMENTO E ENGENHARIA DE VÍDEO" in desc
    assert "RASTREABILIDADE IRIS" in desc
    assert "Lanczos" in desc
    assert "#4k" in desc


def test_build_edited_video_youtube_title_joined():
    vpath = Path("2026-10-09_16h22m-18h35m_Canon-SX60_3clipes_orig-1920x1080_to_4K-3840x2160_video_editado.mp4")
    rec = {
        "clip_count": 3,
        "duration_seconds": 120.0,
        "metadata_json": {}
    }
    title = build_edited_video_youtube_title(vpath, rec)
    assert title == "2026-10-09 (16:22 - 18:35) - Vídeo 4K UHD"


def test_build_edited_video_youtube_title_single_clip_long():
    # Clipe único com 180s (3 minutos) de duração -> calcula término
    vpath = Path("2026-10-09_16h22m_Canon-SX60_1clipe_video_editado.mp4")
    rec = {
        "clip_count": 1,
        "duration_seconds": 180.0,
        "metadata_json": {}
    }
    title = build_edited_video_youtube_title(vpath, rec)
    assert title == "2026-10-09 (16:22 - 16:25) - Vídeo 4K UHD"


def test_build_edited_video_youtube_title_single_clip_short():
    # Clipe único curto (25 segundos) -> mesmo minuto
    vpath = Path("2026-10-09_16h22m_Canon-SX60_1clipe_video_editado.mp4")
    rec = {
        "clip_count": 1,
        "duration_seconds": 25.0,
        "metadata_json": {}
    }
    title = build_edited_video_youtube_title(vpath, rec)
    assert title == "2026-10-09 (16:22) - Vídeo 4K UHD"


def test_build_edited_video_youtube_title_fallback_meta():
    # Arquivo com nome arbitrário -> usa metadata_json
    vpath = Path("meu_video_customizado.mp4")
    rec = {
        "metadata_json": {
            "first_dt_iso": "2026-10-09T16:22:00",
            "last_dt_iso": "2026-10-09T18:35:00"
        }
    }
    title = build_edited_video_youtube_title(vpath, rec)
    assert title == "2026-10-09 (16:22 - 18:35) - Vídeo 4K UHD"


def test_build_render_cmd_profiles(tmp_path):
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    clip1.write_bytes(b"dummy1")
    clip2.write_bytes(b"dummy2")
    out = tmp_path / "out.mp4"
    
    infos = [
        {"duration": 10.0, "has_audio": True},
        {"duration": 10.0, "has_audio": True}
    ]
    
    # 1. Teste Perfil FAST com QSV (Hardware Acceleration)
    cmd_fast_qsv, unsharp_f, deband_f = build_render_cmd(
        clip_paths=[clip1, clip2],
        clip_infos=infos,
        output_video_path=out,
        trim_starts=[2.0, 2.0],
        trimmed_durs=[6.0, 6.0],
        speed=1.0,
        target_fps=60,
        target_w=3840,
        target_h=2160,
        render_profile="fast",
        encoder_name="h264_qsv (Intel Quick Sync)",
        encoder_args=["-c:v", "h264_qsv"],
        has_any_audio=True
    )
    cmd_fast_qsv_str = " ".join(cmd_fast_qsv)
    assert "-hwaccel qsv" in cmd_fast_qsv_str
    assert "vpp_qsv=w=3840:h=2160:scale_mode=hq:framerate=60" in cmd_fast_qsv_str
    assert "unsharp" not in cmd_fast_qsv_str
    assert "deband" not in cmd_fast_qsv_str
    assert unsharp_f is False
    assert deband_f is False

    # 2. Teste Perfil FAST com CPU (Sem QSV)
    cmd_fast_cpu, _, _ = build_render_cmd(
        clip_paths=[clip1],
        clip_infos=[infos[0]],
        output_video_path=out,
        trim_starts=[0.0],
        trimmed_durs=[10.0],
        speed=1.0,
        target_fps=60,
        target_w=3840,
        target_h=2160,
        render_profile="fast",
        encoder_name="libx264 (CPU)",
        encoder_args=["-c:v", "libx264"],
        has_any_audio=False
    )
    cmd_fast_cpu_str = " ".join(cmd_fast_cpu)
    assert "scale=3840:2160:flags=bicubic" in cmd_fast_cpu_str
    assert "unsharp" not in cmd_fast_cpu_str
    assert "deband" not in cmd_fast_cpu_str

    # 3. Teste Perfil BALANCED
    cmd_bal, unsharp_b, deband_b = build_render_cmd(
        clip_paths=[clip1],
        clip_infos=[infos[0]],
        output_video_path=out,
        trim_starts=[0.0],
        trimmed_durs=[10.0],
        speed=1.0,
        target_fps=60,
        target_w=3840,
        target_h=2160,
        render_profile="balanced",
        encoder_name="h264_qsv (Intel Quick Sync)",
        encoder_args=["-c:v", "h264_qsv"],
        has_any_audio=False
    )
    cmd_bal_str = " ".join(cmd_bal)
    assert "unsharp=luma_msize_x=3" in cmd_bal_str
    assert "scale=3840:2160:flags=bicubic+accurate_rnd" in cmd_bal_str
    assert "deband" not in cmd_bal_str
    assert unsharp_b is True
    assert deband_b is False

    # 4. Teste Perfil QUALITY
    cmd_qual, unsharp_q, deband_q = build_render_cmd(
        clip_paths=[clip1],
        clip_infos=[infos[0]],
        output_video_path=out,
        trim_starts=[0.0],
        trimmed_durs=[10.0],
        speed=1.0,
        target_fps=60,
        target_w=3840,
        target_h=2160,
        render_profile="quality",
        encoder_name="h264_qsv (Intel Quick Sync)",
        encoder_args=["-c:v", "h264_qsv"],
        has_any_audio=False
    )
    cmd_qual_str = " ".join(cmd_qual)
    assert "unsharp=luma_msize_x=5" in cmd_qual_str
    assert "deband=" in cmd_qual_str
    assert "scale=3840:2160:flags=lanczos+accurate_rnd+full_chroma_int" in cmd_qual_str
    assert unsharp_q is True
    assert deband_q is True


def test_build_edited_video_youtube_metadata_profiles(tmp_path):
    vid_path = tmp_path / "sample_video_editado.mp4"
    vid_path.write_bytes(b"dummy")
    yt_cfg = {"video_playlist": "Natureza 4K UHD", "privacy_status": "unlisted"}

    # Fast Profile
    rec_fast = {
        "output_video_path": str(vid_path),
        "camera_model": "PowerShot SX60 HS",
        "clip_count": 1,
        "metadata_json": {"render_profile": "fast"}
    }
    meta_fast = build_edited_video_youtube_metadata(vid_path, rec_fast, yt_cfg)
    assert "Perfil Rápido" in meta_fast["description"]
    assert "Intel QSV VPP" in meta_fast["description"]
    assert "Intel QSV" in meta_fast["tags"]

    # Balanced Profile
    rec_bal = {
        "output_video_path": str(vid_path),
        "camera_model": "PowerShot SX60 HS",
        "clip_count": 1,
        "metadata_json": {"render_profile": "balanced"}
    }
    meta_bal = build_edited_video_youtube_metadata(vid_path, rec_bal, yt_cfg)
    assert "Perfil Balanceado" in meta_bal["description"]
    assert "Bicúbica" in meta_bal["description"]
    assert "Bicubic" in meta_bal["tags"]

    # Quality Profile
    rec_qual = {
        "output_video_path": str(vid_path),
        "camera_model": "PowerShot SX60 HS",
        "clip_count": 1,
        "metadata_json": {"render_profile": "quality"}
    }
    meta_qual = build_edited_video_youtube_metadata(vid_path, rec_qual, yt_cfg)
    assert "Perfil Qualidade Máxima" in meta_qual["description"]
    assert "Lanczos" in meta_qual["description"]
    assert "Lanczos" in meta_qual["tags"]


def test_build_render_cmd_force_software(tmp_path):
    clip1 = tmp_path / "clip1.mp4"
    clip1.write_bytes(b"dummy")
    out_video = tmp_path / "out.mp4"

    cmd_soft, unsharp, deband = build_render_cmd(
        clip_paths=[clip1],
        clip_infos=[{"duration": 10.0, "has_audio": True}],
        output_video_path=out_video,
        trim_starts=[0.0],
        trimmed_durs=[10.0],
        speed=1.0,
        target_fps=60,
        target_w=3840,
        target_h=2160,
        render_profile="fast",
        encoder_name="h264_qsv (Intel Quick Sync)",
        encoder_args=["-c:v", "h264_qsv"],
        has_any_audio=True,
        force_software=True
    )
    cmd_str = " ".join(cmd_soft)
    assert "-hwaccel qsv" not in cmd_str
    assert "vpp_qsv" not in cmd_str
    assert "scale=3840:2160:flags=bicubic" in cmd_str


def test_render_edited_video_software_fallback(tmp_path, monkeypatch):
    import io
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"dummy")
    out_video = tmp_path / "out.mp4"

    monkeypatch.setattr(
        "src.modules.video_edit.renderer.get_video_stream_info",
        lambda p: {"duration": 5.0, "has_audio": False}
    )

    def mock_detect(preset="ultrafast", crf=15, force_cpu=False, force_recheck=False):
        if force_cpu:
            return "libx264 (CPU)", ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
        return "h264_qsv (Intel Quick Sync)", ["-c:v", "h264_qsv"]

    monkeypatch.setattr("src.modules.video_edit.renderer.detect_ffmpeg_encoder", mock_detect)

    calls = []

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            self.cmd = cmd
            self.stdout = []
            calls.append(cmd)
            if len(calls) == 1:
                self.returncode = 1
                self.stderr = io.StringIO("MFX_ERR_DEVICE_BUSY\n")
            else:
                self.returncode = 0
                self.stderr = io.StringIO("")
                out_video.write_bytes(b"0" * 2000)

        def poll(self):
            return self.returncode

        def wait(self):
            pass

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    cfg = {
        "speed": 1.0,
        "target_fps": 60,
        "render_profile": "fast"
    }

    ok, enc_used, err, stats = render_edited_video(
        clip_paths=[clip],
        output_video_path=out_video,
        config=cfg
    )

    assert ok is True
    assert len(calls) == 2
    assert "libx264" in enc_used

