"""
Testes unitários automatizados para o módulo de consenso de espécies em rajadas (IRIS Bird ID - Burst Consensus).
"""

import pytest
from src.modules.bird_id.burst_consensus import aggregate_burst_species


def test_aggregate_burst_species_empty():
    """Garante que listas vazias retornem None graciosamente."""
    assert aggregate_burst_species([]) is None
    assert aggregate_burst_species([{"crop_path": "c1.jpg", "predictions": []}]) is None


def test_aggregate_burst_species_unanimous():
    """Garante que uma rajada com votos unânimes consolide a espécie com alta certeza."""
    crops_preds = [
        {
            "crop_path": "/crops/burst_01.jpg",
            "item_path": "/photos/burst_01.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.90},
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "common_name_en": "Boat-billed Flycatcher", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.08},
            ]
        },
        {
            "crop_path": "/crops/burst_02.jpg",
            "item_path": "/photos/burst_02.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.94},
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "common_name_en": "Boat-billed Flycatcher", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.05},
            ]
        },
        {
            "crop_path": "/crops/burst_03.jpg",
            "item_path": "/photos/burst_03.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.86},
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "common_name_en": "Boat-billed Flycatcher", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.10},
            ]
        }
    ]

    res = aggregate_burst_species(crops_preds, min_species_confidence=0.70)
    assert res is not None
    assert res["species_common"] == "Bem-te-vi"
    assert res["species_scientific"] == "Pitangus sulphuratus"
    assert res["species_common_en"] == "Great Kiskadee"
    assert res["family"] == "Tyrannidae"
    assert res["order"] == "Passeriformes"
    assert res["total_crops"] == 3
    assert res["supporting_crops"] == 3
    assert res["agreement_ratio"] == 1.0
    assert res["confidence"] > 0.85
    assert res["needs_review"] is False


def test_aggregate_burst_species_majority_wins_and_rescues_deviant():
    """
    Garante que a espécie majoritária vença por Soft Voting e resgate fotos
    com ângulos desfavoráveis na mesma rajada.
    """
    crops_preds = [
        # 3 fotos muito nítidas de Bem-te-vi
        {
            "crop_path": "/crops/burst_01.jpg",
            "item_path": "/photos/burst_01.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.92},
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "common_name_en": "Boat-billed Flycatcher", "confidence": 0.05},
            ]
        },
        {
            "crop_path": "/crops/burst_02.jpg",
            "item_path": "/photos/burst_02.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.88},
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "common_name_en": "Boat-billed Flycatcher", "confidence": 0.07},
            ]
        },
        {
            "crop_path": "/crops/burst_03.jpg",
            "item_path": "/photos/burst_03.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.85},
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "common_name_en": "Boat-billed Flycatcher", "confidence": 0.10},
            ]
        },
        # 1 foto com ângulo difícil onde o classificador hesitou e colocou Neinei como top1 com score baixo (0.52)
        {
            "crop_path": "/crops/burst_04.jpg",
            "item_path": "/photos/burst_04.jpg",
            "predictions": [
                {"scientific_name": "Megarynchus pitangua", "common_name": "Neinei", "common_name_en": "Boat-billed Flycatcher", "family": "Tyrannidae", "order": "Passeriformes", "confidence": 0.52},
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "confidence": 0.40},
            ]
        }
    ]

    res = aggregate_burst_species(crops_preds, min_species_confidence=0.70, min_agreement_ratio=0.50)
    assert res is not None
    assert res["species_common"] == "Bem-te-vi"
    assert res["species_scientific"] == "Pitangus sulphuratus"
    assert res["total_crops"] == 4
    assert res["supporting_crops"] == 3
    assert res["agreement_ratio"] == 0.75  # 3 em 4 apoiaram como top-1
    assert res["needs_review"] is False


def test_aggregate_burst_species_severe_disagreement_needs_review():
    """Garante que empate ou dispersão de espécies marque a rajada com needs_review = True."""
    crops_preds = [
        {
            "crop_path": "/crops/burst_01.jpg",
            "item_path": "/photos/burst_01.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.60},
                {"scientific_name": "Turdus rufiventris", "common_name": "Sabiá-laranjeira", "confidence": 0.35},
            ]
        },
        {
            "crop_path": "/crops/burst_02.jpg",
            "item_path": "/photos/burst_02.jpg",
            "predictions": [
                {"scientific_name": "Turdus rufiventris", "common_name": "Sabiá-laranjeira", "confidence": 0.65},
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "confidence": 0.30},
            ]
        }
    ]

    res = aggregate_burst_species(crops_preds, min_species_confidence=0.70, min_agreement_ratio=0.60)
    assert res is not None
    # Concordância é 1/2 = 50% (< 60% mínimo requerido), deve sinalizar revisão
    assert res["needs_review"] is True


def test_aggregate_burst_species_single_crop():
    """Garante funcionamento consistente para rajadas com apenas 1 recorte válido."""
    crops_preds = [
        {
            "crop_path": "/crops/single.jpg",
            "item_path": "/photos/single.jpg",
            "predictions": [
                {"scientific_name": "Pitangus sulphuratus", "common_name": "Bem-te-vi", "common_name_en": "Great Kiskadee", "confidence": 0.88},
            ]
        }
    ]

    res = aggregate_burst_species(crops_preds, min_species_confidence=0.70)
    assert res is not None
    assert res["species_common"] == "Bem-te-vi"
    assert res["total_crops"] == 1
    assert res["supporting_crops"] == 1
    assert res["agreement_ratio"] == 1.0
    assert res["needs_review"] is False
