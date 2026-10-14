# IA & Engenharia: Como Estender o IRIS (Novo Estágio)

A arquitetura do IRIS foi desenhada com o **Open/Closed Principle** em mente. Para criar um novo estágio no pipeline (por exemplo, um módulo de inferência de visão computacional local para detecção de aves em fotos ou um gerador de thumbnails), basta seguir quatro passos padronizados.

---

## 1. Passo 1: Criar o Módulo e a Classe do Estágio

Crie uma nova pasta dentro de `iris/src/modules/` (ex: `iris/src/modules/bird_detector/`) contendo o arquivo `stage.py`:

```python
"""Módulo de detecção automática de pássaros via IA local."""

from src.core.pipeline import PipelineStage
from src.core.project import Project
from rich.console import Console

console = Console()

class BirdDetectorStage(PipelineStage):
    """Estágio responsável por analisar imagens e detectar espécies."""

    def __init__(self, stage_id: str, name: str):
        super().__init__(stage_id, name)

    def run(self, project: Project, **kwargs) -> bool:
        """Executa a inferência nos arquivos organizados do projeto."""
        console.print(f"[bold cyan]Iniciando detecção em: {project.name}[/bold cyan]")
        
        # 1. Recupera os itens do projeto
        items = project.get_items_by_category("photo")
        if not items:
            console.print("[dim]Nenhuma foto comum encontrada. Pulando etapa.[/dim]")
            return True

        # 2. Executa a lógica de domínio
        for item in items:
            # Lógica de inferência aqui...
            pass

        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    """Função fábrica obrigatória requerida pelo PipelineRunner."""
    return BirdDetectorStage(stage_id, name)
```

> [!IMPORTANT]
> É obrigatório expor a função `get_stage(stage_id, name)` no módulo para que o carregador dinâmico do `PipelineRunner` consiga instanciar a classe.

---

## 2. Passo 2: Registrar o Estágio no `config.yaml`

Abra o arquivo `iris/config.yaml` e adicione a declaração do novo estágio dentro da lista `pipeline.stages` na posição sequencial desejada:

```yaml
pipeline:
  stages:
    # ... estágios anteriores ...
    - id: bird_detect
      name: "Detecção Local de Aves (IA)"
      module: src.modules.bird_detector.stage
      enabled: true
    # ... estágios seguintes ...
```

---

## 3. Passo 3: Adicionar Parâmetros Específicos do Módulo

No mesmo arquivo `config.yaml`, adicione o bloco de configurações específicas para o seu módulo sob a chave `modules`:

```yaml
modules:
  bird_detect:
    enabled: true
    confidence_threshold: 0.75
    model_path: "models/yolov8_birds.onnx"
```

---

## 4. Passo 4: Criar o Teste Automatizado

Crie o arquivo de teste correspondente em `iris/tests/test_bird_detector.py`:

```python
import pytest
from unittest.mock import MagicMock
from src.modules.bird_detector.stage import BirdDetectorStage

def test_bird_detector_skips_empty_project():
    stage = BirdDetectorStage("bird_detect", "Detecção Local de Aves")
    project = MagicMock()
    project.get_items_by_category.return_value = []
    
    assert stage.run(project) is True
```

Execute o `pytest` para certificar-se de que a implementação é válida e não interfere nos demais módulos:

```bash
python -m pytest iris/tests/test_bird_detector.py
```
Pronto! Seu novo estágio agora é carregado automaticamente pelo pipeline do IRIS.
