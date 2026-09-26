import pytest
from pathlib import Path
from datetime import datetime

from src.core.project import Project, create_project
from src.core.pipeline import PipelineRunner
from src.modules.timelapse.encoder import detect_ffmpeg_encoder
from src.modules.timelapse.renderer import build_video_filter_chain
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
        crop_mode="center",
        is_test=False
    )
    assert name.startswith("2026-08-17_16h55m-18h30m_Canon-PowerShot-SX60-HS_4608x3456_4K_center_60fps_1fpi_")
    assert name.endswith("_timelapse.mp4")

    # Teste com outros modos de corte (top e bottom)
    name_top = generate_timelapse_video_name(
        first_dt=d1, last_dt=d2, camera_model="Canon", orig_w=4000, orig_h=3000,
        total_photos=100, crop_mode="top"
    )
    assert "_4K_top_60fps_" in name_top

    name_bottom = generate_timelapse_video_name(
        first_dt=d1, last_dt=d2, camera_model="Canon", orig_w=4000, orig_h=3000,
        total_photos=100, crop_mode="bottom"
    )
    assert "_4K_bottom_60fps_" in name_bottom

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


def test_build_video_filter_chain_deband_and_grain():
    # Caso 1: Deband habilitado com grão (padrão otimizado para YouTube)
    deband_cfg = {"enabled": True, "add_grain": True}
    vf = build_video_filter_chain(
        crop_mode="center",
        target_w=3840,
        target_h=2160,
        deband_config=deband_cfg
    )
    assert "scale=3840:2160:flags=lanczos" in vf
    assert "(iw-ow)/2" in vf
    assert "deband=1thr=0.04:2thr=0.04:3thr=0.04:range=16:blur=true:coupling=true" in vf
    assert "noise=alls=1:allf=t" in vf

    # Caso 2: Deband habilitado sem grão
    deband_cfg_no_grain = {"enabled": True, "add_grain": False}
    vf_no_grain = build_video_filter_chain(
        crop_mode="top",
        target_w=1920,
        target_h=1080,
        deband_config=deband_cfg_no_grain
    )
    assert "scale=1920:1080:flags=lanczos" in vf_no_grain
    assert "y='0'" in vf_no_grain
    assert "deband=1thr=0.04:2thr=0.04:3thr=0.04:range=16:blur=true:coupling=true" in vf_no_grain
    assert "noise=" not in vf_no_grain

    # Caso 3: Deband desabilitado
    deband_cfg_disabled = {"enabled": False, "add_grain": True}
    vf_disabled = build_video_filter_chain(
        crop_mode="bottom",
        target_w=3840,
        target_h=2160,
        deband_config=deband_cfg_disabled
    )
    assert "scale=3840:2160:flags=lanczos" in vf_disabled
    assert "deband=" not in vf_disabled
    assert "noise=" not in vf_disabled

    # Caso 4: Configuração ausente / None
    vf_none = build_video_filter_chain(
        crop_mode="bottom",
        target_w=3840,
        target_h=2160,
        deband_config=None
    )
    assert "deband=" not in vf_none
    assert "noise=" not in vf_none


def test_describer_duration_and_bytes_formatting():
    from src.modules.youtube.describer import format_duration_human, format_bytes_human, calculate_aspect_ratio

    # Duração
    assert format_duration_human(0) == "0 segundos"
    assert format_duration_human(45) == "45 segundos"
    assert format_duration_human(60) == "1 minuto"
    assert format_duration_human(120) == "2 minutos"
    assert format_duration_human(135) == "2 minutos e 15 segundos"
    assert format_duration_human(3600) == "1 hora"
    assert format_duration_human(3665) == "1 hora, 1 minuto e 5 segundos"
    assert format_duration_human(7325) == "2 horas, 2 minutos e 5 segundos"

    # Bytes
    assert format_bytes_human(0) == "0 MB"
    assert format_bytes_human(500) == "500 B"
    assert format_bytes_human(1024 * 50) == "50.0 KB"
    assert format_bytes_human(1024**2 * 142) == "142.0 MB"
    assert format_bytes_human(int(1024**3 * 4.82)) == "4.82 GB"

    # Aspect ratio
    assert calculate_aspect_ratio(4000, 3000) == "4:3"
    assert calculate_aspect_ratio(4608, 3456) == "4:3"
    assert calculate_aspect_ratio(3840, 2160) == "16:9"
    assert calculate_aspect_ratio(6000, 4000) == "3:2"
    assert calculate_aspect_ratio(1080, 1080) == "1:1"


