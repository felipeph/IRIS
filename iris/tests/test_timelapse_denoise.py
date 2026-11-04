import json
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from src.core.config import config
from src.core.project import create_project, ProjectItem
from src.modules.timelapse_denoise.engine import (
    extract_jpeg_app1_segments,
    inject_jpeg_app1_segments,
    compute_hot_pixel_map,
    process_sequence_denoise,
)
from src.modules.timelapse_denoise.stage import TimelapseDenoiseStage
from src.modules.timelapse.stage import TimelapseStage
from src.modules.youtube.describers.timelapse import build_rich_youtube_description


def _build_dummy_jpeg_with_app1(img: np.ndarray, custom_exif_payload: bytes = b"Exif\x00\x00IRIS_ASTRO_TEST_GPS") -> bytes:
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    assert ok
    raw = buf.tobytes()
    seg_len = (len(custom_exif_payload) + 2).to_bytes(2, "big")
    app1_seg = b"\xff\xe1" + seg_len + custom_exif_payload
    return inject_jpeg_app1_segments(raw, app1_seg)


def test_jpeg_app1_extract_and_inject_roundtrip():
    """Garante que segmentos binários APP1 (EXIF/GPS/XMP) são extraídos e reinjetados sem perda."""
    img = np.full((64, 64, 3), 40, dtype=np.uint8)
    payload = b"Exif\x00\x00CAMERA=GoPro_HERO5;ISO=800;SHUTTER=10s;GPS=-20.45,-45.43"
    jpeg_with_exif = _build_dummy_jpeg_with_app1(img, payload)

    extracted = extract_jpeg_app1_segments(jpeg_with_exif)
    assert payload in extracted

    ok, new_buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 96])
    assert ok
    reinjected = inject_jpeg_app1_segments(new_buf.tobytes(), extracted)
    assert reinjected.startswith(b"\xff\xd8")
    assert extract_jpeg_app1_segments(reinjected) == extracted

    decoded = cv2.imdecode(np.frombuffer(reinjected, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    assert decoded.shape == (64, 64, 3)


def test_hot_pixel_map_distinguishes_fixed_defects_from_moving_stars():
    """
    Valida que compute_hot_pixel_map detecta hot pixels estacionários (mesma coordenada em todos os frames),
    mas ignora completamente estrelas que se movem ao longo dos frames.
    """
    frames = []
    for t in range(7):
        im = np.full((80, 80, 3), 25, dtype=np.uint8)
        # Hot pixel estacionário em (20, 30)
        im[20, 30] = [220, 220, 220]
        # Estrela em movimento que se desloca 3 pixels por frame
        star_x = 10 + t * 3
        im[50, star_x] = [240, 240, 240]
        frames.append(im)

    defect_map, hp_count = compute_hot_pixel_map(frames, threshold=8)
    assert hp_count == 1
    assert defect_map[20, 30, 1] > 180
    # Nenhuma posição da estrela em movimento deve ser marcada como hot pixel
    for t in range(7):
        star_x = 10 + t * 3
        assert defect_map[50, star_x, 1] == 0


def test_process_sequence_denoise_reduces_noise_and_preserves_stars(tmp_path: Path):
    """
    Valida em uma sequência sintética de 7 frames de céu estrelado que:
    1. O ruído de fundo do céu escuro cai drasticamente (>40%).
    2. O hot pixel fixo na coordenada (15, 15) é suprimido.
    3. A estrela em movimento preserva seu brilho pontual (>95%) sem gerar rastro fantasma.
    4. Os metadados EXIF binários são preservados nos arquivos de saída.
    """
    rng = np.random.default_rng(42)
    seq_dir = tmp_path / "timelapse_20-46-48"
    seq_dir.mkdir(parents=True)
    out_dir = seq_dir / "denoised"

    photo_paths = []
    for t in range(7):
        base = np.full((120, 160, 3), 28.0, dtype=np.float32)
        noise = rng.normal(0.0, 4.2, size=base.shape).astype(np.float32)
        frame = np.clip(base + noise, 0, 255).astype(np.uint8)

        # Hot pixel fixo em (15, 15)
        frame[15, 15] = [210, 210, 210]

        # Estrela brilhante 3x3 que se move 4px por frame
        sx = 30 + t * 4
        sy = 70
        frame[sy - 1 : sy + 2, sx - 1 : sx + 2] = 220
        frame[sy, sx] = 250

        p = seq_dir / f"frame_{t:04d}.jpg"
        raw_bytes = _build_dummy_jpeg_with_app1(frame, f"Exif\x00\x00FRAME={t}".encode("ascii"))
        p.write_bytes(raw_bytes)
        photo_paths.append(p)

    ok, stats = process_sequence_denoise(
        photo_paths=photo_paths,
        output_dir=out_dir,
        window_size=7,
        sigma_range=5.0,
        hot_pixel_threshold=8,
        chroma_denoise=True,
        jpeg_quality=98,
    )
    assert ok is True
    assert stats["processed_photos"] == 7
    assert stats["hot_pixels_detected"] >= 1

    orig_mid = cv2.imread(str(photo_paths[3]))
    clean_mid_path = out_dir / photo_paths[3].name
    assert clean_mid_path.exists()
    clean_mid = cv2.imread(str(clean_mid_path))

    # 1. Ruído espacial no fundo escuro (y: 85..115, x: 20..140) deve reduzir mais de 40%
    std_orig = float(np.std(orig_mid[85:115, 20:140, 1].astype(np.float32)))
    std_clean = float(np.std(clean_mid[85:115, 20:140, 1].astype(np.float32)))
    assert std_clean < std_orig * 0.60

    # 2. Hot pixel em (15, 15) deve ter sido removido para próximo do fundo (~28)
    assert clean_mid[15, 15, 1] < 50

    # 3. Estrela no frame 3 (sy=70, sx=30 + 3*4 = 42) deve permanecer brilhante (>215)
    assert clean_mid[70, 42, 1] > 215
    # E a posição da estrela do frame 1 (sx=34) deve estar limpa no frame 3 (sem fantasma)
    assert clean_mid[70, 34, 1] < 45

    # 4. EXIF preservado
    assert b"FRAME=3" in extract_jpeg_app1_segments(clean_mid_path.read_bytes())


def test_timelapse_denoise_stage_and_timelapse_stage_integration(tmp_path: Path, monkeypatch):
    """
    Valida que TimelapseDenoiseStage salva na subpasta 'denoised/' mantendo originais intactos,
    e que TimelapseStage consome automaticamente a subpasta 'denoised/' e documenta na descrição do YouTube.
    """
    dest_root = Path(config.get("general.destination_root"))
    monkeypatch.setitem(
        config.config.setdefault("modules", {}),
        "timelapse_denoise",
        {
            "enabled": True,
            "output_subfolder": "denoised",
            "use_denoised_frames": True,
            "window_size": 5,
            "sigma_range": 4.5,
            "hot_pixel_threshold": 8,
            "chroma_denoise": True,
            "jpeg_quality": 95,
            "apply_to_normal_timelapse": False,
        },
    )

    rel_dir = "4_Timelapses_LongaExposicao/GoPro/2026/11/03/timelapse_20-46-48"
    seq_dir = dest_root / Path(rel_dir)
    seq_dir.mkdir(parents=True)

    proj = create_project("test_night_tl_denoise", str(tmp_path))
    items = []
    for i in range(5):
        img = np.full((60, 80, 3), 25 + (i % 2), dtype=np.uint8)
        img[10, 10] = [200, 200, 200]  # hot pixel
        p = seq_dir / f"2026-11-03_20-46-{10+i:02d}_GoPro.jpg"
        p.write_bytes(_build_dummy_jpeg_with_app1(img))
        items.append(
            ProjectItem(
                original_path=str(p),
                staging_path=str(p),
                organized_path=str(p),
                status="organized",
                verified=True,
                file_size_bytes=p.stat().st_size,
                meta_timestamp=f"2026-11-03T20:46:{10+i:02d}",
                meta_camera_make="GoPro",
                meta_camera_model="HERO5 Black",
                meta_extension=".jpg",
                meta_width=80,
                meta_height=60,
                category="timelapse_long_exposure",
                relative_dest_dir=rel_dir,
            )
        )
    proj.save_items_batch(items)

    orig_bytes_before = [ (seq_dir / f"2026-11-03_20-46-{10+i:02d}_GoPro.jpg").read_bytes() for i in range(5) ]

    denoise_stage = TimelapseDenoiseStage("timelapse_denoise", "Denoise")
    assert denoise_stage.run(proj, interactive=False) is True

    denoised_dir = seq_dir / "denoised"
    assert denoised_dir.exists()
    assert len(list(denoised_dir.glob("*.jpg"))) == 5
    assert (denoised_dir / "denoise_manifest.json").exists()

    # Originais devem permanecer 100% idênticos byte a byte
    for i in range(5):
        p_orig = seq_dir / f"2026-11-03_20-46-{10+i:02d}_GoPro.jpg"
        assert p_orig.read_bytes() == orig_bytes_before[i]

    # Agora testa TimelapseStage consumindo automaticamente os frames de denoised/
    captured_photo_paths = []

    def fake_prepare_sequence(photo_paths, target_dir, is_test=False, test_sample_size=120):
        captured_photo_paths.extend(photo_paths)
        temp_dir = target_dir / ".temp_sequence"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return True, temp_dir, list(photo_paths)

    def fake_render_video(sequence_dir, output_video_path, photo_count, config, orig_w=0, orig_h=0, **kw):
        output_video_path.parent.mkdir(parents=True, exist_ok=True)
        output_video_path.write_bytes(b"FAKE_MP4_DATA")
        return True, "libx264", "", {"render_time_seconds": 1.0, "avg_fps": 30.0, "deband_enabled": True, "deband_grain": True}

    with patch("src.modules.timelapse.stage.prepare_numbered_sequence", side_effect=fake_prepare_sequence), \
         patch("src.modules.timelapse.stage.render_timelapse_video", side_effect=fake_render_video), \
         patch("src.modules.timelapse.stage.notify_timelapse_render_done"):
        tl_stage = TimelapseStage("timelapse", "Timelapse")
        assert tl_stage.run(proj, interactive=False) is True

    assert len(captured_photo_paths) == 5
    assert all(p.parent.name == "denoised" for p in captured_photo_paths)

    tl_records = proj.get_timelapses()
    assert len(tl_records) == 1
    meta = tl_records[0]["metadata_json"]
    if isinstance(meta, str):
        meta = json.loads(meta)
    assert meta["spatiotemporal_denoise"] is True

    desc = build_rich_youtube_description(tl_records[0], project_name=proj.name)
    assert "Filtro Bilateral Espaço-Temporal" in desc

def test_hot_pixel_sparse_coords_and_sparse_removal_parity():
    from src.modules.timelapse_denoise.engine import extract_hot_pixel_coords, remove_hot_pixels

    frames = [np.full((50, 50, 3), 30, dtype=np.uint8) for _ in range(5)]
    frames[0][12, 18] = [210, 210, 210]
    frames[1][12, 18] = [215, 215, 215]
    frames[2][12, 18] = [212, 212, 212]
    frames[3][12, 18] = [211, 211, 211]
    frames[4][12, 18] = [213, 213, 213]

    defect_map, count = compute_hot_pixel_map(frames, threshold=10)
    assert count == 1
    coords = extract_hot_pixel_coords(defect_map)
    assert len(coords[0]) == 1
    assert coords[0][0] == 12 and coords[1][0] == 18

    cleaned = remove_hot_pixels(frames[0], coords, defect_map)
    assert cleaned[12, 18, 0] == 30
    assert cleaned[12, 18, 1] == 30
    assert cleaned[12, 18, 2] == 30


def test_no_white_saturation_on_dark_sky_cpu_and_gpu(tmp_path: Path):
    """
    Garante que o acumulador Q5 16-bit preserva o brilho medio de frames escuros (~28 ADU)
    sem sofrer underflow/overflow (bug de imagens brancas ~251 ADU), tanto em CPU quanto em GPU OpenCL.
    """
    rng = np.random.default_rng(123)
    seq_dir = tmp_path / "dark_sky"
    seq_dir.mkdir(parents=True)

    photo_paths = []
    for t in range(7):
        base = np.full((80, 100, 3), 28.0, dtype=np.float32)
        noise = rng.normal(0.0, 3.5, size=base.shape).astype(np.float32)
        frame = np.clip(base + noise, 0, 255).astype(np.uint8)
        f_path = seq_dir / f"dark_{t:03d}.jpg"
        f_path.write_bytes(_build_dummy_jpeg_with_app1(frame))
        photo_paths.append(f_path)

    for use_gpu_flag in (False, True):
        out_dir = seq_dir / ("denoised_gpu" if use_gpu_flag else "denoised_cpu")
        ok, stats = process_sequence_denoise(
            photo_paths=photo_paths,
            output_dir=out_dir,
            window_size=7,
            sigma_range=4.5,
            use_gpu=use_gpu_flag,
        )
        assert ok is True
        assert stats["processed_photos"] == 7
        if use_gpu_flag and stats["use_gpu"]:
            assert stats["gpu_frames"] == 7
            assert stats["cpu_frames"] == 0
        else:
            assert stats["cpu_frames"] == 7
        for p in photo_paths:
            out_img = cv2.imread(str(out_dir / p.name))
            assert out_img is not None
            mean_val = float(out_img.mean())
            assert 24.0 <= mean_val <= 32.0, f"Saturacao detectada (use_gpu={use_gpu_flag}): mean={mean_val}"


