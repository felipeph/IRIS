# Visão Geral: O que é o IRIS?

## 1. Origem e Propósito

O **IRIS (Imaging Resources and Integration System)** nasceu para solucionar um problema crônico e bem conhecido por fotógrafos e produtores de conteúdo de natureza: **o atrito operacional da pós-captura**.

Quando um fotógrafo retorna de uma expedição de campo ou de uma sessão noturna de astrofotografia, ele frequentemente traz consigo centenas de gigabytes distribuídos em múltiplos cartões SD:
- Milhares de fotos sequenciais capturadas em intervalos regulares para criação de timelapses.
- Dezenas de clipes de vídeo curtos registrando pássaros ariscos em zoom extremo (com tremidos no início e no final da gravação causados pelo toque no botão do obturador).
- Centenas de frames fotográficos brutos (RAW) de crateras lunares que necessitam de alinhamento subpixel, seleção de qualidade e descarte atmosférico.
- Fotos avulsas de retratos e família que precisam de arquivamento cronológico e higienização para armazenamento em nuvem.

Historicamente, o processamento desse material exigia horas de trabalho braçal em frente ao computador: abrir utilitários de cópia, renomear arquivos manualmente, abrir o Premiere/DaVinci para aplicar upscale e corte de pontas em cada vídeo, abrir programas legados do Windows (como PIPP, AutoStakkert! e RegiStax) para alinhar imagens lunares e, por fim, fazer upload vídeo por vídeo na interface web do YouTube digitando títulos e tags repetitivas.

**O IRIS elimina essa fricção por completo.** Ele atua como um sistema operacional dedicado para a ingestão, engenharia de dados, processamento por GPU e publicação de mídias pessoais.

---

## 2. O Que o Sistema é Capaz de Fazer?

O IRIS implementa um fluxo integrado de ponta a ponta dividido em estágios granulares e desacoplados:

### A. Ingestão Segura e Acelerada
- **Modo Copy & Verify**: Realiza a leitura da mídia em blocos de 4MB na RAM, computando o hash `xxHash64` em memória enquanto grava no SSD. Em seguida, força a escrita física na controladora com `os.fsync()` e lê os bytes do destino para confirmação matemática da cópia (executa apenas 2 leituras de disco, em vez das 3 do método ingênuo).
- **Modo Move Rápido**: Move instantaneamente estruturas de diretórios utilizando chamadas de sistema atômicas (`os.replace` / `shutil.move`) com pipeline multithreaded em 5 fases, deduplicação prévia e cálculo de hash direto no SSD de alta velocidade.

### B. Sanitização Cirúrgica de Metadados (Google Fotos Storage Saver)
- Inspeciona os segmentos binários de fotografias JPEG e remove cirurgicamente blocos proprietários que causam a rejeição de fotos pelo motor de compactação em nuvem do Google Fotos (como blocos APP2/MPF da CIPA DC-007, MakerNotes proprietárias da Canon e lixo binário pós-marcador EOI), preservando 100% dos pixels intactos sem nenhuma recompressão destrutiva.

### C. Taxonomia e Nomenclatura Semântica
- Extrai metadados ópticos profundos (distância focal milimétrica, abertura f/, velocidade de obturador, sensibilidade ISO, resolução e dimensões reais).
- Classifica automaticamente as mídias em 7 categorias isoladas (`1_Entrada`, `2_AlbunsDatas`, `3_Videos`, `4_Timelapses`, `5_Astrofotografia`, `6_Produzidos`, `7_Video_Editado_4K`).
- Renomeia arquivos com padrão determinístico rico em telemetria, substituindo nomes opacos como `IMG_0412.JPG` por strings legíveis como `2026-09-22_14-30-00_CANON_SX60HS_16MP_4000x3000_1365mm_f6.5_1-1000s_ISO100_IMG_0412.JPG`.

### D. Renderização 4K UHD de Timelapses
- Agrupa sequências temporais contínuas de fotos e renderiza vídeos master em 4K UHD (3840x2160 a 60 FPS).
- Aplica corte inteligente de proporção de aspecto (*aspect ratio cropping*: `bottom`, `center` ou `top`) com interpolação de alta fidelidade Lanczos.
- Injeta filtro de **Deband 16-bit com micro-dither** (ruído temporal imperceptível a olho nu), forçando os transcoders do YouTube a manterem gradientes suaves de céu sem faixas de posterização (banding).
- Aceleração gráfica por GPU via NVENC, Intel QSV ou AMD AMF.

### E. Edição, Estabilização e Upscale 4K de Vídeos
- Módulo interativo para seleção individual de clipes ou fusão automática de sessões contíguas gravadas em um intervalo de até 10 minutos.
- Trimming automático inteligente (corta os primeiros e últimos 2.0 segundos de gravação para eliminar o tremido involuntário de aperto de botão, com proteção para clipes curtos).
- Controle de aceleração dinâmica de reprodução (`--speed=Nx`) com reamostragem suave até 60 FPS.
- Filtro seletivo de realce de bordas (*Unsharp Mask*) combinado com upscale Lanczos para acionar os codecs premium VP09/AV01 no YouTube.

### F. Astrofotografia Lunar: Stacking & Wavelets Autônomos
- Pipeline autônomo lunar completo através da CLI `iris-astro`:
  1. **Pré-processamento**: Detecta o disco da Lua no sensor, extrai coordenadas inteiras do centro de massa e executa um corte circular centrado idêntico em centenas de arquivos RAW da Canon (CR2), equalizando o ganho linear.
  2. **Stacking Multiponto Headless**: Integração isolada via subprocesso com o motor do PlanetarySystemStacker (PSS vendorizado com patches headless), gerando stacks em TIFF 16-bit sem compressão para múltiplos percentuais de descarte (10%, 25%, 50%).
  3. **Wavelets À Trous Multiescala**: Motor matemático próprio (`LunarWaveletEngine`) que realiza a decomposição da imagem em planos de frequência B3-spline, com algoritmo **Limb Guard** para proteger a borda iluminada da Lua contra halos brancos e ringing.
  4. **Micro-Relevo & Deconvolução**: Deconvolução Richardson-Lucy contra o *seeing* atmosférico, realce 3D de relevo (*Local Clarity*) e reprodução matemática de alta precisão (49.0 dB PSNR) de presets clássicos do RegiStax.

### G. Publicação Enriquecida no YouTube
- Integração oficial via YouTube Data API v3 com OAuth 2.0.
- Upload com suporte a *Resumable Chunks* e barra de progresso visual no terminal.
- Construção dinâmica de fichas técnicas completas nas descrições dos vídeos (equipamento, resolução, filtros aplicados, geolocalização e data).
- Associação automática a playlists temáticas e limpeza segura de disco local pós-confirmação de publicação.
