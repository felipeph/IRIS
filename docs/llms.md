# Manifesto LLM (`llms.txt`)

Este arquivo segue a especificação padronizada **`llms.txt`**, oferecendo um resumo condensado, estruturado e com links semânticos para que modelos de linguagem de grande porte (LLMs) e agentes de inteligência artificial compreendam todo o projeto **IRIS** em uma única leitura.

---

```text
# IRIS — Imaging Resources and Integration System
> Central de Engenharia e Automação de Mídia para Fotografia, Vídeo 4K, Astrofotografia Lunar e YouTube.
> Repositório: https://github.com/felipeph/IRIS
> Documentação: https://felipeph.github.io/IRIS/

## Resumo Executivo
O IRIS é uma plataforma de linha de comando (CLI) desenvolvida em Python para orquestrar de ponta a ponta fluxos audiovisuais pessoais. Substitui processos manuais de ingestão, renomeação, edição e publicação por um pipeline determinístico, idempotente e resiliente a falhas.

## Invariantes e Princípios de Arquitetura
- Zero Data Loss: Nenhum arquivo original é deletado sem confirmação prévia de hash verificado (xxHash64) no destino e envio prioritário para a lixeira (Send2Trash).
- Dual-Database SQLite com WAL Mode: iris_central.db para catálogo global e <projeto>.db para estado granular por arquivo. Propriedades ACID completas sem servidores externos.
- Concorrência Segura: ProjectLock baseado em arquivo atômico com PID e heartbeat (TTL de 300 segundos).
- GPU First com Fallback: Renderização FFmpeg acelerada via NVENC/QSV/AMF com cache de sondagem, cooldown de 1.0s de VRAM e transição transparente para CPU (libx264).
- Isolamento de Licenças: Integração com PlanetarySystemStacker (GPL-3) via subprocesso isolado, mantendo o código mestre do IRIS sob licença MIT.

## Módulos do Pipeline (Estágios)
1. Ingestão (ingestion):
   - CopyStrategy: Cópia em buffer de 4MB na RAM + xxHash64 simultâneo + os.fsync() + verificação no SSD.
   - MoveStrategy: Movimentação multithreaded em 5 fases com os.replace() atômico e deduplicação prévia.
2. Sanitização EXIF (sanitization):
   - Remoção de blocos MPF (APP2), MakerNotes Canon e trailers pós-EOI via ExifTool sem recompressão de pixels, para compatibilidade com o Google Fotos Storage Saver.
3. Planejamento (planning):
   - Extração de telemetria óptica (focal, abertura, ISO, obturador) e inferência taxonômica de câmeras.
4. Organização Física (organize):
   - Particionamento em 7 categorias numéricas e renomeação semântica rica com megapixels e dimensões reais. Extração de amostras de timelapses para álbuns.
5. Limpeza (cleanup):
   - Limpeza auditada da origem pós-verificação formal de integridade via Send2Trash.
6. Timelapse 4K (timelapse):
   - Renderização 4K UHD 60fps com interpolação Lanczos, crop adaptativo (bottom, center, top) e Deband 16-bit com ruído temporal anti-banding para VP09/AV01 no YouTube.
7. Edição de Vídeo 4K (video_edit):
   - Trimming de 2.0s contra tremidos mecânicos, aceleração dinâmica (--speed=Nx), upscale 4K Lanczos e filtro Unsharp Mask.
8. YouTube (youtube):
   - YouTube Data API v3 OAuth 2.0 com Resumable Upload em chunks de 64MB (configurável), fichas técnicas detalhadas e gestão automática de playlists.
9. Astrofotografia Lunar Stacking (astro_stack):
   - Pré-processamento de RAWs com recorte centralizado de disco lunar em coordenadas inteiras e empilhamento multiponto PSS headless em TIFFs 16-bit.
10. Astrofotografia Wavelets (astro_sharpen):
    - Motor À Trous B3-spline multiescala com algoritmo Limb Guard contra halos no limbo lunar, Deconvolução Richardson-Lucy e família de presets RegiStax (PSNR 49.0 dB).
11. CLI iris-astro (astro):
    - Comandos autônomos de terminal: iris-astro stack, iris-astro sharpen e iris-astro pipeline.

## Suíte de Testes
- Framework: pytest (157 testes automatizados, 100% passando).
- Execução: python -m pytest iris/tests
```
