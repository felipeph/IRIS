import importlib
import inspect
from abc import ABC, abstractmethod
from src.core.project import Project
from src.core.config import config
from rich.console import Console

console = Console()

class PipelineStage(ABC):
    """Classe base para todas as etapas do pipeline."""
    
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
        
        console.print(f"\n[bold blue]=== Fim do Pipeline ===[/bold blue]")
