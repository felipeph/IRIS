# Proposta 08: Sincronização Transacional e Reconciliação do Duplo Banco de Dados SQLite

> **Status**: [CONCLUÍDA] Implementada transação atômica via SQLite `ATTACH DATABASE` (dual-write atômico em única conexão) e serviço de auto-cura/reconciliação bidirecional (`reconcile_project_with_central` e `reconcile_all_projects_with_central`).

## Contexto e Localização do Problema

- **Arquivo Principal**: [`src/core/project.py`](file:///c:/code/IRIS/iris/src/core/project.py) (linhas 10-143, 456-570, 708-854 e 890-1269)
- **Princípio Afetado**: **Consistência de Estado (ACID) e Single Source of Truth**

### O Trecho de Código Atual

```python
# Em src/core/project.py

def save_timelapse(self, record: dict):
    # 1. Grava no banco local do projeto
    with get_db_connection(self._project_db_file) as conn:
        cursor.execute("INSERT INTO timelapses ...")
        conn.commit()  # <-- Transação 1 concluída
        
    # 2. Grava no banco central
    save_central_timelapse(record_copy)  # <-- Transação 2 independente
```

E no caso de uploads para o YouTube:
```python
def update_timelapse_youtube(self, video_path: str, video_id: str, url: str):
    with get_db_connection(self._project_db_file) as conn:
        cursor.execute("UPDATE timelapses SET youtube_video_id=? ...")
        conn.commit()
    update_central_timelapse_youtube(video_path, video_id, url)
```

---

## Diagnóstico da Causa-Raiz

1. **Ausência de Atomicidade Distribuída (Split-Brain em Potencial)**:
   - O IRIS adota uma arquitetura de banco de dados duplo:
     1. **Banco do Projeto** (`~/.iris/projects/{nome_projeto}.db`): Armazena itens individuais de mídia e registros gerados daquele projeto.
     2. **Banco Central** (`~/.iris/projects/iris_central.db`): Atua como agregador global de todos os projetos, vídeos editados, timelapses e sessões de astrofotografia para buscas globais e controle histórico.
   - A escrita nesses dois bancos é feita de forma **sequencial desvinculada**:
     - Primeiro faz commit no banco local;
     - Depois abre outra conexão e faz commit no banco central.
   - Se o processo for interrompido entre as duas chamadas (queda de energia, fechamento forçado da janela do terminal, exceção inesperada ou timeout de lock do SQLite no central):
     - O banco local é atualizado, mas o central fica desatualizado;
     - Os bancos entram em **estado dessincronizado permanente**.
   - Não existe hoje nenhum mecanismo de reconciliação, sincronização em segundo plano ou reparo na inicialização.

2. **Duplicação Maciça de DDL e Esquemas**:
   - As tabelas `timelapses`, `edited_videos`, `astro_stacks` e `astro_sharpens` têm suas estruturas e scripts de migração (`ALTER TABLE`) **duplicados linha por linha** em `init_central_db()` e `_init_project_db()`.
   - Manter dois esquemas idênticos manualmente em 1.200 linhas de código é uma fonte contínua de bugs de manutenção.

---

## Abordagens de Solução

### Abordagem A: "Transação Atômica Cruzada via SQLite `ATTACH DATABASE`" (Recomendada para Consistência Imediata)
**Conceito**: O SQLite suporta nativamente conectar múltiplos arquivos de banco em uma única sessão através do comando `ATTACH DATABASE`. Isso permite que uma **única transação atômica** (`BEGIN TRANSACTION ... COMMIT`) atualize tanto o banco do projeto quanto o banco central simultaneamente:

```sql
ATTACH DATABASE 'C:/Users/.../.iris/projects/iris_central.db' AS central;

BEGIN TRANSACTION;
  -- Atualiza banco local
  INSERT INTO main.timelapses (...) VALUES (...);
  -- Atualiza banco central
  INSERT INTO central.timelapses (...) VALUES (...);
COMMIT;
```
Se qualquer erro ocorrer durante a escrita no central, o SQLite faz **rollback em ambos os arquivos automaticamente**!

- **Vantagens**:
  - Garantia ACID matemática real entre os dois arquivos sem precisar de complexos coordenadores de transação (2PC).
  - Mantém a separação física atual de arquivos (`{projeto}.db` + `iris_central.db`).
- **Desvantagens**:
  - Requer que o caminho do banco central esteja acessível na mesma conexão SQLite.

---

### Abordagem B: "Serviço de Reconciliação e Auto-Cura (`ProjectSyncService`)" (Recomendada para Resiliência)
**Conceito**: Mantém as conexões separadas, mas cria um módulo de sincronização com base na coluna `updated_at`:
1. Ao abrir qualquer projeto (`get_project(name)`), ou através de um comando CLI `iris sync`, o IRIS compara os registros entre `{projeto}.db` e `iris_central.db`.
2. Registros mais recentes em um banco sobrescrevem versões defasadas no outro automaticamente.

- **Vantagens**:
  - Resolve discrepâncias acumuladas do passado.
  - Permite recuperar o banco central mesmo se ele for deletado (ele é reconstruído a partir dos bancos de projeto existentes).
- **Desvantagens**:
  - Não impede a breve inconsistência transitória no momento da falha, apenas repara na próxima execução.

---

### Abordagem C: "Consolidação em Banco Único Central com Particionamento Lógico" (Visão Arquitetural Definitiva)
**Conceito**: Questionar a necessidade de ter dezenas de arquivos `.db` separados. O SQLite em modo WAL suporta bancos de terabytes com facilidade.
- Todas as tabelas (`items`, `timelapses`, etc.) residem exclusivamente em `iris_central.db`, todas com a chave `project_name`.
- Se o usuário quiser exportar um projeto individual para backup ou arquivo externo, o IRIS exporta uma cópia filtrada sob demanda (`iris export-project`).

- **Vantagens**:
  - Elimina 100% dos problemas de sincronização (existe apenas uma fonte da verdade).
  - Reduz o código de persistência em mais de 600 linhas.
  - Consultas analíticas entre projetos tornam-se triviais.
- **Desvantagens**:
  - Mudança arquitetural maior: exige migrar os projetos antigos para o banco unificado.

---

## Tabela Comparativa

| Critério | Atual (Inconsistente) | Abordagem A (ATTACH Transacional) | Abordagem B (Reconciliação Sync) | Abordagem C (Banco Unificado) |
| :--- | :---: | :---: | :---: | :---: |
| **Garantia ACID Atômica** | ❌ Não | 🟢 100% Sim | ⚠️ Eventual (reparada) | 🟢 100% Sim |
| **Recuperação de Desastres** | ❌ Não | ⚠️ Manual | 🟢 Automática (`iris sync`) | 🟢 Backup único |
| **Linhas de Código Duplicadas** | ~500 linhas | ~450 linhas | ~400 linhas | **0 linhas (cai 600)** |
| **Impacto de Migração** | — | Baixo (transparente) | Baixo (aditivo) | Alto (requer migrador) |

---

## Implementação Recomendada (Abordagem A + B)

A união do `ATTACH DATABASE` para as gravações diárias com uma função de auto-cura no boot oferece o melhor dos dois mundos:

```python
# Em src/core/project.py

def get_attached_project_connection(project_db_path: Path, central_db_path: Path) -> sqlite3.Connection:
    """Retorna conexão com o banco do projeto e o central anexado na mesma sessão transacional."""
    conn = get_db_connection(project_db_path)
    # Anexa o banco central com alias 'central'
    conn.execute(f"ATTACH DATABASE ? AS central;", (str(central_db_path.resolve()),))
    return conn

def save_timelapse_atomic(self, record: dict):
    """Grava o timelapse no banco local e central em uma transação atômica única."""
    self._ensure_db_initialized()
    with get_attached_project_connection(self._project_db_file, CENTRAL_DB_PATH) as conn:
        cursor = conn.cursor()
        
        # 1. Grava no banco local (main)
        cursor.execute("INSERT INTO main.timelapses (...) VALUES (...) ON CONFLICT(...) ...", params)
        
        # 2. Grava no banco central na MESMA transação
        cursor.execute("INSERT INTO central.timelapses (...) VALUES (...) ON CONFLICT(...) ...", central_params)
        
        # Se qualquer um dos dois falhar, ambos sofrem rollback automático
        conn.commit()
```
