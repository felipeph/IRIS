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
    get_item_source_folder,
    summarize_session_cameras,
)
from src.modules.video_edit.renderer import (
    build_atempo_chain,
    build_render_cmd,
    build_concat_demuxer_cmd,
    render_edited_video,
    is_same_aspect_ratio,
    build_scale_pad_filter,
    get_video_stream_info,
)
from src.modules.video_edit.stage import get_stage as get_video_edit_stage
from src.modules.youtube.describer import (
    format_chapters_block,
    build_edited_video_youtube_metadata,
    build_edited_video_youtube_title,
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
    assert "2026-08-17_14-30" in name
    assert "Canon-PowerShot-SX60-HS" in name
    assert "1clipe" in name
    assert "1920x1080-to-3840x2160" in name
    assert "fps-29-97-to-60" in name
    assert "_1-0x_" in name
    assert "trim2-0s" in name
    assert "_audio_" in name
    assert "00m26s" in name
    assert "video_editado" not in name


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
    
    assert "2026-08-17_14-30" in name
    assert "Sony-A7IV" in name
    assert "3clipes" in name
    assert "1920x1080-to-3840x2160" in name
    assert "fps-30-to-60" in name
    assert "_2-5x_" in name
    assert "trim0s" in name
    assert "_mute_" in name
    assert "02m05s" in name
    assert "video_editado" not in name


def test_generate_edited_video_name_with_bird_and_gps():
    start_dt = datetime(2026, 10, 23, 14, 30, 0)
    end_dt = datetime(2026, 10, 23, 14, 35, 0)
    
    name = generate_edited_video_name(
        first_dt=start_dt,
        last_dt=end_dt,
        camera_model="Canon PowerShot SX60 HS",
        clip_count=3,
        orig_w=1920,
        orig_h=1080,
        target_w=3840,
        target_h=2160,
        orig_fps=30.0,
        target_fps=60,
        speed=1.0,
        trim_seconds=2.0,
        has_audio=True,
        final_duration_s=45.0,
        species_pt="Bem-te-vi",
        lat=-20.456887,
        lng=-45.438307
    )
    
    assert name.endswith(".mp4")
    assert "." not in name[:-4]
    assert name == "2026-10-23_14-30_Bem-te-vi_Canon-PowerShot-SX60-HS_3clipes_1920x1080-to-3840x2160_fps-30-to-60_1-0x_trim2-0s_audio_00m45s_S20-4569_W45-4383.mp4"


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
    # 1 clipe na mesma pasta A, mas câmera diferente (GoPro) -> agora unificado na mesma sessão da pasta!
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
    assert len(sessions) == 2
    
    # Sessão 1: folder_a unifica Canon SX60 e GoPro Hero 11 ordenados cronologicamente
    assert len(sessions[0]) == 4
    assert sessions[0][0].original_path == "/orig/folder_a/c1.mp4"
    assert sessions[0][1].original_path == "/orig/folder_a/c2.mp4"
    assert sessions[0][2].original_path == "/orig/folder_a/c4.mp4"
    assert sessions[0][3].original_path == "/orig/folder_a/c3.mp4"
    assert sessions[0][0].meta_camera_model == "SX60"
    assert sessions[0][2].meta_camera_model == "Hero 11"
    
    # Sessão 2: folder_b Canon SX60 (c5 isolado pela pasta de origem)
    assert len(sessions[1]) == 1
    assert sessions[1][0].original_path == "/orig/folder_b/c5.mp4"


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
    assert res[0]["source_video_paths"] == ["/orig/c1.mp4"]
    
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
    assert "Vídeo 4K UHD" not in meta["title"]
    assert "Canon PowerShot SX60 HS" not in meta["title"]
    assert "Canon PowerShot SX60 HS" in meta["description"]
    
    desc = meta["description"]
    assert "TEMPO, CAPTURA E VELOCIDADE" in desc
    assert "EQUIPAMENTO E ARQUIVO ORIGINAL" in desc
    assert "PROCESSAMENTO E ENGENHARIA DE VÍDEO" in desc
    assert "RASTREABILIDADE IRIS" in desc
    assert "Lanczos" in desc
    assert "#4k" in desc


def test_build_edited_video_youtube_metadata_single_clip(tmp_path):
    vid_path = tmp_path / "2026-08-17_14h30m_Canon-SX60_1clipe_video_editado.mp4"
    vid_path.write_bytes(b"dummy")
    rec = {
        "output_video_path": str(vid_path),
        "source_video_paths": ["C:/input/2026-08-17_14-30-00_Canon-SX60.mp4"],
        "clip_count": 1,
        "mode": "individual",
        "metadata_json": {}
    }
    meta = build_edited_video_youtube_metadata(vid_path, rec, {})
    desc = meta["description"]
    assert "• Arquivo Original: 2026-08-17_14-30-00_Canon-SX60.mp4" in desc


def test_build_edited_video_youtube_metadata_joined_source_list(tmp_path):
    vid_path = tmp_path / "2026-08-17_14h30m-15h10m_GoPro10_3clipes_video_editado.mp4"
    vid_path.write_bytes(b"dummy video")

    rec = {
        "output_video_path": str(vid_path),
        "source_video_paths": [
            "C:/input/session1/2026-08-17_14-30-00_GoPro10.mp4",
            "C:/input/session1/2026-08-17_14-35-15_GoPro10.mp4",
            "C:/input/session1/2026-08-17_14-40-30_GoPro10.mp4",
        ],
        "clip_count": 3,
        "mode": "joined",
        "duration_seconds": 90.0,
        "metadata_json": {
            "camera_model": "GoPro HERO10 Black",
            "camera_make": "GoPro",
            "first_dt_formatted": "17/08/2026 às 14:30:00"
        }
    }
    yt_cfg = {"video_playlist": "Natureza 4K UHD"}
    meta = build_edited_video_youtube_metadata(vid_path, rec, yt_cfg)
    desc = meta["description"]

    assert "• Modo de Edição: Sessão Concatenada (3 clipes unidos)" in desc
    assert "• Arquivos Originais Concatenados:" in desc
    assert "  - 2026-08-17_14-30-00_GoPro10.mp4" in desc
    assert "  - 2026-08-17_14-35-15_GoPro10.mp4" in desc
    assert "  - 2026-08-17_14-40-30_GoPro10.mp4" in desc
    assert "..." not in desc


def test_build_edited_video_youtube_metadata_joined_json_string(tmp_path):
    vid_path = tmp_path / "out.mp4"
    vid_path.write_bytes(b"dummy")
    rec = {
        "output_video_path": str(vid_path),
        "source_video_paths": '["C:/a/clipA.mp4", "C:/b/clipB.mp4"]',
        "clip_count": 2,
        "mode": "joined",
        "metadata_json": {}
    }
    meta = build_edited_video_youtube_metadata(vid_path, rec, {})
    desc = meta["description"]
    assert "  - clipA.mp4" in desc
    assert "  - clipB.mp4" in desc


def test_build_edited_video_youtube_title_joined():
    vpath = Path("2026-10-09_16h22m-18h35m_Canon-SX60_3clipes_orig-1920x1080_to_4K-3840x2160_video_editado.mp4")
    rec = {
        "clip_count": 3,
        "duration_seconds": 120.0,
        "metadata_json": {}
    }
    title = build_edited_video_youtube_title(vpath, rec)
    assert title.startswith("2026-10-09 (16:22 - 18:35)")
    assert "Vídeo 4K UHD" not in title


def test_build_edited_video_youtube_title_single_clip_long():
    # Clipe único com 180s (3 minutos) de duração -> calcula término
    vpath = Path("2026-10-09_16h22m_Canon-SX60_1clipe_video_editado.mp4")
    rec = {
        "clip_count": 1,
        "duration_seconds": 180.0,
        "metadata_json": {}
    }
    title = build_edited_video_youtube_title(vpath, rec)
    assert title.startswith("2026-10-09 (16:22 - 16:25)")
    assert "Vídeo 4K UHD" not in title


def test_build_edited_video_youtube_title_single_clip_short():
    # Clipe único curto (25 segundos) -> mesmo minuto
    vpath = Path("2026-10-09_16h22m_Canon-SX60_1clipe_video_editado.mp4")
    rec = {
        "clip_count": 1,
        "duration_seconds": 25.0,
        "metadata_json": {}
    }
    title = build_edited_video_youtube_title(vpath, rec)
    assert title.startswith("2026-10-09 (16:22)")
    assert "Vídeo 4K UHD" not in title


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
    assert title.startswith("2026-10-09 (16:22 - 18:35)")
    assert "Vídeo 4K UHD" not in title


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


def test_group_videos_auto_join_birds_same_species_same_day():
    """Valida o agrupamento automático de múltiplos vídeos da mesma espécie de ave gravados no mesmo dia."""
    # 3 clipes de Bem-te-vi no dia 2026-10-25
    b1 = ProjectItem(
        original_path="/dcim/b1.mp4", staging_path="/staging/b1.mp4", organized_path="/iris/3_Videos/2026/10/25/Bem-te-vi/b1.mp4",
        category="video", meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T09:00:00", meta_duration_str="30s"
    )
    b2 = ProjectItem(
        original_path="/dcim/b2.mp4", staging_path="/staging/b2.mp4", organized_path="/iris/3_Videos/2026/10/25/Bem-te-vi/b2.mp4",
        category="video", meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T11:30:00", meta_duration_str="45s"
    )
    b3 = ProjectItem(
        original_path="/dcim/b3.mp4", staging_path="/staging/b3.mp4", organized_path="/iris/3_Videos/2026/10/25/Bem-te-vi/b3.mp4",
        category="video", meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T16:00:00", meta_duration_str="20s"
    )

    # 2 clipes de Sabiá-laranjeira no dia 2026-10-25
    s1 = ProjectItem(
        original_path="/dcim/s1.mp4", staging_path="/staging/s1.mp4", organized_path="/iris/3_Videos/2026/10/25/Sabia-laranjeira/s1.mp4",
        category="video", meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T10:00:00", meta_duration_str="40s"
    )
    s2 = ProjectItem(
        original_path="/dcim/s2.mp4", staging_path="/staging/s2.mp4", organized_path="/iris/3_Videos/2026/10/25/Sabia-laranjeira/s2.mp4",
        category="video", meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T14:00:00", meta_duration_str="50s"
    )

    # 1 clipe de Bem-te-vi no dia seguinte (2026-10-26) -> deve formar sessão separada por ser outro dia
    b_next_day = ProjectItem(
        original_path="/dcim/b_next.mp4", staging_path="/staging/b_next.mp4", organized_path="/iris/3_Videos/2026/10/26/Bem-te-vi/b_next.mp4",
        category="video", meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-26T08:00:00", meta_duration_str="60s"
    )

    # 1 clipe de paisagem sem ave no dia 2026-10-25
    land = ProjectItem(
        original_path="/dcim/land.mp4", staging_path="/staging/land.mp4", organized_path="/iris/3_Videos/2026/10/25/land.mp4",
        category="video", meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T12:00:00", meta_duration_str="15s"
    )

    bird_map = {
        "/staging/b1.mp4": {"species_common": "Bem-te-vi", "species_scientific": "Pitangus sulphuratus", "confidence": 0.85, "needs_review": False},
        "/staging/b2.mp4": {"species_common": "Bem-te-vi", "species_scientific": "Pitangus sulphuratus", "confidence": 0.90, "needs_review": False},
        "/staging/b3.mp4": {"species_common": "Bem-te-vi", "species_scientific": "Pitangus sulphuratus", "confidence": 0.88, "needs_review": False},
        "/staging/s1.mp4": {"species_common": "Sabiá-laranjeira", "species_scientific": "Turdus rufiventris", "confidence": 0.92, "needs_review": False},
        "/staging/s2.mp4": {"species_common": "Sabiá-laranjeira", "species_scientific": "Turdus rufiventris", "confidence": 0.95, "needs_review": False},
        "/staging/b_next.mp4": {"species_common": "Bem-te-vi", "species_scientific": "Pitangus sulphuratus", "confidence": 0.87, "needs_review": False},
    }

    items = [b1, b2, b3, s1, s2, b_next_day, land]

    # No modo individual com auto_join_birds=True
    sessions = group_videos_into_sessions(items, mode="individual", bird_ident_map=bird_map, auto_join_birds=True)

    # Espera-se exatamente 4 sessões:
    # 1. Bem-te-vi (2026-10-25) com 3 clipes (b1, b2, b3)
    # 2. Sabiá-laranjeira (2026-10-25) com 2 clipes (s1, s2)
    # 3. Paisagem (2026-10-25) com 1 clipe (land)
    # 4. Bem-te-vi (2026-10-26) com 1 clipe (b_next_day)
    assert len(sessions) == 4

    # Sessão 1: Bem-te-vi dia 25 (primeiro clipe b1 às 09:00)
    assert len(sessions[0]) == 3
    assert [it.original_path for it in sessions[0]] == ["/dcim/b1.mp4", "/dcim/b2.mp4", "/dcim/b3.mp4"]

    # Sessão 2: Sabiá-laranjeira dia 25 (primeiro clipe s1 às 10:00)
    assert len(sessions[1]) == 2
    assert [it.original_path for it in sessions[1]] == ["/dcim/s1.mp4", "/dcim/s2.mp4"]

    # Sessão 3: Paisagem dia 25 (land às 12:00)
    assert len(sessions[2]) == 1
    assert sessions[2][0].original_path == "/dcim/land.mp4"

    # Sessão 4: Bem-te-vi dia 26 (b_next_day às 08:00 do dia 26)
    assert len(sessions[3]) == 1
    assert sessions[3][0].original_path == "/dcim/b_next.mp4"


def test_group_videos_auto_join_birds_different_cameras():
    """Vídeos da mesma ave e mesmo dia gravados com câmeras diferentes são unificados em ordem cronológica."""
    b_canon1 = ProjectItem(
        original_path="/c1.mp4", staging_path="/staging/c1.mp4", category="video",
        meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T10:00:00"
    )
    b_canon2 = ProjectItem(
        original_path="/c2.mp4", staging_path="/staging/c2.mp4", category="video",
        meta_camera_make="Canon", meta_camera_model="SX60",
        meta_timestamp="2026-10-25T11:00:00"
    )
    b_gopro = ProjectItem(
        original_path="/g1.mp4", staging_path="/staging/g1.mp4", category="video",
        meta_camera_make="GoPro", meta_camera_model="Hero 11",
        meta_timestamp="2026-10-25T10:30:00"
    )

    bird_map = {
        "/staging/c1.mp4": {"species_common": "Bem-te-vi", "confidence": 0.90, "needs_review": False},
        "/staging/c2.mp4": {"species_common": "Bem-te-vi", "confidence": 0.90, "needs_review": False},
        "/staging/g1.mp4": {"species_common": "Bem-te-vi", "confidence": 0.90, "needs_review": False},
    }

    sessions = group_videos_into_sessions([b_canon1, b_canon2, b_gopro], mode="individual", bird_ident_map=bird_map, auto_join_birds=True)
    assert len(sessions) == 1
    assert [it.original_path for it in sessions[0]] == ["/c1.mp4", "/g1.mp4", "/c2.mp4"]


def test_group_videos_auto_join_birds_disabled():
    """Quando auto_join_birds=False, o comportamento individual original 1:1 é preservado estritamente."""
    b1 = ProjectItem(original_path="/b1.mp4", staging_path="/staging/b1.mp4", category="video", meta_timestamp="2026-10-25T10:00:00")
    b2 = ProjectItem(original_path="/b2.mp4", staging_path="/staging/b2.mp4", category="video", meta_timestamp="2026-10-25T11:00:00")

    bird_map = {
        "/staging/b1.mp4": {"species_common": "Bem-te-vi", "confidence": 0.90, "needs_review": False},
        "/staging/b2.mp4": {"species_common": "Bem-te-vi", "confidence": 0.90, "needs_review": False},
    }

    sessions = group_videos_into_sessions([b1, b2], mode="individual", bird_ident_map=bird_map, auto_join_birds=False)
    assert len(sessions) == 2
    assert len(sessions[0]) == 1
    assert len(sessions[1]) == 1


def test_group_videos_auto_join_birds_quality_filters():
    """Vídeos com needs_review=True ou confiança abaixo do mínimo não são agrupados como ave confirmada."""
    b1 = ProjectItem(original_path="/b1.mp4", staging_path="/staging/b1.mp4", category="video", meta_timestamp="2026-10-25T10:00:00")
    b_low_conf = ProjectItem(original_path="/b_low.mp4", staging_path="/staging/b_low.mp4", category="video", meta_timestamp="2026-10-25T10:30:00")
    b_review = ProjectItem(original_path="/b_rev.mp4", staging_path="/staging/b_rev.mp4", category="video", meta_timestamp="2026-10-25T11:00:00")

    bird_map = {
        "/staging/b1.mp4": {"species_common": "Bem-te-vi", "confidence": 0.85, "needs_review": False},
        "/staging/b_low.mp4": {"species_common": "Bem-te-vi", "confidence": 0.40, "needs_review": False}, # Abaixo de 0.70
        "/staging/b_rev.mp4": {"species_common": "Bem-te-vi", "confidence": 0.85, "needs_review": True},  # Necessita revisão
    }

    sessions = group_videos_into_sessions([b1, b_low_conf, b_review], mode="individual", bird_ident_map=bird_map, auto_join_birds=True)
    # Apenas b1 tem alta certeza confirmada; b_low e b_rev viram itens individuais não agrupados
    assert len(sessions) == 3
    assert len(sessions[0]) == 1
    assert len(sessions[1]) == 1
    assert len(sessions[2]) == 1


def test_group_videos_joined_mode_with_birds_and_folders():
    """No modo joined com auto_join_birds=True, aves são unificadas por espécie e paisagens por pasta."""
    b1 = ProjectItem(original_path="/DCIM/100CANON/b1.mp4", staging_path="/staging/b1.mp4", category="video", meta_camera_make="Canon", meta_camera_model="SX60", meta_timestamp="2026-10-25T09:00:00")
    b2 = ProjectItem(original_path="/DCIM/100CANON/b2.mp4", staging_path="/staging/b2.mp4", category="video", meta_camera_make="Canon", meta_camera_model="SX60", meta_timestamp="2026-10-25T14:00:00")
    land1 = ProjectItem(original_path="/DCIM/100CANON/l1.mp4", staging_path="/staging/l1.mp4", category="video", meta_camera_make="Canon", meta_camera_model="SX60", meta_timestamp="2026-10-25T10:00:00")
    land2 = ProjectItem(original_path="/DCIM/100CANON/l2.mp4", staging_path="/staging/l2.mp4", category="video", meta_camera_make="Canon", meta_camera_model="SX60", meta_timestamp="2026-10-25T15:00:00")

    bird_map = {
        "/staging/b1.mp4": {"species_common": "Bem-te-vi", "confidence": 0.90, "needs_review": False},
        "/staging/b2.mp4": {"species_common": "Bem-te-vi", "confidence": 0.90, "needs_review": False},
    }

    sessions = group_videos_into_sessions([b1, b2, land1, land2], mode="joined", bird_ident_map=bird_map, auto_join_birds=True)
    # Espera-se 2 sessões: 1 para Bem-te-vi (2 clipes) e 1 para paisagens de 100CANON (2 clipes)
    assert len(sessions) == 2
    assert len(sessions[0]) == 2
    assert [it.original_path for it in sessions[0]] == ["/DCIM/100CANON/b1.mp4", "/DCIM/100CANON/b2.mp4"]
    assert len(sessions[1]) == 2
    assert [it.original_path for it in sessions[1]] == ["/DCIM/100CANON/l1.mp4", "/DCIM/100CANON/l2.mp4"]


def test_video_edit_stage_with_bird_auto_join(tmp_path, monkeypatch):
    """Testa a execução do VideoEditStage unindo automaticamente vídeos da mesma espécie de ave."""
    proj = Project("TestBirdJoinProj")

    v1_file = tmp_path / "v1.mp4"
    v2_file = tmp_path / "v2.mp4"
    v1_file.write_bytes(b"dummy1")
    v2_file.write_bytes(b"dummy2")

    it1 = ProjectItem(
        original_path=str(v1_file),
        staging_path=str(v1_file),
        organized_path=str(v1_file),
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-10-25T09:00:00",
        meta_width=1920,
        meta_height=1080,
        meta_duration_str="30s"
    )
    it2 = ProjectItem(
        original_path=str(v2_file),
        staging_path=str(v2_file),
        organized_path=str(v2_file),
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-10-25T11:00:00",
        meta_width=1920,
        meta_height=1080,
        meta_duration_str="30s"
    )
    proj.save_item(it1)
    proj.save_item(it2)

    # Registra identificação taxonômica no SQLite do projeto
    proj.add_bird_identification({
        "item_path": str(v1_file.resolve()),
        "is_video": True,
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "confidence": 0.91,
        "needs_review": False
    })
    proj.add_bird_identification({
        "item_path": str(v2_file.resolve()),
        "is_video": True,
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "confidence": 0.89,
        "needs_review": False
    })

    # Mock de renderização
    def mock_render(clip_paths, output_video_path, config):
        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        output_video_path.write_bytes(b"0" * 1000)
        return True, "h264_qsv", "", {"final_duration_seconds": 60.0, "trim_seconds": 2.0}

    monkeypatch.setattr("src.modules.video_edit.stage.render_edited_video", mock_render)
    monkeypatch.setattr("src.modules.video_edit.stage.send_windows_toast", lambda *a, **k: None)
    monkeypatch.setattr("src.modules.video_edit.stage.send_ntfy_notification", lambda *a, **k: None)

    stage = get_video_edit_stage("video_edit", "Edição de Vídeo")
    ok = stage.run(proj, interactive=False, mode="individual")
    assert ok is True

    # Verifica persistência no SQLite
    recs = proj.get_edited_videos()
    assert len(recs) == 1
    rec = recs[0]
    assert rec["clip_count"] == 2
    assert "Bem-te-vi" in rec["output_video_path"]
    assert "2clipes" in rec["output_video_path"]
    assert rec["metadata_json"]["bird_identification"]["species_common"] == "Bem-te-vi"


def test_summarize_session_cameras_single_and_multi():
    c1 = ProjectItem(original_path="/c1.mp4", staging_path="/c1.mp4", meta_camera_make="Canon", meta_camera_model="SX60")
    c2 = ProjectItem(original_path="/c2.mp4", staging_path="/c2.mp4", meta_camera_make="Canon", meta_camera_model="SX60")
    g1 = ProjectItem(original_path="/g1.mp4", staging_path="/g1.mp4", meta_camera_make="GoPro", meta_camera_model="Hero 11")

    single_summary = summarize_session_cameras([c1, c2])
    assert single_summary["is_multi_camera"] is False
    assert single_summary["camera_token"] == "SX60"
    assert single_summary["camera_names_full"] == ["Canon SX60"]

    multi_summary = summarize_session_cameras([c1, g1, c2])
    assert multi_summary["is_multi_camera"] is True
    assert multi_summary["camera_token"] == "Multi-Camera"
    assert multi_summary["camera_names_full"] == ["Canon SX60", "GoPro Hero 11"]

    fname = generate_edited_video_name(
        first_dt=datetime(2026, 11, 13, 10, 0, 0),
        camera_model=multi_summary["camera_token"],
        clip_count=3,
    )
    assert "_Multi-Camera_" in fname
    assert "3clipes" in fname


def test_build_concat_demuxer_cmd(tmp_path):
    lst = tmp_path / "concat_list.txt"
    lst.write_text("file 'part_0001.mp4'\n", encoding="utf-8")
    out = tmp_path / "final.mp4"

    cmd = build_concat_demuxer_cmd(lst, out)
    cmd_str = " ".join(cmd)
    assert "-f concat" in cmd_str
    assert "-safe 0" in cmd_str
    assert "-c copy" in cmd_str
    assert "-movflags +faststart" in cmd_str
    assert str(out.resolve()) == cmd[-1]


def test_build_render_cmd_single_clip_silent_audio_injection(tmp_path):
    clip = tmp_path / "mudo.mp4"
    clip.write_bytes(b"dummy")
    out = tmp_path / "out.mp4"

    cmd, _, _ = build_render_cmd(
        clip_paths=[clip],
        clip_infos=[{"duration": 10.0, "has_audio": False}],
        output_video_path=out,
        trim_starts=[0.0],
        trimmed_durs=[10.0],
        speed=1.0,
        target_fps=60,
        target_w=3840,
        target_h=2160,
        render_profile="quality",
        encoder_name="libx264 (CPU)",
        encoder_args=["-c:v", "libx264"],
        has_any_audio=True,
    )
    cmd_str = " ".join(cmd)
    assert "anullsrc=channel_layout=stereo:sample_rate=48000" in cmd_str
    assert "-shortest" in cmd_str
    assert "-c:a aac" in cmd_str
    assert "-video_track_timescale 90000" in cmd_str


def test_render_edited_video_two_step_individual_then_concat(tmp_path, monkeypatch):
    import io
    import subprocess

    c1 = tmp_path / "cam1.mp4"
    c2 = tmp_path / "cam2.mp4"
    c1.write_bytes(b"dummy1")
    c2.write_bytes(b"dummy2")
    out_video = tmp_path / "out_final.mp4"

    monkeypatch.setattr(
        "src.modules.video_edit.renderer.get_video_stream_info",
        lambda p: {"duration": 5.0, "has_audio": True}
    )
    monkeypatch.setattr(
        "src.modules.video_edit.renderer.detect_ffmpeg_encoder",
        lambda preset="slow", crf=16, force_cpu=False: ("libx264 (CPU)", ["-c:v", "libx264"])
    )

    calls = []

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            self.cmd = cmd
            self.stdout = []
            self.stderr = io.StringIO("")
            self.returncode = 0
            calls.append(cmd)
            Path(cmd[-1]).write_bytes(b"0" * 2000)

        def poll(self):
            return self.returncode

        def wait(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    ok, enc_used, err, stats = render_edited_video(
        clip_paths=[c1, c2],
        output_video_path=out_video,
        config={"speed": 1.0, "target_fps": 60, "render_profile": "quality"}
    )

    assert ok is True
    assert err == ""
    assert len(calls) == 3  # Etapa 1 (c1), Etapa 1 (c2), Etapa 2 (concat demuxer)
    assert "-filter_complex" not in " ".join(calls[0])
    assert "-filter_complex" not in " ".join(calls[1])
    assert "-f concat" in " ".join(calls[2])
    assert "-c copy" in " ".join(calls[2])
    assert stats["two_step_concat"] is True
    assert stats["parts_rendered"] == 2
    assert out_video.exists()
    # Garante que os arquivos e pasta temporários foram limpos
    tmp_dirs = [p for p in tmp_path.iterdir() if p.is_dir() and p.name.startswith(".tmp_concat_")]
    assert tmp_dirs == []


def test_build_edited_video_youtube_metadata_multi_camera(tmp_path):
    vid_path = tmp_path / "2026-11-13_10-00_Multi-Camera_2clipes_1920x1080-to-3840x2160_fps-30-to-60_1-0x_trim2-0s_audio_01m00s.mp4"
    vid_path.write_bytes(b"dummy")
    rec = {
        "output_video_path": str(vid_path),
        "camera_model": "Multi-Camera",
        "clip_count": 2,
        "mode": "joined",
        "metadata_json": {
            "camera_model": "Multi-Camera",
            "camera_models": ["Canon PowerShot SX60 HS", "GoPro Hero 11"],
            "camera_makes": ["Canon", "GoPro"],
            "orig_resolutions": ["1920x1080", "2704x1520"],
            "first_dt_formatted": "13/11/2026 às 10:00:00",
        }
    }
    meta = build_edited_video_youtube_metadata(vid_path, rec, {})
    assert "Canon PowerShot SX60 HS / GoPro Hero 11" in meta["description"]
    assert "1920x1080 / 2704x1520" in meta["description"]
    assert "Canon PowerShot SX60 HS" in meta["tags"]
    assert "GoPro Hero 11" in meta["tags"]


def test_is_same_aspect_ratio():
    assert is_same_aspect_ratio(1920, 1080) is True
    assert is_same_aspect_ratio(1280, 720) is True
    assert is_same_aspect_ratio(2704, 1520) is True
    assert is_same_aspect_ratio(3840, 2160) is True

    assert is_same_aspect_ratio(1440, 1080) is False  # 4:3
    assert is_same_aspect_ratio(640, 480) is False    # 4:3
    assert is_same_aspect_ratio(1080, 1920) is False  # 9:16
    assert is_same_aspect_ratio(1080, 1080) is False  # 1:1


def test_build_render_cmd_aspect_ratio_pillarbox_fast_qsv(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"dummy")
    out = tmp_path / "out.mp4"

    # 16:9 mantém vpp_qsv 100% em hardware
    cmd_16_9, _, _ = build_render_cmd(
        clip_paths=[clip],
        clip_infos=[{"duration": 10.0, "width": 1920, "height": 1080, "has_audio": False}],
        output_video_path=out,
        trim_starts=[0.0],
        trimmed_durs=[10.0],
        speed=1.0,
        target_fps=60,
        target_w=3840,
        target_h=2160,
        render_profile="fast",
        encoder_name="h264_qsv (Intel Quick Sync)",
        encoder_args=["-c:v", "h264_qsv"],
        has_any_audio=False,
    )
    cmd_16_9_str = " ".join(cmd_16_9)
    assert "-hwaccel qsv" in cmd_16_9_str
    assert "vpp_qsv=w=3840:h=2160" in cmd_16_9_str

    # 4:3 (1440x1080) e 9:16 (1080x1920) usam scale+pad preservando o encoder h264_qsv
    for w, h in [(1440, 1080), (1080, 1920)]:
        cmd_non_16_9, _, _ = build_render_cmd(
            clip_paths=[clip],
            clip_infos=[{"duration": 10.0, "width": w, "height": h, "has_audio": False}],
            output_video_path=out,
            trim_starts=[0.0],
            trimmed_durs=[10.0],
            speed=1.0,
            target_fps=60,
            target_w=3840,
            target_h=2160,
            render_profile="fast",
            encoder_name="h264_qsv (Intel Quick Sync)",
            encoder_args=["-c:v", "h264_qsv"],
            has_any_audio=False,
        )
        cmd_str = " ".join(cmd_non_16_9)
        assert "vpp_qsv" not in cmd_str
        assert "-c:v h264_qsv" in cmd_str
        assert "scale=3840:2160:flags=bicubic:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=3840:2160:(ow-iw)/2:(oh-ih)/2:black,setsar=1" in cmd_str


def test_build_render_cmd_aspect_ratio_balanced_and_quality(tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"dummy")
    out = tmp_path / "out.mp4"

    for profile, expected_flags in [
        ("balanced", "bicubic+accurate_rnd"),
        ("quality", "lanczos+accurate_rnd+full_chroma_int"),
    ]:
        cmd, _, _ = build_render_cmd(
            clip_paths=[clip],
            clip_infos=[{"duration": 10.0, "width": 640, "height": 480, "has_audio": False}],
            output_video_path=out,
            trim_starts=[0.0],
            trimmed_durs=[10.0],
            speed=1.0,
            target_fps=60,
            target_w=3840,
            target_h=2160,
            render_profile=profile,
            encoder_name="libx264 (CPU)",
            encoder_args=["-c:v", "libx264"],
            has_any_audio=False,
        )
        cmd_str = " ".join(cmd)
        expected_filter = (
            f"scale=3840:2160:flags={expected_flags}"
            ":force_original_aspect_ratio=decrease:force_divisible_by=2,"
            "pad=3840:2160:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
        )
        assert expected_filter in cmd_str


def test_get_video_stream_info_rotation_swap(tmp_path, monkeypatch):
    import json
    import subprocess

    vid = tmp_path / "vertical.mp4"
    vid.write_bytes(b"dummy")

    class MockCompleted:
        def __init__(self, payload):
            self.returncode = 0
            self.stdout = json.dumps(payload)

    # Caso 1: rotação via side_data_list (-90°)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: MockCompleted({
            "format": {"duration": "12.5"},
            "streams": [{
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "side_data_list": [{"rotation": -90}],
            }],
        }),
    )
    info1 = get_video_stream_info(vid)
    assert info1["width"] == 1080
    assert info1["height"] == 1920

    # Caso 2: rotação via tags.rotate ("90")
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: MockCompleted({
            "format": {"duration": "10.0"},
            "streams": [{
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "tags": {"rotate": "90"},
            }],
        }),
    )
    info2 = get_video_stream_info(vid)
    assert info2["width"] == 1080
    assert info2["height"] == 1920

    # Caso 3: rotação 180° mantém largura e altura
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: MockCompleted({
            "format": {"duration": "10.0"},
            "streams": [{
                "codec_type": "video",
                "width": 1920,
                "height": 1080,
                "r_frame_rate": "30/1",
                "tags": {"rotate": "180"},
            }],
        }),
    )
    info3 = get_video_stream_info(vid)
    assert info3["width"] == 1920
    assert info3["height"] == 1080


