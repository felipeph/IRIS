# Referência Técnica: Dicionário de Dados do Banco SQLite

O IRIS implementa persistência relacional ACID com **Dual-Database SQLite em modo WAL** (`PRAGMA journal_mode = WAL; PRAGMA user_version = 2;`):

1. **Banco Central (`~/.iris/projects/iris_central.db`)**: Catálogo global de projetos, catálogo taxonômico de espécies (`species_catalog`) e espelho consolidado de todos os artefatos produzidos (`timelapses`, `edited_videos`, `astro_stacks`, `astro_sharpens`, `bird_identifications`).
2. **Banco do Projeto (`~/.iris/projects/<projeto>.db`)**: Isola a tabela `items` (milhares de fotos/vídeos por lote) e recebe gravações simultâneas (*Dual-Write* via `ATTACH DATABASE ... AS central`) nas tabelas compartilhadas.

---

## 1. Tabelas Exclusivas do Banco Central (`iris_central.db`)

### 1.1. Tabela `projects`
Registra todas as sessões de trabalho criadas no IRIS.

| Coluna | Tipo | Restrições / Default | Descrição |
| :--- | :--- | :--- | :--- |
| `name` | `TEXT` | `PRIMARY KEY` | Nome único do projeto (ex.: `2026-10-24_15-30_DCIM`) |
| `source_path` | `TEXT` | | Caminho da pasta de origem original (ex.: cartão SD `G:\DCIM`) |
| `current_stage_id` | `TEXT` | | ID da última etapa concluída no pipeline (ex.: `organize`, `youtube`) |
| `total_source_files` | `INTEGER` | | Total de arquivos de mídia mapeados na origem |
| `total_source_size_bytes`| `INTEGER` | | Volume total em bytes mapeado na origem |
| `auto_cleanup` | `INTEGER` | `DEFAULT 0` | Flag booleana (`1` = limpeza automática da origem ativada) |
| `geo_location_id` | `TEXT` | `DEFAULT ''` | ID do local predefinido no `GeoService` (ex.: `formiga-sao-luiz`) |
| `created_at` | `TIMESTAMP`| `DEFAULT now` | Timestamp de criação do projeto |
| `updated_at` | `TIMESTAMP`| `DEFAULT now` | Timestamp da última modificação |

### 1.2. Tabela `species_catalog`
Catálogo taxonômico global de aves (pré-populado com a curadoria regional de MG `br_mg_aves.csv` e enriquecido automaticamente a cada identificação/correção).

| Coluna | Tipo | Restrições / Default | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | `PRIMARY KEY AUTOINCREMENT` | ID interno da espécie |
| `species_common` | `TEXT` | `NOT NULL` | Nome popular em português (ex.: `Bem-te-vi`) |
| `species_scientific` | `TEXT` | `NOT NULL UNIQUE` | Nome científico canônico (ex.: `Pitangus sulphuratus`) |
| `species_common_en` | `TEXT` | `DEFAULT ''` | Nome popular em inglês (ex.: `Great Kiskadee`) |
| `family` | `TEXT` | `DEFAULT ''` | Família taxonômica (ex.: `Tyrannidae`) |
| `order_name` | `TEXT` | `DEFAULT ''` | Ordem taxonômica (ex.: `Passeriformes`) |
| `use_count` | `INTEGER` | `DEFAULT 1` | Contador de frequência para ordenação inteligente na busca |
| `source` | `TEXT` | `DEFAULT 'historical'` | Origem do registro (`curated_mg`, `historical`, `inaturalist`, `manual`) |
| `created_at` | `TIMESTAMP`| `DEFAULT CURRENT_TIMESTAMP` | Data de inclusão |
| `updated_at` | `TIMESTAMP`| `DEFAULT CURRENT_TIMESTAMP` | Última atualização |

---

## 2. Tabela Exclusiva do Banco do Projeto (`<projeto>.db`)

### 2.1. Tabela `items` (Espelho da dataclass `ProjectItem`)
Rastreia individualmente cada foto, RAW ou vídeo ingerido no lote. Possui índices otimizados para `original_path` (UNIQUE), `status`, `category`, `(status, verified)` e `burst_id`.

