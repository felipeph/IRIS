# Manifesto LLM (`llms.txt`)

Este arquivo segue a especificação padronizada **`llms.txt`**, oferecendo um resumo condensado e atualizado para que modelos de linguagem (LLMs) e agentes de IA compreendam todo o projeto **IRIS** em uma única leitura.

---

```text
# IRIS — Imaging Resources and Integration System
> Central de Engenharia e Automação de Mídia para Fotografia, Ornitologia por IA, Vídeo 4K, Astrofotografia Lunar e YouTube.
> Repositório: https://github.com/felipeph/IRIS
> Documentação: https://felipeph.github.io/IRIS/

## Resumo Executivo
O IRIS é uma plataforma CLI em Python que orquestra de ponta a ponta fluxos audiovisuais de natureza e astrofotografia: ingestão segura, organização por categorias e rajadas, geolocalização reversa, identificação taxonômica de aves (YOLOv8s + iNaturalist API v2 + catálogo global), empilhamento e wavelets lunares, renderização de timelapses e vídeos 4K (com auto-join por ave/dia) e publicação no YouTube.

## Invariantes e Princípios de Arquitetura
- Zero Data Loss: Nenhum arquivo original é removido sem hash xxHash64 verificado no SSD e envio prioritário para a Lixeira (Send2Trash). Arquivos RAW e vídeos originais nunca são regravados pelo ExifTool.
- Dual-Database SQLite com WAL Mode (Schema v2): `iris_central.db` (projetos, `species_catalog` e tabelas espelhadas) e `<projeto>.db` (tabela `items` + Dual-Write via ATTACH DATABASE e transações SAVEPOINT).
- Arquitetura Modular com Fachadas Retrocompatíveis:
  - `src/core/config_menu.py` + `src/core/config_menus/*` (9 submenus temáticos).
  - `src/core/project.py` + `src/core/project_mixins/*` (`schema`, `base`, `items`, `media`, `astro`, `birds`, `central_db`).
  - `src/modules/youtube/describer.py` + `src/modules/youtube/describers/*` (`formatting`, `geo`, `birds`, `timelapse`, `video_edit`).
- Concorrência Segura: `ProjectLock` atômico via `os.O_CREAT | os.O_EXCL` com PID e TTL.

## As 14 Etapas do Pipeline (`pipeline.stages`)
1. `ingestion` (`src.modules.ingestion.stage`): MoveStrategy (5 fases multithreaded) ou CopyStrategy com xxHash64 -> `1_Entrada/<projeto>/`.
2. `cleanup` (`src.modules.cleanup.stage`): Limpeza Hash-Guarded da origem após `verified == 1`.
3. `planning` (`src.modules.planning.stage`): Extração EXIF/ffprobe, detecção de rajadas (`burst_id`), perfis de timelapse (normal e longa exposição) e geolocalização (`GeoService`).
4. `organize` (`src.modules.organize.stage`): Movimentação para `2_AlbunsDatas/`, `3_Videos/`, `4_Timelapses/`, `4_Timelapses_LongaExposicao/`, `5_Lua/` com deduplicação xxHash64 e amostras de timelapse.
5. `sanitization` (`src.modules.sanitization.stage`): Sanitização EXIF e injeção de Geotag/IPTC/XMP via argfile UTF-8 exclusivamente nas fotos de `2_AlbunsDatas/`.
6. `bird_detect` (`src.modules.bird_id.detect_stage`): Detecção espacial YOLOv8s em fotos/vídeos e salvamento dos melhores recortes por nitidez Laplaciana em `10_Aves/Recortes/<projeto>/`.
7. `bird_id` (`src.modules.bird_id.classify_stage`): Classificação via iNaturalist Computer Vision API v2 (ou BioCLIP) com prior geográfico, consenso de rajada e early exit -> `bird_identifications` e `species_catalog`.
8. `bird_organize` (`src.modules.bird_id.organize_stage`): Renomeação taxonômica (`_{Nome_PT}_{Nome_Cientifico}`) e organização em subpastas por espécie.
9. `bird_tag` (`src.modules.bird_id.tag_stage`): Injeção de tags taxonômicas EXIF/IPTC/XMP UTF-8 via ExifTool.
   * Atalho Interativo `[B]` (`src.modules.bird_id.correction`): Revisão manual de espécies, busca no catálogo global, propagação em lote para rajadas/sessões e atualização física/EXIF.
10. `astro_stack` (`src.modules.astro_stack.stage`): Pré-processamento RAW e empilhamento lunar headless via PlanetarySystemStacker (`.venv_astro`) -> `8_Astro_Stack/`.
11. `astro_sharpen` (`src.modules.astro_sharpen.stage`): Motor `LunarWaveletEngine` À Trous B3-spline com Limb Guard, CLAHE 16-bit e presets RegiStax -> `9_Astro_Sharpening/`.
12. `timelapse` (`src.modules.timelapse.stage`): Renderização 4K UHD (normal 60fps e longa exposição 30fps) com Lanczos e Deband 16-bit -> `6_Produzidos/`.
13. `video_edit` (`src.modules.video_edit.stage`): Masterização e upscale 4K UHD de vídeos com trimming, speed e Auto-Join automático por espécie de ave e data -> `7_Video_Editado_4K/`.
14. `youtube` (`src.modules.youtube.stage`): Upload resumable em chunks de 64MB na YouTube Data API v3, títulos/descrições ornitológicas e geográficas, roteamento multi-playlist e limpeza local pós-verificação.

## Suíte de Testes
- Framework: `pytest` (380+ testes automatizados, incluindo `test_architecture_contracts.py`).
- Execução: `python -m pytest iris/tests`
```
