# Projeto IRIS - TODO List

## 📌 Pendentes (A Fazer)
- [ ] **feat**: Implementar módulo local de visão computacional (GPU/on-device, via YOLO ou classificador leve) para inferência em amostragem de frames e extração automática de palavras-chave/tags da cena (ex: nuvens, sol, chuva, pássaros) sem custo de tokens ou dependência de APIs externas. *(Adicionado em: 22/09/2026 22:06)*
- [ ] **feat**: Criar módulo de geração de thumbnails para o YouTube com sobreposição discreta de metadados sobre um frame (data/hora do timelapse, velocidade em relação ao tempo real, resolução final, FPS e localização da captura). *(Adicionado em: 22/09/2026 22:02)*
- [ ] **feat**: Enriquecer as descrições dos vídeos publicados no YouTube com informações e metadados técnicos detalhados do timelapse. *(Adicionado em: 22/09/2026 22:02)*

## ✅ Concluídos
- [x] **feat**: Incluir o alinhamento vertical de corte (`bottom`, `center` ou `top`) no padrão de nomenclatura do arquivo de vídeo gerado para o timelapse. *(Concluído em: 25/09/2026 22:30)*
- [x] **feat**: Padronização dos nomes de fotos com resolução em megapixels (ex: `16MP`) e dimensões (`4000x3000`), e vídeos com classificação (`4K`) e dimensões (`3840x2160`). *(Concluído em: 25/09/2026 22:30)*
- [x] **perf**: Nova arquitetura de ingestão rápida baseada em movimentação nativa do SO (Strategy Pattern com `MoveStrategy` multithreaded em 5 fases, deduplicação prévia, `os.replace` / `shutil.move`, `xxHash64` no SSD, limpeza automática da origem e suporte exaustivo a formatos modernos e legados). *(Concluído em: 25/09/2026 21:35)*
- [x] **refactor**: Avaliação, planejamento arquitetural (/grill-me) e implementação da ingestão por movimentação nativa do SO em vez de cópia manual, preservando modo clássico de cópia e compatibilidade total com o pipeline. *(Concluído em: 25/09/2026 21:35)*
- [x] **feat**: Extração e cópia automática de amostra de fotos do timelapse durante a organização física para subpastas de álbuns ('2_AlbunsDatas/YYYY/MM/DD/timelapse_amostras_HH-MM-SS/'), preservando arquivos originais com metadados EXIF, espaçadas por intervalo temporal configurável (padrão 5 min) e garantindo primeiro e último frame. *(Concluído em: 25/09/2026 13:56)*
- [x] **feat**: Limpeza automática configurável da origem (SD Card) pós-verificação de hash, com envio seguro para a Lixeira (send2trash), opção 16 no config global e atalho 'L' por projeto na CLI. *(Concluído em: 22/09/2026 22:35)*
- [x] **feat**: Suporte a execução concorrente e segura de múltiplas instâncias em projetos distintos com ProjectLock (bloqueio exclusivo anti-colisão com auto-recuperação), SQLite WAL mode, logs isolados por projeto e desacoplamento de estado do config.yaml. *(Concluído em: 22/09/2026 22:13)*
- [x] **feat**: Desenvolver sistema de renomeação e organização dos arquivos em pastas, mantendo a lógica original do 'fotos-backup-workflow'. *(Adicionado em: 20/09/2026 21:07)*
- [x] **feat**: Criar funcionalidade de ingestão para copiar arquivos de um SD/HD para a pasta de destino (1_Entrada/Staging), seguindo os princípios do fluxo original do 'fotos backup workflow'. *(Adicionado em: 20/09/2026 15:08)*
- [x] **feat**: Implementar verificação de segurança (hash SHA-256) na cópia de arquivos para garantir integridade.
- [x] **chore**: Preparação do código para o repositório no GitHub (inclusão de `.gitignore`).
- [x] **feat**: Desenvolvimento do Módulo de Limpeza de Dados (cleanup) pós-ingestão.
