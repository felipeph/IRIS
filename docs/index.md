# IRIS — Imaging Resources and Integration System

<p align="center">
  <strong>Central de Engenharia e Automação de Mídia para Fotografia, Ornitologia por IA, Vídeo 4K, Astrofotografia Lunar e YouTube</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue.svg?logo=python" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Integridade-Zero_Data_Loss-red.svg" alt="Zero Data Loss">
  <img src="https://img.shields.io/badge/Banco_de_Dados-Dual_SQLite_WAL-success.svg?logo=sqlite" alt="SQLite Dual WAL">
  <img src="https://img.shields.io/badge/Acelera%C3%A7%C3%A3o-GPU_NVENC%2FQSV%2FAMF-orange.svg" alt="GPU Acceleration">
  <img src="https://img.shields.io/badge/Testes-380%2B_Passed-brightgreen.svg" alt="380+ Passed Tests">
  <img src="https://img.shields.io/badge/Licen%C3%A7a-MIT-green.svg" alt="MIT License">
</p>

---

## O que é o IRIS?

O **IRIS (Imaging Resources and Integration System)** é uma plataforma autônoma de linha de comando (CLI) desenvolvida para gerenciar, com rigor de integridade e automação de ponta a ponta, todo o ciclo de vida de produção audiovisual de natureza e astrofotografia.

```mermaid
flowchart LR
    A["📷 Cartão SD / Câmeras"] --> B["📥 1-4. Ingestão, Limpeza,\nPlanejamento & Organização"]
    B --> C["📍 5. Sanitização EXIF\n& Geotag UTF-8"]
    C --> D["🦜 6-9. Aves: YOLOv8 +\niNaturalist + Catálogo [B]"]
    B --> E["🌙 10-11. Astro Lunar:\nPSS Stack + Wavelets"]
    B & D --> F["🎬 12-13. Timelapse 4K &\nVídeo 4K (Auto-Join Aves)"]
    F --> G["🚀 14. YouTube API v3\n(Upload 64MB + Playlists)"]
```

---

## Princípios Inegociáveis do Sistema

> [!IMPORTANT]
> ### 1. Zero Data Loss (Prevenção Absoluta de Perda de Dados)
> Nenhum byte de mídia original pode ser destruído sem comprovação matemática prévia (`xxHash64`) de que uma réplica íntegra está persistida no SSD. Arquivos RAW e vídeos originais jamais são alterados fisicamente por ferramentas de metadados.

> [!TIP]
> ### 2. Arquitetura Dual-Database SQLite com Modo WAL
> O rastreamento de estado opera com dois bancos relacionais ACID (`PRAGMA user_version = 2`):
> - **Banco Central (`iris_central.db`)**: Guarda o catálogo de projetos, catálogo taxonômico global (`species_catalog`) e histórico consolidado de mídias.
> - **Banco por Projeto (`<projeto>.db`)**: Isola transações por lote com suporte a `SAVEPOINT` e *Dual-Write* atômico via `ATTACH DATABASE`.

> [!NOTE]
> ### 3. Visão Computacional Híbrida & Aceleração por Hardware
> - **Ornitologia & Geolocalização**: Detecção local via YOLOv8s combinada à API de Visão Computacional do iNaturalist com prior geográfico (`GeoService`), consenso e *early exit* em rajadas, e revisão interativa com catálogo regional.
> - **GPU First, CPU Fallback**: Renderização 4K UHD (3840x2160) via NVIDIA NVENC, Intel QSV ou AMD AMF com fallback transparente para software (`libx264`).

---

## Mapa da Documentação

| Seção | Descrição | Tópicos Principais |
| :--- | :--- | :--- |
| **[Visão Geral](visao-geral/introducao.md)** | Introdução ao sistema, câmeras e setup. | Equipamentos catalogados, menu interativo em 9 subpáginas, guia rápido. |
| **[Arquitetura & Engenharia](arquitetura/principios-de-design.md)** | Fundamentos de software e decisões técnicas. | Clean Architecture, SOLID, Dual SQLite, Locks atômicos, ADRs. |
| **[Módulos do Pipeline](modulos/01-ingestao.md)** | Deep Dive nas etapas do sistema. | Ingestão, Organização, Sanitização & Geo, Aves (YOLO + iNaturalist), Timelapse 4K, Vídeo 4K, Astro e YouTube. |
| **[IA & Engenharia](ia-e-engenharia/contexto-para-ia.md)** | Especificação formal para agentes de IA e manutenção. | Mapa modular do código, invariantes, suíte de 380+ testes em `pytest`, `llms.txt`. |
| **[Referência Técnica](referencia/pipeline-lifecycle.md)** | **Matriz Mestre do Pipeline** e Dicionário SQLite. | Mapeamento Etapa $\rightarrow$ Módulo `.py` $\rightarrow$ Tabelas SQLite $\rightarrow$ Pastas `C:\IRIS`. |