def test_describer_exposure_range_summaries():
    from src.modules.youtube.describer import summarize_exposure_param

    # Valor único
    assert summarize_exposure_param(["f/4.0", "f/4.0", "f/4.0"], "aperture") == "f/4.0"
    assert summarize_exposure_param(["4.0"], "aperture") == "f/4.0"
    assert summarize_exposure_param(["ISO100", "ISO100"], "iso") == "ISO 100"
    assert summarize_exposure_param(["100"], "iso") == "ISO 100"
    assert summarize_exposure_param(["1/125s", "1/125s"], "shutter") == "1/125s"

    # Variação / Holy Grail
    iso_range = summarize_exposure_param(["ISO100", "ISO400", "ISO800"], "iso")
    assert iso_range == "ISO 100 – ISO 800"

    aperture_range = summarize_exposure_param(["f2.8", "f4.0", "f8.0"], "aperture")
    assert aperture_range == "f/2.8 – f/8.0"

    shutter_range = summarize_exposure_param(["1/1000s", "1/500s", "1/30s", "2s"], "shutter")
    assert "1/1000s" in shutter_range
    assert "2s" in shutter_range


def test_build_rich_youtube_description_full():
    from src.modules.youtube.describer import build_rich_youtube_description, build_youtube_tags

    record = {
        "project_name": "2026-08-17_16-55_4_Timelapses",
        "sequence_dir": "C:/IRIS/4_Timelapses/Canon/2026/08/17/timelapse_16-55-00",
        "output_video_path": "C:/IRIS/6_Produzidos/2026/08/2026-08-17_16h55m-18h30m_Canon_4608x3456_4K_60fps_2fpi_137x_00m41s_timelapse.mp4",
        "photo_count": 1250,
        "fps": 60,
        "frames_per_image": 2,
        "resolution": "3840x2160",
        "crop_mode": "center",
        "encoder": "h264_nvenc",
        "duration_seconds": 41.7,
        "speedup_factor": 137,
        "metadata_json": {
            "camera_make": "Canon",
            "camera_model": "PowerShot SX60 HS",
            "orig_width": 4608,
            "orig_height": 3456,
            "total_orig_size_bytes": int(4.82 * 1024**3),
            "video_size_bytes": int(142.5 * 1024**2),
            "orig_formats": ["JPG"],
            "first_dt_formatted": "17/08/2026 às 16:55:02",
            "last_dt_formatted": "17/08/2026 às 18:30:14",
            "date_str": "17/08/2026",
            "real_duration_seconds": 5712,
            "avg_interval_seconds": 4.6,
            "apertures": ["f/4.0"],
            "shutters": ["1/1000s", "1/60s"],
            "isos": ["ISO100"],
            "focals": ["21mm"],
            "focal_equiv_summary": "21mm",
            "render_stats": {
                "render_time_seconds": 38.2,
                "avg_fps": 32.7
            }
        }
    }

    desc = build_rich_youtube_description(record, project_name="2026-08-17_16-55_4_Timelapses")

    # Verifica blocos essenciais
    assert "Vídeo Timelapse renderizado em alta definição 4K UHD (3840x2160) a 60 FPS." in desc
    assert "⏱️ TEMPO E CAPTURA:" in desc
    assert "17/08/2026 às 16:55:02 até 17/08/2026 às 18:30:14" in desc
    assert "1.250 fotos" in desc
    assert "137x mais rápido que a vida real" in desc
    assert "4.6 segundos (Intervalômetro)" in desc
    assert "30 fotos/segundo" in desc

    assert "📷 EQUIPAMENTO E ARQUIVOS ORIGINAIS:" in desc
    assert "Canon PowerShot SX60 HS" in desc
    assert "4608x3456" in desc
    assert "21mm equiv. 35mm" in desc
    assert "f/4.0" in desc
    assert "ISO 100" in desc
    assert "4.82 GB" in desc

    assert "🎞️ PROCESSAMENTO E ENGENHARIA DE VÍDEO (IRIS):" in desc
    assert "4K UHD (3840x2160) • Proporção 16:9" in desc
    assert "Lanczos 3" in desc
    assert "Deband 16-bit com micro-grão temporal dither" in desc
    assert "h264_nvenc" in desc
    assert "Redução de" in desc
    assert "38.2 segundos" in desc

    assert "📂 RASTREABILIDADE DO PROJETO:" in desc
    assert "2026-08-17_16-55_4_Timelapses" in desc
    assert "timelapse_16-55-00" in desc

    assert len(desc) <= 5000

    tags = build_youtube_tags(record)
    assert "timelapse" in tags
    assert "4k" in tags
    assert "canon" in tags


