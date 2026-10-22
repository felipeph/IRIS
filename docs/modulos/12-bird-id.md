# Módulo 12: Identificação Taxonômica de Aves (`bird_id`)

O módulo de Identificação Taxonômica de Aves (`src.modules.bird_id`) é estruturado em **três etapas atômicas e sequenciais** no pipeline do IRIS, permitindo máxima transparência, auditoria intermediária e desacoplamento total entre detecção espacial, inferência taxonômica e manipulação de arquivos físicos.

---

## 1. Arquitetura Modular em Três Estágios Atômicos

```mermaid
flowchart TD
    subgraph E1["Estágio 1: Detecção Espacial (bird_detect / BirdDetectStage)"]
        Media["Mídias Elegíveis (Teleobjetivas >= 300mm ou Vídeos)"]
        YOLO["YOLOv8s (Detecção da Classe Bird)"]
        CropPhotos["Recorte Contextual com Margem (15%)"]
        CropVideos["Amostragem Adaptativa & Nitidez (Laplaciano)"]
        SaveRoot["Salva Recortes Exclusivamente na Raiz do IRIS:\n{destination_root}/10_Aves/Recortes/{project_name}/"]
        DB1["Persiste crop_path e crops_info no SQLite do Projeto"]
        
        Media --> YOLO
        YOLO --> CropPhotos & CropVideos
        CropPhotos & CropVideos --> SaveRoot
        SaveRoot --> DB1
    end

    subgraph E2["Estágio 2: Classificação Taxonômica (bird_id / BirdClassifyStage)"]
        ReadCrops["Lê Recortes em Disco (da Raiz do IRIS)"]
        Classifier["iNaturalist API v2 (Geomodel) / BioCLIP"]
        VideoVote["Votação Ponderada Acumulada em Vídeos"]
        DB2["Atualiza bird_identifications no SQLite"]
        CSV["Gera relatorio_aves.csv & Tabela Rich de Conferência"]
        
        DB1 --> ReadCrops
        ReadCrops --> Classifier
        Classifier --> VideoVote
        VideoVote --> DB2
        DB2 --> CSV
    end

    subgraph E3["Estágio 3: Organização Física (bird_organize / BirdOrganizeStage)"]
        CheckGate{"Confiança >= min_species_confidence?"}
        Rename["1. Renomeação Tripla:\n_[Nome_PT]_[Nome_Cientifico]_[Nome_EN]"]
        Subfolder["2. Movimentação para Subpasta:\n2_AlbunsDatas/YYYY/MM/DD/{Nome_PT}/"]
        EXIF["3. Injeção de Tags EXIF/IPTC via ExifTool"]
        DB3["4. Sincronização Atômica SQLite\n(organized_path e status final)"]
        
        CSV --> CheckGate
        CheckGate -->|Sim| Rename
        Rename --> Subfolder
        Subfolder --> EXIF
        EXIF --> DB3
        CheckGate -->|Não / Dúvida| Skip["Preserva Arquivo Físico Intacto\n(needs_review=True)"]
    end
```

---

## 2. Detalhamento dos Três Estágios

### 2.1. Estágio 1: `bird_detect` (`BirdDetectStage`)
- **Objetivo**: Detectar pássaros, extrair caixas delimitadoras e persistir recortes de alta qualidade.
- **Local dos Recortes**: Salvos **exclusivamente na raiz do IRIS** em `{destination_root}/{iris_crops_folder}/{project_name}/` (padrão: `10_Aves/Recortes/{project_name}/`). Nenhuma cópia duplicada é mantida na pasta interna de metadados do projeto.
- **Persistência no SQLite**:
  - Para cada mídia com detecção, cria um registro na tabela `bird_identifications` contendo o caminho absoluto do recorte (`crop_path`) e métricas do bounding box.
  - Para vídeos, armazena no campo `metadata_json` o dicionário `video_crops` com a lista de todos os recortes extraídos (índice do frame, timestamp, nitidez Laplaciana e caminho do recorte em disco).

### 2.2. Estágio 2: `bird_id` (`BirdClassifyStage`)
- **Objetivo**: Identificar a espécie taxonômica sem mover nem renomear nenhum arquivo físico.
- **Entrada**: Lê os recortes salvos na raiz do IRIS referenciados no banco SQLite ou no disco.
- **Motores Taxonômicos**:
  - **iNaturalist Computer Vision API v2**: Utiliza coordenadas GPS extraídas dos metadados da imagem/vídeo para condicionamento geográfico (*geomodel*), obtendo precisão em escala regional.
  - **BioCLIP (Zero-Shot)**: Fallback local robusto via embeddings textuais de catálogo regional (`br_mg_aves.csv`).
