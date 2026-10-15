# Proposta 01: Eliminação do Fallback Silencioso para `unlink()` na Limpeza do Cartão SD

## Contexto e Localização do Problema

- **Arquivo**: [`src/modules/cleanup/stage.py`](file:///c:/code/IRIS/iris/src/modules/cleanup/stage.py)
- **Linhas Críticas**: 171-197
- **Princípio Afetado**: **Zero Data Loss**

### O Trecho de Código Atual

```python
# Double check no SSD
dest_path = Path(item.staging_path)
is_safe_to_delete = False

if dest_path.exists() and dest_path.stat().st_size == file_size:
    is_safe_to_delete = True
else:
    is_safe_to_delete = False

if is_safe_to_delete:
    live.update(generate_renderable(tracker, *render_args, "Limpando SD: Enviando para a lixeira..."))
    try:
        send2trash(str(orig_path))
        deleted_count += 1
        tracker.update(file_size)
    except Exception:
        try:
            orig_path.unlink()  # <-- PERIGO: Exclusão permanente direta na mídia de origem!
            deleted_count += 1
            tracker.update(file_size)
        except Exception:
            skipped_count += 1
            tracker.update(file_size)
```

---

## Diagnóstico da Causa-Raiz

1. **Incompatibilidade Arquitetural de `send2trash` com Mídias Removíveis no Windows**:
   - No sistema operacional Windows, unidades com sistemas de arquivos FAT32, exFAT ou mídias identificadas como `DRIVE_REMOVABLE` (como quase todos os cartões SD de câmeras e pen drives USB) **não possuem diretório de Lixeira** (`$RECYCLE.BIN`).
   - Quando `send2trash` é executado contra um caminho como `E:\DCIM\100CANON\IMG_0001.CR2`, a API do Windows falha imediatamente com exceção de sistema.
   - O código do IRIS intercepta qualquer exceção em um bloco genérico `except Exception:` e parte imediatamente para o `orig_path.unlink()`.

2. **Inobservância do Princípio *Zero Data Loss***:
   - O usuário configurou a limpeza com a premissa explícita de que os arquivos seriam enviados com segurança para a **Lixeira do SO**, permitindo restauração manual caso algo desse errado.
   - Em vez disso, o arquivo original do cartão de memória é **permanentemente destruído** sem aviso prévio.

3. **Dupla Checagem Frágil (Apenas `st_size`)**:
   - Antes da exclusão, a única validação executada é:
     ```python
     if dest_path.exists() and dest_path.stat().st_size == file_size:
     ```
   - Nenhum cálculo de hash (xxHash64) é realizado no momento da exclusão.
   - **Agravante com a Sanitização**: A etapa `SanitizationStage` altera arquivos JPEG em disco removendo metadados APP2/MPF e previews. Com isso, o tamanho do arquivo no SSD diminui. Se o cleanup for executado após a sanitização, a checagem `st_size == file_size` falha e o arquivo é pulado; mas se for executado antes, e o arquivo de destino estiver corrompido (com zeros ou ruído de mesmo tamanho), o original no SD é permanentemente apagado.

---

## Abordagens de Solução

### Abordagem A: "Fail-Safe Estrito" (Nunca Usar `unlink` na Origem)
**Conceito**: O IRIS **nunca** apaga arquivos com `unlink()` na mídia de origem. Se a unidade não suportar `send2trash`, a operação é abortada para aquele arquivo com aviso ao usuário.

- **Vantagens**:
  - Impossível perder dados originais da câmera por bug ou falha de disco.
  - Alinhamento 100% com as melhores práticas de fotografia (recomenda-se sempre formatar o cartão direto na câmera após validar os backups no PC).
- **Desvantagens**:
  - Usuários que desejam esvaziar o cartão via script precisarão formatar o cartão manualmente na câmera.
- **Configuração**: Nenhuma flag extra necessária; torna-se o comportamento padrão.

---

### Abordagem B: "Hash-Guarded com Confirmação Explícita de Drive Removível" (Padrão Recomendado)
**Conceito**: O IRIS verifica se a mídia de origem suporta Lixeira. Caso não suporte e `send2trash` falhe:
1. Em modo sequencial automático (`auto_clean=True`): **RECUSA** a exclusão permanente a menos que uma flag explícita `modules.cleanup.allow_permanent_sd_clean: true` esteja configurada no `config.yaml`.
2. Em modo interativo: Mostra um modal vermelho na CLI avisando claramente: `[AVISO] A unidade E: (Cartão SD) não suporta Lixeira. Deseja excluir PERMANENTEMENTE os arquivos originais?`
3. Imediatamente antes de qualquer `unlink()`, calcula o `xxHash64` do arquivo de destino no SSD e confere com o `item.file_hash` registrado na ingestão. Se divergir, aborta imediatamente.

- **Vantagens**:
  - Flexibilidade para quem realmente quer liberar espaço no SD card.
  - Segurança matemática garantida por validação de hash em tempo real antes da exclusão.
- **Desvantagens**:
  - Pequeno overhead de leitura de hash caso a verificação seja feita em todos os arquivos no momento da limpeza.

---

### Abordagem C: "Quarentena Local / Staging Hold"
**Conceito**: Em vez de mexer no SD card, o IRIS marca os itens no banco de dados como `ready_for_sd_wipe`. Cria-se um comando dedicado `iris sd-wipe` que roda um checklist pré-formatação com relatório de integridade total dos arquivos já salvos nos discos definitivos.

- **Vantagens**:
  - Desacopla a limpeza do pipeline sequencial diário.
  - Gera um relatório para conferência antes de liberar o cartão.
- **Desvantagens**:
  - Adiciona uma etapa manual para o usuário.

---

## Tabela Comparativa

| Critério | Atual (Falho) | Abordagem A | Abordagem B (Recomendada) | Abordagem C |
| :--- | :---: | :---: | :---: | :---: |
| **Risco de Perda de Dados** | 🔴 Muito Alto | 🟢 Zero | 🟢 Praticamente Zero | 🟢 Zero |
| **Conferência de Hash em Tempo Real** | ❌ Não | N/A | ✅ Sim | ✅ Sim |
| **Compatibilidade com SD Cards** | ⚠️ Destrutiva | ⚠️ Requer Formatação | ✅ Automática e Segura | ⚠️ Fluxo Separado |
| **Complexidade de Implementação** | — | Baixa (10 linhas) | Média (40 linhas) | Média |

---

## Esboço de Código da Solução Recomendada (Abordagem B)

```python
# Em src/modules/cleanup/stage.py

from src.modules.ingestion.strategies.base import compute_file_hash

allow_permanent = config.get("modules.cleanup.allow_permanent_sd_clean", False)

for orig_path, item in items_to_delete:
    file_size = orig_path.stat().st_size
    dest_path = Path(item.staging_path)

    # 1. Validação física no SSD
    if not dest_path.exists():
        skipped_count += 1
        continue

    # 2. Se sanitização alterou o tamanho, o hash do banco reflete o novo arquivo.
    # Para o arquivo da origem, comparamos com o hash original ingerido:
    source_hash_ok = (compute_file_hash(orig_path) == item.file_hash)
    if not source_hash_ok:
        console.print(f"[red]AVISO: Hash da origem não confere para {orig_path.name}. Preservando.[/red]")
        skipped_count += 1
        continue

    # 3. Tentativa primária: Lixeira do SO
    try:
        send2trash(str(orig_path))
        deleted_count += 1
        tracker.update(file_size)
    except Exception as trash_err:
        # Se falhou e unidade não tem lixeira:
        if allow_permanent:
            try:
                orig_path.unlink()
                deleted_count += 1
                tracker.update(file_size)
            except Exception as unlink_err:
                skipped_count += 1
        else:
            console.print(f"[yellow]Drive sem Lixeira. '{orig_path.name}' preservado (allow_permanent_sd_clean=false).[/yellow]")
            skipped_count += 1
```
