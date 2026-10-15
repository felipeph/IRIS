# Proposta 03: Correção de Race Condition no Bloqueio Exclusivo (`ProjectLock`)

> **Status**: ✅ **Implementada (Abordagem A: Criação Atômica Exclusiva via Kernel)**  
> **Data de Conclusão**: 15/10/2026  
> **Branch**: `fix/concurrency-race-condition-project-lock`

## Contexto e Localização do Problema

- **Arquivo**: [`src/core/lock.py`](file:///c:/code/IRIS/iris/src/core/lock.py)
- **Linhas Críticas**: 82-133 (`acquire` method)
- **Princípio Afetado**: **Isolamento de Concorrência e Integridade de Dados**

### O Trecho de Código Atual

```python
def acquire(self) -> bool:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    current_pid = os.getpid()

    if self.lock_file.exists():
        info = self.get_lock_info()
        if info:
            owner_pid = info.get("pid", 0)
            if owner_pid == current_pid:
                self._is_acquired = True
                return True
                
            if is_pid_alive(owner_pid):
                raise ProjectLockedError(self.project_name, info)
            else:
                self.lock_file.unlink(missing_ok=True)

    # Gravação atômica do lock
    lock_data = {
        "project_name": self.project_name,
        "pid": current_pid,
        "hostname": socket.gethostname(),
        "acquired_at": datetime.now().isoformat()
    }

    temp_lock = PROJECTS_DIR / f"{self.project_name}.lock.{current_pid}.tmp"
    try:
        with open(temp_lock, "w", encoding="utf-8") as f:
            json.dump(lock_data, f, indent=2)
        os.replace(temp_lock, self.lock_file)  # <-- FALHA: os.replace sobrescreve o arquivo de destino silenciosamente!
        self._is_acquired = True
        return True
```

---

## Diagnóstico da Causa-Raiz

1. **Vulnerabilidade de Time-of-Check to Time-of-Use (TOCTOU)**:
   - O código verifica se `self.lock_file.exists()`.
   - Se duas instâncias do IRIS forem iniciadas quase simultaneamente (ex: um script chamando o IRIS ou o usuário abrindo dois terminais):
     - **T0**: Processo A verifica `lock_file.exists()` $\rightarrow$ `False`.
     - **T1**: Processo B verifica `lock_file.exists()` $\rightarrow$ `False`.
     - **T2**: Processo A cria `temp_lock` e chama `os.replace(temp_lock, self.lock_file)`. Processo A obtém a posse do lock.
     - **T3**: Processo B cria seu `temp_lock` e chama `os.replace(temp_lock, self.lock_file)`.
     - **Consequência**: No Windows e no Linux/POSIX, a especificação de `os.replace` determina que **o arquivo de destino deve ser substituído silenciosamente e atomicamente** se já existir. O lock do Processo A é sumariamente sobrescrito pelos dados do Processo B!
   - Ambos os processos acreditam que adquiriram o lock com sucesso.

2. **Impacto no Sistema**:
   - Duas instâncias operando no mesmo projeto causam:
     - Escritas concorrentes no mesmo arquivo SQLite (`database is locked` / timeouts de WAL).
     - Colisão física de arquivos na pasta de staging (`1_Entrada/{projeto}/raw`).
     - Execução simultânea de encoders FFmpeg ou do PlanetarySystemStacker consumindo 100% de CPU/GPU e abortando tarefas.

---

## Abordagens de Solução

### Abordagem A: "Criação Atômica Exclusiva via Kernel (`os.O_CREAT | os.O_EXCL`)" (Recomendada)
**Conceito**: Em vez de gravar em arquivo temporário e usar `os.replace`, cria-se o arquivo de lock diretamente através da chamada de baixo nível do sistema operacional com a flag de exclusão mútua:

```python
import os
import json

flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
try:
    fd = os.open(str(self.lock_file), flags, 0o644)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(lock_data, f)
    self._is_acquired = True
except FileExistsError:
    # O arquivo JÁ existia antes! Kernel garantiu que ninguém sobrescreveu.
    # Aqui fazemos a checagem se o PID proprietário ainda está vivo.
```

- **Vantagens**:
  - Garantia atômica direta pelo kernel do SO (Windows e POSIX).
  - Impossível haver race condition: se dois processos tentarem ao mesmo nanossegundo, exatamente um receberá sucesso e o outro receberá `FileExistsError`.
  - Simples de implementar e totalmente compatível com a estrutura atual de arquivo JSON.
- **Desvantagens**:
  - Requer lidar com limpeza de lock órfão (se o PID anterior morreu, apaga e tenta abrir com `os.O_EXCL` novamente).

---

### Abordagem B: "Kernel File Lock Nativo (`msvcrt` no Windows / `fcntl` no Linux)"
**Conceito**: O arquivo de lock permanece aberto por um descritor de arquivo mantido pelo processo enquanto ele estiver vivo. O sistema operacional aplica uma trava no arquivo:
- No Windows: `msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)`
- No Linux/macOS: `fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)`

- **Vantagens**:
  - **Auto-recuperação perfeita de locks órfãos**: Se o processo do IRIS for encerrado abruptamente por `SIGKILL`, queda de energia ou fechamento de janela, o próprio kernel do Windows fecha o handle e **libera a trava imediatamente**.
  - Não há necessidade de consultar PID ou heurística de processo vivo (`is_pid_alive`).
- **Desvantagens**:
  - O descritor de arquivo deve ser mantido aberto durante toda a vida útil da execução do projeto.
  - Exige ramificação de código por sistema operacional (`if sys.platform == "win32"`).

---

### Abordagem C: "Tabela de Bloqueios no `iris_central.db`"
**Conceito**: Remove completamente os arquivos `.lock` do disco e utiliza a garantia ACID do SQLite central:
```sql
CREATE TABLE IF NOT EXISTS project_locks (
    project_name TEXT PRIMARY KEY,
    pid INTEGER,
    hostname TEXT,
    acquired_at TIMESTAMP
);
```
A tentativa de aquisição é feita com `INSERT INTO project_locks ...`. Se violar a chave primária, lê o PID registrado e checa se está vivo.

- **Vantagens**:
  - Centraliza o estado do sistema em um único lugar (`iris_central.db`).
  - Permite inspecionar todos os locks ativos do sistema com um simples `SELECT * FROM project_locks`.
- **Desvantagens**:
  - Adiciona concorrência no banco central. Se o banco central estiver em lock, o controle de locks pode sofrer timeout.

---

## Tabela Comparativa

| Critério | Atual (Vulnerável) | Abordagem A (Atômico O_EXCL) | Abordagem B (Kernel Lock) | Abordagem C (SQLite Central) |
| :--- | :---: | :---: | :---: | :---: |
| **Proteção contra Race Condition** | ❌ 0% | 🟢 100% | 🟢 100% | 🟢 100% |
| **Limpeza de Locks Órfãos** | ⚠️ Parcial | ⚠️ Baseada em PID | 🟢 Instantânea via SO | ⚠️ Baseada em PID |
| **Complexidade** | — | Baixa (15 linhas) | Média (código por SO) | Média |
| **Dependência de Arquivo Aberto** | ❌ Não | ❌ Não | ⚠️ Requer handle aberto | ❌ Não |

---

## Implementação Recomendada (Abordagem A com Auto-Recuperação de Órfãos)

```python
# Em src/core/lock.py

import os
import json
import socket
from datetime import datetime

class ProjectLock:
    def acquire(self) -> bool:
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        current_pid = os.getpid()
        
        lock_data = {
            "project_name": self.project_name,
            "pid": current_pid,
            "hostname": socket.gethostname(),
            "acquired_at": datetime.now().isoformat()
        }

        # Loop de tentativa com suporte a limpeza de lock órfão
        for attempt in range(2):
            try:
                # O_CREAT | O_EXCL garante criação atômica sem sobrescrever
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                fd = os.open(str(self.lock_file), flags, 0o644)
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    json.dump(lock_data, f, indent=2)
                self._is_acquired = True
                return True
            except FileExistsError:
                # O arquivo já existe: inspecionar o proprietário
                info = self.get_lock_info()
                if not info:
                    # Arquivo vazio ou corrompido: remove e tenta novamente
                    self.lock_file.unlink(missing_ok=True)
                    continue

                owner_pid = info.get("pid", 0)
                if owner_pid == current_pid:
                    self._is_acquired = True
                    return True

                if is_pid_alive(owner_pid):
                    raise ProjectLockedError(self.project_name, info)
                else:
                    log_event(f"Lock órfão de '{self.project_name}' (PID {owner_pid} inativo) removido.", "warning")
                    self.lock_file.unlink(missing_ok=True)
                    # Loop tenta novamente no próximo ciclo
                    continue

        raise RuntimeError(f"Não foi possível adquirir o lock para o projeto '{self.project_name}'.")
```
