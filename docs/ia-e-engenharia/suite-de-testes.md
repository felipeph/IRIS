# IA & Engenharia: Suíte de Testes Automatizados (`pytest`)

O IRIS conta com uma bateria de **mais de 380 testes automatizados** baseados em `pytest`, cobrindo desde regras atômicas de formatação e contratos arquiteturais até simulações multiprocesso de concorrência, visão computacional e mocks de hardware/APIs.

---

## 1. Principais Grupos de Teste (`iris/tests/`)

| Arquivo de Teste | Foco Principal |
| :--- | :--- |
| `test_architecture_contracts.py` | **Contrato Arquitetural**: garante ausência de chaves duplicadas no YAML, sincronia entre `config.example.yaml` e os 14 estágios do pipeline, e integridade das fachadas (`config_menu`, `describer`, `project`). |
| `test_bird_id.py`, `test_bird_correction.py`, `test_inaturalist_client.py`, `test_reporter.py` | Pipeline de Aves em 4 estágios (YOLOv8s + iNaturalist API v2 / BioCLIP), consenso e *early exit* em rajadas, catálogo global `species_catalog` e fluxo de revisão/correção manual (`[B]`). |
| `test_geo.py`, `test_sanitization_geo.py`, `test_exiftool_utf8.py` | `GeoService`, geocodificação reversa (Nominatim/BigDataCloud), token `{gps}`, injeção EXIF/IPTC/XMP via *argfile* UTF-8 e preservação intocada de RAWs/vídeos. |
| `test_astro_stack.py`, `test_astro_wavelets.py` | Pré-processador de RAWs, isolamento de ambiente `.venv_astro`, subprocesso PSS headless, motor `LunarWaveletEngine` À Trous, Limb Guard e presets RegiStax. |
| `test_classifier.py`, `test_namer.py`, `test_organize_stage.py` | Heurísticas de timelapses (normal, sub-segundo e longa exposição), detecção de rajadas (`burst_id`), deduplicação por hash e amostragem para álbuns. |
| `test_ingestion_stage.py`, `test_cleanup_stage.py`, `test_cleanup_empty_dirs.py` | `MoveStrategy` (5 fases) e `CopyStrategy`, limpeza Hash-Guarded de SD Card e poda contínua de diretórios vazios. |
| `test_project.py`, `test_project_transactions.py`, `test_concurrency.py` | Dual-Database SQLite em modo WAL, transações aninhadas com `SAVEPOINT`, `ProjectLock` atômico (`O_CREAT | O_EXCL`) e reconciliação central. |
| `test_timelapse_and_youtube.py`, `test_video_edit.py`, `test_youtube_birds.py`, `test_youtube_cleanup.py` | Renderização 4K Lanczos/Deband, Auto-Join de vídeos de aves por espécie e dia, Resumable Upload em chunks de 64MB, descrições/títulos modulares e limpeza pós-upload. |
| `test_config_menu.py`, `test_pipeline.py`, `test_ui.py` | Navegação nos 9 submenus de configuração, auto-migração de schemas legados no `ConfigManager`, `PipelineRunner` e painéis verticais Rich. |

---

## 2. Como Executar os Testes

Para executar toda a suíte completa no terminal:

```bash
python -m pytest iris/tests
```

Para validar rapidamente os contratos arquiteturais e menus:

```bash
python -m pytest iris/tests/test_architecture_contracts.py iris/tests/test_config_menu.py -v
```

---

## 3. Isolamento Hermético (`conftest.py`)

A fixture global autouse em [conftest.py](file:///c:/code/IRIS/iris/tests/conftest.py) redireciona automaticamente `CENTRAL_DB_PATH`, `PROJECTS_DIR` e `general.destination_root` para diretórios temporários (`tmp_path`) em todos os testes, garantindo **zero poluição** no banco central de produção ou na pasta `C:\IRIS`.
