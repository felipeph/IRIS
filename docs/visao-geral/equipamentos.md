# Visão Geral: Equipamentos & Câmeras Catalogadas

O IRIS possui inteligência taxonômica para inspecionar os cabeçalhos EXIF das imagens e identificar o equipamento emissor, ajustando automaticamente suas rotinas de nomenclatura, classificação e processamento com base no perfil de captura de cada sensor.

---

## 1. Canon PowerShot SX60 HS

<p align="center">
  <strong>Identificador Interno:</strong> <code>CANON_SX60HS</code>
</p>

* **Tipo de Sensor:** 1/2.3" CMOS de 16.1 Megapixels (Resolução nativa: 4608x3456 ou 4000x3000 em 4:3).
* **Óptica:** Zoom óptico contínuo ultra-longo de 65x (equivalente a 21mm–1365mm em formato 35mm), expansível digitalmente.
* **Formatos de Arquivo:** JPEG (`.JPG`) e RAW proprietário Canon de 12-bit (`.CR2`).
* **Vídeo Nativo:** Full HD 1080p a 60 FPS (`.MP4`).
* **Casos de Uso Primários no IRIS:**
  - **Aves e Animais Silvestres em Superzoom:** Capturas a 1365mm onde a aproximação óptica extrema resulta em vídeos com leve trepidação nos extremos de tempo (tratados pelo módulo `video_edit` com trimming e upscale Lanczos).
  - **Astrofotografia Lunar:** Séries de fotografias RAW (`.CR2`) em tripé fixo com zoom máximo de 1365mm. Quando a distância focal equivalente calculada ultrapassa 1000mm, o classificador do IRIS categoriza o arquivo como `5_Astrofotografia/Lua/`.
  - **Sanitização de Metadados:** Devido ao firmware complexo da PowerShot, seus JPEGs gravam blocos APP2 (MPF) e extensos MakerNotes que exigem saneamento pelo `SanitizationStage` para aprovação na cota do Google Fotos.

---

## 2. GoPro Hero 5 Black

<p align="center">
  <strong>Identificador Interno:</strong> <code>GOPRO_HERO5</code>
</p>

* **Tipo de Sensor:** 1/2.3" CMOS de 12 Megapixels (Resolução nativa: 4000x3000).
* **Óptica:** Lente ultra-grande angular fixa de abertura f/2.8 (Field of View amplo de 118° a 149°).
* **Formatos de Arquivo:** JPEG (`.JPG`) e vídeos em H.264/MP4 (`.MP4`).
* **Casos de Uso Primários no IRIS:**
  - **Timelapses de Longa Duração:** Captura de centenas ou milhares de fotos contínuas em modo *Time Lapse Photo* (com intervalos de 2s, 5s, 10s ou 30s).
  - **Regra de Detecção:** Quando o classificador encontra sequências com mais de 300 fotos mantendo intervalo temporal estável (tolerância de 1.5x), o lote é automaticamente isolado na pasta `4_Timelapses/` para renderização em 4K UHD 60 FPS com alinhamento vertical selecionável (geralmente `crop_mode: bottom` para priorizar a linha do horizonte e do solo contra o céu aberto).

---

## 3. Canon PowerShot S50 (com Firmware CHDK)

<p align="center">
  <strong>Identificador Interno:</strong> <code>CANON_S50_CHDK</code>
</p>

* **Tipo de Sensor:** Sensor CCD clássico de 1/1.8" de 5.0 Megapixels (Resolução nativa: 2592x1944).
* **Firmware:** Canon Hack Development Kit (CHDK) carregado na memória via cartão de memória.
* **Casos de Uso Primários no IRIS:**
  - **Automação de Câmera e Detecção de Movimento:** Capturas contínuas acionadas por scripts em Lua/uBasic para monitoramento ambiental e vigilância de ninhos de pássaros.
  - **Comportamento no Pipeline:** Devido à idade da câmera e ao firmware customizado, os timestamps e números de série são normalizados na etapa de planejamento (`PlanningStage`), garantindo que a nomenclatura cronológica permaneça estável.

---

## 4. Canon EOS Rebel T6

<p align="center">
  <strong>Identificador Interno:</strong> <code>CANON_T6</code>
</p>

* **Tipo de Sensor:** Sensor APS-C CMOS de 18.0 Megapixels (Resolução nativa: 5184x3456).
* **Óptica Principal Utilizada:** Canon EF 50mm f/1.8 STM (distância focal equivalente a 80mm).
* **Formatos de Arquivo:** JPEG (`.JPG`) e RAW (`.CR2`).
* **Casos de Uso Primários no IRIS:**
  - **Retratos e Eventos Familiares:** Fotos individuais de altíssima nitidez e desfoque de fundo (bokeh).
  - **Comportamento no Pipeline:** São classificadas estritamente na categoria `2_AlbunsDatas/YYYY/MM/DD/`, organizadas cronologicamente por ano, mês e dia com preservação total de tags EXIF e perfil de cores original.

---

## 5. Smartphones e Dispositivos Genéricos

<p align="center">
  <strong>Identificadores Internos:</strong> <code>SMARTPHONE</code> ou <code>UNKNOWN</code>
</p>

* Para fotos capturadas em dispositivos móveis (Android/iOS) ou câmeras de terceiros sem regra de heurística específica, o IRIS extrai o campo `Make` e `Model` do cabeçalho TIFF/EXIF e sanitiza a string para nomes seguros no sistema de arquivos do Windows (ex.: substituindo espaços por sublinhados e eliminando caracteres especiais).