| Grupo | Coluna | Tipo | Descrição |
| :--- | :--- | :--- | :--- |
| **Ingestão & Integridade** | `original_path` | `TEXT UNIQUE` | Caminho original do arquivo no cartão SD/HD |
| | `staging_path` | `TEXT` | Caminho temporário na pasta `1_Entrada/<projeto>/` |
| | `status` | `TEXT` | Estado do item (`pending`, `copied`, `planned`, `organized`, `error`) |
| | `file_size_bytes` | `INTEGER` | Tamanho do arquivo em bytes (atualizado pós-sanitização) |
| | `file_hash` | `TEXT` | Hash hexadecimal `xxHash64` de integridade |
| | `verified` | `INTEGER` | `1` se o hash no SSD foi matematicamente comprovado contra a origem |
| **Metadados Ópticos & Vídeo** | `meta_is_video` / `meta_is_raw` | `INTEGER` | Flags booleanas indicando se é vídeo ou arquivo RAW |
| | `meta_date_str` / `meta_time_str` | `TEXT` | Data (`YYYY-MM-DD`) e hora (`HH-MM-SS`) da captura |
| | `meta_timestamp` | `TEXT` | Timestamp ISO de captura com sub-segundos |
| | `meta_camera_make` / `meta_camera_model`| `TEXT` | Fabricante e modelo normalizado da câmera |
| | `meta_focal_length_equiv` / `meta_focal_str`| `REAL` / `TEXT`| Distância focal equivalente em 35mm (usada para filtro Lunar e Aves) |
| | `meta_aperture_str` / `meta_shutter_str` / `meta_iso_str` | `TEXT` | Abertura (`f4.0`), obturador (`1-500s`) e sensibilidade (`ISO100`) |
| | `meta_resolution_str` / `meta_width` / `meta_height` | `TEXT` / `INT` | Classificação (`16MP`, `4K`) e dimensões em pixels (`4000x3000`) |
| | `meta_fps_str` / `meta_duration_str` | `TEXT` | Taxa de quadros (`60fps`) e duração (`15s`) para vídeos |
| | `meta_original_stem` / `meta_extension` | `TEXT` | Nome original sem extensão e extensão padronizada |
| **Geolocalização** | `meta_latitude` / `meta_longitude` / `meta_gps_accuracy` | `REAL` | Coordenadas GPS (nativas do EXIF ou atribuídas pelo projeto) |
| | `geo_source` / `geo_written` | `TEXT` / `INT` | Fonte do GPS (`exif`, `project`) e flag `1` se injetado via ExifTool |
| **Organização & Rajadas** | `category` | `TEXT` | Categoria (`fotos_avulsas`, `videos`, `timelapse`, `timelapse_long_exposure`, `lua`) |
| | `burst_id` | `TEXT` | Identificador de rajada contínua (`rajada_YYYY-MM-DD_HH-MM-SS` ou vazio) |
| | `target_filename` | `TEXT` | Nome semântico planejado (com `{gps}` e taxonomia de ave se aplicável) |
| | `relative_dest_dir` / `organized_path` | `TEXT` | Subdiretório relativo e caminho absoluto final em `C:\IRIS` |
| | `extra_dest_dirs_json` / `extra_organized_paths_json` | `TEXT` | Caminhos extras em JSON (ex.: cópias de amostra de timelapse para `2_AlbunsDatas`) |

---

## 3. Tabelas Compartilhadas (`SHARED_TABLES_DDL` — Local + Central)

Definidas em [schema.py](file:///c:/code/IRIS/iris/src/core/project_mixins/schema.py), estas tabelas existem tanto em `<projeto>.db` quanto em `iris_central.db` e são sincronizadas via *Dual-Write* (`_execute_dual_write`) e auto-reconciliação (`reconcile_project_with_central`):

### 3.1. Tabela `bird_identifications`
Armazena as detecções YOLOv8s e classificações taxonômicas (iNaturalist API v2 / BioCLIP / Correção Manual).
- **Chave única**: `UNIQUE(project_name, item_path)`
- **Colunas principais**: `project_name`, `item_path`, `is_video`, `species_common`, `species_scientific`, `confidence`, `top2_common`, `top2_scientific`, `top2_confidence`, `top3_common`, `top3_scientific`, `top3_confidence`, `needs_review` (`1` quando abaixo do limiar de confiança), `crop_saved_path` (caminho em `10_Aves/Recortes/`), `metadata_json` (inclui `species_common_en`, `family`, `order`, `taxon_id`, `burst_consensus`, `burst_early_exit`, `video_crops`, `manual_correction`).

### 3.2. Tabela `timelapses`
Rastreia sequências renderizadas em 4K UHD (normais e longa exposição).
- **Chave única**: `output_video_path UNIQUE`
- **Colunas principais**: `project_name`, `sequence_dir`, `output_video_path`, `photo_count`, `fps`, `frames_per_image`, `resolution`, `crop_mode`, `encoder`, `duration_seconds`, `speedup_factor`, `youtube_video_id`, `youtube_url`, `youtube_privacy`, `status` (`rendered`, `uploaded`), `metadata_json`, `local_file_deleted`.

### 3.3. Tabela `edited_videos`
Rastreia vídeos 4K masterizados (modo `individual` ou `joined`, incluindo concatenação automática por espécie de ave e dia).
- **Chave única**: `output_video_path UNIQUE`
- **Colunas principais**: `project_name`, `source_video_paths` (JSON array), `output_video_path`, `mode`, `clip_count`, `speed_factor`, `orig_fps`, `target_fps`, `orig_resolution`, `target_resolution`, `trim_start_sec`, `trim_end_sec`, `audio_stripped`, `duration_seconds`, `encoder`, `youtube_video_id`, `youtube_url`, `youtube_privacy`, `status`, `metadata_json`, `local_file_deleted`.

### 3.4. Tabelas `astro_stacks` e `astro_sharpens`
Rastreiam sessões de empilhamento lunar via PlanetarySystemStacker (`astro_stacks`, único por `(project_name, session_dir)`) e resultados do motor de wavelets À Trous (`astro_sharpens`, único por `output_tiff_path`).
