"""
Módulo de Abstração de Notificação e Progresso (RFC 10).
Desacopla a interface visual (Rich/Terminal) da lógica de negócios do pipeline.
Permite execuções Headless/Daemon, testes automatizados e integração com UIs alternativas.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from rich.console import Console
from rich.prompt import Confirm


class ProgressReporter(ABC):
    """Contrato abstrato para emissão de progresso e confirmações do usuário."""

    @abstractmethod
    def start_stage(self, title: str, total_units: int, mode: str = "bytes", total_items: int = 0) -> None:
        """Inicia uma etapa com a quantidade total de unidades esperada."""
        pass

    @abstractmethod
    def update(self, increment: int = 0, current_item: str = "", status_msg: str = "") -> None:
        """Atualiza o progresso corrente."""
        pass

    @abstractmethod
    def confirm(self, prompt: str, default: bool = True) -> bool:
        """Solicita uma confirmação sim/não."""
        pass

    @abstractmethod
    def log(self, message: str, level: str = "info") -> None:
        """Registra uma mensagem informativa ou erro."""
        pass

    @abstractmethod
    def end_stage(self, success: bool, message: str = "") -> None:
        """Finaliza a etapa corrente."""
        pass


class SilentReporter(ProgressReporter):
    """
    Implementação silenciosa de ProgressReporter para testes unitários,
    scripts headless e execução não-interativa.
    """

    def __init__(self, default_confirm_response: bool = True):
        self.default_confirm = default_confirm_response
        self.logs: list[tuple[str, str]] = []
        self.updates: list[dict[str, Any]] = []

    def start_stage(self, title: str, total_units: int, mode: str = "bytes", total_items: int = 0) -> None:
        pass

    def update(self, increment: int = 0, current_item: str = "", status_msg: str = "") -> None:
        self.updates.append({"increment": increment, "item": current_item, "msg": status_msg})

    def confirm(self, prompt: str, default: bool = True) -> bool:
        return self.default_confirm

    def log(self, message: str, level: str = "info") -> None:
        self.logs.append((level, message))

    def end_stage(self, success: bool, message: str = "") -> None:
        pass


class RichConsoleReporter(ProgressReporter):
    """
    Implementação baseada em Rich para interações ricas no terminal do usuário.
    """

    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self._current_title: str = ""

    def start_stage(self, title: str, total_units: int, mode: str = "bytes", total_items: int = 0) -> None:
        self._current_title = title

    def update(self, increment: int = 0, current_item: str = "", status_msg: str = "") -> None:
        pass

    def confirm(self, prompt: str, default: bool = True) -> bool:
        return Confirm.ask(prompt, default=default, console=self.console)

    def log(self, message: str, level: str = "info") -> None:
        if level == "error":
            self.console.print(f"[red]{message}[/red]")
        elif level == "warning":
            self.console.print(f"[yellow]{message}[/yellow]")
        elif level == "success":
            self.console.print(f"[green]{message}[/green]")
        else:
            self.console.print(f"[cyan]{message}[/cyan]")

    def end_stage(self, success: bool, message: str = "") -> None:
        if message:
            if success:
                self.console.print(f"[green]{message}[/green]")
            else:
                self.console.print(f"[red]{message}[/red]")