def test_build_edited_video_youtube_metadata_non_16_9_aspect(tmp_path):
    vid_path = tmp_path / "sample.mp4"
    vid_path.write_bytes(b"dummy")

    rec_4_3 = {
        "output_video_path": str(vid_path),
        "camera_model": "Canon SX60",
        "clip_count": 1,
        "orig_resolution": "1440x1080",
        "metadata_json": {"orig_width": 1440, "orig_height": 1080},
    }
    meta_4_3 = build_edited_video_youtube_metadata(vid_path, rec_4_3, {})
    assert "1440x1080 (Proporção 4:3 ➔ Enquadramento 4K Pillarbox/Letterbox)" in meta_4_3["description"]

    rec_9_16 = {
        "output_video_path": str(vid_path),
        "camera_model": "Smartphone",
        "clip_count": 1,
        "orig_resolution": "1080x1920",
        "metadata_json": {"orig_width": 1080, "orig_height": 1920},
    }
    meta_9_16 = build_edited_video_youtube_metadata(vid_path, rec_9_16, {})
    assert "1080x1920 (Proporção 9:16 ➔ Enquadramento 4K Pillarbox/Letterbox)" in meta_9_16["description"]


def test_group_videos_into_sessions_preloads_bird_map_once(tmp_path):
    """Garante que group_videos_into_sessions lê list_bird_identifications no máximo 1 vez mesmo com muitos vídeos sem ave."""
    from unittest.mock import MagicMock

    proj = create_project("test_preload_bird_map", str(tmp_path))

    videos = []
    for i in range(15):
        v = tmp_path / f"clip_{i:02d}.mp4"
        v.write_bytes(b"vid")
        videos.append(ProjectItem(
            original_path=str(v),
            staging_path=str(v),
            organized_path=str(v),
            category="video",
            meta_timestamp=f"2026-11-20T09:{i:02d}:00",
        ))
    proj.save_items_batch(videos)

    # Apenas 2 vídeos têm ave identificada; os outros 13 são sem ave (cenário que antes causava N+1 full scans)
    for idx in (0, 3):
        proj.add_bird_identification({
            "item_path": str(tmp_path / f"clip_{idx:02d}.mp4"),
            "is_video": True,
            "species_common": "Bem-te-vi",
            "species_scientific": "Pitangus sulphuratus",
            "confidence": 0.90,
            "needs_review": False,
        })

    list_spy = MagicMock(wraps=proj.list_bird_identifications)
    get_spy = MagicMock(wraps=proj.get_bird_identification)
    proj.list_bird_identifications = list_spy
    proj.get_bird_identification = get_spy

    sessions = group_videos_into_sessions(videos, mode="individual", project=proj, auto_join_birds=True)

    assert list_spy.call_count == 1
    assert get_spy.call_count == 0
    # 2 vídeos de Bem-te-vi unidos em 1 sessão + 13 individuais = 14 sessões
    assert len(sessions) == 14


