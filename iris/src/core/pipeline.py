import importlib
import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from src.core.project import Project
from src.core.config import config
from src.core.cleanup import clean_empty_directories
from rich.console import Console

console = Console()

class PipelineStage(ABC):
    """Classe base para todas as etapas do pipeline.
    
    Princípio de Isolamento de Projeto:
    Cada PipelineStage deve processar exclusivamente itens e artefatos pertencentes
    ao `Project` fornecido (project.items ou tabelas internas do projeto).
    É terminantemente proibido realizar varreduras em diretórios globais de destino
    (ex: dest_root) como fallback para encontrar trabalho.
    Se um projeto não possuir itens da categoria esperada pelo estágio, a etapa
    deve ser ignorada graciosamente retornando True.
    """
    
    def __init__(self, stage_id: str, name: str):
        self.stage_id = stage_id
        self.name = name

    @abstractmethod
    def run(self, project: Project, **kwargs) -> bool:
        """
        Executa a lógica da etapa para o projeto.
        Deve retornar True em caso de sucesso, False caso contrário.
        """
        pass

def _invoke_stage(stage: PipelineStage, project: Project, kwargs: dict) -> bool:
    """Invoca o método run do stage passando apenas argumentos aceitos por sua assinatura."""
    sig = inspect.signature(stage.run)
    has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
    if has_var_keyword:
        return stage.run(project, **kwargs)
    accepted_args = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return stage.run(project, **accepted_args)

class PipelineRunner:
    """Gerencia e executa as etapas configuradas no pipeline."""
    
    def __init__(self):
        self.stages = self._load_stages_from_config()

    def _load_stages_from_config(self) -> list[PipelineStage]:
        stages = []
        pipeline_config = config.get("pipeline.stages", [])
        
        for stage_conf in pipeline_config:
            if not stage_conf.get("enabled", False):
                continue
                
            module_path = stage_conf.get("module")
            stage_id = stage_conf.get("id")
            name = stage_conf.get("name")
            
            try:
                # Importa dinamicamente o módulo da etapa
                module = importlib.import_module(module_path)
                
                # Instancia a etapa
                if hasattr(module, "get_stage"):
                    stage_instance = module.get_stage(stage_id, name)
                    stages.append(stage_instance)
                else:
                    console.print(f"[red]Módulo {module_path} não possui função 'get_stage'.[/red]")
            except Exception as e:
                console.print(f"[red]Erro ao carregar etapa {stage_id} do módulo {module_path}: {e}[/red]")
                
        return stages

    def _sweep_empty_directories(self):
        """Varre e remove pastas vazias na raiz de destino do IRIS."""
        dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
        removed = clean_empty_directories(dest_root, preserve_root=True)
        if removed > 0:
            console.print(f"[dim]🧹 Limpeza: {removed} pasta(s) vazia(s) removida(s) na raiz do IRIS ({dest_root}).[/dim]")

    def run_stage(self, project: Project, target_stage_id: str, **kwargs) -> bool:
        """Executa apenas uma etapa específica pelo seu ID."""
        kwargs.setdefault("interactive", True)
        if target_stage_id == "cleanup":
            kwargs.setdefault("auto_clean", getattr(project, "auto_cleanup", False))
        for stage in self.stages:
            if stage.stage_id == target_stage_id:
                console.print(f"\n[bold blue]--- Executando Etapa: '{stage.name}' ---[/bold blue]")
                try:
                    success = _invoke_stage(stage, project, kwargs)
                    if success:
                        project.current_stage_id = stage.stage_id
                        project.save()
                        self._sweep_empty_directories()
                        console.print(f"[green]OK: Etapa '{stage.name}' concluída com sucesso.[/green]")
                        return True
                    else:
                        console.print(f"[red]ERRO: Etapa '{stage.name}' falhou.[/red]")
                        return False
                except KeyboardInterrupt:
                    console.print(f"\n[yellow]⚠ Execução interrompida pelo usuário durante '{stage.name}'. Progresso salvo.[/yellow]")
                    return False
                except Exception as e:
                    console.print(f"[red]ERRO: Erro inesperado na etapa '{stage.name}': {e}[/red]")
                    return False
                    
        console.print(f"[red]ERRO: Etapa '{target_stage_id}' não encontrada ou não habilitada no config.[/red]")
        return False

    def run_project(self, project: Project, **kwargs):
        """Executa o pipeline para um projeto."""
        console.print(f"\n[bold blue]=== Executando Pipeline para '{project.name}' ===[/bold blue]")
        call_kwargs = dict(kwargs)
        call_kwargs.setdefault("interactive", False)
        
        start_index = 0
        if project.current_stage_id:
            # Encontrar onde parar/retomar
            for i, stage in enumerate(self.stages):
                if stage.stage_id == project.current_stage_id:
                    start_index = i + 1  # Inicia na próxima etapa, assumindo que current_stage_id foi concluída
                    break
                    
        stages_to_run = self.stages[start_index:]
        if not stages_to_run:
            console.print(f"\n[yellow]ℹ Todas as {len(self.stages)} etapas do pipeline já foram concluídas para o projeto '{project.name}'.[/yellow]")
            console.print(f"[dim]Última etapa registrada: '{project.current_stage_id}'.[/dim]")
            console.print("[dim]Para reexecutar uma etapa específica, selecione-a pelo número no menu interativo.[/dim]")
            console.print(f"\n[bold blue]=== Fim do Pipeline ===[/bold blue]")
            return

        for stage in stages_to_run:
            if stage.stage_id == "cleanup":
                if not getattr(project, "auto_cleanup", False):
                    console.print(f"\n[dim]-> Pulando etapa: {stage.name} (Limpeza automática desativada no projeto)[/dim]")
                    continue
                call_kwargs["auto_clean"] = True

            console.print(f"\n[bold cyan]-> Iniciando etapa: {stage.name}[/bold cyan]")
            try:
                success = _invoke_stage(stage, project, call_kwargs)
                if success:
                    project.current_stage_id = stage.stage_id
                    project.save()
                    self._sweep_empty_directories()
                    console.print(f"[green]OK: Etapa '{stage.name}' concluída com sucesso.[/green]")
                else:
                    console.print(f"[red]ERRO: Etapa '{stage.name}' falhou. Interrompendo pipeline.[/red]")
                    break
            except KeyboardInterrupt:
                console.print(f"\n[yellow]⚠ Execução interrompida pelo usuário durante '{stage.name}'. Progresso salvo.[/yellow]")
                break
            except Exception as e:
                console.print(f"[red]ERRO: Erro inesperado na etapa '{stage.name}': {e}[/red]")
                break
        
        self._sweep_empty_directories()
        console.print(f"\n[bold blue]=== Fim do Pipeline ===[/bold blue]")
