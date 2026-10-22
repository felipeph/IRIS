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

def test_classify_sx60_wide_angle_raw_not_astro():
    # Foto RAW da SX60 tirada em grande angular (21mm) ou zoom moderado não deve ir para astro_lua
    meta = MediaMetadata(
        file_path=Path("IMG_0001.CR2"),
        is_video=False,
        date_str="2026-09-06",
        time_str="14-00-00",
        timestamp=datetime(2026, 9, 6, 14, 0, 0),
        camera_model="PowerShot SX60 HS",
        camera_make="Canon",
        focal_length_equiv=50.0,
        focal_str="50mm",
        original_stem="IMG_0001",
        extension="CR2",
        is_raw=True,
    )
    items = classify_media_batch([meta], class_config={"moon_zoom_threshold_mm": 1000.0})
    assert len(items) == 1
    assert items[0].category != "astro_lua"
    assert "5_Astrofotografia" not in str(items[0].relative_dest_dir)

def test_classify_canon_sx60_moon_raw_burst_as_astro_not_timelapse():
    # 300 fotos RAW da Lua disparadas em sequência rápida com SX60 no zoom máximo (1386mm equiv)
    base_time = datetime(2026, 10, 18, 20, 41, 9)
    photos = []
    for i in range(300):
        dt = base_time + timedelta(seconds=i * 2)
        photos.append(MediaMetadata(
            file_path=Path(f"IMG_{4197 + i}.CR2"),
            is_video=False,
            date_str="2026-10-18",
            time_str=dt.strftime("%H-%M-%S"),
            timestamp=dt,
            camera_model="PowerShot-SX60-HS",
            camera_make="Canon",
            focal_length_equiv=1385.84,  # Calculado via FocalLength35efl do ExifTool
            focal_str="1386mm",
            original_stem=f"IMG_{4197 + i}",
            extension="CR2",
            is_raw=True,
        ))

    class_config = {
        "moon_zoom_threshold_mm": 1000.0,
        "timelapse_min_photos": 200,
        "timelapse_max_interval_seconds": 60.0,
    }

    items = classify_media_batch(photos, class_config=class_config)
    assert len(items) == 300
    # Todas devem ser classificadas como astro_lua, NENHUMA como timelapse
    assert all(it.category == "astro_lua" for it in items)
    assert not any(it.category == "timelapse" for it in items)
    assert all("5_Astrofotografia" in str(it.relative_dest_dir) for it in items)
    assert all("sessao_20-41-09" in str(it.relative_dest_dir) for it in items)


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
    assert all(it.category == "timelapse_long_exposure" for it in items)
    assert "4_Timelapses_LongaExposicao" in str(items[0].relative_dest_dir)


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
    assert all(it.category != "timelapse" and it.category != "timelapse_long_exposure" for it in items)


