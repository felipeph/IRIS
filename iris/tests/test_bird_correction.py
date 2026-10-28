"""
Testes unitários automatizados para o Catálogo de Espécies e Módulo de Correção de Aves (IRIS Bird ID).
"""

import os
import sqlite3
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.core.project import Project, create_project, get_db_connection
from src.core.pipeline import PipelineRunner
from src.modules.bird_id.catalog import (
    sync_species_catalog,
    search_species,
    list_species,
    get_species,
    register_or_increment_species,
    clean_bird_text,
    normalize_ascii_lower
)
from src.modules.bird_id.stage import get_stage
from src.modules.bird_id.correction import BirdCorrectionStage


def test_normalize_and_clean_bird_text():
    assert normalize_ascii_lower("Sabiá-laranjeira") == "sabia-laranjeira"
    assert normalize_ascii_lower("CARCARÁ") == "carcara"
    assert clean_bird_text("  Suiriri   ") == "Suiriri"


def test_sync_species_catalog_with_seed(tmp_path):
    central_db = tmp_path / "iris_central_test.db"
    seed_csv = tmp_path / "seed_aves.csv"

    # Cria CSV de teste
    seed_csv.write_text(
        "scientific_name,common_name_pt,common_name_en,family,order\n"
        "Tyrannus melancholicus,Suiriri,Tropical Kingbird,Tyrannidae,Passeriformes\n"
        "Pitangus sulphuratus,Bem-te-vi,Great Kiskadee,Tyrannidae,Passeriformes\n"
        "Turdus rufiventris,Sabiá-laranjeira,Rufous-bellied Thrush,Turdidae,Passeriformes\n",
        encoding="utf-8"
    )

    total = sync_species_catalog(central_db_path=central_db, seed_csv_path=seed_csv)
    assert total == 3

    species_list = list_species(limit=10, db_path=central_db)
    assert len(species_list) == 3
    sci_names = [s["species_scientific"] for s in species_list]
    assert "Tyrannus melancholicus" in sci_names
    assert "Pitangus sulphuratus" in sci_names


def test_search_species_ranking_and_accents(tmp_path):
    central_db = tmp_path / "iris_central_test.db"
    register_or_increment_species("Suiriri", "Tyrannus melancholicus", family="Tyrannidae", db_path=central_db, count_increment=10)
    register_or_increment_species("Sabiá-laranjeira", "Turdus rufiventris", family="Turdidae", db_path=central_db, count_increment=5)
    register_or_increment_species("Sabiá-do-campo", "Mimus saturninus", family="Mimidae", db_path=central_db, count_increment=2)
    register_or_increment_species("Bem-te-vi", "Pitangus sulphuratus", family="Tyrannidae", db_path=central_db, count_increment=20)

    # Busca com 'sabia' sem acento deve retornar ambos os sabiás, ranqueados por use_count
    res_sabia = search_species("sabia", limit=5, db_path=central_db)
    assert len(res_sabia) == 2
    assert res_sabia[0]["species_common"] == "Sabiá-laranjeira"
    assert res_sabia[1]["species_common"] == "Sabiá-do-campo"

    # Busca por parte do nome científico
    res_tyr = search_species("tyrannus", limit=5, db_path=central_db)
    assert len(res_tyr) >= 1
    assert res_tyr[0]["species_scientific"] == "Tyrannus melancholicus"

    # Busca vazia retorna todos ranqueados por uso
    all_res = search_species("", limit=10, db_path=central_db)
    assert all_res[0]["species_common"] == "Bem-te-vi"  # 20 usos


