# IA & Engenharia: Guia & Contexto para Agentes de IA

Este documento foi projetado para que **Agentes Autônomos de Inteligência Artificial** e desenvolvedores compreendam rapidamente a arquitetura modular, as invariantes lógicas e o mapa de código do **IRIS (Imaging Resources and Integration System)**.

---

## 1. O Domínio e as Invariantes do Sistema

1. **Ator Único:** O sistema foi construído para uso pessoal de Felipe Heitmann. Não há necessidade de suporte multi-usuário (multitenancy) nem tabelas de permissões RBAC.
2. **Invariante Zero Data Loss:** Nunca adicione comandos de deleção direta de arquivos (`os.remove`, `shutil.rmtree`) sem:
   - Uma verificação formal de status `verified == 1` na tabela SQLite correspondente.
   - Usar prioritariamente o envio para a lixeira via `send2trash` (respeitando `allow_permanent_sd_clean` para cartões SD removíveis).
   - **Arquivos RAW e Vídeos originais NUNCA são regravados fisicamente pelo ExifTool** (coordenadas e metadados entram no nome via token `{gps}` e no banco SQLite).
3. **Invariante de Isolamento de Projeto:** Todo `PipelineStage` deve manipular estritamente os arquivos vinculados à instância de `Project` recebida no método `run(project)`. Nunca escreva código que faça varreduras globais em `destination_root` como fallback para encontrar trabalho.
4. **Persistência Relacional Dual-DB (`CURRENT_SCHEMA_VERSION = 2`):** O estado reside em `~/.iris/projects/iris_central.db` e `~/.iris/projects/<projeto>.db` em modo WAL, sincronizados via *Dual-Write* (`ATTACH DATABASE ... AS central`).

---

## 2. Mapa Conceitual do Código-Fonte

