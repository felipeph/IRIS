"""
Testes unitários automatizados para o módulo de Identificação de Aves (BirdIdStage / IRIS Bird ID).
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import cv2
import pytest
import numpy as np
from PIL import Image

from src.core.config import config
from src.core.project import Project, ProjectItem, create_project
from src.core.pipeline import PipelineRunner
from src.modules.bird_id.detector import BirdDetector
from src.modules.bird_id.classifier import BirdClassifier, load_species_catalog
from src.modules.bird_id.video_processor import VideoBirdProcessor, calculate_sharpness
from src.modules.bird_id.stage import BirdIdStage, get_stage
from src.modules.bird_id.reporter import export_bird_review_csv


def test_get_stage_and_pipeline_loading():
    from src.modules.bird_id.detect_stage import BirdDetectStage
    from src.modules.bird_id.classify_stage import BirdClassifyStage
    from src.modules.bird_id.organize_stage import BirdOrganizeStage
    from src.modules.bird_id.tag_stage import BirdTagStage

    s_detect = get_stage("bird_detect", "Detecção e Recorte de Aves")
    assert isinstance(s_detect, BirdDetectStage)
    assert s_detect.stage_id == "bird_detect"

    s_classify = get_stage("bird_id", "Classificação de Aves")
    assert isinstance(s_classify, BirdClassifyStage)
    assert s_classify.stage_id == "bird_id"

    s_organize = get_stage("bird_organize", "Organização Física de Aves")
    assert isinstance(s_organize, BirdOrganizeStage)
    assert s_organize.stage_id == "bird_organize"

    s_tag = get_stage("bird_tag", "Injeção de Metadados de Aves")
    assert isinstance(s_tag, BirdTagStage)
    assert s_tag.stage_id == "bird_tag"


def test_species_catalog_loading():
    csv_path = Path(__file__).resolve().parent.parent / "src" / "modules" / "bird_id" / "species_lists" / "br_mg_aves.csv"
    assert csv_path.exists()
    species = load_species_catalog(csv_path)
    assert len(species) >= 90
    names = [s["scientific_name"] for s in species]
    assert "Psittacara leucophthalmus" in names
    assert "Pitangus sulphuratus" in names


def test_calculate_sharpness():
    # Imagem plana sem bordas = nitidez baixa/zero
    flat_img = np.ones((100, 100), dtype=np.uint8) * 128
    assert calculate_sharpness(flat_img) == 0.0

    # Imagem com padrão alternado preto e branco = alta nitidez
    checker = np.zeros((100, 100), dtype=np.uint8)
    checker[::2, ::2] = 255
    assert calculate_sharpness(checker) > 100.0


@patch("ultralytics.YOLO")
def test_bird_detector_mocked(mock_yolo_cls):
    mock_model = MagicMock()
    mock_yolo_cls.return_value = mock_model

    # Simula detecção de ave
    mock_box = MagicMock()
    mock_box.conf = [0.85]
    mock_box.xyxy = [[50, 50, 150, 150]]
    mock_res = MagicMock()
    mock_res.boxes = [mock_box]
    mock_model.predict.return_value = [mock_res]

    detector = BirdDetector(model_name="yolov8s.pt", confidence=0.25)
    img_bgr = np.zeros((300, 300, 3), dtype=np.uint8)
    crop_pil, crop_bgr, detected, conf, bbox = detector.detect_and_crop(img_bgr)

    assert detected is True
    assert conf == 0.85
    assert bbox is not None
    assert isinstance(crop_pil, Image.Image)


@patch("open_clip.create_model_and_transforms")
@patch("open_clip.get_tokenizer")
def test_bird_classifier_mocked(mock_tokenizer_func, mock_create_model):
    import torch
    mock_model = MagicMock()
    mock_model.to.return_value = mock_model
    mock_preprocess = MagicMock(return_value=torch.zeros((3, 224, 224)))
    mock_create_model.return_value = (mock_model, None, mock_preprocess)

    # Mock de tokenizer e embeddings (95 espécies cadastradas)
    mock_tokenizer_func.return_value = lambda texts: torch.zeros((len(texts), 77), dtype=torch.long)
    mock_model.encode_text.return_value = torch.randn(95, 512)
    mock_model.encode_image.return_value = torch.randn(2, 512)

    classifier = BirdClassifier(device="cpu", classifier_type="bioclip")
    dummy_img = Image.new("RGB", (100, 100), color="blue")
    preds = classifier.classify_crop(dummy_img, top_k=3, use_tta=True)

    assert len(preds) == 3
    assert "scientific_name" in preds[0]
    assert "common_name" in preds[0]
    assert "confidence" in preds[0]


def test_bird_classifier_inaturalist_mocked():
    mock_client = MagicMock()
    mock_client.score_image.return_value = [
        {
            "scientific_name": "Pitangus sulphuratus",
            "common_name": "Bem-te-vi",
            "common_name_en": "Great Kiskadee",
            "family": "Tyrannidae",
            "order": "Passeriformes",
            "confidence": 0.95
        }
    ]

    classifier = BirdClassifier(classifier_type="inaturalist", inat_client=mock_client)
    dummy_img = Image.new("RGB", (100, 100), color="green")
    preds = classifier.classify_crop(
        dummy_img,
        top_k=1,
        lat=-19.92,
        lng=-43.94,
        accuracy=25000,
        observed_on="2026-10-22 09:00:00"
    )

    assert len(preds) == 1
    assert preds[0]["common_name"] == "Bem-te-vi"
    assert mock_client.score_image.called
    kwargs = mock_client.score_image.call_args[1]
    assert kwargs["lat"] == -19.92
    assert kwargs["lng"] == -43.94
    assert kwargs["positional_accuracy"] == 25000


def test_export_bird_review_csv(tmp_path):
    csv_file = tmp_path / "review.csv"
    records = [
        {
            "item_path": "foto1.jpg",
            "is_video": False,
            "species_common": "Bem-te-vi",
            "species_scientific": "Pitangus sulphuratus",
            "confidence": 0.88,
            "needs_review": False,
            "top2_common": "Neinei",
            "top2_scientific": "Megarynchus pitangua",
            "top2_confidence": 0.08,
            "top3_common": "",
            "top3_scientific": "",
            "top3_confidence": 0.0,
            "crop_saved_path": "crop1.jpg"
        }
    ]
    export_bird_review_csv(records, csv_file)
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8")
    assert "Pitangus sulphuratus" in content
    assert "Bem-te-vi" in content


def test_bird_id_stage_empty_project(tmp_path):
    proj = Project("empty_bird_proj")
    stage = BirdIdStage("bird_id", "Identificação de Aves")
    success = stage.run(proj)
    assert success is True


@patch("src.modules.bird_id.detect_stage.BirdDetector")
@patch("src.modules.bird_id.classify_stage.BirdClassifier")
def test_bird_id_stage_with_telephoto_item(mock_classifier_cls, mock_detector_cls, tmp_path):
    # Setup mocks
    mock_detector = MagicMock()
    mock_detector_cls.return_value = mock_detector
    dummy_pil = Image.new("RGB", (100, 100), color="green")
    dummy_bgr = np.zeros((100, 100, 3), dtype=np.uint8)
    mock_detector.detect_and_crop.return_value = (dummy_pil, dummy_bgr, True, 0.92, (10, 10, 90, 90))

    mock_classifier = MagicMock()
    mock_classifier_cls.return_value = mock_classifier
    mock_classifier.classify_crop.return_value = [
        {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.85},
        {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "confidence": 0.10},
        {"scientific_name": "Fluvicola nengeta", "common_name": "Lavadeira-mascarada", "confidence": 0.05},
    ]

    # Cria arquivo real no tmp_path para safe_imread
    img_file = tmp_path / "superzoom_bird.jpg"
    import cv2
    cv2.imwrite(str(img_file), dummy_bgr)

    proj = Project("test_bird_proj")
    proj.save()

    item = ProjectItem(
        original_path=str(img_file),
        staging_path=str(img_file),
        status="copied",
        meta_focal_length_equiv=1200.0,  # Superzoom teleobjetiva (ex: Canon SX60 1200mm)
        meta_is_video=False
    )
    proj.save_item(item)

    stage = BirdIdStage("bird_id", "Identificação de Aves")
    success = stage.run(proj)
    assert success is True

    # Verifica persistência no SQLite do projeto
    records = proj.list_bird_identifications()
    assert len(records) == 1
    rec = records[0]
    assert rec["species_common"] == "Bem-te-vi"
    assert rec["species_scientific"] == "Pitangus sulphuratus"
    assert rec["confidence"] == pytest.approx(0.85, 0.01)
    assert rec["needs_review"] is False

    # Verifica se gerou relatório CSV
    csv_rep = proj.project_dir / "relatorio_aves.csv"
    assert csv_rep.exists()


@patch("src.modules.bird_id.detect_stage.BirdDetector")
def test_bird_detect_stage_saves_only_in_iris_root(mock_detector_cls, tmp_path, monkeypatch):
    from src.modules.bird_id.detect_stage import BirdDetectStage
    from src.core.config import config
    import cv2

    mock_detector = MagicMock()
    mock_detector_cls.return_value = mock_detector
    dummy_pil = Image.new("RGB", (80, 80), color="blue")
    dummy_bgr = np.zeros((80, 80, 3), dtype=np.uint8)
    mock_detector.detect_and_crop.return_value = (dummy_pil, dummy_bgr, True, 0.94, (5, 5, 75, 75))

    iris_dest_root = tmp_path / "IRIS_ROOT"
    iris_dest_root.mkdir(parents=True, exist_ok=True)
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: str(iris_dest_root) if k in ("general.destination_root", "storage.destination_root") else orig_get(k, d))

    photo_file = tmp_path / "aves_sx60.jpg"
    cv2.imwrite(str(photo_file), dummy_bgr)

    proj = Project("detect_only_proj")
    proj.save()

    item = ProjectItem(
        original_path=str(photo_file),
        staging_path=str(photo_file),
        status="copied",
        meta_focal_length_equiv=1365.0,
        meta_is_video=False
    )
    proj.save_item(item)

    stage = BirdDetectStage("bird_detect", "Detecção e Recorte de Aves")
    success = stage.run(proj)
    assert success is True

    # Verifica se o recorte foi salvo EXCLUSIVAMENTE na raiz do IRIS
    iris_crop_file = iris_dest_root / "10_Aves" / "Recortes" / proj.name / f"crop_{photo_file.stem}.jpg"
    assert iris_crop_file.exists()

    # Verifica que NÃO foi salvo na pasta oculta do projeto
    project_crop_dir = proj.project_dir / "recortes_aves"
    assert not project_crop_dir.exists()

    # Verifica persistência no banco
    records = proj.list_bird_identifications()
    assert len(records) == 1
    rec = records[0]
    assert rec["crop_saved_path"] == str(iris_crop_file.resolve())
    assert rec["metadata_json"]["detection_status"] == "detected"
    assert rec["metadata_json"]["yolo_conf"] == pytest.approx(0.94, 0.01)


@patch("src.modules.bird_id.classify_stage.BirdClassifier")
def test_bird_classify_stage_atomic_does_not_touch_files(mock_classifier_cls, tmp_path):
    from src.modules.bird_id.classify_stage import BirdClassifyStage
    import cv2

    mock_classifier = MagicMock()
    mock_classifier_cls.return_value = mock_classifier
    mock_classifier.classify_crop.return_value = [
        {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.95, "family": "Tyrannidae", "order": "Passeriformes"}
    ]

    crop_img = tmp_path / "crop_foto1.jpg"
    cv2.imwrite(str(crop_img), np.zeros((50, 50, 3), dtype=np.uint8))

    photo_file = tmp_path / "foto1.jpg"
    photo_file.write_text("foto_original_raw_ou_jpeg")

    proj = Project("classify_only_proj")
    proj.save()

    item = ProjectItem(
        original_path=str(photo_file),
        staging_path=str(photo_file),
        status="copied",
        meta_is_video=False
    )
    proj.save_item(item)

    # Detecção pré-gravada no banco
    proj.save_bird_detection({
        "item_path": str(photo_file),
        "is_video": False,
        "crop_saved_path": str(crop_img),
        "metadata_json": {"detection_status": "detected"}
    })

    stage = BirdClassifyStage("bird_id", "Classificação de Aves")
    success = stage.run(proj)
    assert success is True

    # O arquivo original NÃO pode ter sido movido nem renomeado nesta etapa!
    assert photo_file.exists()
    assert photo_file.name == "foto1.jpg"

    # Confere dados taxonômicos no banco
    rec = proj.get_bird_identification(str(photo_file))
    assert rec is not None
    assert rec["species_common"] == "Bem-te-vi"
    assert rec["confidence"] == pytest.approx(0.95, 0.01)
    assert rec["needs_review"] is False

    # Confere se relatório CSV foi gerado
    csv_file = proj.project_dir / "relatorio_aves.csv"
    assert csv_file.exists()


def test_bird_organize_stage_atomic_moves_and_tags(tmp_path, monkeypatch):
    from src.modules.bird_id.organize_stage import BirdOrganizeStage
    from src.core.config import config
    import cv2

    base_dir = tmp_path / "2_AlbunsDatas" / "2026" / "10" / "22"
    base_dir.mkdir(parents=True, exist_ok=True)
    orig_file = base_dir / "2026-10-22_12-00_Canon_IMG_1234.JPG"
    cv2.imwrite(str(orig_file), np.zeros((30, 30, 3), dtype=np.uint8))

    proj = Project("organize_only_proj")
    proj.save()

    item = ProjectItem(
        original_path=str(orig_file),
        staging_path=str(orig_file),
        organized_path=str(orig_file),
        status="organized"
    )
    proj.save_item(item)

    # Identificação de alta certeza no banco
    proj.add_bird_identification({
        "item_path": str(orig_file),
        "is_video": False,
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "confidence": 0.90,
        "needs_review": False,
        "crop_saved_path": "dummy_crop.jpg"
    })

    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: False if k == "modules.bird_id.write_exif_tags" else orig_get(k, d))

    stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves")
    success = stage.run(proj)
    assert success is True

    # Arquivo original deve ter sido movido para subpasta {Bem-te-vi} e renomeado
    assert not orig_file.exists()
    species_dir = base_dir / "Bem-te-vi"
    assert species_dir.exists()
    renamed_file = next(species_dir.glob("*.JPG"))
    assert "Bem-te-vi_Pitangus-sulphuratus" in renamed_file.name
    assert "[" not in renamed_file.name
    assert "]" not in renamed_file.name

    # Verifica sincronização no banco de dados do projeto
    updated_item = proj.get_item(item.original_path)
    assert updated_item.organized_path == str(renamed_file.resolve())


def test_build_bird_filename():
    from src.modules.bird_id.action import build_bird_filename, sanitize_bird_token
    original = "2026-09-06_15-10-00_Canon-SX60_16MP_1365mm_IMG_1234.JPG"
    new_name = build_bird_filename(original, "Beija-flor-de-fronte-violeta", "Thalurania glaucopis", "Violet-fronted Woodnymph")
    assert "Beija-flor-de-fronte-violeta_Thalurania-glaucopis" in new_name
    assert "[" not in new_name
    assert "]" not in new_name
    assert new_name.endswith(".JPG")
    assert new_name.startswith("2026-09-06_15-10-00_Canon-SX60_16MP_1365mm_IMG_1234_")

    # Idempotência: não duplica tags se já presentes
    double_call = build_bird_filename(new_name, "Beija-flor-de-fronte-violeta", "Thalurania glaucopis")
    assert double_call == new_name


@patch("rawpy.imread")
def test_safe_read_image_or_raw_mocked(mock_rawpy_imread, tmp_path):
    from src.modules.bird_id.detector import safe_read_image_or_raw
    import cv2
    import rawpy

    # Simula extração de thumbnail JPEG embutido
    dummy_bgr = np.ones((50, 50, 3), dtype=np.uint8) * 100
    _, jpeg_buf = cv2.imencode(".jpg", dummy_bgr)

    mock_thumb = MagicMock()
    mock_thumb.format = rawpy.ThumbFormat.JPEG
    mock_thumb.data = jpeg_buf.tobytes()

    mock_raw = MagicMock()
    mock_raw.extract_thumb.return_value = mock_thumb
    mock_rawpy_imread.return_value.__enter__.return_value = mock_raw

    raw_fake = tmp_path / "teste_foto.cr2"
    raw_fake.write_bytes(b"dummy_raw_data")

    res = safe_read_image_or_raw(str(raw_fake))
    assert res is not None
    assert res.shape == (50, 50, 3)


def test_apply_bird_organization_high_and_low_certainty(tmp_path):
    from src.modules.bird_id.action import apply_bird_organization
    import cv2

    base_dir = tmp_path / "2_AlbunsDatas" / "2026" / "09" / "06"
    base_dir.mkdir(parents=True, exist_ok=True)
    photo_file = base_dir / "2026-09-06_15-10-00_SX60_IMG_1234.JPG"
    cv2.imwrite(str(photo_file), np.zeros((20, 20, 3), dtype=np.uint8))

    proj = Project("test_action_proj")
    proj.save()

    item = ProjectItem(
        original_path=str(photo_file),
        staging_path=str(photo_file),
        organized_path=str(photo_file),
        status="organized"
    )
    proj.save_item(item)

    cfg = {
        "min_species_confidence": 0.75,
        "rename_files": True,
        "organize_in_subfolders": True,
        "write_exif_tags": False  # desativa escrita real de EXIF no teste unitário
    }

    # 1. Caso de Baixa Certeza (confiança 0.60 < 0.75): NÃO deve renomear nem mover
    low_rec = {
        "species_common": "Sabiá-laranjeira",
        "species_scientific": "Turdus rufiventris",
        "species_common_en": "Rufous-bellied Thrush",
        "confidence": 0.60,
        "needs_review": True
    }
    path_low = apply_bird_organization(item, proj, low_rec, cfg)
    assert path_low == photo_file
    assert photo_file.exists()

    # 2. Caso de Alta Certeza (confiança 0.88 >= 0.75): DEVE mover para subpasta e renomear
    high_rec = {
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "confidence": 0.88,
        "needs_review": False
    }
    path_high = apply_bird_organization(item, proj, high_rec, cfg)
    assert path_high != photo_file
    assert path_high.exists()
    assert not photo_file.exists()
    # Verifica que foi movido para subpasta com nome popular
    assert path_high.parent.name == "Bem-te-vi"
    # Verifica renomeação segura
    assert "Bem-te-vi_Pitangus-sulphuratus" in path_high.name
    assert "[" not in path_high.name
    assert "]" not in path_high.name
    # Verifica atualização no SQLite
    updated_item = proj.get_item(item.original_path)
    assert updated_item is not None
    assert updated_item.organized_path == str(path_high.resolve())
    assert updated_item.target_filename == path_high.name


def test_video_bird_processor_decoupled(tmp_path):
    from src.modules.bird_id.video_processor import VideoBirdProcessor

    # Simula detector e classificador isolados
    mock_detector = MagicMock()
    mock_classifier = MagicMock()

    processor = VideoBirdProcessor(detector=mock_detector, classifier=mock_classifier)

    # 1. Testa classificação de recortes já gravados em disco sem precisar do vídeo
    crop_file1 = tmp_path / "crop1.jpg"
    crop_file2 = tmp_path / "crop2.jpg"
    import cv2
    cv2.imwrite(str(crop_file1), np.zeros((40, 40, 3), dtype=np.uint8))
    cv2.imwrite(str(crop_file2), np.zeros((40, 40, 3), dtype=np.uint8))

    saved_crops = [
        {"crop_path": str(crop_file1), "frame_idx": 10, "sharpness": 120.0, "score": 90.0},
        {"crop_path": str(crop_file2), "frame_idx": 30, "sharpness": 150.0, "score": 110.0}
    ]

    mock_classifier.classify_crop.side_effect = [
        [{"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.90, "family": "Tyrannidae", "order": "Passeriformes"}],
        [{"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.85, "family": "Tyrannidae", "order": "Passeriformes"}]
    ]

    res = processor.classify_video_crops(saved_crops, classifier=mock_classifier, duration_sec=10.0, min_confident_crops=2)
    assert res is not None
    assert res["species_common"] == "Bem-te-vi"
    assert res["species_crops_count"] == 2
    assert res["is_confident_detection"] is True
    assert res["confidence"] > 0.80
    assert mock_classifier.classify_crop.call_count == 2


@patch("src.modules.bird_id.detect_stage.BirdDetector")
def test_bird_detect_stage_video_persists_in_sqlite(mock_detector_cls, tmp_path, monkeypatch):
    """Garante que BirdDetectStage processa vídeos, salva recortes e persiste metadados no SQLite sem erro de serialização."""
    from src.modules.bird_id.detect_stage import BirdDetectStage
    from src.core.config import config
    import cv2

    # Cria vídeo sintético
    video_path = tmp_path / "video_teste.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(video_path), fourcc, 10.0, (160, 160))
    for _ in range(15):
        frame = np.ones((160, 160, 3), dtype=np.uint8) * 100
        out.write(frame)
    out.release()

    iris_dest_root = tmp_path / "IRIS_DEST"
    iris_dest_root.mkdir(parents=True, exist_ok=True)
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: str(iris_dest_root) if k in ("general.destination_root", "storage.destination_root") else orig_get(k, d))

    mock_detector = MagicMock()
    mock_detector_cls.return_value = mock_detector
    mock_detector.confidence = 0.25

    box_mock = MagicMock()
    box_mock.conf = [0.91]
    box_mock.xyxy = [[10, 10, 70, 70]]
    r_mock = MagicMock()
    r_mock.boxes = [box_mock]
    mock_detector.model.predict.return_value = [r_mock]

    proj = Project("video_detect_test_proj")
    proj.save()

    item = ProjectItem(
        original_path=str(video_path),
        staging_path=str(video_path),
        status="copied",
        meta_is_video=True
    )
    proj.save_item(item)

    stage = BirdDetectStage("bird_detect", "Detecção de Aves")
    success = stage.run(proj)
    assert success is True

    # Verifica persistência no SQLite
    records = proj.list_bird_identifications()
    assert len(records) == 1
    rec = records[0]
    assert rec["is_video"] is True
    assert rec["crop_saved_path"] != ""
    assert Path(rec["crop_saved_path"]).exists()

    # Valida que metadados dos recortes são 100% serializáveis e preservam métricas
    meta = rec["metadata_json"]
    assert meta["yolo_detected"] is True
    assert meta["detection_status"] == "detected"
    assert len(meta["video_crops"]) > 0
    first_crop = meta["video_crops"][0]
    assert "crop_path" in first_crop
    assert "frame_idx" in first_crop
    assert "score" in first_crop
    assert "pil_img" not in first_crop
    assert "bgr_img" not in first_crop


@patch("src.modules.bird_id.classify_stage.BirdClassifier")
def test_bird_classify_stage_video_weighted_voting_and_csv(mock_classifier_cls, tmp_path):
    """Testa a classificação de vídeo na Etapa 7 a partir do registro gerado na Etapa 6."""
    from src.modules.bird_id.classify_stage import BirdClassifyStage
    import cv2

    crop1 = tmp_path / "crop_vid_f0.jpg"
    crop2 = tmp_path / "crop_vid_f5.jpg"
    cv2.imwrite(str(crop1), np.zeros((40, 40, 3), dtype=np.uint8))
    cv2.imwrite(str(crop2), np.zeros((40, 40, 3), dtype=np.uint8))

    video_file = tmp_path / "video_passaro.mp4"
    video_file.write_text("dummy_video")

    proj = Project("video_classify_test_proj")
    proj.save()

    item = ProjectItem(
        original_path=str(video_file),
        staging_path=str(video_file),
        status="copied",
        meta_is_video=True
    )
    proj.save_item(item)

    proj.save_bird_detection({
        "item_path": str(video_file),
        "is_video": True,
        "crop_saved_path": str(crop1),
        "metadata_json": {
            "detection_status": "detected",
            "duration_sec": 5.0,
            "video_crops": [
                {"crop_path": str(crop1), "frame_idx": 0, "score": 100.0, "yolo_conf": 0.95},
                {"crop_path": str(crop2), "frame_idx": 5, "score": 120.0, "yolo_conf": 0.96}
            ]
        }
    })

    mock_classifier = MagicMock()
    mock_classifier_cls.return_value = mock_classifier
    mock_classifier.classify_crop.return_value = [
        {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.92, "family": "Tyrannidae", "order": "Passeriformes"}
    ]

    stage = BirdClassifyStage("bird_id", "Classificação de Aves")
    success = stage.run(proj)
    assert success is True

    # Confere dados atualizados no banco
    rec = proj.get_bird_identification(str(video_file))
    assert rec is not None
    assert rec["species_common"] == "Bem-te-vi"
    assert rec["is_video"] is True
    assert rec["confidence"] > 0.85
    assert rec["needs_review"] is False

    # Confere se relatório CSV inclui o vídeo
    csv_file = proj.project_dir / "relatorio_aves.csv"
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8")
    assert "video_passaro.mp4" in content
    assert "Bem-te-vi" in content


def test_bird_classify_stage_video_fallback_disk_search(tmp_path, monkeypatch):
    """Testa fallback de vídeo no disco quando o banco SQLite não possui registro prévio."""
    from src.modules.bird_id.classify_stage import BirdClassifyStage
    from src.core.config import config
    import cv2

    iris_dest_root = tmp_path / "IRIS_FALLBACK"
    iris_dest_root.mkdir(parents=True, exist_ok=True)
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: str(iris_dest_root) if k in ("general.destination_root", "storage.destination_root") else orig_get(k, d))

    proj = Project("video_fallback_proj")
    proj.save()

    video_file = tmp_path / "video_avulso.mp4"
    video_file.write_text("dummy")

    item = ProjectItem(
        original_path=str(video_file),
        staging_path=str(video_file),
        status="copied",
        meta_is_video=True
    )
    proj.save_item(item)

    # Cria recortes físicos no padrão crop_{stem}_f*.jpg
    crops_dir = iris_dest_root / "10_Aves" / "Recortes" / proj.name
    crops_dir.mkdir(parents=True, exist_ok=True)
    crop_f0 = crops_dir / f"crop_{video_file.stem}_f0.jpg"
    cv2.imwrite(str(crop_f0), np.zeros((30, 30, 3), dtype=np.uint8))

    with patch("src.modules.bird_id.classify_stage.BirdClassifier") as mock_clf_cls:
        mock_clf = MagicMock()
        mock_clf_cls.return_value = mock_clf
        mock_clf.classify_crop.return_value = [
            {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.90}
        ]

        stage = BirdClassifyStage("bird_id", "Classificação de Aves")
        success = stage.run(proj)
        assert success is True

    rec = proj.get_bird_identification(str(video_file))
    assert rec is not None
    assert rec["is_video"] is True
    assert rec["species_common"] == "Bem-te-vi"


def test_bird_classify_stage_burst_consensus(tmp_path):
    """Garante que fotos com o mesmo burst_id recebam classificação consensual unificada."""
    from src.modules.bird_id.classify_stage import BirdClassifyStage
    proj = create_project("test_burst_id_proj", str(tmp_path))

    photo1 = tmp_path / "BURST_001.JPG"
    photo2 = tmp_path / "BURST_002.JPG"
    photo3 = tmp_path / "BURST_003.JPG"
    for p in [photo1, photo2, photo3]:
        p.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 20)

    crop1 = tmp_path / "crop_BURST_001.jpg"
    crop2 = tmp_path / "crop_BURST_002.jpg"
    crop3 = tmp_path / "crop_BURST_003.jpg"
    for c in [crop1, crop2, crop3]:
        cv2.imwrite(str(c), np.zeros((40, 40, 3), dtype=np.uint8))

    burst_id = "rajada_2026-10-22_10-00-00"
    item1 = ProjectItem(str(photo1), str(photo1), category="rajada", burst_id=burst_id, status="copied", verified=True)
    item2 = ProjectItem(str(photo2), str(photo2), category="rajada", burst_id=burst_id, status="copied", verified=True)
    item3 = ProjectItem(str(photo3), str(photo3), category="rajada", burst_id=burst_id, status="copied", verified=True)
    proj.save_items_batch([item1, item2, item3])

    proj.save_bird_detection({"item_path": str(photo1), "is_video": False, "crop_saved_path": str(crop1), "metadata_json": {}})
    proj.save_bird_detection({"item_path": str(photo2), "is_video": False, "crop_saved_path": str(crop2), "metadata_json": {}})
    proj.save_bird_detection({"item_path": str(photo3), "is_video": False, "crop_saved_path": str(crop3), "metadata_json": {}})

    with patch("src.modules.bird_id.classify_stage.BirdClassifier") as mock_clf_cls:
        mock_clf = MagicMock()
        mock_clf_cls.return_value = mock_clf

        # Simula: foto 1 e foto 2 muito nítidas de Bem-te-vi, foto 3 com pose desfavorável sugerindo Neinei como top1
        def mock_classify(pil_img, **kwargs):
            # Se for a foto 3 (baseada em kwargs ou contador simples)
            return [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.88},
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "confidence": 0.10}
            ]
        mock_clf.classify_crop.side_effect = mock_classify

        stage = BirdClassifyStage("bird_id", "Classificação de Aves")
        success = stage.run(proj)
        assert success is True

    # Verifica se todas as 3 fotos da rajada receberam o consenso
    for p in [photo1, photo2, photo3]:
        rec = proj.get_bird_identification(str(p))
        assert rec is not None
        assert rec["species_common"] == "Bem-te-vi"
        assert rec["species_scientific"] == "Pitangus sulphuratus"
        assert rec["confidence"] > 0.80
        assert rec["needs_review"] is False
        assert rec["metadata_json"]["burst_consensus"] is True
        assert rec["metadata_json"]["burst_id"] == burst_id
        assert rec["metadata_json"]["burst_crops_count"] == 3


def test_bird_organize_stage_burst_siblings_unification(tmp_path, monkeypatch):
    """Garante que fotos da mesma rajada sem recorte sejam unificadas na subpasta da espécie."""
    from src.modules.bird_id.organize_stage import BirdOrganizeStage

    proj = create_project("test_burst_org_proj", str(tmp_path))

    burst_dir = tmp_path / "2_AlbunsDatas" / "2026" / "10" / "22" / "rajada_10-00-00"
    burst_dir.mkdir(parents=True, exist_ok=True)

    photo_with_crop = burst_dir / "BURST_001.JPG"
    photo_without_crop = burst_dir / "BURST_002.JPG"
    photo_with_crop.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 20)
    photo_without_crop.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 20)

    burst_id = "rajada_2026-10-22_10-00-00"
    item1 = ProjectItem(str(photo_with_crop), str(photo_with_crop), organized_path=str(photo_with_crop), category="rajada", burst_id=burst_id, status="organized", verified=True)
    item2 = ProjectItem(str(photo_without_crop), str(photo_without_crop), organized_path=str(photo_without_crop), category="rajada", burst_id=burst_id, status="organized", verified=True)
    proj.save_items_batch([item1, item2])

    proj.add_bird_identification({
        "item_path": str(photo_with_crop),
        "is_video": False,
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "family": "Tyrannidae",
        "order": "Passeriformes",
        "confidence": 0.90,
        "needs_review": False,
        "crop_saved_path": str(photo_with_crop)
    })

    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: False if k == "modules.bird_id.write_exif_tags" else orig_get(k, d))

    stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves")
    success = stage.run(proj)
    assert success is True

    # Ambas as fotos devem ter sido movidas para a subpasta da espécie e dentro dela a pasta da rajada:
    # 2_AlbunsDatas/2026/10/22/Bem-te-vi/rajada_10-00-00/
    date_dir = tmp_path / "2_AlbunsDatas" / "2026" / "10" / "22"
    species_dir = date_dir / "Bem-te-vi"
    target_burst_dir = species_dir / "rajada_10-00-00"

    assert species_dir.exists()
    assert target_burst_dir.exists()

    target_photo1 = next(target_burst_dir.glob("*BURST_001*"))
    target_photo2 = target_burst_dir / "BURST_002.JPG"

    assert target_photo1.exists()
    assert target_photo2.exists()

    # A pasta original da rajada na raiz da data ficou vazia e deve ter sido removida
    assert not burst_dir.exists()

    # O item 2 sem recorte teve seu organized_path atualizado para a pasta da rajada dentro da espécie
    item2_updated = proj.get_item(str(photo_without_crop))
    assert Path(item2_updated.organized_path).parent == target_burst_dir


def test_bird_organize_multiple_bursts_and_singles_same_day(tmp_path, monkeypatch):
    """Garante que em uma data determinada, a pasta da espécie contenha múltiplas rajadas e avulsas."""
    from src.modules.bird_id.organize_stage import BirdOrganizeStage

    proj = create_project("test_multi_bursts_proj", str(tmp_path))

    date_dir = tmp_path / "2_AlbunsDatas" / "2026" / "10" / "22"
    burst1_dir = date_dir / "rajada_10-00-00"
    burst2_dir = date_dir / "rajada_14-30-00"
    burst1_dir.mkdir(parents=True, exist_ok=True)
    burst2_dir.mkdir(parents=True, exist_ok=True)

    b1_f1 = burst1_dir / "B1_001.JPG"
    b1_f2 = burst1_dir / "B1_002.JPG"
    b2_f1 = burst2_dir / "B2_001.JPG"
    avulsa = date_dir / "2026-10-22_12-00-00_IMG_9999.JPG"

    for f in [b1_f1, b1_f2, b2_f1, avulsa]:
        f.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 20)

    item_b1_1 = ProjectItem(str(b1_f1), str(b1_f1), organized_path=str(b1_f1), category="rajada", burst_id="rajada_2026-10-22_10-00-00", status="organized")
    item_b1_2 = ProjectItem(str(b1_f2), str(b1_f2), organized_path=str(b1_f2), category="rajada", burst_id="rajada_2026-10-22_10-00-00", status="organized")
    item_b2_1 = ProjectItem(str(b2_f1), str(b2_f1), organized_path=str(b2_f1), category="rajada", burst_id="rajada_2026-10-22_14-30-00", status="organized")
    item_avulsa = ProjectItem(str(avulsa), str(avulsa), organized_path=str(avulsa), category="avulsa", status="organized")
    proj.save_items_batch([item_b1_1, item_b1_2, item_b2_1, item_avulsa])

    for f in [b1_f1, b1_f2, b2_f1, avulsa]:
        proj.add_bird_identification({
            "item_path": str(f),
            "is_video": False,
            "species_common": "Bem-te-vi",
            "species_scientific": "Pitangus sulphuratus",
            "species_common_en": "Great Kiskadee",
            "confidence": 0.92,
            "needs_review": False,
            "crop_saved_path": str(f)
        })

    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: False if k == "modules.bird_id.write_exif_tags" else orig_get(k, d))

    stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves")
    assert stage.run(proj) is True

    species_dir = date_dir / "Bem-te-vi"
    assert species_dir.exists()

    # 1. As rajadas devem estar como subpastas de Bem-te-vi
    target_burst1 = species_dir / "rajada_10-00-00"
    target_burst2 = species_dir / "rajada_14-30-00"
    assert target_burst1.exists()
    assert target_burst2.exists()
    assert len(list(target_burst1.glob("*.JPG"))) == 2
    assert len(list(target_burst2.glob("*.JPG"))) == 1

    # 2. A foto avulsa deve estar diretamente na pasta da espécie
    avulsa_matches = list(species_dir.glob("*IMG_9999*"))
    assert len(avulsa_matches) == 1
    assert avulsa_matches[0].parent == species_dir

    # 3. As pastas originais de rajada vazias foram removidas
    assert not burst1_dir.exists()
    assert not burst2_dir.exists()


def test_bird_organize_unidentified_remains_in_date_root(tmp_path, monkeypatch):
    """Garante que fotos e rajadas não identificadas (ou em revisão) permaneçam na data, fora da pasta de espécie."""
    from src.modules.bird_id.organize_stage import BirdOrganizeStage

    proj = create_project("test_unidentified_proj", str(tmp_path))

    date_dir = tmp_path / "2_AlbunsDatas" / "2026" / "10" / "22"
    burst_ident_dir = date_dir / "rajada_10-00-00"
    burst_unident_dir = date_dir / "rajada_16-00-00"
    burst_ident_dir.mkdir(parents=True, exist_ok=True)
    burst_unident_dir.mkdir(parents=True, exist_ok=True)

    ident_f = burst_ident_dir / "IDENT_001.JPG"
    unident_f = burst_unident_dir / "UNIDENT_001.JPG"
    unident_avulsa = date_dir / "UNIDENT_AVULSA.JPG"

    for f in [ident_f, unident_f, unident_avulsa]:
        f.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 20)

    it_ident = ProjectItem(str(ident_f), str(ident_f), organized_path=str(ident_f), category="rajada", burst_id="rajada_2026-10-22_10-00-00", status="organized")
    it_unident = ProjectItem(str(unident_f), str(unident_f), organized_path=str(unident_f), category="rajada", burst_id="rajada_2026-10-22_16-00-00", status="organized")
    it_unident_avulsa = ProjectItem(str(unident_avulsa), str(unident_avulsa), organized_path=str(unident_avulsa), category="avulsa", status="organized")
    proj.save_items_batch([it_ident, it_unident, it_unident_avulsa])

    # Apenas ident_f tem alta certeza
    proj.add_bird_identification({
        "item_path": str(ident_f),
        "is_video": False,
        "species_common": "Sabiá-laranjeira",
        "species_scientific": "Turdus rufiventris",
        "species_common_en": "Rufous-bellied Thrush",
        "confidence": 0.89,
        "needs_review": False,
        "crop_saved_path": str(ident_f)
    })
    # unident_f tem baixa confiança e needs_review
    proj.add_bird_identification({
        "item_path": str(unident_f),
        "is_video": False,
        "species_common": "Pássaro Desconhecido",
        "confidence": 0.35,
        "needs_review": True,
        "crop_saved_path": str(unident_f)
    })
    # unident_avulsa sequer possui registro de identificação

    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: False if k == "modules.bird_id.write_exif_tags" else orig_get(k, d))

    stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves")
    assert stage.run(proj) is True

    # 1. Apenas a espécie identificada tem pasta criada (sanitizada sem acento)
    species_dir = date_dir / "Sabia-laranjeira"
    assert species_dir.exists()
    assert (species_dir / "rajada_10-00-00").exists()

    # 2. A rajada não identificada permanece na raiz da data, fora de qualquer espécie
    assert burst_unident_dir.exists()
    assert unident_f.exists()

    # 3. A avulsa não identificada permanece na raiz da data, fora de qualquer espécie
    assert unident_avulsa.exists()
    assert unident_avulsa.parent == date_dir


def test_bird_organize_idempotency(tmp_path, monkeypatch):
    """Garante que rodar a organização repetidamente não altere a estrutura nem crie aninhamentos indevidos."""
    from src.modules.bird_id.organize_stage import BirdOrganizeStage

    proj = create_project("test_idempotency_proj", str(tmp_path))

    date_dir = tmp_path / "2_AlbunsDatas" / "2026" / "10" / "22"
    burst_dir = date_dir / "rajada_10-00-00"
    burst_dir.mkdir(parents=True, exist_ok=True)
    photo = burst_dir / "BURST_001.JPG"
    photo.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 20)

    item = ProjectItem(str(photo), str(photo), organized_path=str(photo), category="rajada", burst_id="rajada_2026-10-22_10-00-00", status="organized")
    proj.save_item(item)

    proj.add_bird_identification({
        "item_path": str(photo),
        "is_video": False,
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "confidence": 0.95,
        "needs_review": False,
        "crop_saved_path": str(photo)
    })

    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: False if k == "modules.bird_id.write_exif_tags" else orig_get(k, d))

    stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves")

    # Primeira execução
    assert stage.run(proj) is True
    target_burst = date_dir / "Bem-te-vi" / "rajada_10-00-00"
    assert target_burst.exists()
    organized_files = list(target_burst.glob("*.JPG"))
    assert len(organized_files) == 1
    first_path = organized_files[0]

    # Segunda execução (idempotência)
    assert stage.run(proj) is True
    assert target_burst.exists()
    # Não deve aninhar rajada_10-00-00/rajada_10-00-00 nem Bem-te-vi/Bem-te-vi
    assert not (target_burst / "rajada_10-00-00").exists()
    assert not (target_burst / "Bem-te-vi").exists()
    assert first_path.exists()


def test_sanitize_bird_token():
    from src.modules.bird_id.action import sanitize_bird_token

    assert sanitize_bird_token("Sabiá-laranjeira") == "Sabia-laranjeira"
    assert sanitize_bird_token("João-de-barro") == "Joao-de-barro"
    assert sanitize_bird_token("Beija-flor-de-fronte-violeta") == "Beija-flor-de-fronte-violeta"
    assert sanitize_bird_token("Thalurania glaucopis") == "Thalurania-glaucopis"
    assert sanitize_bird_token("  Águia-pescadora / Pandion haliaetus  ") == "Aguia-pescadora-Pandion-haliaetus"


def test_bird_tag_stage_unit(tmp_path, monkeypatch):
    """Testa o estágio BirdTagStage de forma isolada."""
    from src.modules.bird_id.tag_stage import BirdTagStage

    proj = create_project("test_tag_stage_proj", str(tmp_path))

    photo = tmp_path / "foto_ave.jpg"
    photo.write_bytes(b"\xFF\xD8\xFF\xE0" + b"\x00" * 20)

    item = ProjectItem(str(photo), str(photo), organized_path=str(photo), status="organized")
    proj.save_item(item)

    proj.add_bird_identification({
        "item_path": str(photo),
        "is_video": False,
        "species_common": "Bem-te-vi",
        "species_scientific": "Pitangus sulphuratus",
        "species_common_en": "Great Kiskadee",
        "confidence": 0.92,
        "needs_review": False
    })

    # 1. Caso desabilitado em config
    orig_get = config.get
    monkeypatch.setattr(config, "get", lambda k, d=None: False if k == "modules.bird_id.write_exif_tags" else orig_get(k, d))
    stage = BirdTagStage("bird_tag", "Injeção de Metadados de Aves")
    assert stage.run(proj) is True

    # 2. Caso ExifTool ausente: não deve quebrar
    monkeypatch.setattr(config, "get", lambda k, d=None: True if k == "modules.bird_id.write_exif_tags" else orig_get(k, d))
    monkeypatch.setattr("shutil.which", lambda cmd: None)
    monkeypatch.setenv("IRIS_EXIFTOOL_PATH", "")
    assert stage.run(proj) is True

    # 3. Caso normal com ExifTool simulado
    mock_apply_meta = MagicMock(return_value=True)
    monkeypatch.setattr("src.modules.bird_id.tag_stage.apply_bird_metadata", mock_apply_meta)
    monkeypatch.setattr("shutil.which", lambda cmd: "C:\\exiftool.exe")

    assert stage.run(proj) is True
    assert mock_apply_meta.call_count == 1
    call_args = mock_apply_meta.call_args[0]
    assert call_args[0] == photo
    assert call_args[1]["species_common"] == "Bem-te-vi"





