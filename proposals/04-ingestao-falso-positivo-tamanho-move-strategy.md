# Proposta 04: Correção do Falso Positivo de Arquivo Idêntico por Tamanho em Bytes (`MoveStrategy`)

## Contexto e Localização do Problema

- **Arquivo**: [`src/modules/ingestion/strategies/move_strategy.py`](file:///c:/code/IRIS/iris/src/modules/ingestion/strategies/move_strategy.py)
- **Linhas Críticas**: 28-53 (`_resolve_collision`) e 93-111 (`execute`)
- **Princípio Afetado**: **Zero Data Loss e Integridade de Ingestão**

### O Trecho de Código Atual

```python
def _resolve_collision(self, target_path: Path, src_size: int) -> tuple[Path, bool]:
    """Resolve colisões de nomes no destino. Retorna (target_path_resolvido, is_identical)."""
    if not target_path.exists():
        return target_path, False

    # Se já existe arquivo no destino com mesmo tamanho, considera idêntico
    if target_path.stat().st_size == src_size:
        return target_path, True  # <-- FALHA GRAVE: Presunção cega de identidade!

    # Se existe com tamanho diferente, gera sufixo incremental (_1, _2...)
    base_stem = target_path.stem
    suffix = target_path.suffix
    parent_dir = target_path.parent
    counter = 1
    
    while True:
        candidate = parent_dir / f"{base_stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate, False
        if candidate.stat().st_size == src_size:
            return candidate, True
        counter += 1
```

E no loop principal da Fase 3 de Ingestão:

```python
resolved_target, is_identical = self._resolve_collision(target_candidate, src_size)

if is_identical:
    # Arquivo idêntico já presente no destino
    already_ingested_bytes += src_size
    if not db_item or not db_item.verified:
        file_hash = db_item.file_hash if (db_item and db_item.file_hash) else compute_file_hash(resolved_target)
        item = ProjectItem(
            original_path=orig_key,
            staging_path=str(resolved_target.resolve()),
            status="copied",
            file_size_bytes=src_size,
            file_hash=file_hash,
            verified=True
        )
        project.save_item(item)
    continue  # <-- O arquivo da origem NUNCA é movido nem copiado!
```

---

## Diagnóstico da Causa-Raiz

1. **A Falácia do "Mesmo Tamanho = Mesmo Arquivo" na Fotografia**:
   - Em câmeras digitais modernas (Canon, Sony, Nikon, GoPro):
     - Arquivos **RAW não comprimidos** têm **exatamente o mesmo tamanho em bytes** para todas as fotos tiradas com o mesmo sensor (ex: um sensor de 24MP sempre gera arquivos de exatamente 24.576.000 bytes ou similar).
     - Fotos tiradas em modo burst (rajada) ou timelapses com cena estática frequentemente geram arquivos JPEG com tamanhos idênticos até o último byte.
   - Suponha que no dia 01 foi ingerido o arquivo `IMG_0001.CR2` (foto de uma flor, 24.576.000 bytes).
   - No dia 02, o cartão da câmera reiniciou o contador e gravou um novo `IMG_0001.CR2` (foto da Lua, exatamente 24.576.000 bytes).
   - O IRIS detecta que `target_path.stat().st_size == src_size`, marca `is_identical = True`, e **ignora a foto da Lua**! A foto nunca entra no pipeline e é descartada.

2. **Distorção no Banco de Dados**:
   - Pior ainda: o novo item do dia 02 é registrado no SQLite como apontando para a foto antiga do dia 01 (`staging_path=resolved_target`). O sistema perde a rastreabilidade real da foto nova.

---

## Abordagens de Solução

### Abordagem A: "Confirmação Obrigatória por xxHash64 em Caso de Colisão de Tamanho" (Recomendada)
**Conceito**: O teste de tamanho continua sendo um filtro rápido inicial (se tamanhos forem diferentes, certamente os arquivos são diferentes). Porém, **se os tamanhos forem idênticos**, calcula-se o hash xxHash64 do arquivo da origem e do destino para confirmar matematicamente se são o mesmo conteúdo.

```python
if target_path.stat().st_size == src_size:
    # Tamanhos idênticos: tira a prova real com hash ultra-rápido (xxHash64)
    if compute_file_hash(src_path) == compute_file_hash(target_path):
        return target_path, True
    # Se os hashes forem diferentes, NÃO é idêntico: gera sufixo _1, _2...
```

- **Vantagens**:
  - Elimina 100% dos falsos positivos.
  - Como colisões de nome exato acontecem apenas para uma minoria de arquivos, o impacto de performance é desprezível.
  - Preserva a velocidade turbo do `MoveStrategy`.
- **Desvantagens**:
  - Exige ler o arquivo do cartão SD caso haja colisão de nome e tamanho para calcular o hash da origem.

---

### Abordagem B: "Pre-Hash Rápido Head & Tail (Cabeçalho + Rodapé) + Hash Completo"
**Conceito**: Em arquivos RAW de 30MB-50MB, ler o arquivo inteiro do cartão SD pode levar 500ms. Um pré-teste lendo apenas os primeiros 64KB (onde ficam metadados EXIF e timestamp da captura) e os últimos 64KB descarta mais de 99.9% dos arquivos falsamente idênticos em menos de 1ms:
1. Se `st_size` for igual: compara os primeiros 64KB. Se diferirem $\rightarrow$ arquivos distintos, gera `_1`.
2. Se os primeiros 64KB forem iguais: calcula o xxHash64 completo para confirmação definitiva.

- **Vantagens**:
  - Ultra rápido mesmo em cartões SD lentos (USB 2.0).
  - Segurança matemática final idêntica à Abordagem A.
- **Desvantagens**:
  - Código ligeiramente mais extenso para ler os chunks iniciais e finais.

---

### Abordagem C: "Desativar Deduplicação por Conteúdo no Staging (Estrutura Estrita por Timestamp)"
**Conceito**: O staging de entrada (`1_Entrada`) nunca deve tentar deduplicar arquivos por conteúdo. A função do staging é apenas trazer o que está na mídia com fidelidade. Se houver nomes iguais, resolve puramente com sufixo ou inclui a subpasta relativa da origem (ex: `100CANON/IMG_0001.JPG`). A deduplicação real é postergada para a etapa de Organização (`OrganizeStage`).

- **Vantagens**:
  - Separação clara de responsabilidades: Ingestão apenas move dados; Organização cuida de deduplicação.
- **Desvantagens**:
  - Pode ocupar mais espaço temporário no SSD se o usuário reinserir o mesmo cartão várias vezes sem limpá-lo.

---

## Tabela Comparativa

| Critério | Atual (Perigoso) | Abordagem A (xxHash64) | Abordagem B (Head/Tail + Hash) | Abordagem C (Apenas Sufixo) |
| :--- | :---: | :---: | :---: | :---: |
| **Garantia de Não Perder Fotos** | ❌ Não | 🟢 100% | 🟢 100% | 🟢 100% |
| **Velocidade em SD Lento** | 🟢 Imediata | 🟡 Razoável se houver colisão | 🟢 Ultra rápida | 🟢 Imediata |
| **Integridade do Banco SQLite** | ❌ Corrompida | 🟢 Correta | 🟢 Correta | 🟢 Correta |
| **Complexidade** | — | Baixa (10 linhas) | Média (25 linhas) | Baixa (8 linhas) |

---

## Implementação Recomendada (Abordagem A)

```python
# Em src/modules/ingestion/strategies/move_strategy.py

def _resolve_collision(self, src_path: Path, target_path: Path, src_size: int) -> tuple[Path, bool]:
    """
    Resolve colisões de nomes no destino.
    Retorna (target_path_resolvido, is_identical).
    """
    if not target_path.exists():
        return target_path, False

    # Se já existe arquivo no destino com mesmo tamanho:
    if target_path.stat().st_size == src_size:
        # Tira a prova real calculando o hash de ambos
        if compute_file_hash(src_path) == compute_file_hash(target_path):
            return target_path, True

    # Se tamanho ou conteúdo forem diferentes, gera sufixo incremental (_1, _2...)
    base_stem = target_path.stem
    suffix = target_path.suffix
    parent_dir = target_path.parent
    counter = 1
    
    while True:
        candidate = parent_dir / f"{base_stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate, False
            
        if candidate.stat().st_size == src_size:
            if compute_file_hash(src_path) == compute_file_hash(candidate):
                return candidate, True
                
        counter += 1
```
