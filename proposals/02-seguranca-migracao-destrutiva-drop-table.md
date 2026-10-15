# Proposta 02: Eliminação de Migração Destrutiva com `DROP TABLE` no Banco de Dados do Projeto

## Contexto e Localização do Problema

- **Arquivo**: [`src/core/project.py`](file:///c:/code/IRIS/iris/src/core/project.py)
- **Linhas Críticas**: 204-211
- **Princípio Afetado**: **Zero Data Loss** e **Integridade Histórica**

### O Trecho de Código Atual

```python
def _init_project_db(self):
    with get_db_connection(self._project_db_file) as conn:
        cursor = conn.cursor()
        
        # Destructive migration: Se houver coluna metadata_json, deleta a tabela!
        try:
            cursor.execute("SELECT metadata_json FROM items LIMIT 1")
            cursor.execute("DROP TABLE items")
            conn.commit()
        except sqlite3.OperationalError:
            pass
```

---

## Diagnóstico da Causa-Raiz

1. **Origem do Código (Hack Temporário de Desenvolvimento)**:
   - Em iterações iniciais da arquitetura do IRIS, a tabela `items` armazenava os metadados fotográficos condensados em uma única coluna JSON chamada `metadata_json`.
   - Posteriormente, o modelo evoluiu para colunas relacionais normalizadas (`meta_is_video`, `meta_date_str`, `meta_camera_model`, `meta_focal_length_equiv`, etc.) para permitir indexação e consultas diretas mais rápidas.
   - Em vez de implementar uma migração formal que lesse o JSON antigo e preenchesse as novas colunas, foi incluído um trecho de conveniência que simplesmente **apaga a tabela inteira (`DROP TABLE items`)** caso detecte a coluna legada.

2. **Impacto e Risco em Produção**:
   - Se o usuário tentar abrir um projeto anterior que foi gravado nesse formato intermediário, ou se restaurar um backup de projeto de semanas atrás, **todos os registros de itens ingeridos, hashes, status de verificação e caminhos organizados serão sumariamente deletados**.
   - Como o SQLite executa DDLs imediatamente, a destruição do estado é irreversível para aquele banco local sem um backup externo.

---

## Abordagens de Solução

### Abordagem A: "Migração em Memória com Shadow Table (Cutover Atômico)"
**Conceito**: Em vez de descartar a tabela antiga, cria-se uma tabela temporária `items_v2`, migram-se os dados convertendo o JSON antigo para as colunas normalizadas e executa-se a troca atômica.

```sql
-- 1. Cria tabela com novo esquema
CREATE TABLE IF NOT EXISTS items_v2 (...);

-- 2. Copia dados
-- (Realizado via script Python lendo metadata_json e inserindo em items_v2)

-- 3. Transição segura
DROP TABLE items;
ALTER TABLE items_v2 RENAME TO items;
```

- **Vantagens**:
  - Preserva 100% dos dados legados.
  - A operação é atômica dentro de uma transação SQLite.
- **Desvantagens**:
  - Requer código de migração que sabe deserializar o JSON antigo.

---

### Abordagem B: "Remoção Imediata do `DROP TABLE` + Migração `PRAGMA table_info`" (Recomendada para Simplicidade)
**Conceito**: Se todos os projetos ativos do usuário já estão no novo esquema e não há necessidade de suportar bancos de rascunho muito antigos, remove-se completamente as 6 linhas do `DROP TABLE`. Adicionalmente, verifica-se colunas ausentes usando `PRAGMA table_info(items)` e emite-se apenas `ALTER TABLE items ADD COLUMN ...`.

- **Vantagens**:
  - Corrige o risco de segurança em 3 minutos.
  - Elimina uma consulta de introspecção desnecessária a cada inicialização de conexão.
- **Desvantagens**:
  - Se algum banco realmente tiver apenas a coluna `metadata_json`, gerará erro de coluna ausente até ser migrado manualmente ou recriado.

---

### Abordagem C: "Controle Formal de Versão do Esquema com `PRAGMA user_version`" (Padrão Arquitetural Enterprise)
**Conceito**: Utiliza o recurso nativo do SQLite `PRAGMA user_version` para versionar o banco de dados do projeto:
- Versão 0: Criação inicial
- Versão 1: Schema antigo com `metadata_json`
- Versão 2: Schema normalizado com 25 colunas
- Versão 3: Adição de índices

Ao conectar, o IRIS checa `PRAGMA user_version` e executa um pipeline ordenado de migrações (`migration_v1_to_v2`, `migration_v2_to_v3`).

- **Vantagens**:
  - Padrão da indústria para SQLite em Python (similar ao Alembic/Django Migrations, mas ultra leve).
  - Torna futuras adições de colunas e índices completamente determinísticas e testáveis.
- **Desvantagens**:
  - Exige estruturar um pequeno módulo de migração (`src/core/migrations.py`).

---

## Tabela Comparativa

| Critério | Atual (Inaceitável) | Abordagem A (Shadow Table) | Abordagem B (Remoção + PRAGMA) | Abordagem C (user_version) |
| :--- | :---: | :---: | :---: | :---: |
| **Risco de Perda de Dados** | 🔴 100% se achar coluna | 🟢 Zero | 🟢 Zero | 🟢 Zero |
| **Preservação de Dados Legados** | ❌ Não | ✅ Sim | ⚠️ Requer schema novo | ✅ Sim (Determinístico) |
| **Complexidade** | — | Média (30 linhas) | Baixa (remover 6 linhas) | Média/Alta (60 linhas) |
| **Escalabilidade Futura** | ❌ Frágil | ⚠️ Manual | ⚠️ Ad-hoc | 🟢 Excelente |

---

## Recomendação

Para o momento atual do IRIS:
1. **Passo Imediato**: Adotar a **Abordagem B** removendo imediatamente as linhas de `DROP TABLE items` de `_init_project_db()`.
2. **Passo Arquitetural**: Implementar a **Abordagem C** (`PRAGMA user_version`) no âmbito da refatoração da camada de banco de dados (ver Proposta 09).

### Código Recomendado para Correção Imediata

```python
# Em src/core/project.py

def _init_project_db(self):
    with get_db_connection(self._project_db_file) as conn:
        cursor = conn.cursor()
        
        # Cria a tabela de itens se não existir
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items (
                original_path TEXT PRIMARY KEY,
                staging_path TEXT,
                status TEXT,
                file_size_bytes INTEGER,
                file_hash TEXT,
                verified INTEGER,
                meta_is_video INTEGER,
                meta_date_str TEXT,
                meta_time_str TEXT,
                meta_timestamp TEXT,
                meta_camera_model TEXT,
                meta_camera_make TEXT,
                meta_focal_length_equiv REAL,
                meta_focal_str TEXT,
                meta_aperture_str TEXT,
                meta_shutter_str TEXT,
                meta_iso_str TEXT,
                meta_resolution_str TEXT,
                meta_fps_str TEXT,
                meta_duration_str TEXT,
                meta_original_stem TEXT,
                meta_extension TEXT,
                meta_is_raw INTEGER,
                meta_width INTEGER,
                meta_height INTEGER,
                category TEXT DEFAULT '',
                target_filename TEXT DEFAULT '',
                relative_dest_dir TEXT DEFAULT '',
                extra_dest_dirs_json TEXT DEFAULT '[]',
                organized_path TEXT DEFAULT '',
                extra_organized_paths_json TEXT DEFAULT '[]'
            )
        """)
        # Migração não destrutiva de colunas extras caso o schema seja antigo
        cursor.execute("PRAGMA table_info(items)")
        cols = {row[1] for row in cursor.fetchall()}
        
        if "category" not in cols:
            cursor.execute("ALTER TABLE items ADD COLUMN category TEXT DEFAULT ''")
        if "target_filename" not in cols:
            cursor.execute("ALTER TABLE items ADD COLUMN target_filename TEXT DEFAULT ''")
        if "organized_path" not in cols:
            cursor.execute("ALTER TABLE items ADD COLUMN organized_path TEXT DEFAULT ''")
            
        conn.commit()
```
