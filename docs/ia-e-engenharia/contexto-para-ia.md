# IA & Engenharia: Guia & Contexto para Agentes de IA

Este documento foi projetado para que **Agentes Autônomos de Inteligência Artificial** (como modelos LLM executando tarefas de refatoração, extensão ou depuração) compreendam a arquitetura, as invariantes lógicas e as convenções do código do **IRIS (Imaging Resources and Integration System)**.

---

## 1. O Domínio e as Invariantes do Sistema

1. **Ator Único:** O sistema foi construído para uso pessoal de Felipe Heitmann. Não há necessidade de suporte multi-usuário (multitenancy) nem tabelas de permissões RBAC.
2. **Invariante Zero Data Loss:** Nunca adicione comandos de deleção direta de arquivos (`os.remove`, `shutil.rmtree`) sem:
   - Uma verificação formal de status `verified == 1` na tabela SQLite correspondente.
   - Usar prioritariamente o envio para a lixeira via `send2trash`.
3. **Invariante de Isolamento de Projeto:** Todo `PipelineStage` deve manipular estritamente os arquivos vinculados à instância de `Project` recebida no método `run(project)`. Nunca escreva código que faça varreduras globais em `destination_root` como fallback para encontrar trabalho.
4. **Persistência Relacional:** O estado da aplicação reside nos bancos SQLite (`iris_central.db` e `<projeto>.db`). Nunca reintroduza persistência em arquivos de texto soltos (como JSONs na raiz).

---

## 2. Mapa Conceitual do Código-Fonte

```text
iris/
├── main.py                  # Ponto de entrada interativo da CLI (Rich)
├── config.yaml              # Configuração declarativa central
├── src/
│   ├── core/                # Módulos de Infraestrutura e Regras Globais
│   │   ├── config.py        # ConfigManager (parse, persistência e auto-cura UTF-8)
│   │   ├── config_menu.py   # Menu interativo em subpáginas
│   │   ├── project.py       # Modelo Project e acesso SQLite dual (WAL mode)
│   │   ├── pipeline.py      # PipelineRunner e classe base abstrata PipelineStage
│   │   ├── lock.py          # ProjectLock (controle de concorrência com TTL)
│   │   ├── metadata.py      # Extrator de tags EXIF e metadados de vídeo
│   │   ├── classifier.py    # MediaClassifier (árvore de decisão taxonômica)
│   │   ├── namer.py         # MediaNamer (formatação de nomes semânticos)
│   │   ├── ui.py            # Componentes Rich (tabelas, painéis e barras de progresso)
│   │   └── logger.py        # Logger centralizado com rotação
│   └── modules/             # Implementações Concretas dos Estágios do Pipeline
│       ├── ingestion/       # Estágio 1: Ingestão (CopyStrategy e MoveStrategy)
│       ├── sanitization/    # Estágio 2: Saneamento EXIF via ExifTool
│       ├── planning/        # Estágio 3: Planejamento e catalogação no staging
│       ├── organize/        # Estágio 4: Movimentação definitiva e amostragem
│       ├── cleanup/         # Estágio 5: Limpeza segura da origem
│       ├── timelapse/       # Estágio 6: Renderização 4K Lanczos e Deband 16-bit
│       ├── video_edit/      # Estágio 7: Trimming, speed e upscale 4K
│       ├── youtube/         # Estágio 8: YouTube Data API v3 OAuth 2.0
│       ├── astro_stack/     # Estágio 9: Pré-processamento e PSS Stacking
│       ├── astro_sharpen/   # Estágio 10: Wavelets À Trous e presets RegiStax
│       └── astro/           # CLI unificada iris-astro e motor matemático wavelets
├── vendor/                  # Dependências de terceiros isoladas (PSS - GPL-3)
├── secrets/                 # Credenciais locais do YouTube (fora do git)
└── tests/                   # Bateria de 157 testes automatizados em pytest
```

---

## 3. Diretrizes de Codificação para Agentes

1. **Tipagem e Assinaturas:** Mantenha type hints explícitos (`project: Project`, `kwargs: dict`, `-> bool`) em todos os novos métodos.
2. **Preservação de Compatibilidade:** Ao alterar assinaturas de métodos de estágios do pipeline, lembre-se de que a função `_invoke_stage` em `pipeline.py` utiliza reflexão (`inspect.signature`) para injetar apenas argumentos aceitos pela classe.
3. **Padrão de Nomenclatura de Arquivos:** Nunca insira pontos no corpo dos nomes de arquivos gerados (ex.: use traços para sub-segundos como `14-30-00-12` em vez de `14-30-00.12`), pois pontos adicionais quebram a identificação de extensões em alguns sistemas operacionais.
4. **Tratamento de Hardware GPU:** Sempre que instanciar filtros ou codificadores FFmpeg, mantenha o padrão de encapsulamento com `detect_ffmpeg_encoder`, respeitando o cache da sessão e a flag `force_software=True`.
5. **Verificação com Testes:** Toda alteração de código deve ser validada executando a suíte de testes:
   ```bash
   python -m pytest iris/tests
   ```
   Nenhum teste pode quebrar (156 passed, 1 skipped).