def test_normal_timelapse_with_isolated_buffer_stalls():
    """Timelapse diurno metronômico de 250 fotos a cada 5s, com 3 travadas de buffer isoladas de 8s."""
    base_time = datetime(2026, 9, 6, 10, 0, 0)
    photos = []
    curr = base_time
    for i in range(250):
        # Travadas esporádicas nos índices 50, 120 e 180 (8s em vez de 5s)
        if i in (50, 120, 180):
            curr += timedelta(seconds=8.0)
        elif i > 0:
            curr += timedelta(seconds=5.0)

        photos.append(MediaMetadata(
            file_path=Path(f"TL_{i:04d}.JPG"),
            is_video=False,
            date_str="2026-09-06",
            time_str=curr.strftime("%H-%M-%S"),
            timestamp=curr,
            camera_model="EOS R7",
            camera_make="Canon",
            shutter_str="1/500",
            original_stem=f"TL_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos)
    assert len(items) == 250
    assert all(it.category == "timelapse" for it in items)
    assert "4_Timelapses" in str(items[0].relative_dest_dir)


def test_normal_timelapse_excessive_stalls_rejected():
    """Sequência irregular com 20% de intervalos flutuantes não deve ser aceita como timelapse."""
    base_time = datetime(2026, 9, 6, 10, 0, 0)
    photos = []
    curr = base_time
    for i in range(250):
        # A cada 5 fotos, ocorre uma pausa longa de 15s (20% de atrasos)
        if i % 5 == 0 and i > 0:
            curr += timedelta(seconds=15.0)
        elif i > 0:
            curr += timedelta(seconds=5.0)

        photos.append(MediaMetadata(
            file_path=Path(f"IRREG_{i:04d}.JPG"),
            is_video=False,
            date_str="2026-09-06",
            time_str=curr.strftime("%H-%M-%S"),
            timestamp=curr,
            camera_model="EOS R7",
            camera_make="Canon",
            shutter_str="1/500",
            original_stem=f"IRREG_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos)
    assert len(items) == 250
    # Deve rejeitar como timelapse devido ao excesso de atrasos e variação
    assert all(it.category != "timelapse" for it in items)


def test_night_singles_random_intervals_not_timelapse():
    """Fotos noturnas avulsas (shutter 10s) tiradas em intervalos desiguais não viram timelapse."""
    base_time = datetime(2026, 9, 6, 22, 0, 0)
    photos = []
    curr = base_time
    intervals = [12.0, 45.0, 18.0, 90.0, 25.0, 150.0, 30.0, 200.0, 20.0, 60.0] * 7  # 70 fotos
    for i, intv in enumerate(intervals):
        curr += timedelta(seconds=intv)
        photos.append(MediaMetadata(
            file_path=Path(f"NIGHT_{i:04d}.CR2"),
            is_video=False,
            date_str="2026-09-06",
            time_str=curr.strftime("%H-%M-%S"),
            timestamp=curr,
            camera_model="EOS 6D",
            camera_make="Canon",
            shutter_str="10",
            original_stem=f"NIGHT_{i:04d}",
            extension="CR2",
            is_raw=True,
        ))

    items = classify_media_batch(photos)
    assert len(items) == len(intervals)
    assert all(it.category != "timelapse" and it.category != "timelapse_long_exposure" for it in items)


def test_long_exposure_disabled_fallback():
    """Quando o perfil de longa exposição está desabilitado, fotos de longa exposição não formam timelapse_long_exposure."""
    base_time = datetime(2026, 9, 6, 21, 0, 0)
    photos = []
    curr = base_time
    for i in range(80):
        curr += timedelta(seconds=65)
        photos.append(MediaMetadata(
            file_path=Path(f"DIS_{i:04d}.CR2"),
            is_video=False,
            date_str="2026-09-06",
            time_str=curr.strftime("%H-%M-%S"),
            timestamp=curr,
            camera_model="EOS 6D",
            camera_make="Canon",
            shutter_str="60",
            original_stem=f"DIS_{i:04d}",
            extension="CR2",
            is_raw=True,
        ))

    class_config = {
        "timelapse_long_exposure": {"enabled": False}
    }
    items = classify_media_batch(photos, class_config=class_config)
    assert len(items) == 80
    assert all(it.category != "timelapse_long_exposure" for it in items)


def test_classify_fast_cadence_subsecond_timelapse():
    """Valida detecção de timelapse de ação (ex: GoPro 0.5s) com deltas de 0s e 1s devido a segundos inteiros."""
    base_time = datetime(2026, 10, 18, 14, 0, 0)
    photos = []
    for i in range(250):
        # Disparo a 0.5s quantizado para segundos inteiros (ex: 0, 0, 1, 1, 2, 2...)
        dt = base_time + timedelta(seconds=int(i * 0.5))
        photos.append(MediaMetadata(
            file_path=Path(f"GOPRO_{i:04d}.JPG"),
            is_video=False,
            date_str="2026-10-18",
            time_str=dt.strftime("%H-%M-%S"),
            timestamp=dt,
            camera_model="HERO5 Black",
            camera_make="GoPro",
            shutter_str="1/2000",
            original_stem=f"GOPRO_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos)
    assert len(items) == 250
    assert all(it.category == "timelapse" for it in items)
    assert "4_Timelapses" in str(items[0].relative_dest_dir)


def test_classify_fast_burst_not_timelapse():
    """Garante que uma rajada rápida (ex: 25 fotos com deltas 0s e 1s) NÃO vire timelapse devido ao piso de fotos."""
    base_time = datetime(2026, 10, 18, 14, 0, 0)
    photos = []
    for i in range(25):
        dt = base_time + timedelta(seconds=int(i * 0.5))
        photos.append(MediaMetadata(
            file_path=Path(f"BURST_{i:04d}.JPG"),
            is_video=False,
            date_str="2026-10-18",
            time_str=dt.strftime("%H-%M-%S"),
            timestamp=dt,
            camera_model="HERO5 Black",
            camera_make="GoPro",
            shutter_str="1/2000",
            original_stem=f"BURST_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos)
    assert len(items) == 25
    assert all(it.category != "timelapse" for it in items)


def test_iris_auto_folder_not_blind_bypassed():
    """Pastas com nomenclatura automática do IRIS (ex: timelapse_17-18-35) não devem sofrer bypass cego."""
    base_time = datetime(2026, 10, 18, 17, 18, 35)
    photos = []
    curr = base_time
    # 40 fotos com intervalos caóticos e espaçados
    for i in range(40):
        curr += timedelta(seconds=20 if i % 2 == 0 else 45)
        photos.append(MediaMetadata(
            file_path=Path(f"SX60_{i:04d}.JPG"),
            source_folder_name="timelapse_17-18-35",
            is_video=False,
            date_str="2026-10-18",
            time_str=curr.strftime("%H-%M-%S"),
            timestamp=curr,
            camera_model="SX60",
            camera_make="Canon",
            shutter_str="1/400",
            original_stem=f"SX60_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos)
    assert len(items) == 40
    # Não deve ser classificado como timelapse
    assert all(it.category != "timelapse" for it in items)


def test_classify_burst_detection_enabled():
    """Garante que fotos consecutivas com delta <= 1.5s sejam classificadas como rajada com mesmo burst_id."""
    base_time = datetime(2026, 10, 22, 9, 45, 0)
    photos = []
    curr = base_time
    for i in range(5):
        curr += timedelta(seconds=0.5)
        photos.append(MediaMetadata(
            file_path=Path(f"BURST_{i:04d}.JPG"),
            source_folder_name="DCIM/100CANON",
            is_video=False,
            date_str="2026-10-22",
            time_str=curr.strftime("%H-%M-%S"),
            timestamp=curr,
            camera_model="EOS R7",
            camera_make="Canon",
            shutter_str="1/2000",
            original_stem=f"BURST_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos, class_config={"enable_burst_detection": True, "burst_interval_seconds": 1.5})
    assert len(items) == 5
    assert all(it.category == "rajada" for it in items)
    expected_first_time = photos[0].time_str
    assert all(f"rajada_{expected_first_time}" in str(it.relative_dest_dir) for it in items)
    expected_burst_id = f"rajada_2026-10-22_{expected_first_time}"
    assert all(it.burst_id == expected_burst_id for it in items)


def test_classify_burst_detection_disabled():
    """Garante que quando desabilitado, fotos de rajada permaneçam como avulsas e com burst_id vazio."""
    base_time = datetime(2026, 10, 22, 9, 45, 0)
    photos = []
    curr = base_time
    for i in range(5):
        curr += timedelta(seconds=0.5)
        photos.append(MediaMetadata(
            file_path=Path(f"BURST_{i:04d}.JPG"),
            source_folder_name="DCIM/100CANON",
            is_video=False,
            date_str="2026-10-22",
            time_str=curr.strftime("%H-%M-%S"),
            timestamp=curr,
            camera_model="EOS R7",
            camera_make="Canon",
            shutter_str="1/2000",
            original_stem=f"BURST_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos, class_config={"enable_burst_detection": False})
    assert len(items) == 5
    assert all(it.category == "avulsa" for it in items)
    assert all("rajada" not in str(it.relative_dest_dir) for it in items)
    assert all(it.burst_id == "" for it in items)


def test_classify_burst_subsecond_same_second():
    """Garante que fotos de rajada rápida no mesmo segundo (delta == 0s) recebam o mesmo burst_id."""
    base_time = datetime(2026, 10, 22, 10, 15, 30)
    photos = []
    for i in range(4):
        photos.append(MediaMetadata(
            file_path=Path(f"FAST_{i:04d}.JPG"),
            source_folder_name="DCIM/100CANON",
            is_video=False,
            date_str="2026-10-22",
            time_str="10-15-30",
            timestamp=base_time,  # Mesmo segundo exato
            camera_model="EOS R7",
            camera_make="Canon",
            shutter_str="1/4000",
            original_stem=f"FAST_{i:04d}",
            extension="JPG",
            is_raw=False,
        ))

    items = classify_media_batch(photos, class_config={"enable_burst_detection": True})
    assert len(items) == 4
    assert all(it.category == "rajada" for it in items)
    assert all(it.burst_id == "rajada_2026-10-22_10-15-30" for it in items)


def test_classify_burst_mixed_singles_and_bursts():
    """Garante que fotos avulsas isoladas e rajadas intercaladas sejam corretamente segregadas."""
    t0 = datetime(2026, 10, 22, 8, 0, 0)
    photos = []

    # 1. Foto avulsa isolada
    photos.append(MediaMetadata(
        file_path=Path("SINGLE_01.JPG"),
        source_folder_name="DCIM/100CANON",
        is_video=False,
        date_str="2026-10-22",
        time_str="08-00-00",
        timestamp=t0,
        camera_model="EOS R7",
        camera_make="Canon",
        shutter_str="1/2000",
        original_stem="SINGLE_01",
        extension="JPG",
        is_raw=False,
    ))

    # Pausa de 1 minuto
    # 2. Rajada de 3 fotos a cada 0.3s
    t1 = t0 + timedelta(minutes=1)
    for i in range(3):
        t = t1 + timedelta(seconds=0.3 * i)
        photos.append(MediaMetadata(
            file_path=Path(f"BURST_{i:02d}.JPG"),
            source_folder_name="DCIM/100CANON",
            is_video=False,
            date_str="2026-10-22",
            time_str=t.strftime("%H-%M-%S"),
            timestamp=t,
            camera_model="EOS R7",
            camera_make="Canon",
            shutter_str="1/2000",
            original_stem=f"BURST_{i:02d}",
            extension="JPG",
            is_raw=False,
        ))

    # Pausa de 2 minutos
    # 3. Outra foto avulsa isolada
    t2 = t1 + timedelta(minutes=2)
    photos.append(MediaMetadata(
        file_path=Path("SINGLE_02.JPG"),
        source_folder_name="DCIM/100CANON",
        is_video=False,
        date_str="2026-10-22",
        time_str="08-03-00",
        timestamp=t2,
        camera_model="EOS R7",
        camera_make="Canon",
        shutter_str="1/2000",
        original_stem="SINGLE_02",
        extension="JPG",
        is_raw=False,
    ))

    items = classify_media_batch(photos, class_config={"enable_burst_detection": True, "burst_interval_seconds": 1.5})
    assert len(items) == 5

    # Primeira foto: avulsa
    assert items[0].category == "avulsa"
    assert items[0].burst_id == ""
    assert "rajada" not in str(items[0].relative_dest_dir)

    # Fotos 1, 2, 3: rajada com mesmo burst_id
    burst_items = items[1:4]
    assert all(it.category == "rajada" for it in burst_items)
    burst_id_val = burst_items[0].burst_id
    assert burst_id_val.startswith("rajada_2026-10-22_")
    assert all(it.burst_id == burst_id_val for it in burst_items)

    # Última foto: avulsa
    assert items[4].category == "avulsa"
    assert items[4].burst_id == ""
    assert "rajada" not in str(items[4].relative_dest_dir)



