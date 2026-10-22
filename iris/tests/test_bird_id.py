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
    from src.modules.bird_id.detect_stage import BirdDetectStage
    from src.modules.bird_id.classify_stage import BirdClassifyStage
    from src.modules.bird_id.organize_stage import BirdOrganizeStage

    s_detect = get_stage("bird_detect", "Detecção e Recorte de Aves")
    assert isinstance(s_detect, BirdDetectStage)
    assert s_detect.stage_id == "bird_detect"

    s_classify = get_stage("bird_id", "Classificação de Aves")
    assert isinstance(s_classify, BirdClassifyStage)
    assert s_classify.stage_id == "bird_id"

    s_organize = get_stage("bird_organize", "Organização Física de Aves")
    assert isinstance(s_organize, BirdOrganizeStage)
    assert s_organize.stage_id == "bird_organize"


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
def test_bird_detect_stage_saves_only_in_iris_root(mock_detector_cls, tmp_path):
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
    orig_dest = config.get("general.destination_root")
    config.set("general.destination_root", str(iris_dest_root))

    try:
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
    finally:
        config.set("general.destination_root", orig_dest)


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


def test_bird_organize_stage_atomic_moves_and_tags(tmp_path):
    from src.modules.bird_id.organize_stage import BirdOrganizeStage
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

    from src.core.config import config
    orig_exif = config.get("modules.bird_id.write_exif_tags")
    config.set("modules.bird_id.write_exif_tags", False)

    try:
        stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves")
        success = stage.run(proj)
        assert success is True

        # Arquivo original deve ter sido movido para subpasta {Bem-te-vi} e renomeado
        assert not orig_file.exists()
        species_dir = base_dir / "Bem-te-vi"
        assert species_dir.exists()
        renamed_file = next(species_dir.glob("*.JPG"))
        assert "[Bem-te-vi]_[Pitangus-sulphuratus]_[Great-Kiskadee]" in renamed_file.name

        # Verifica sincronização no banco de dados do projeto
        updated_item = proj.get_item(item.original_path)
        assert updated_item.organized_path == str(renamed_file.resolve())
    finally:
        config.set("modules.bird_id.write_exif_tags", orig_exif)


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


