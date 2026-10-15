# Proposta 10: Desacoplamento da Interface Rich das Estratégias de Negócio

## Contexto e Localização do Problema

- **Arquivos Afetados**:
  - [`src/modules/ingestion/strategies/copy_strategy.py`](file:///c:/code/IRIS/iris/src/modules/ingestion/strategies/copy_strategy.py)
  - [`src/modules/ingestion/strategies/move_strategy.py`](file:///c:/code/IRIS/iris/src/modules/ingestion/strategies/move_strategy.py)
  - [`src/modules/organize/stage.py`](file:///c:/code/IRIS/iris/src/modules/organize/stage.py)
  - [`src/modules/cleanup/stage.py`](file:///c:/code/IRIS/iris/src/modules/cleanup/stage.py)
  - [`src/modules/video_edit/stage.py`](file:///c:/code/IRIS/iris/src/modules/video_edit/stage.py)
  - [`src/modules/timelapse/renderer.py`](file:///c:/code/IRIS/iris/src/modules/timelapse/renderer.py)
- **Princípio Afetado**: **Separação de Apresentação e Domínio (Separation of Concerns)** e **Testabilidade**

### Exemplos do Acoplamento Atual

Em `copy_strategy.py`:
```python
def copy_and_verify(src_path: Path, dest_path: Path, live: Live, tracker: ProgressTracker, render_args) -> tuple[bool, str]:
    ...
    # Lógica de cópia e I/O misturada com chamadas diretas de renderização de tela
    live.update(PipelineUI.generate_renderable(tracker, "ETAPA 1: INGESTÃO E VALIDAÇÃO", *render_args, "Ingestão: Copiando..."))
```

Em `organize/stage.py`:
```python
# Prompt interativo chamado nas entranhas da estratégia
confirmed = Confirm.ask("Deseja iniciar a movimentação física dos arquivos?", default=True)
if not confirmed:
    return False
```

Em `cleanup/stage.py`:
```python
if not Confirm.ask("[bold red]Deseja enviar estes arquivos verificados da origem para a Lixeira?[/bold red]"):
    return True
```

---

## Diagnóstico da Causa-Raiz

1. **Dependência Forte de Terminal Interativo nos Algoritmos de Negócio**:
   - As funções responsáveis por copiar bytes, mover pastas, verificar hashes e aplicar filtros de vídeo conhecem diretamente o objeto `rich.live.Live` e o `rich.console.Console`.
   - Isso impede que o IRIS seja executado em:
     - **Modo Headless / Daemon**: Execução agendada em segundo plano via cron ou serviço do Windows sem console interativo alocado.
     - **Agentes de IA e Scripts Automatizados**: A biblioteca `rich.prompt.Confirm.ask()` bloqueia o processo esperando entrada manual pelo stdin sem timeout.
     - **Testes Unitários**: Testar uma simples cópia de arquivo exige criar mocks complexos para `Live`, `Console` e interceptar `Confirm`.

2. **Dificuldade de Troca ou Customização de UI**:
   - Se amanhã você quiser adicionar uma interface web leve (via FastAPI/Streamlit) ou exibir notificações nativas em tempo real no Windows, terá que reescrever todos os loops de todas as etapas.

---

## Abordagens de Solução

### Abordagem A: "Padrão Observer / ProgressReporter" (Recomendada para o IRIS)
**Conceito**: Criar uma interface abstrata `ProgressReporter` que define o contrato de notificação:

```python
class ProgressReporter(ABC):
    @abstractmethod
    def update(self, completed: int, total: int, current_item: str, message: str): pass
    @abstractmethod
    def confirm(self, prompt: str, default: bool = True) -> bool: pass
    @abstractmethod
    def log(self, message: str, level: str = "info"): pass
```

Criar duas implementações:
1. `RichConsoleReporter`: Usa o `Live`, `ProgressBar` e `Confirm.ask` atuais para a experiência visual no terminal.
2. `HeadlessReporter` (ou `SilentReporter`): Grava apenas no log do projeto e responde automaticamente valores padrão para confirmações, perfeito para testes unitários e automações.

- **Vantagens**:
  - As funções de negócio passam a receber apenas `reporter: ProgressReporter`.
  - `copy_and_verify(src, dest, reporter)` não sabe o que é `rich.live.Live`.
  - Os testes unitários rodam 10x mais rápido sem piscar o terminal.
- **Desvantagens**:
  - Requer atualizar os parâmetros das funções auxiliares.

---

### Abordagem B: "Arquitetura Orientada a Eventos (Event Bus / Pub-Sub)"
**Conceito**: As etapas emitem eventos de domínio desacoplados:
- `events.publish(ItemIngestedEvent(path, size, hash))`
- `events.publish(StageProgressEvent(current, total, speed))`
- `events.publish(ConfirmationRequiredEvent(prompt, callback))`

O módulo de UI escuta os eventos e atualiza a barra Rich.

- **Vantagens**:
  - Desacoplamento de nível enterprise.
  - Múltiplos ouvintes podem escutar o mesmo evento (ex: a UI do terminal atualiza a barra e o módulo de notificações NTFY manda um push no Telegram/Windows Toast).
- **Desvantagens**:
  - Maior complexidade arquitetural; pode ser excessivo para uma CLI local.

---

### Abordagem C: "Funções Geradoras (`yield Progress`)"
**Conceito**: As estratégias deixam de chamar `update()` e transformam-se em geradores Python (`yield`):

```python
def execute_ingestion(...) -> Generator[ProgressState, None, IngestionResult]:
    for item in items:
        # processa...
        yield ProgressState(completed=done, total=total, file=item.name)
```
O orquestrador da UI itera sobre o gerador:
```python
with Live(...) as live:
    for state in strategy.execute_ingestion(...):
        live.update(render(state))
```

- **Vantagens**:
  - Muito elegante e puramente idiomático em Python.
  - A estratégia de negócio não depende de nenhuma classe externa de relatório.
- **Desvantagens**:
  - Mais difícil lidar com prompts interativos bidirecionais (requer `generator.send()`).

---

## Tabela Comparativa

| Critério | Atual (Acoplado) | Abordagem A (Reporter Pattern) | Abordagem B (Event Bus) | Abordagem C (Geradores yield) |
| :--- | :---: | :---: | :---: | :---: |
| **Facilidade de Testes Unitários** | 🔴 Muito Difícil (Requer Mocks) | 🟢 Trivial (`SilentReporter`) | 🟢 Trivial | 🟢 Trivial |
| **Execução Headless/Automação** | ❌ Não suportada | 🟢 100% Suportada | 🟢 100% Suportada | 🟢 100% Suportada |
| **Complexidade** | — | Baixa | Alta | Média |
| **Bidirecionalidade (Prompts)** | ⚠️ Hardcoded na tela | 🟢 Injetada via método `confirm()` | ⚠️ Assíncrona | ⚠️ Complexa (`send()`) |

---

## Implementação Recomendada (Abordagem A)

```python
# Em src/core/reporter.py

from abc import ABC, abstractmethod

class ProgressReporter(ABC):
    @abstractmethod
    def start_stage(self, title: str, total_units: int, mode: str = "bytes"): pass
    
    @abstractmethod
    def update(self, increment: int, current_file: str = "", status_msg: str = ""): pass
    
    @abstractmethod
    def confirm(self, prompt: str, default: bool = True) -> bool: pass
    
    @abstractmethod
    def end_stage(self, success: bool, message: str = ""): pass


class SilentReporter(ProgressReporter):
    """Usado em testes unitários e execuções em segundo plano."""
    def __init__(self, default_confirm_response: bool = True):
        self.default_confirm = default_confirm_response
        
    def start_stage(self, title, total_units, mode="bytes"): pass
    def update(self, increment, current_file="", status_msg=""): pass
    def confirm(self, prompt, default=True): return self.default_confirm
    def end_stage(self, success, message=""): pass
```

Uso na estratégia de negócio (totalmente livre de Rich):
```python
# Em src/modules/ingestion/strategies/copy_strategy.py

def copy_and_verify(src_path: Path, dest_path: Path, reporter: ProgressReporter) -> tuple[bool, str]:
    hasher = xxhash.xxh64()
    with open(src_path, 'rb') as f_src, open(dest_path, 'wb') as f_dest:
        while chunk := f_src.read(4 * 1024 * 1024):
            hasher.update(chunk)
            f_dest.write(chunk)
            reporter.update(len(chunk), current_file=src_path.name, status_msg="Copiando...")
            
    # Sincroniza e verifica...
    reporter.update(0, current_file=src_path.name, status_msg="Verificado!")
    return True, hasher.hexdigest()
```
