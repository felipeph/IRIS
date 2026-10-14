# IRIS - Imaging Resources and Integration System :camera::rocket:

[![Documentação](https://img.shields.io/badge/docs-GitHub_Pages-blue.svg)](https://felipeph.github.io/IRIS/)
[![Testes](https://img.shields.io/badge/tests-157_passed-success.svg)](https://github.com/felipeph/IRIS)
[![Licença](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/felipeph/IRIS)

IRIS (Imaging Resources and Integration System) é uma central de engenharia e automação local para fluxos completos de fotografia, vídeo 4K, astrofotografia lunar e publicação no YouTube. Seu design é fundamentado no princípio inegociável **Zero Data Loss**, persistência ACID com SQLite duplo em modo WAL e aceleração por GPU.

## Documentação Oficial

A documentação completa, interativa e pesquisável do IRIS está disponível online:
👉 **[https://felipeph.github.io/IRIS/](https://felipeph.github.io/IRIS/)**

Conteúdo técnico organizado em `docs/`:
- **Visão Geral**: Equipamentos suportados (SX60 HS, GoPro, CHDK, T6), guia rápido e opções de configuração.
- **Arquitetura & Engenharia**: Princípios SOLID/Clean Architecture, persistência ACID dual-database SQLite, concorrência com `ProjectLock`, probing dinâmico de GPU e ADRs (Architecture Decision Records).
- **Módulos do Pipeline**: Deep dive em todos os estágios (Ingestão Copy/Move, Sanitização EXIF para Google Fotos, Organização, Limpeza, Timelapse 4K, Edição de Vídeo 4K, YouTube API v3, Astro Stack com PSS headless e Wavelets À Trous com presets RegiStax).
- **IA & Desenvolvimento**: Especificação para agentes de IA, suíte de 157 testes em `pytest`, guia de extensão e manifesto `llms.txt`.

## Licença
Este é um projeto pessoal open-source. Sinta-se livre para adaptar para seus próprios fluxos de backup.
