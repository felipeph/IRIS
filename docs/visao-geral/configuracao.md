# Visão Geral: Configuração do Sistema & Menu Interativo

O comportamento do IRIS é completamente parametrizável via arquivo `config.yaml`. Além da edição direta em editor de texto, o sistema oferece um **Menu de Configurações Interativo por Subpáginas** (`config_menu.py`), categorizado tematicamente em 5 grupos e desacoplado do código principal.

---

## 1. Estrutura do Arquivo `config.yaml`

O arquivo é estruturado em blocos funcionais em formato YAML:

```yaml
general:
  default_source: "G:\\DCIM"
  destination_root: "C:\\IRIS"
  last_project: ""
  log_level: "INFO"
  theme: "light"

classification:
  burst_interval_seconds: 1.5
  enable_burst_detection: false
  enable_timelapse_album_samples: true
  moon_zoom_threshold_mm: 1000.0
  timelapse_max_interval_seconds: 60.0
  timelapse_min_photos: 300
  timelapse_sample_interval_minutes: 10.0
  timelapse_tolerance_ratio: 1.5

naming:
  photo_pattern: "{date}_{time}_{camera}_{resolution}_{dimensions}_{focal}_{aperture}_{shutter}_{iso}_{original}.{ext}"
  video_pattern: "{date}_{time}_{camera}_{resolution}_{dimensions}_{fps}_{duration}_{original}.{ext}"

modules:
  ingestion:
    max_workers: 4
    strategy: "move"          # Opções: "copy" (Copy & Verify) ou "move" (MoveStrategy rápida)

  cleanup:
    auto_clean: true          # Limpeza automática do cartão SD após verificação com sucesso

  timelapse:
    enabled: true
    crf: 15
    fps: 60
    target_width: 3840
    target_height: 2160
    crop_mode: "bottom"       # "bottom", "center", "top" ou "full"
    render_profile: "fast"    # "fast" (GPU) ou "quality" (CPU)
    deband:
      enabled: false
      add_grain: false
    windows_toast: true
    ntfy_topic: "iris-alerts"

  video_edit:
    enabled: true
    crf: 16
    mode: "individual"        # "individual" ou "session" (junção por sessão contígua)
    speed: 5.0                # Fator de aceleração (Nx)
    trim_enabled: true
    trim_seconds: 2.0         # Segundos cortados no início e no fim
    strip_audio: true         # Mudo (-an)
    unsharp_filter: true      # Realce de nitidez antes do upscale
    deband_enabled: true

  astro_stack:
    enabled: true
    keep_percents: [10, 25, 50, 75]
    align_box_width: 64
    align_search_width: 20
    margin_pixels: 128
    stab_mode: "Surface"
    timeout_seconds: 600

  astro_sharpen:
    enabled: true
    presets: ["registax_fiel", "registax_clean", "registax_iluminado", "registax_pro"]
    enable_clahe: true
    use_limb_guard: true

  youtube:
    enabled: true
    category_id: "22"
    privacy_status: "public"  # "private", "unlisted" ou "public"
    playlist: "Timelapses"
    video_playlist: "Natureza 4K UHD"
    cleanup_local_videos: true
    cleanup_to_trash: true    # Enviar para a Lixeira do Windows (send2trash)
```

---

## 2. O Menu Interativo de Configurações (`config_menu.py`)

Ao selecionar a opção de configurações na CLI, o usuário é apresentado a um hub categorizado em 5 subpáginas temáticas:

```text
╭─────────────────────────────────────────────────────────────────────────────╮
│ ⚙️ IRIS - CENTRAL DE CONFIGURAÇÕES                                         │
╰─────────────────────────────────────────────────────────────────────────────╯

[1] 📁 Armazenamento & Ingestão (Origem, Destino SSD, Estratégia, Concorrência)
[2] 🗂️ Organização & Nomenclatura (Padrões de Nome, Limites de Zoom, Amostras)
[3] ⏱️ Renderização de Timelapse 4K (Resolução, FPS, Crop, Deband, GPU)
[4] 🎬 Edição e Upscale de Vídeo 4K (Modo, Velocidade, Trimming, Áudio)
[5] 🚀 YouTube & Notificações (Privacidade, Playlists, Limpeza, Toast, NTFY)
[6] 🌙 Astrofotografia Lunar (PSS Stacking, Margens, Presets de Wavelets)
[0] Voltar ao Menu Principal
```

### Principais Vantagens do Sistema de Menus:
- **Preservação de Comentários e Estrutura:** As alterações são salvas reescrevendo estritamente os campos modificados via manipulação atômica de arquivos.
- **Auto-Cura de Codificação UTF-8 e Mojibake:** O módulo inclui um mecanismo de resiliência que detecta caracteres double-encoded (como `Ã§` em vez de `ç`) e reescreve automaticamente os bytes em UTF-8 puro, eliminando corrupção de acentos no console do Windows.
- **Validação de Tipos em Tempo de Execução:** Entradas de inteiros, números de ponto flutuante, booleanos (`True`/`False`) e listas recebem coerção de tipos estrita antes da persistência.