def test_render_edited_video_returns_clip_effective_durations_with_speed_and_trim(tmp_path, monkeypatch):
    """Valida que render_edited_video retorna clip_effective_durations respeitando trim e speed."""
    import io
    import subprocess

    c1 = tmp_path / "c1.mp4"
    c2 = tmp_path / "c2.mp4"
    c3 = tmp_path / "c3.mp4"
    for c in (c1, c2, c3):
        c.write_bytes(b"dummy")
    out_video = tmp_path / "joined.mp4"

    # c1=20s (trim 2+2 -> 16s / 2.0 = 8.0s), c2=4s (<= 2*2+1=5s, sem trim -> 4s / 2.0 = 2.0s), c3=30s (trim 2+2 -> 26s / 2.0 = 13.0s)
    durations_by_name = {"c1.mp4": 20.0, "c2.mp4": 4.0, "c3.mp4": 30.0}
    monkeypatch.setattr(
        "src.modules.video_edit.renderer.get_video_stream_info",
        lambda p: {"duration": durations_by_name[p.name], "width": 1920, "height": 1080, "has_audio": False},
    )
    monkeypatch.setattr(
        "src.modules.video_edit.renderer.detect_ffmpeg_encoder",
        lambda preset="slow", crf=16, force_cpu=False: ("libx264 (CPU)", ["-c:v", "libx264"]),
    )

    class MockPopen:
        def __init__(self, cmd, *args, **kwargs):
            self.stdout = []
            self.stderr = io.StringIO("")
            self.returncode = 0
            Path(cmd[-1]).write_bytes(b"0" * 2000)

        def poll(self):
            return self.returncode

        def wait(self):
            pass

    monkeypatch.setattr(subprocess, "Popen", MockPopen)

    ok, _, err, stats = render_edited_video(
        clip_paths=[c1, c2, c3],
        output_video_path=out_video,
        config={"speed": 2.0, "trim_enabled": True, "trim_seconds": 2.0, "target_fps": 60, "render_profile": "quality"},
    )

    assert ok is True
    assert err == ""
    assert stats["clip_effective_durations"] == [8.0, 2.0, 13.0]


