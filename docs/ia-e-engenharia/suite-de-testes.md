# IA & Engenharia: Suíte de Testes Automatizados (`pytest`)

O IRIS possui uma sólida bateria de **157 testes automatizados** baseados em `pytest`, cobrindo desde regras atômicas de formatação de nomes até simulações completas de falha de concorrência e mocks de chamadas externas de hardware e APIs.

---

## 1. Estrutura dos Arquivos de Teste

A suíte reside em `iris/tests/` e é dividida por responsabilidade funcional:

| Arquivo de Teste | Itens Testados | Foco Principal |
| :--- | :--- | :--- |
| `test_astro_stack.py` | 16 testes | Pré-processador de RAWs, detecção de centro de massa, subprocesso PSS e persistência. |
| `test_astro_wavelets.py` | 15 testes | Transformada B3-spline À Trous, cálculo do Limb Guard, Deconvolução Richardson-Lucy e presets RegiStax. |
| `test_classifier.py` | 6 testes | Heurísticas do `MediaClassifier`, detecção de sequências de timelapses e limites de zoom lunar. |
| `test_cleanup_stage.py` | 5 testes | Aborto de limpeza em caso de hash não verificado e integração com `Send2Trash`. |
| `test_concurrency.py` | 10 testes | `ProjectLock`, expiração de TTL, detecção de lock órfão por morte de PID e concorrência multissessão. |
| `test_config_menu.py` | 10 testes | Navegação de subpáginas do menu interativo, coerção de tipos e auto-cura de mojibake UTF-8. |
| `test_ingestion_stage.py` | 7 testes | Ingestão em blocos com hash simultâneo, MoveStrategy em 5 fases e retomabilidade após interrupção. |
| `test_namer.py` | 3 testes | Composição semântica de nomes de fotos e vídeos com tags EXIF reais. |
| `test_organize_stage.py` | 8 testes | Movimentação física para as 7 categorias e amostragem de frames de timelapse para álbuns. |
| `test_pipeline.py` | 6 testes | Carregamento dinâmico de estágios via `importlib`, transição de status e tratamento de `Ctrl+C`. |
| `test_project.py` | 6 testes | Transações SQLite em modo WAL, migrations de colunas e integridade de chave estrangeira. |
| `test_timelapse_and_youtube.py` | 22 testes | Filtergraph FFmpeg Lanczos/Deband, Resumable Upload em chunks e construção de descrições ricas. |
| `test_ui.py` | 4 testes | Renderização de painéis e barras de progresso Rich sem estouro horizontal no console. |
| `test_video_edit.py` | 20 testes | Trimming de bordas, aceleração dinâmica (`Nx`), detecção de encoders de hardware e cache de sondagem. |
| `test_youtube_cleanup.py` | 19 testes | Verificação de status na API do YouTube e limpeza segura de disco local pós-publicação. |

---

## 2. Como Executar os Testes

Para executar toda a suíte completa no terminal:

```bash
python -m pytest iris/tests
```

Para rodar apenas um módulo específico com saída detalhada:

```bash
python -m pytest iris/tests/test_astro_wavelets.py -v
```

Para rodar testes com relatório de falha detalhado:

```bash
python -m pytest iris/tests --tb=short
```

---

## 3. Padrões e Práticas de Mocking

1. **Zero Efeito Colateral em Disco:** Os testes utilizam as fixtures `tmp_path` do pytest para criar estruturas temporárias de arquivos em cada cenário, garantindo isolamento total do sistema real.
2. **Mocks de Chamadas Externas:**
   - Comandos de sistema (`ffmpeg`, `exiftool`) são mockados através de `unittest.mock.patch('subprocess.Popen')` ou `subprocess.run`.
   - A API do YouTube é mockada com objetos que simulam respostas HTTP `308 Resume Incomplete` e `200 OK`.
3. **Mocks de Hardware GPU:**
   - O teste de `detect_ffmpeg_encoder` simula respostas de inicialização de hardware da NVIDIA e Intel para verificar o mecanismo de cache e fallback para CPU.
