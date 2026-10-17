# Referência Técnica: Dicionário de Dados do Banco SQLite

O IRIS implementa persistência relacional com garantia ACID através de dois níveis de bancos de dados SQLite: o **Banco Central (`iris_central.db`)** e o **Banco do Projeto (`<projeto>.db`)**.

---

## 1. Tabelas do Banco Central (`iris_central.db`)

Localizado em `~/.iris/iris_central.db`.

### Tabela `projects`
Armazena o registro de todas as sessões de trabalho criadas no computador.

| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | PRIMARY KEY AUTOINCREMENT | Identificador numérico da sessão |
| `name` | `TEXT` | UNIQUE NOT NULL | Nome do projeto (ex.: `2026-10-14_Sessao_Passaros`) |
| `source_path` | `TEXT` | NOT NULL | Caminho da pasta de origem original (cartão SD) |
| `dest_path` | `TEXT` | NOT NULL | Caminho da pasta de *staging* do projeto no SSD |
| `current_stage_id`| `TEXT` | | Identificador da última etapa executada (ex: `organize`) |
| `status` | `TEXT` | DEFAULT 'in_progress' | Estado geral (`in_progress`, `completed`, `error`) |
| `total_files` | `INTEGER` | DEFAULT 0 | Quantidade total de arquivos catalogados no projeto |
| `total_bytes` | `INTEGER` | DEFAULT 0 | Volume total de dados do projeto em bytes |
| `created_at` | `TIMESTAMP`| DEFAULT CURRENT_TIMESTAMP | Data e hora de criação da sessão |
| `updated_at` | `TIMESTAMP`| DEFAULT CURRENT_TIMESTAMP | Data e hora da última modificação de estado |

---

## 2. Tabelas do Banco de Projeto (`<projeto>.db`)

Localizado na raiz do projeto em `1_Entrada/<projeto>/<projeto>.db`.

### Tabela `files`
Rastreia individualmente cada foto ou vídeo ingerido da origem.

| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | PRIMARY KEY AUTOINCREMENT | ID interno do arquivo |
| `original_path` | `TEXT` | NOT NULL | Caminho do arquivo original na mídia de origem |
| `staging_path` | `TEXT` | | Caminho do arquivo na pasta de staging temporária |
| `final_path` | `TEXT` | | Caminho do arquivo após a organização física |
| `size_bytes` | `INTEGER` | NOT NULL | Tamanho do arquivo em bytes |
| `xxhash64` | `TEXT` | NOT NULL | Hash hexadecimal xxHash64 de integridade |
| `verified` | `INTEGER` | DEFAULT 0 | Flag booleana (`1` = íntegro / `0` = pendente ou falho) |
| `category` | `TEXT` | DEFAULT 'unknown' | Categoria (`photo`, `video`, `timelapse`, `astro`) |
| `camera_model` | `TEXT` | | Identificador canônico da câmera detectada |
| `capture_date` | `TEXT` | | Timestamp ISO da captura extraído do EXIF |
| `width` | `INTEGER` | | Largura da imagem em pixels |
| `height` | `INTEGER` | | Altura da imagem em pixels |
| `focal_length` | `REAL` | | Distância focal equivalente em milímetros |
| `exposure` | `TEXT` | | Informações combinadas de exposição (abertura, shutter, ISO) |
| `status` | `TEXT` | DEFAULT 'ingested' | Estado (`ingested`, `sanitized`, `organized`) |
| `created_at` | `TIMESTAMP`| DEFAULT CURRENT_TIMESTAMP | Timestamp de auditoria |

### Tabela `timelapses`
Rastreia as sequências de timelapse renderizadas em 4K.

| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | PRIMARY KEY AUTOINCREMENT | ID do timelapse |
| `project_name` | `TEXT` | | Nome do projeto associado |
| `video_path` | `TEXT` | UNIQUE | Caminho do arquivo de vídeo MP4 gerado |
| `photo_count` | `INTEGER` | | Quantidade de fotos utilizadas na sequência |
| `frames_per_image`| `INTEGER` | | Multiplicador de quadros por foto |
| `resolution` | `TEXT` | DEFAULT '3840x2160' | Resolução do vídeo master |
| `crop_mode` | `TEXT` | | Modo de enquadramento (`bottom`, `center`, `top`, `full`) |
| `encoder` | `TEXT` | | Encoder FFmpeg utilizado (`h264_nvenc`, etc.) |
| `duration_seconds`| `REAL` | | Duração total do vídeo em segundos |
| `speedup_factor` | `INTEGER` | | Fator de aceleração em relação ao tempo real |
| `youtube_video_id`| `TEXT` | | ID do vídeo retornado pela YouTube Data API v3 |
| `youtube_url` | `TEXT` | | URL pública/unlisted de visualização no YouTube |
| `youtube_privacy` | `TEXT` | | Estado de privacidade (`public`, `unlisted`, `private`) |
| `status` | `TEXT` | DEFAULT 'rendered' | Estado (`rendered`, `uploaded`) |
| `metadata_json` | `TEXT` | DEFAULT '{}' | Telemetria detalhada em JSON |
| `local_file_deleted`| `INTEGER` | DEFAULT 0 | Flag indicando se a cópia local foi apagada pós-upload |

### Tabela `edited_videos`
Rastreia clipes comuns masterizados, estabilizados e upscalados para 4K UHD.

| Coluna | Tipo | Restrições | Descrição |
| :--- | :--- | :--- | :--- |
| `id` | `INTEGER` | PRIMARY KEY AUTOINCREMENT | ID do vídeo editado |
| `project_name` | `TEXT` | | Nome do projeto associado |
| `source_video_paths`| `TEXT` | | Lista de arquivos de vídeo originais processados |
| `output_video_path` | `TEXT` | UNIQUE | Caminho do vídeo master MP4 final |
| `mode` | `TEXT` | | Modo de operação (`individual` ou `session`) |
| `clip_count` | `INTEGER` | DEFAULT 1 | Quantidade de clipes unidos |
| `speed_factor` | `REAL` | DEFAULT 1.0 | Fator de velocidade aplicado (`Nx`) |
| `target_fps` | `REAL` | DEFAULT 60.0 | Taxa de quadros de saída |
| `target_resolution`| `TEXT` | DEFAULT '3840x2160' | Resolução de saída em 4K UHD |
| `trim_start_sec` | `REAL` | DEFAULT 2.0 | Segundos removidos no início |
| `trim_end_sec` | `REAL` | DEFAULT 2.0 | Segundos removidos no fim |
| `audio_stripped` | `INTEGER` | DEFAULT 0 | Flag indicando se o áudio foi silenciado (`-an`) |
| `duration_seconds`| `REAL` | | Duração final do clipe master |
| `youtube_video_id`| `TEXT` | | ID retornado pelo YouTube pós-upload |
| `local_file_deleted`| `INTEGER` | DEFAULT 0 | Flag indicando se o arquivo local foi enviado para a lixeira |

### Tabelas `astro_stacks` e `astro_sharpens`
Armazenam o histórico de empilhamento de astrofotografia lunar (diretório de entrada de RAWs, descarte percentual, caminhos dos TIFFs de 16-bit e presets de wavelets aplicados).