def test_video_edit_stage_persists_clips_timeline(tmp_path, monkeypatch):
    """Garante que VideoEditStage persiste metadata_json['clips_timeline'] pareado com os clipes reais."""
    proj = create_project("TestClipsTimeline", str(tmp_path))

    orig_dir = tmp_path / "DCIM" / "100CANON"
    orig_dir.mkdir(parents=True)
    v1 = orig_dir / "VID_01.mp4"
    v2 = orig_dir / "VID_02.mp4"
    v1.write_bytes(b"v1")
    v2.write_bytes(b"v2")

    it1 = ProjectItem(
        original_path=str(v1),
        staging_path=str(v1),
        organized_path=str(v1),
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-11-21T14:30:12",
        meta_duration_str="20s",
    )
    it2 = ProjectItem(
        original_path=str(v2),
        staging_path=str(v2),
        organized_path=str(v2),
        category="video",
        meta_camera_make="Canon",
        meta_camera_model="SX60",
        meta_timestamp="2026-11-21T14:31:05",
        meta_duration_str="26s",
    )
    proj.save_items_batch([it1, it2])

    def mock_render(clip_paths, output_video_path, config):
        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        output_video_path.write_bytes(b"0" * 2000)
        return True, "libx264", "", {
            "final_duration_seconds": 42.5,
            "trim_seconds": 2.0,
            "clip_effective_durations": [18.5, 24.0],
        }

    monkeypatch.setattr("src.modules.video_edit.stage.render_edited_video", mock_render)
    monkeypatch.setattr("src.modules.video_edit.stage.send_windows_toast", lambda *a, **k: None)
    monkeypatch.setattr("src.modules.video_edit.stage.send_ntfy_notification", lambda *a, **k: None)

    stage = get_video_edit_stage("video_edit", "Edição de Vídeo")
    ok = stage.run(proj, interactive=False, mode="joined")
    assert ok is True

    recs = proj.get_edited_videos()
    assert len(recs) == 1
    timeline = recs[0]["metadata_json"]["clips_timeline"]
    assert timeline == [
        {
            "index": 1,
            "filename": "VID_01.mp4",
            "time_str": "14:30:12",
            "camera": "Canon SX60",
            "duration_seconds": 18.5,
        },
        {
            "index": 2,
            "filename": "VID_02.mp4",
            "time_str": "14:31:05",
            "camera": "Canon SX60",
            "duration_seconds": 24.0,
        },
    ]


