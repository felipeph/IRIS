# ADR-001: Estratégias de Ingestão (MoveStrategy vs CopyStrategy)

* **Status:** Aprovado e Implementado
* **Data:** 25/09/2026
* **Decisores:** Felipe Heitmann

---

## Contexto

A ingestão original do IRIS foi concebida exclusivamente sob o modo clássico `CopyStrategy`: leitura em chunks de 4MB com cálculo simultâneo de xxHash64, gravação no SSD, chamada de `os.fsync()` e releitura de destino para verificação cruzada.

Embora esse método seja à prova de falhas em cartões de memória lentos montados via USB 2.0/3.0, ele se tornava um gargalo quando o usuário transferia pastas de dezenas de gigabytes já localizadas dentro do mesmo disco físico ou em discos NVMe de alta velocidade:
1. O processo de cópia convencional duplicava temporariamente o uso de espaço em disco no SSD.
2. A velocidade média ficava limitada pela vazão de leitura e reescrita completa dos arquivos, levando vários minutos para concluir sessões grandes.

---

## Decisão

Implementamos o **Strategy Pattern** na etapa de ingestão (`IngestionStage`), permitindo que o usuário escolha entre duas estratégias no `config.yaml`:
- **`strategy: "copy"` (CopyStrategy clássica)**: Recomendada para cartões SD externos com conexão instável.
- **`strategy: "move"` (MoveStrategy multithreaded em 5 fases)**: Arquitetura acelerada que utiliza chamadas de sistema atômicas (`os.replace` ou `shutil.move`), executada nas seguintes fases:
  1. *Fase 1 (Planning)*: Varredura dos arquivos na origem.
  2. *Fase 2 (Deduplication)*: Comparação rápida por tamanho e hash prévio para não mover arquivos redundantes.
  3. *Fase 3 (Moving)*: Movimentação multithreaded via `ThreadPoolExecutor(max_workers=4)`. No mesmo sistema de arquivos, a movimentação é instantânea (apenas alteração de ponteiro de diretório no inode/MFT do SO).
  4. *Fase 4 (Verification)*: Hashing rápido executado diretamente no SSD de destino a velocidades de vários gigabytes por segundo.
  5. *Fase 5 (Cleanup)*: Remoção de diretórios residuais vazios na origem.

---

## Consequências

- **Positivas:** Em discos locais ou estações com SSD NVMe, a ingestão de 50GB caiu de mais de 8 minutos para menos de 45 segundos.
- **Salvaguardas:** Ambas as estratégias mantêm o axioma **Zero Data Loss**. O status `verified` só é concedido após o hash do arquivo no destino ser computado e gravado com sucesso no banco de dados SQLite.