```text
iris/
├── main.py                      # Ponto de entrada interativo da CLI (Rich) e atalhos [B], [G], [L], [C]
├── config.yaml                  # Configuração declarativa ativa
├── config.example.yaml          # Template de referência sincronizado (validado por teste de contrato)
├── src/
│   ├── core/                    # Infraestrutura e Serviços Centrais
│   │   ├── config.py            # ConfigManager (parse, persistência, auto-migração e auto-cura UTF-8)
│   │   ├── config_menu.py       # Hub principal do menu de configurações (fachada retrocompatível)
│   │   ├── config_menus/        # Submenus modulares por domínio:
│   │   │   ├── storage_org.py   # Armazenamento, Ingestão, Organização, Classificação e Rajadas
│   │   │   ├── timelapse.py     # Timelapse Normal e Timelapse Longa Exposição
│   │   │   ├── video_youtube.py # Edição de Vídeo 4K e YouTube & Notificações
│   │   │   ├── astro.py         # Astrofotografia Lunar (PSS e Wavelets)
│   │   │   ├── bird_id.py       # Identificação Taxonômica de Aves (YOLOv8 + iNaturalist)
│   │   │   └── geolocation.py   # CRUD de Locais Predefinidos e Geotags
│   │   ├── project.py           # Project, ProjectItem e conexões SQLite (fachada retrocompatível)
│   │   ├── project_mixins/      # Decomposição modular da persistência SQLite (RFC 09):
│   │   │   ├── schema.py        # CURRENT_SCHEMA_VERSION e SHARED_TABLES_DDL
│   │   │   ├── base.py          # ProjectBase, transações SAVEPOINT e Dual-Write ATTACH
│   │   │   ├── items.py         # Queries O(1), filtros parametrizados e batch upsert em `items`
│   │   │   ├── media.py         # Persistência de `timelapses` e `edited_videos`
│   │   │   ├── astro.py         # Persistência de `astro_stacks` e `astro_sharpens`
│   │   │   ├── birds.py         # Persistência de `bird_identifications`
│   │   │   └── central_db.py    # Consultas globais em `iris_central.db` e reconciliação
│   │   ├── geo.py               # GeoService, GeoLocation, Reverse Geocoding (Nominatim/BigDataCloud)
│   │   ├── pipeline.py          # PipelineRunner e classe abstrata PipelineStage
│   │   ├── lock.py              # ProjectLock atômico via kernel (O_CREAT | O_EXCL) com TTL
│   │   ├── cleanup.py           # Poda ascendente de diretórios vazios e descarte de Thumbs.db
│   │   ├── metadata.py          # Extrator EXIF/ffprobe e normalização óptica
│   │   ├── classifier.py        # MediaClassifier (normal, longa exposição, rajadas, lua)
│   │   ├── namer.py             # MediaNamer (formatação semântica com {gps} e taxonomia)
│   │   ├── ui.py                # Painéis verticais Rich Live e ProgressTracker
│   │   └── logger.py            # Logger centralizado com rotação por projeto
│   └── modules/                 # Implementações dos 14 Estágios do Pipeline
│       ├── ingestion/           # Etapa 1: Ingestão (MoveStrategy 5 fases e CopyStrategy)
│       ├── cleanup/             # Etapa 2: Limpeza Hash-Guarded da origem (Send2Trash)
│       ├── planning/            # Etapa 3: Planejamento, metadados, burst_id e categorias
│       ├── organize/            # Etapa 4: Movimentação física, deduplicação xxHash64 e amostras
│       ├── sanitization/        # Etapa 5: Sanitização EXIF e Geotag UTF-8 (via argfile ExifTool)
│       ├── bird_id/             # Pipeline Ornitológico (Etapas 6 a 9 + Correção Manual [B]):
│       │   ├── detect_stage.py  # Etapa 6 (`bird_detect`): Detecção YOLOv8s e recortes em 10_Aves/
│       │   ├── classify_stage.py# Etapa 7 (`bird_id`): Classificação iNaturalist/BioCLIP + Burst Early Exit
│       │   ├── organize_stage.py# Etapa 8 (`bird_organize`): Subpastas por espécie e renomeação
│       │   ├── tag_stage.py     # Etapa 9 (`bird_tag`): Injeção EXIF/IPTC/XMP UTF-8
│       │   ├── correction.py    # Atalho [B]: Fluxo interativo de revisão/correção manual em lote
│       │   └── catalog.py       # Catálogo global `species_catalog` e curadoria regional MG
│       ├── astro_stack/         # Etapa 10: Pré-processamento RAW e PSS Stacking Headless
│       ├── astro_sharpen/       # Etapa 11: Wavelets À Trous e presets RegiStax
│       ├── astro/               # CLI autônoma `iris-astro` e motor matemático `LunarWaveletEngine`
│       ├── timelapse/           # Etapa 12: Renderização 4K (Normal e Longa Exposição)
│       ├── video_edit/          # Etapa 13: Upscale 4K, trimming, speed e Auto-Join por Ave/Dia
│       └── youtube/             # Etapa 14: Upload 64MB, playlists dinâmicas e `describers/` modulares:
│           ├── stage.py         # Orquestração de upload e limpeza pós-verificação
│           ├── uploader.py      # Cliente OAuth 2.0 YouTube Data API v3
│           ├── describer.py     # Fachada retrocompatível de metadados do YouTube
│           └── describers/      # Módulos de formatação (`formatting`, `geo`, `birds`, `timelapse`, `video_edit`)
├── vendor/                      # PlanetarySystemStacker isolado (GPL-3 via subprocesso)
├── secrets/                     # Credenciais locais (YouTube OAuth e iNaturalist JWT)
└── tests/                       # Bateria de 380+ testes automatizados em pytest
```

---

## 3. Diretrizes de Codificação para Agentes

1. **Consulte a Matriz Mestre:** Antes de alterar o fluxo entre etapas, consulte [pipeline-lifecycle.md](../referencia/pipeline-lifecycle.md) e [schema-banco-de-dados.md](../referencia/schema-banco-de-dados.md).
2. **Modularidade sem Quebra de Fachada:** Ao adicionar novos submenus de configuração ou regras de descrição do YouTube, edite os submódulos em `src/core/config_menus/` ou `src/modules/youtube/describers/`, mantendo as re-exportações em `config_menu.py`, `describer.py` e `project.py`.
3. **ExifTool no Windows sempre com Argfile UTF-8:** Qualquer invocação ao ExifTool com caminhos acentuados ou tags IPTC/XMP deve usar arquivo temporário UTF-8 (`-charset UTF8 -@ argfile`) para evitar corrupção CP1252.
4. **Contrato Arquitetural e Testes:** Sempre valide suas alterações executando:
   ```bash
   python -m pytest iris/tests
   ```
   O arquivo `test_architecture_contracts.py` verifica automaticamente o alinhamento entre `config.example.yaml`, os módulos do pipeline e as fachadas públicas.