- **Vídeos**: Realiza votação ponderada acumulada entre os múltiplos frames extraídos pelo estágio 1.
- **Auditoria**: Atualiza os registros no SQLite com dados taxonômicos completos (`species_sci`, `species_pt`, `species_en`, `family`, `order`, `confidence`, `needs_review`) e gera o relatório `relatorio_aves.csv` no diretório do projeto.

### 2.3. Estágio 3: `bird_organize` (`BirdOrganizeStage`)
- **Objetivo**: Aplicar modificações estruturais no disco apenas para detecções que superem o limiar de confiança (`min_species_confidence`, padrão: 75%).
- **Ações Físicas**:
  1. **Renomeação Tripla**: Preserva todos os metadados técnicos de disparo e anexa os nomes populares e científicos higienizados:
     `..._[Bem-te-vi]_[Pitangus-sulphuratus]_[Great-Kiskadee]_IMG_1234.JPG`
  2. **Subpasta por Espécie**: Move a mídia para a subpasta com o nome em português dentro da sua categoria cronológica (`2_AlbunsDatas/YYYY/MM/DD/{Nome_PT}/` ou `3_Videos/.../{Nome_PT}/`).
  3. **Tags EXIF/IPTC**: Injeta tags taxonômicas (HierarchicalSubject, Keywords, Caption) sem recodificação de pixels via `exiftool`.
  4. **Sincronização SQLite**: Atualiza `items.organized_path` e o caminho correspondente em `bird_identifications` atomicamente.

---

## 3. Amostragem e Extração de Vídeos

- **Amostragem Adaptativa**: Extrai frames distribuídos de acordo com a duração do clipe.
- **Seleção por Nitidez**: Avalia o foco via Variância do Laplaciano ponderada pelo score do YOLO:
  $$S = \text{Var}(\nabla^2 I) \times \text{conf}_{\text{YOLO}} \times \sqrt{\text{Área}}$$
- **Limite Configurável (`video_max_crops`)**: Determina a quantidade máxima de melhores recortes salvos e enviados para classificação taxonômica (padrão: 5 recortes por vídeo).

---

## 4. Parâmetros de Configuração (`config.yaml`)

| Parâmetro | Tipo | Padrão | Descrição |
| :--- | :---: | :---: | :--- |
| `modules.bird_id.enabled` | bool | `true` | Habilita os estágios de identificação de aves. |
| `modules.bird_id.iris_crops_folder` | str | `10_Aves/Recortes` | Pasta de destino dos recortes na raiz do IRIS. |
| `modules.bird_id.video_max_crops` | int | `5` | Máximo de recortes mais nítidos extraídos por vídeo. |
| `modules.bird_id.video_target_frames` | int | `15` | Frames amostrados proporcionalmente à duração do clipe. |
| `modules.bird_id.min_species_confidence` | float | `0.75` | Limiar mínimo de confiança para organização e renomeação ($75\%$). |
| `modules.bird_id.rename_files` | bool | `true` | Habilita renomeação física no estágio de organização. |
| `modules.bird_id.organize_in_subfolders` | bool | `true` | Habilita separação em subpastas `{Nome_PT}/`. |
| `modules.bird_id.write_exif_tags` | bool | `true` | Injeta metadados IPTC/EXIF via ExifTool. |
| `modules.bird_id.zoom_threshold_mm` | float | `300.0` | Distância focal equivalente mínima para teleobjetivas. |
| `modules.bird_id.yolo_model` | str | `yolov8s.pt` | Modelo YOLOv8 utilizado (`yolov8s.pt`, etc.). |
| `modules.bird_id.yolo_confidence` | float | `0.25` | Limiar mínimo de confiança do detector YOLO. |

Todos os parâmetros podem ser ajustados interativamente através da opção `8. 🦜 Identificação de Aves` no menu global de configurações (`python iris/main.py -> C`).

---

## 5. Auditoria e Relatórios

- **`relatorio_aves.csv`**: Gerado na pasta do projeto ao final da classificação, contendo caminho original, nomes taxonômicos, métricas de confiança, caminho do recorte e status de revisão.
- **Tabela Rich Interativa**: Resumo no terminal colorido destacando espécies com alta certeza em verde e casos pendentes de revisão em amarelo/vermelho.
- **Rastreabilidade no SQLite**: Todas as mídias mantêm vínculo direto com a localização exata do recorte armazenado em disco na raiz do IRIS.
