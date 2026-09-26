# Projeto IRIS - TODO List

## 📌 Pendentes (A Fazer)
- [ ] **feat**: Incluir o alinhamento vertical de corte (`bottom`, `center` ou `top`) no padrão de nomenclatura do arquivo de vídeo gerado para o timelapse. *(Adicionado em: 25/09/2026 20:31)*
- [ ] **perf**: Experimentar nova arquitetura de ingestão rápida baseada em movimentação nativa do SO (pipeline em 5 etapas: 1. varredura rápida da origem e registro inicial no BD; 2. varredura e registro do destino; 3. comparação/deduplicação preliminar por nome, extensão e tamanho; 4. comando mover nativo; 5. cálculo de hash SHA-256 e extração de metadados pós-mover no BD), mantendo compatibilidade e segurança sem desestabilizar o fluxo robusto atual. *(Adicionado em: 25/09/2026 20:14)*
- [ ] **feat**: Implementar módulo local de visão computacional (GPU/on-device, via YOLO ou classificador leve) para inferência em amostragem de frames e extração automática de palavras-chave/tags da cena (ex: nuvens, sol, chuva, pássaros) sem custo de tokens ou dependência de APIs externas. *(Adicionado em: 22/09/2026 22:06)*
- [ ] **feat**: Criar módulo de geração de thumbnails para o YouTube com sobreposição discreta de metadados sobre um frame (data/hora do timelapse, velocidade em relação ao tempo real, resolução final, FPS e localização da captura). *(Adicionado em: 22/09/2026 22:02)*
- [ ] **feat**: Enriquecer as descrições dos vídeos publicados no YouTube com informações e metadados técnicos detalhados do timelapse. *(Adicionado em: 22/09/2026 22:02)*
- [ ] **refactor**: Avaliar e planejar a arquitetura de ingestão utilizando a operação de mover nativa do sistema operacional (SO) em vez de cópia manual, analisando integridade (hashing), comportamento cross-device/unidades e desempenho. *(Adicionado em: 21/09/2026 22:10)*

## ✅ Concluídos
- [x] **feat**: Extração e cópia automática de amostra de fotos do timelapse durante a organização física para subpastas de álbuns ('2_AlbunsDatas/YYYY/MM/DD/timelapse_amostras_HH-MM-SS/'), preservando arquivos originais com metadados EXIF, espaçadas por intervalo temporal configurável (padrão 5 min) e garantindo primeiro e último frame. *(Concluído em: 25/09/2026 13:56)*
- [x] **feat**: Limpeza automática configurável da origem (SD Card) pós-verificação de hash, com envio seguro para a Lixeira (send2trash), opção 16 no config global e atalho 'L' por projeto na CLI. *(Concluído em: 22/09/2026 22:35)*
- [x] **feat**: Suporte a execução concorrente e segura de múltiplas instâncias em projetos distintos com ProjectLock (bloqueio exclusivo anti-colisão com auto-recuperação), SQLite WAL mode, logs isolados por projeto e desacoplamento de estado do config.yaml. *(Concluído em: 22/09/2026 22:13)*
- [x] **feat**: Desenvolver sistema de renomeação e organização dos arquivos em pastas, mantendo a lógica original do 'fotos-backup-workflow'. *(Adicionado em: 20/09/2026 21:07)*
- [x] **feat**: Criar funcionalidade de ingestão para copiar arquivos de um SD/HD para a pasta de destino (1_Entrada/Staging), seguindo os princípios do fluxo original do 'fotos backup workflow'. *(Adicionado em: 20/09/2026 15:08)*
- [x] **feat**: Implementar verificação de segurança (hash SHA-256) na cópia de arquivos para garantir integridade.
- [x] **chore**: Preparação do código para o repositório no GitHub (inclusão de `.gitignore`).
- [x] **feat**: Desenvolvimento do Módulo de Limpeza de Dados (cleanup) pós-ingestão.