def test_format_chapters_block_rules_and_edge_cases():
    """Valida formatação MM:SS, HH:MM:SS, Multi-Camera, fallback de nome e ordem crescente."""
    assert format_chapters_block([]) == ""
    assert format_chapters_block([{"filename": "a.mp4", "time_str": "10:00:00", "duration_seconds": 30.0}]) == ""

    # Câmera única < 1h -> MM:SS sem sufixo de câmera
    single_cam = [
        {"filename": "c1.mp4", "time_str": "14:30:12", "camera": "Canon SX60", "duration_seconds": 18.0},
        {"filename": "c2.mp4", "time_str": "14:31:05", "camera": "Canon SX60", "duration_seconds": 24.0},
        {"filename": "c3.mp4", "time_str": "14:33:10", "camera": "Canon SX60", "duration_seconds": 15.0},
    ]
    block_single = format_chapters_block(single_cam)
    assert block_single == (
        "📑 CAPÍTULOS (TOMADAS):\n"
        "00:00 Tomada 1 - 14:30:12\n"
        "00:18 Tomada 2 - 14:31:05\n"
        "00:42 Tomada 3 - 14:33:10"
    )

    # Multi-Câmera + duração total >= 1h -> HH:MM:SS com modelo da câmera
    multi_cam_long = [
        {"filename": "m1.mp4", "time_str": "08:00:00", "camera": "Canon SX60", "duration_seconds": 2400.0},
        {"filename": "m2.mp4", "time_str": "08:45:00", "camera": "GoPro Hero 11", "duration_seconds": 1800.0},
        {"filename": "m3.mp4", "time_str": "", "camera": "Canon SX60", "duration_seconds": 600.0},
    ]
    block_long = format_chapters_block(multi_cam_long)
    assert block_long == (
        "📑 CAPÍTULOS (TOMADAS):\n"
        "00:00:00 Tomada 1 - 08:00:00 (Canon SX60)\n"
        "00:40:00 Tomada 2 - 08:45:00 (GoPro Hero 11)\n"
        "01:10:00 Tomada 3 - m3 (Canon SX60)"
    )

    # Clipes sub-segundo mantêm timestamps estritamente crescentes
    sub_sec = [
        {"filename": "s1.mp4", "time_str": "09:00:00", "camera": "Cam", "duration_seconds": 0.4},
        {"filename": "s2.mp4", "time_str": "09:00:05", "camera": "Cam", "duration_seconds": 0.4},
    ]
    block_sub = format_chapters_block(sub_sec)
    assert "00:00 Tomada 1 - 09:00:00" in block_sub
    assert "00:01 Tomada 2 - 09:00:05" in block_sub


