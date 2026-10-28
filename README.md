# IRIS - Imaging Resources and Integration System :camera::rocket:

[![Documentação](https://img.shields.io/badge/docs-GitHub_Pages-blue.svg)](https://felipeph.github.io/IRIS/)
[![Testes](https://img.shields.io/badge/tests-380%2B_passed-success.svg)](https://github.com/felipeph/IRIS)
[![Licença](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/felipeph/IRIS)

IRIS (Imaging Resources and Integration System) é uma central de engenharia e automação local para fluxos completos de fotografia, identificação taxonômica de aves por IA, geolocalização inteligente, vídeo 4K, astrofotografia lunar e publicação no YouTube. Seu design é fundamentado no princípio inegociável **Zero Data Loss**, persistência ACID com SQLite duplo em modo WAL e aceleração por GPU.

## Documentação Oficial

A documentação completa, interativa e pesquisável do IRIS está disponível online:
👉 **[https://felipeph.github.io/IRIS/](https://felipeph.github.io/IRIS/)**

Conteúdo técnico organizado em `docs/`:
- **Visão Geral**: Equipamentos suportados (SX60 HS, GoPro, CHDK, T6), guia rápido e opções de configuração em 9 categorias temáticas.
- **Arquitetura & Engenharia**: Princípios SOLID/Clean Architecture, persistência ACID dual-database SQLite (`project_mixins`), concorrência com `ProjectLock`, geolocalização (`GeoService`), probing dinâmico de GPU e ADRs.
- **Módulos do Pipeline (14 Etapas)**: Ingestão Copy/Move, Limpeza Hash-Guarded, Planejamento & Rajadas, Organização Física, Sanitização EXIF & Geotag UTF-8, Pipeline de Aves em 4 estágios (YOLOv8s + iNaturalist API v2 + Catálogo & Correção Manual), Astro Stack (PSS headless), Wavelets À Trous (presets RegiStax), Timelapse 4K (Normal & Longa Exposição), Edição de Vídeo 4K (Auto-Join por Ave/Dia) e YouTube API v3 (chunks de 64MB).
- **IA & Desenvolvimento**: [Matriz Mestre do Pipeline](docs/referencia/pipeline-lifecycle.md), [Dicionário SQLite](docs/referencia/schema-banco-de-dados.md), [Guia de Contexto para IA](docs/ia-e-engenharia/contexto-para-ia.md), suíte de 380+ testes em `pytest` com contratos arquiteturais e manifesto `llms.txt`.

## Licença
Este é um projeto pessoal open-source. Sinta-se livre para adaptar para seus próprios fluxos de backup.