def test_project_and_central_timelapse_metadata_json_persistence(tmp_path):
    import uuid
    proj_name = f"test_meta_{uuid.uuid4().hex[:10]}"
    proj = create_project(proj_name, str(tmp_path / "source"))
    vpath = str(tmp_path / "out_video.mp4")
    
    meta_dict = {
        "camera_model": "SX60",
        "iso_summary": "ISO 100 – ISO 400",
        "real_duration_seconds": 3600
    }
    
    record = {
        "project_name": proj.name,
        "sequence_dir": str(tmp_path / "seq"),
        "output_video_path": vpath,
        "photo_count": 500,
        "fps": 60,
        "frames_per_image": 1,
        "resolution": "3840x2160",
        "crop_mode": "center",
        "encoder": "h264_nvenc",
        "duration_seconds": 8.3,
        "speedup_factor": 432,
        "metadata_json": meta_dict
    }
    
    try:
        proj.save_timelapse(record)
        
        # Carregar do banco do projeto
        tls = proj.get_timelapses()
        assert len(tls) == 1
        loaded_meta = tls[0]["metadata_json"]
        assert isinstance(loaded_meta, dict)
        assert loaded_meta["camera_model"] == "SX60"
        assert loaded_meta["iso_summary"] == "ISO 100 – ISO 400"
        assert loaded_meta["real_duration_seconds"] == 3600

        # Carregar do banco central
        from src.core.project import list_central_timelapses
        central_tls = list_central_timelapses(project_name=proj.name)
        assert len(central_tls) >= 1
        target = [t for t in central_tls if t["output_video_path"] == vpath][0]
        assert target["metadata_json"]["camera_model"] == "SX60"
    finally:
        if proj._project_db_file.exists():
            try:
                proj._project_db_file.unlink()
            except Exception:
                pass


def test_build_timelapse_youtube_metadata_with_project_fallback(tmp_path):
    from src.core.project import ProjectItem
    proj_name = f"test_yt_fallback_{tmp_path.name}"
    proj = create_project(proj_name, str(tmp_path / "source"))

    seq_dir = tmp_path / "4_Timelapses" / "timelapse_10-00-00"
    seq_dir.mkdir(parents=True, exist_ok=True)

    # Criar itens simulados
    p1 = seq_dir / "photo1.jpg"
    p2 = seq_dir / "photo2.jpg"
    p1.write_text("dummy1")
    p2.write_text("dummy2")

    item1 = ProjectItem(
        original_path=str(p1),
        staging_path=str(p1),
        organized_path=str(p1),
        file_size_bytes=1024 * 1024 * 4,
        meta_camera_make="Sony",
        meta_camera_model="A7IV",
        meta_width=7008,
        meta_height=4672,
        meta_aperture_str="f/2.8",
        meta_shutter_str="1/500s",
        meta_iso_str="ISO 200",
        meta_focal_str="24mm",
        meta_focal_length_equiv=24.0,
        meta_extension=".jpg",
        meta_timestamp="2026-09-26T10:00:00"
    )
    item2 = ProjectItem(
        original_path=str(p2),
        staging_path=str(p2),
        organized_path=str(p2),
        file_size_bytes=1024 * 1024 * 4,
        meta_camera_make="Sony",
        meta_camera_model="A7IV",
        meta_width=7008,
        meta_height=4672,
        meta_aperture_str="f/2.8",
        meta_shutter_str="1/250s",
        meta_iso_str="ISO 400",
        meta_focal_str="24mm",
        meta_focal_length_equiv=24.0,
        meta_extension=".jpg",
        meta_timestamp="2026-09-26T11:00:00"
    )
    proj.save_item(item1)
    proj.save_item(item2)

    vpath = tmp_path / "2026-09-26_10h00m-11h00m_Sony_4K_60fps_timelapse.mp4"
    vpath.write_bytes(b"dummy_video_content")

    # Registro legado sem metadata_json
    legacy_record = {
        "project_name": proj.name,
        "sequence_dir": str(seq_dir),
        "output_video_path": str(vpath),
        "photo_count": 2,
        "duration_seconds": 1.0,
        "speedup_factor": 3600,
        "encoder": "libx264",
        "fps": 60,
        "resolution": "3840x2160"
    }

    yt_config = {"privacy_status": "unlisted", "category_id": "22"}
    meta = build_timelapse_youtube_metadata(vpath, legacy_record, yt_config, project=proj)

    assert "Sony A7IV" in meta["description"]
    assert "7008x4672" in meta["description"]
    assert "24mm" in meta["description"]
    assert "f/2.8" in meta["description"]
    assert "ISO 200 – ISO 400" in meta["description"]
    assert "sony" in meta["tags"]


