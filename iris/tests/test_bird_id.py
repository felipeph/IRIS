"""
Testes unitários automatizados para o módulo de Identificação de Aves (BirdIdStage / IRIS Bird ID).
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
from PIL import Image

from src.core.project import Project, ProjectItem
from src.core.pipeline import PipelineRunner
from src.modules.bird_id.detector import BirdDetector
from src.modules.bird_id.classifier import BirdClassifier, load_species_catalog
from src.modules.bird_id.video_processor import VideoBirdProcessor, calculate_sharpness
from src.modules.bird_id.stage import BirdIdStage, get_stage
from src.modules.bird_id.reporter import export_bird_review_csv


def test_get_stage_and_pipeline_loading():
    stage = get_stage("bird_id", "Identificação de Aves")
    assert isinstance(stage, BirdIdStage)
    assert stage.stage_id == "bird_id"
    assert stage.name == "Identificação de Aves"


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

    classifier = BirdClassifier(device="cpu")
    dummy_img = Image.new("RGB", (100, 100), color="blue")
    preds = classifier.classify_crop(dummy_img, top_k=3, use_tta=True)

    assert len(preds) == 3
    assert "scientific_name" in preds[0]
    assert "common_name" in preds[0]
    assert "confidence" in preds[0]


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


@patch("src.modules.bird_id.stage.BirdDetector")
@patch("src.modules.bird_id.stage.BirdClassifier")
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


def test_build_bird_filename():
    from src.modules.bird_id.action import build_bird_filename
    original = "2026-09-06_15-10-00_Canon-SX60_16MP_1365mm_IMG_1234.JPG"
    new_name = build_bird_filename(original, "Bem-te-vi", "Pitangus sulphuratus", "Great Kiskadee")
    assert "[Bem-te-vi]_[Pitangus-sulphuratus]_[Great-Kiskadee]" in new_name
    assert new_name.endswith(".JPG")
    assert new_name.startswith("2026-09-06_15-10-00_Canon-SX60_16MP_1365mm_IMG_1234_")

    # Idempotência: não duplica tags se já presentes
    double_call = build_bird_filename(new_name, "Bem-te-vi", "Pitangus sulphuratus", "Great Kiskadee")
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
    # Verifica renomeação tripla
    assert "[Bem-te-vi]_[Pitangus-sulphuratus]_[Great-Kiskadee]" in path_high.name
    # Verifica atualização no SQLite
    updated_item = proj.get_item(item.original_path)
    assert updated_item is not None
    assert updated_item.organized_path == str(path_high.resolve())
    assert updated_item.target_filename == path_high.name

