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


def test_classify_timelapse_with_album_samples():
    base_time = datetime(2026, 9, 6, 10, 0, 0)
    photos = []
    # 300 fotos a cada 2 segundos (duração total: 598 segundos ~ 10 minutos)
    for i in range(300):
        dt = base_time + timedelta(seconds=i * 2)
        photos.append(MediaMetadata(
            file_path=Path(f"IMG_{i:04d}.JPG"),
            is_video=False,
            date_str="2026-09-06",
            time_str=dt.strftime("%H-%M-%S"),
            timestamp=dt,
            camera_model="SX60",
            camera_make="Canon",
            focal_length_equiv=50.0,
            original_stem=f"IMG_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    class_config = {
        "timelapse_min_photos": 300,
        "timelapse_max_interval_seconds": 60.0,
        "timelapse_tolerance_ratio": 1.5,
        "enable_timelapse_album_samples": True,
        "timelapse_sample_interval_minutes": 5.0,
    }

    items = classify_media_batch(photos, class_config=class_config)
    assert len(items) == 300
    assert all(it.category == "timelapse" for it in items)

    # Identificar itens com destino extra (amostras)
    sampled = [it for it in items if it.extra_dest_dirs]
    # Esperado: Primeiro (0s), Meio (~300s / 5min) e Último (598s)
    assert len(sampled) == 3

    # Primeiro e último frame
    assert sampled[0].metadata.original_stem == "IMG_0000"
    assert sampled[-1].metadata.original_stem == "IMG_0299"

    # Verificar pasta destino da amostra
    sample_dir_str = str(sampled[0].extra_dest_dirs[0])
    assert "2_AlbunsDatas" in sample_dir_str
    assert "timelapse_amostras_10-00-00" in sample_dir_str


def test_classify_timelapse_short_sequence_guarantees_first_and_last():
    base_time = datetime(2026, 9, 6, 14, 0, 0)
    photos = []
    # 300 fotos a cada 0.4s (duração total: 120s = 2 minutos, menor que intervalo de 5min)
    for i in range(300):
        dt = base_time + timedelta(seconds=i * 0.4)
        photos.append(MediaMetadata(
            file_path=Path(f"IMG_{i:04d}.JPG"),
            is_video=False,
            date_str="2026-09-06",
            time_str=dt.strftime("%H-%M-%S"),
            timestamp=dt,
            camera_model="SX60",
            camera_make="Canon",
            focal_length_equiv=50.0,
            original_stem=f"IMG_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    class_config = {
        "timelapse_min_photos": 300,
        "timelapse_max_interval_seconds": 60.0,
        "timelapse_tolerance_ratio": 1.5,
        "enable_timelapse_album_samples": True,
        "timelapse_sample_interval_minutes": 5.0,
    }

    items = classify_media_batch(photos, class_config=class_config)
    sampled = [it for it in items if it.extra_dest_dirs]
    # Deve garantir exatamente 2 fotos: primeira e última
    assert len(sampled) == 2
    assert sampled[0].metadata.original_stem == "IMG_0000"
    assert sampled[1].metadata.original_stem == "IMG_0299"


def test_classify_timelapse_samples_disabled():
    base_time = datetime(2026, 9, 6, 16, 0, 0)
    photos = []
    for i in range(300):
        dt = base_time + timedelta(seconds=i * 2)
        photos.append(MediaMetadata(
            file_path=Path(f"IMG_{i:04d}.JPG"),
            is_video=False,
            date_str="2026-09-06",
            time_str=dt.strftime("%H-%M-%S"),
            timestamp=dt,
            camera_model="SX60",
            camera_make="Canon",
            focal_length_equiv=50.0,
            original_stem=f"IMG_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    class_config = {
        "timelapse_min_photos": 300,
        "timelapse_max_interval_seconds": 60.0,
        "timelapse_tolerance_ratio": 1.5,
        "enable_timelapse_album_samples": False,
    }

    items = classify_media_batch(photos, class_config=class_config)
    sampled = [it for it in items if it.extra_dest_dirs]
    assert len(sampled) == 0


def test_classify_astro_long_exposure_timelapse():
    """Valida detecção de timelapse de astrofotografia com exposição longa (60s) e intervalo de 65s."""
    base_time = datetime(2015, 4, 25, 21, 0, 0)
    photos = []
    current_time = base_time
    
    # 80 fotos de 60s de exposição espaçadas por 65s
    for i in range(80):
        # Inserir um gap harmônico de 3 frames (195s) no meio (ex: foto 40)
        if i == 40:
            current_time += timedelta(seconds=195)
        else:
            current_time += timedelta(seconds=65)
            
        photos.append(MediaMetadata(
            file_path=Path(f"IMG_{i:04d}.CR2"),
            is_video=False,
            date_str="2015-04-25",
            time_str=current_time.strftime("%H-%M-%S"),
            timestamp=current_time,
            camera_model="EOS 6D",
            camera_make="Canon",
            focal_length_equiv=14.0,
            shutter_str="60",
            original_stem=f"IMG_{i:04d}",
            extension="CR2",
            is_raw=True,
        ))

    items = classify_media_batch(photos)
    assert len(items) == 80
    assert all(it.category == "timelapse" for it in items)
    assert "4_Timelapses" in str(items[0].relative_dest_dir)


def test_classify_timelapse_folder_name_recognition():
    """Valida reconhecimento estrutural quando a pasta de origem contém 'timelapse'."""
    base_time = datetime(2015, 4, 25, 20, 0, 0)
    photos = []
    
    # 35 fotos numa pasta com nome de timelapse
    for i in range(35):
        dt = base_time + timedelta(seconds=i * 120)  # Intervalo de 2 minutos
        photos.append(MediaMetadata(
            file_path=Path(f"IMG_{i:04d}.JPG"),
            source_folder_name="2015-04-25 Sítio - Timelapse das estrelas",
            is_video=False,
            date_str="2015-04-25",
            time_str=dt.strftime("%H-%M-%S"),
            timestamp=dt,
            camera_model="EOS 6D",
            camera_make="Canon",
            original_stem=f"IMG_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos)
    assert len(items) == 35
    assert all(it.category == "timelapse" for it in items)


def test_classify_bird_burst_sequences_not_timelapse():
    """Garante que rajadas em fotografia de aves NÃO se transformem em timelapse.
    Cenário: 5 rajadas de 15 fotos com obturador rápido (1/2000s) e 3 minutos de pausa entre aparições.
    """
    base_time = datetime(2026, 9, 6, 8, 0, 0)
    photos = []
    current_time = base_time
    photo_count = 0
    
    for burst_idx in range(5):
        # Disparo de 15 fotos em rajada rápida (0.2s entre cada)
        for f in range(15):
            current_time += timedelta(seconds=0.2)
            photo_count += 1
            photos.append(MediaMetadata(
                file_path=Path(f"BIRD_{photo_count:04d}.JPG"),
                source_folder_name="DCIM/100CANON",
                is_video=False,
                date_str="2026-09-06",
                time_str=current_time.strftime("%H-%M-%S"),
                timestamp=current_time,
                camera_model="EOS R7",
                camera_make="Canon",
                focal_length_equiv=600.0,
                shutter_str="1/2000",
                original_stem=f"BIRD_{photo_count:04d}",
                extension="JPG",
                is_raw=False,
            ))
        # Pausa de 3 minutos aguardando o próximo pássaro pousar
        current_time += timedelta(minutes=3)

    assert len(photos) == 75
    items = classify_media_batch(photos)
    assert len(items) == 75
    # NENHUMA foto deve virar timelapse! Devem ser classificadas como avulsa ou rajada
    assert all(it.category != "timelapse" for it in items)


