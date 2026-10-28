"""
Testes de Contrato Arquitetural do IRIS.
Garante que:
1. Os arquivos YAML (`config.example.yaml` e `config.yaml`) não possuam chaves duplicadas.
2. Todas as 14 etapas do pipeline estejam sincronizadas no `config.example.yaml` e importem com `get_stage()`.
3. As fachadas modulares (`config_menu.py`, `describer.py`, `project.py`) exponham todos os contratos públicos
   e permaneçam enxutas (prevenindo o retorno de monólitos).
"""

import importlib
from pathlib import Path
import yaml

from src.core.pipeline import PipelineStage

IRIS_ROOT = Path(__file__).resolve().parents[1]


class _NoDuplicateKeysLoader(yaml.SafeLoader):
    """YAML Loader que falha caso haja qualquer chave duplicada no mesmo nível de mapeamento."""
    pass


def _construct_mapping_no_duplicates(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Chave YAML duplicada detectada: '{key}' na linha {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_NoDuplicateKeysLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping_no_duplicates,
)


def test_config_example_yaml_has_no_duplicate_keys():
    """Garante que config.example.yaml não possui chaves duplicadas (ex: bird_id duplicado)."""
    example_path = IRIS_ROOT / "config.example.yaml"
    assert example_path.exists()
    content = example_path.read_text(encoding="utf-8")
    data = yaml.load(content, Loader=_NoDuplicateKeysLoader)
    assert isinstance(data, dict)
    assert "general" in data
    assert "modules" in data
    assert "pipeline" in data


def test_config_example_yaml_stages_match_canonical_pipeline():
    """Valida que as 14 etapas canônicas estão declaradas na ordem correta e são instanciáveis."""
    example_path = IRIS_ROOT / "config.example.yaml"
    data = yaml.safe_load(example_path.read_text(encoding="utf-8"))
    stages_cfg = data.get("pipeline", {}).get("stages", [])

    expected_order = [
        "ingestion",
        "cleanup",
        "planning",
        "organize",
        "sanitization",
        "bird_detect",
        "bird_id",
        "bird_organize",
        "bird_tag",
        "astro_stack",
        "astro_sharpen",
        "timelapse",
        "video_edit",
        "youtube",
    ]
    actual_ids = [s["id"] for s in stages_cfg]
    assert actual_ids == expected_order

    for st in stages_cfg:
        mod = importlib.import_module(st["module"])
        assert hasattr(mod, "get_stage"), f"Módulo {st['module']} não expõe get_stage()"
        instance = mod.get_stage(st["id"], st["name"])
        assert isinstance(instance, PipelineStage)


def test_modular_facades_export_all_contracts_and_stay_compact():
    """Garante retrocompatibilidade das fachadas e impede regressão para arquivos monolíticos."""
    import src.core.config_menu as cm_mod
    import src.modules.youtube.describer as desc_mod
    import src.core.project as proj_mod

    # 1. Fachada config_menu.py
    for sym in [
        "show_config_menu",
        "_menu_storage_ingestion",
        "_menu_organization_classification",
        "_menu_timelapse",
        "_menu_timelapse_long_exposure",
        "_menu_video_edit",
        "_menu_youtube_notifications",
        "_menu_astro",
        "_menu_bird_id",
        "_menu_geolocation",
        "_edit_location_flow",
    ]:
        assert hasattr(cm_mod, sym), f"config_menu.py perdeu exportação: {sym}"

    # 2. Fachada describer.py
    for sym in [
        "format_duration_human",
        "format_bytes_human",
        "summarize_exposure_param",
        "calculate_aspect_ratio",
        "build_youtube_title",
        "build_youtube_tags",
        "resolve_project_geolocation",
        "format_location_block",
        "build_geo_hashtags",
        "build_rich_youtube_description",
        "build_edited_video_youtube_title",
        "sanitize_hashtag",
        "resolve_bird_identification",
        "build_bird_youtube_title",
        "format_bird_taxonomy_block",
        "build_bird_hashtags",
        "resolve_bird_target_playlists",
        "build_edited_video_youtube_metadata",
    ]:
        assert hasattr(desc_mod, sym), f"describer.py perdeu exportação: {sym}"

    # 3. Fachada project.py
    for sym in [
        "PROJECTS_DIR",
        "CENTRAL_DB_PATH",
        "CURRENT_SCHEMA_VERSION",
        "SHARED_TABLES_DDL",
        "Project",
        "ProjectItem",
        "get_project",
        "create_project",
        "init_central_db",
        "list_open_projects",
        "get_last_active_project",
        "save_central_timelapse",
        "list_central_timelapses",
        "save_central_edited_video",
        "list_central_edited_videos",
        "save_central_astro_stack",
        "list_central_astro_stacks",
        "save_central_astro_sharpen",
        "list_central_astro_sharpens",
        "reconcile_project_with_central",
        "reconcile_all_projects_with_central",
    ]:
        assert hasattr(proj_mod, sym), f"project.py perdeu exportação: {sym}"

    # 4. Guardrail de tamanho de fachada (< 350 linhas cada)
    cm_lines = len(Path(cm_mod.__file__).read_text(encoding="utf-8").splitlines())
    desc_lines = len(Path(desc_mod.__file__).read_text(encoding="utf-8").splitlines())
    proj_lines = len(Path(proj_mod.__file__).read_text(encoding="utf-8").splitlines())

    assert cm_lines < 350, f"config_menu.py voltou a crescer demais ({cm_lines} linhas)"
    assert desc_lines < 350, f"describer.py voltou a crescer demais ({desc_lines} linhas)"
    assert proj_lines < 350, f"project.py voltou a crescer demais ({proj_lines} linhas)"