def test_project_correct_bird_identification(tmp_path):
    proj_dir = tmp_path / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    central_db = proj_dir / "iris_central.db"

    with patch("src.core.project.PROJECTS_DIR", proj_dir), \
         patch("src.core.project.CENTRAL_DB_PATH", central_db):
        proj = create_project("TestProj", str(tmp_path / "orig"))

        # Adiciona identificação inicial incorreta
        dummy_video = str(tmp_path / "orig" / "MVI_0001.mp4")
        proj.add_bird_identification({
            "item_path": dummy_video,
            "is_video": True,
            "species_common": "periquito-australiano",
            "species_scientific": "Melopsittacus undulatus",
            "confidence": 0.55,
            "needs_review": True,
            "metadata_json": {"duration_sec": 120.0}
        })

        ident_before = proj.get_bird_identification(dummy_video)
        assert ident_before["species_common"] == "periquito-australiano"
        assert ident_before["needs_review"] is True
        assert ident_before["confidence"] == 0.55

        # Aplica a correção manual para Suiriri
        updated = proj.correct_bird_identification(
            item_path=dummy_video,
            new_species={
                "species_common": "Suiriri",
                "species_scientific": "Tyrannus melancholicus",
                "species_common_en": "Tropical Kingbird",
                "family": "Tyrannidae",
                "order": "Passeriformes"
            },
            apply_physical_move=False
        )

        assert updated is not None
        assert updated["species_common"] == "Suiriri"
        assert updated["species_scientific"] == "Tyrannus melancholicus"
        assert updated["confidence"] == 1.0
        assert updated["needs_review"] is False

        # Verifica persistência no SQLite do projeto
        ident_after = proj.get_bird_identification(dummy_video)
        assert ident_after["species_common"] == "Suiriri"
        assert ident_after["species_scientific"] == "Tyrannus melancholicus"
        assert ident_after["confidence"] == 1.0
        assert ident_after["needs_review"] is False
        assert ident_after["metadata_json"]["manual_correction"] is True
        assert ident_after["metadata_json"]["previous_species"]["species_common"] == "periquito-australiano"

        # Verifica catálogo de espécies atualizado
        sp_cat = get_species("Tyrannus melancholicus", db_path=central_db)
        assert sp_cat is not None
        assert sp_cat["species_common"] == "Suiriri"
        assert sp_cat["use_count"] >= 1


def test_get_stage_bird_correction():
    stage = get_stage("bird_correction", "Revisão e Correção de Aves")
    assert isinstance(stage, BirdCorrectionStage)
    assert stage.stage_id == "bird_correction"

    stage_rev = get_stage("bird_review", "Revisão de Aves")
    assert isinstance(stage_rev, BirdCorrectionStage)


def test_bird_correction_physical_move(tmp_path):
    proj_dir = tmp_path / "projects"
    proj_dir.mkdir(parents=True, exist_ok=True)
    central_db = proj_dir / "iris_central.db"
    dest_root = tmp_path / "IRIS"
    dest_root.mkdir(parents=True, exist_ok=True)

    # Cria arquivo simulado em subpasta da espécie errada
    old_bird_dir = dest_root / "3_Videos" / "2026" / "10" / "18" / "periquito-australiano"
    old_bird_dir.mkdir(parents=True, exist_ok=True)
    old_file = old_bird_dir / "2026-10-18_16-40-00_periquito-australiano_Melopsittacus-undulatus_MVI_4190.mp4"
    old_file.write_text("dummy video content")

    with patch("src.core.project.PROJECTS_DIR", proj_dir), \
         patch("src.core.project.CENTRAL_DB_PATH", central_db), \
         patch("src.core.config.config.get", side_effect=lambda k, d=None: dest_root if k == "general.destination_root" else d):

        proj = create_project("MoveProj", str(tmp_path / "orig"))
        from src.core.project import ProjectItem
        item = ProjectItem(
            original_path=str(old_file),
            staging_path="",
            organized_path=str(old_file),
            status="copied"
        )
        proj.save_item(item)

        proj.add_bird_identification({
            "item_path": str(old_file),
            "is_video": True,
            "species_common": "periquito-australiano",
            "species_scientific": "Melopsittacus undulatus",
            "confidence": 0.5,
            "needs_review": True
        })

        # Corrige para Suiriri com movimentação física
        res = proj.correct_bird_identification(
            item_path=str(old_file),
            new_species={
                "species_common": "Suiriri",
                "species_scientific": "Tyrannus melancholicus",
            },
            apply_physical_move=True
        )

        assert res is not None
        # O arquivo deve ter sido movido para a pasta 'Suiriri' e renomeado
        assert not old_file.exists()
        new_bird_dir = dest_root / "3_Videos" / "2026" / "10" / "18" / "Suiriri"
        assert new_bird_dir.exists()
        files_in_new_dir = list(new_bird_dir.glob("*.mp4"))
        assert len(files_in_new_dir) == 1
        assert "Suiriri" in files_in_new_dir[0].name
        assert "Tyrannus-melancholicus" in files_in_new_dir[0].name
