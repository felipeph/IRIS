# Arquitetura & Engenharia: Taxonomia & Nomenclatura Semântica

A organização caótica de arquivos em pastas genéricas (como `DCIM/100CANON` ou `Nova Pasta (2)`) é um dos maiores obstáculos para a localização e catalogação de acervos fotográficos.

O IRIS implementa um sistema determinístico baseado em **7 Categorias Físicas Rígidas** e uma **Gramática de Nomenclatura Rica em Metadados**.

---

## 1. As Sete Categorias de Destino

No diretório raiz configurado (`destination_root`, ex.: `C:\IRIS\`), os arquivos são organizados em diretórios numéricos padronizados:

```text
C:\IRIS\
├── 1_Entrada/                   # Staging Area: Mídias recém-ingeridas antes da classificação
│   └── <nome_do_projeto>/       # Subpasta com banco SQLite local e arquivos originais brutos
├── 2_AlbunsDatas/               # Acervo Cronológico de Fotografias Individuais
│   └── YYYY/MM/DD/              # Particionamento por Ano, Mês e Dia
├── 3_Videos/                    # Vídeos Comuns Originais de Câmera
│   └── YYYY/MM/DD/              # Particionamento cronológico
├── 4_Timelapses/                # Sequências Fotográficas de Timelapse
│   └── <Camera>/YYYY/MM/DD/     # Agrupadas em subpastas cronológicas intactas
├── 5_Astrofotografia/           # Mídias com Zoom Extremo (>=1000mm) e RAWs da Lua
│   └── Lua/YYYY/MM/DD/          # Isolamento para o pipeline de empilhamento astronômico
├── 6_Produzidos/                # Vídeos Renderizados Finais de Timelapses (4K UHD)
│   └── YYYY/MM/DD/              # Arquivos master gerados prontos para publicação
└── 7_Video_Editado_4K/          # Vídeos Comuns Masterizados, Estabilizados e com Upscale 4K
    └── YYYY/MM/DD/              # Clipes tratados com alta fidelidade para YouTube
```

---

## 2. Gramática de Nomenclatura Rica em Metadados

O IRIS rejeita nomes opacos atribuídos pelas câmeras (`IMG_0123.JPG` ou `GOPR0045.MP4`). Em vez disso, ele compõe uma string estruturada utilizando as tags extraídas do cabeçalho EXIF/QuickTime:

### Padrão de Nomenclatura para Fotografias:
```text
{date}_{time}_{camera}_{resolution}_{dimensions}_{focal}_{aperture}_{shutter}_{iso}_{original}.{ext}
```

*Exemplo Real:*
```text
2026-09-22_14-30-00_CANON_SX60HS_16MP_4000x3000_1365mm_f6.5_1-1000s_ISO100_IMG_0412.JPG
```

**Benefícios:**
- **Ordenação Natural no SO:** A data ISO no início (`YYYY-MM-DD_HH-MM-SS`) garante que qualquer visualizador de arquivos liste as fotos em perfeita ordem cronológica.
- **Busca Semântica Instantânea:** O usuário pode pesquisar no Windows Explorer por `1365mm` para encontrar todas as fotos com zoom máximo, ou por `f1.8` para filtrar retratos com abertura ampla.
- **Rastreabilidade:** O nome original da câmera (`IMG_0412`) é preservado no final, permitindo cruzar dados com anotações antigas de campo.

### Padrão de Nomenclatura para Vídeos Originais:
```text
{date}_{time}_{camera}_{resolution}_{dimensions}_{fps}_{duration}_{original}.{ext}
```

*Exemplo Real:*
```text
2026-09-22_15-10-00_CANON_SX60HS_1080p_1920x1080_60fps_45s_MVI_0891.MP4
```

### Padrão para Timelapses Produzidos (4K UHD):
```text
{date}_{time_start}-{time_end}_{camera}_4K_UHD_{fps}fps_{crop_mode}_{real_duration}s_{video_duration}s_timelapse.mp4
```

*Exemplo Real:*
```text
2026-09-22_13-00-15-30_GOPRO_HERO5_4K_UHD_60fps_bottom_9000s_30s_timelapse.mp4
```
*Indica que 9.000 segundos (2h30) de tempo real foram condensados em 30 segundos de vídeo 4K a 60 FPS com alinhamento de corte na base (`bottom`).*

---

## 3. Extração Automática de Amostras de Timelapse para Álbuns

Quando centenas de fotos de um timelapse são arquivadas na categoria `4_Timelapses/`, o álbum familiar de fotos comuns (`2_AlbunsDatas/`) ficaria vazio ou perderia a memória daquele evento.

Para sanar isso, o estágio de organização (`OrganizeStage`) do IRIS possui um algoritmo de amostragem inteligente:
1. Ele identifica o primeiro e o último frame da sequência e garante que ambos sejam copiados para a pasta de álbuns.
2. Ao longo do intervalo da sequência (que pode durar várias horas), ele seleciona e copia uma foto a cada intervalo configurável (padrão de 10 minutos).
3. As amostras são alocadas em `2_AlbunsDatas/YYYY/MM/DD/timelapse_amostras_HH-MM-SS/`, preservando todos os metadados EXIF originais para que o usuário possa apreciar a passagem do tempo no visualizador de fotos sem precisar abrir a pasta bruta com milhares de arquivos.
