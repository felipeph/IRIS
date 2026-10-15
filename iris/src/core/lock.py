import os
import sys
import json
import time
import atexit
import socket
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from src.core.config import PROJECTS_DIR
from src.core.logger import log_event

class ProjectLockedError(Exception):
    """Lançado quando um projeto já está sendo executado por outro processo."""
    def __init__(self, project_name: str, lock_info: Dict[str, Any]):
        self.project_name = project_name
        self.lock_info = lock_info
        self.pid = lock_info.get("pid", 0)
        self.hostname = lock_info.get("hostname", "desconhecido")
        self.acquired_at = lock_info.get("acquired_at", "desconhecido")
        super().__init__(
            f"O projeto '{project_name}' já está em execução pelo processo PID {self.pid} "
            f"em '{self.hostname}' desde {self.acquired_at}."
        )

def is_pid_alive(pid: int) -> bool:
    """Verifica se um processo com o PID fornecido ainda está em execução."""
    if pid <= 0:
        return False
        
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
        if handle == 0:
            err = kernel32.GetLastError()
            # Se for ERROR_ACCESS_DENIED (5), o processo existe mas não temos permissão
            return err == 5
            
        try:
            import ctypes.wintypes
            exit_code = ctypes.wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                STILL_ACTIVE = 259
                return exit_code.value == STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

class ProjectLock:
    """
    Gerencia um arquivo de trava (.lock) exclusivo por projeto.
    Garante que duas instâncias do IRIS não executem o mesmo projeto simultaneamente,
    com auto-recuperação de locks órfãos (stale locks de processos encerrados).
    """

    def __init__(self, project_name: str):
        self.project_name = project_name
        self.lock_file = PROJECTS_DIR / f"{self.project_name}.lock"
        self._is_acquired = False
        self._atexit_registered = False

    def get_lock_info(self, retries: int = 3, retry_delay: float = 0.05) -> Optional[Dict[str, Any]]:
        """
        Lê os dados da trava atual, se existir.
        Tolerante a leituras concorrentes em escrita (arquivos vazios temporários
        ou em processo de escrita/flush por outro processo recém-iniciado).
        """
        for attempt in range(retries):
            if not self.lock_file.exists():
                return None
            try:
                with open(self.lock_file, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if not content:
                        if attempt < retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return None
                    return json.loads(content)
            except (json.JSONDecodeError, PermissionError):
                if attempt < retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None
            except Exception:
                return None
        return None

    def acquire(self) -> bool:
        """
        Tenta obter o lock do projeto de forma atômica via kernel (os.O_CREAT | os.O_EXCL).
        Garante imunidade total a race conditions (TOCTOU) e sobrescrita acidental.
        Se já estiver bloqueado por um PID ativo, lança ProjectLockedError.
        Se o lock existente for órfão (PID morto) ou corrompido, limpa e tenta novamente.
        """
        if self._is_acquired:
            return True

        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        current_pid = os.getpid()

        lock_data = {
            "project_name": self.project_name,
            "pid": current_pid,
            "hostname": socket.gethostname(),
            "acquired_at": datetime.now().isoformat()
        }

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                # Criação atômica exclusiva via kernel:
                # O SO garante que o arquivo só será criado se NÃO existir.
                # Se já existir, lança FileExistsError sem sobrescrever o conteúdo.
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                fd = os.open(str(self.lock_file), flags, 0o644)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(lock_data, f, indent=2)
                        f.flush()
                except Exception:
                    # Se falhar durante a escrita, descarta o arquivo incompleto
                    self.lock_file.unlink(missing_ok=True)
                    raise

                self._is_acquired = True
                if not self._atexit_registered:
                    atexit.register(self.release)
                    self._atexit_registered = True

                log_event(f"Lock do projeto '{self.project_name}' adquirido pelo PID {current_pid}.", "debug")
                return True

            except FileExistsError:
                # O arquivo já existe fisicamente. Inspeciona o processo proprietário.
                info = self.get_lock_info()
                if not info:
                    # Arquivo vazio ou corrompido que persistiu após retentativas: lock órfão inválido
                    log_event(f"Lock corrompido ou vazio do projeto '{self.project_name}' removido.", "warning")
                    self.lock_file.unlink(missing_ok=True)
                    continue

                owner_pid = info.get("pid", 0)
                if owner_pid == current_pid:
                    self._is_acquired = True
                    return True

                if is_pid_alive(owner_pid):
                    raise ProjectLockedError(self.project_name, info)
                else:
                    log_event(f"Lock órfão do projeto '{self.project_name}' (PID {owner_pid} morto) detectado e removido.", "warning")
                    self.lock_file.unlink(missing_ok=True)
                    continue

        raise RuntimeError(f"Não foi possível adquirir o lock para o projeto '{self.project_name}' após {max_attempts} tentativas.")

    def release(self):
        """Libera a trava se este processo for o proprietário."""
        if not self.lock_file.exists():
            self._is_acquired = False
            return

        try:
            info = self.get_lock_info()
            if info and info.get("pid") == os.getpid():
                self.lock_file.unlink(missing_ok=True)
                self._is_acquired = False
                log_event(f"Lock do projeto '{self.project_name}' liberado pelo PID {os.getpid()}.", "debug")
            else:
                self._is_acquired = False
        except Exception as e:
            log_event(f"Erro ao liberar lock de '{self.project_name}': {e}", "warning")
            self._is_acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