def test_build_edited_video_youtube_metadata_includes_chapters_for_joined_and_omits_for_single(tmp_path):
    """Garante inserção do bloco de capítulos antes da ficha técnica apenas em vídeos concatenados."""
    vid_path = tmp_path / "2026-11-21_14-30_SX60_3clipes_1920x1080-to-3840x2160_fps-30-to-60_1-0x_trim2-0s_audio_01m00s.mp4"
    vid_path.write_bytes(b"dummy")

    joined_rec = {
        "output_video_path": str(vid_path),
        "clip_count": 3,
        "mode": "joined",
        "metadata_json": {
            "camera_model": "SX60",
            "first_dt_formatted": "21/11/2026 às 14:30:12",
            "clips_timeline": [
                {"index": 1, "filename": "c1.mp4", "time_str": "14:30:12", "camera": "Canon SX60", "duration_seconds": 18.0},
                {"index": 2, "filename": "c2.mp4", "time_str": "14:31:05", "camera": "Canon SX60", "duration_seconds": 24.0},
                {"index": 3, "filename": "c3.mp4", "time_str": "14:33:10", "camera": "Canon SX60", "duration_seconds": 18.0},
            ],
        },
    }
    meta_joined = build_edited_video_youtube_metadata(vid_path, joined_rec, {})
    desc_joined = meta_joined["description"]
    assert len(desc_joined) <= 5000
    assert "📑 CAPÍTULOS (TOMADAS):" in desc_joined
    assert "00:00 Tomada 1 - 14:30:12" in desc_joined
    assert "00:18 Tomada 2 - 14:31:05" in desc_joined
    assert "00:42 Tomada 3 - 14:33:10" in desc_joined
    assert desc_joined.index("📑 CAPÍTULOS (TOMADAS):") < desc_joined.index("⏱️ TEMPO, CAPTURA E VELOCIDADE:")

    single_rec = {
        "output_video_path": str(vid_path),
        "clip_count": 1,
        "mode": "individual",
        "metadata_json": {
            "camera_model": "SX60",
            "clips_timeline": [
                {"index": 1, "filename": "c1.mp4", "time_str": "14:30:12", "camera": "Canon SX60", "duration_seconds": 20.0},
            ],
        },
    }
    meta_single = build_edited_video_youtube_metadata(vid_path, single_rec, {})
    assert "📑 CAPÍTULOS (TOMADAS):" not in meta_single["description"]


