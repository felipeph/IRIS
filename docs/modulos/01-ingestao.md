# Módulo 01: Ingestão Segura de Mídias (`ingestion`)

O estágio de Ingestão (`IngestionStage`) é a porta de entrada de todo o sistema IRIS. Seu papel é transferir com 100% de integridade as mídias presentes em cartões SD, pendrives ou pastas externas para a área de preparação do projeto (*staging area*) em `1_Entrada/<projeto>/`.

---

## 1. Responsabilidades do Módulo

1. Escanear recursivamente o diretório de origem identificando arquivos suportados (fotos RAW, JPEGs, vídeos MP4/MOV).
2. Transferir os arquivos para o SSD sem corromper timestamps originais nem atributos de arquivo.
3. Computar o hash de integridade `xxHash64` para cada arquivo transferido.
4. Registrar o arquivo no banco de dados SQLite do projeto (`<projeto>.db`) com status `verified = 1`.
5. Apresentar no terminal barras de progresso interativas com taxa de transferência (MB/s) e tempo restante estimado.

---

## 2. Estratégias Disponíveis (Strategy Pattern)

O módulo implementa o **Strategy Pattern**, permitindo alternar entre dois motores de ingestão através do parâmetro `modules.ingestion.strategy` no `config.yaml`:

```mermaid
graph TD
    A["Início da Ingestão"] --> B{"Estratégia Configurada?"}
    
    B -->|copy (Padrão para Cartão SD)| C["CopyStrategy:\nCópia Chunkada em RAM (4MB)\n+ xxHash64 Simultâneo\n+ os.fsync() + Releitura no SSD"]
    
    B -->|move (Padrão para SSD Local)| D["MoveStrategy:\nMultithreaded 5 Fases\n+ Deduplicação Prévia\n+ os.replace() atômico\n+ Hashing Pós-Movimentação no SSD"]
    
    C --> E[("Registra no SQLite do Projeto\n(status: verified=1)")]
    D --> E
```

---

## 3. Modo `copy`: CopyStrategy (Copy & Verify com Hash Simultâneo)

Esta estratégia é calibrada para suportes de gravação lentos ou com conexões físicas vulneráveis (leitores USB de cartões SD).

### O Algoritmo de Cópia em 2 Passadas:
1. Um buffer de **4MB** é alocado na memória RAM.
2. O arquivo de origem é lido bloco a bloco.
3. Para cada bloco lido:
   - Os bytes são enviados ao hasher `xxhash.xxh64()`.
   - Os mesmos bytes são escritos no arquivo de destino no SSD.
4. Ao término da leitura da origem, o hash original já está concluído.
5. É disparado o comando `os.fsync(dest_fd)` para forçar a controladora física a descarregar os buffers de escrita.
6. O arquivo recém-gravado no SSD de destino é reaberto e lido integralmente para calcular o hash de destino.
7. Se os hashes forem idênticos, o arquivo é gravado no SQLite como `verified = 1`.

---

## 4. Modo `move`: MoveStrategy (Movimentação Acelerada em 5 Fases)

Desenvolvida para máxima velocidade em discos de alta velocidade ou movimentações locais no mesmo volume:

- **Fase 1 (Planning):** Varredura dos arquivos na origem montando o catálogo inicial na memória.
- **Fase 2 (Deduplication):** Consulta de duplicatas por tamanho e hash rápido prévio, impedindo o reprocessamento de arquivos já ingeridos.
- **Fase 3 (Moving):** Movimentação paralela via `ThreadPoolExecutor(max_workers=4)`. Quando origem e destino residem no mesmo sistema de arquivos do Windows (ex: NTFS), a chamada `os.replace` executa em **milissegundos**, apenas atualizando as entradas da Master File Table (MFT).
- **Fase 4 (Verification):** O cálculo do hash `xxHash64` ocorre diretamente no SSD de destino, aproveitando velocidades de barramento de múltiplos gigabytes por segundo.
- **Fase 5 (Cleanup):** Higienização de diretórios vazios residuais deixados na pasta de origem.

---

## 5. Esquema de Persistência na Tabela `files`

A cada arquivo validado, a seguinte linha é persistida no banco do projeto:

```sql
INSERT INTO files (
    original_path,
    staging_path,
    size_bytes,
    xxhash64,
    verified,
    category
) VALUES (?, ?, ?, ?, 1, 'unknown');
```

Caso a execução seja interrompida (queda de energia ou `Ctrl+C`), ao reiniciar o projeto o IRIS detecta os arquivos que já possuem `verified = 1` e retoma a transferência exatamente a partir do primeiro arquivo pendente, **sem regravar nada em duplicidade**.
