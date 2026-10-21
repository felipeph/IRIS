"""Orquestrador do subprocesso de empilhamento lunar (AstroStackRunner)."""
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import List, Dict, Any, Optional, Callable

from src.core.config import config
from src.core.logger import log_event

MODULE_DIR = Path(__file__).resolve().parent
WORKER_SCRIPT = MODULE_DIR / "worker.py"


def _resolve_python_exe(candidate: Optional[Any]) -> Optional[Path]:
    """Resolve o executável Python a partir de um caminho (arquivo direto ou pasta de venv)."""
    if candidate is None:
        return None
    val_str = str(candidate).strip()
    if not val_str or val_str.lower() == "auto":
        return None
    p = Path(val_str)
    if p.is_file():
        return p
    if p.is_dir():
        exe = p / "Scripts" / "python.exe" if sys.platform == "win32" else p / "bin" / "python"
        if exe.exists():
            return exe
    return None


def find_astro_python() -> Optional[Path]:
    r"""Descobre o executável Python do ambiente virtual com as dependências do astro.
    
    Ordem de busca:
    1. IRIS_ASTRO_PYTHON (variável de ambiente)
    2. modules.astro_stack.python_path no config.yaml
    3. modules.astro_stack.venv_path no config.yaml (arquivo ou pasta)
    4. iris/.venv_astro/Scripts/python.exe
    5. .venv_astro/Scripts/python.exe (raiz)
    6. iris/.venv/Scripts/python.exe
    7. .venv/Scripts/python.exe (raiz)
    8. ~/.iris/astro_venv/Scripts/python.exe
    9. C:\code\FOTOGRAFIA\pipp-core-test\pss\.venv\Scripts\python.exe
    10. sys.executable (se possuir tifffile e PyQt5)
    """
    env_py = _resolve_python_exe(os.getenv("IRIS_ASTRO_PYTHON"))
    if env_py:
        return env_py

    configured_py = _resolve_python_exe(config.get("modules.astro_stack.python_path"))
    if configured_py:
        return configured_py

    configured_venv = _resolve_python_exe(config.get("modules.astro_stack.venv_path"))
    if configured_venv:
        return configured_venv

    candidates = [
        MODULE_DIR.parents[2] / ".venv_astro",
        MODULE_DIR.parents[3] / ".venv_astro",
        MODULE_DIR.parents[2] / ".venv",
        MODULE_DIR.parents[3] / ".venv",
        Path.home() / ".iris" / "astro_venv",
        Path("C:/code/FOTOGRAFIA/pipp-core-test/pss/.venv"),
    ]

    for cand in candidates:
        exe = _resolve_python_exe(cand)
        if exe:
            return exe

    # Testa se o Python atual tem as dependências mínimas
    try:
        import PyQt5  # type: ignore # noqa: F401
        import tifffile  # type: ignore # noqa: F401
        import cv2  # noqa: F401
        return Path(sys.executable)
    except ImportError:
        pass

    return None


class AstroStackRunner:
    """Executa o empilhamento lunar invocando o worker no ambiente virtual dedicado."""

    def __init__(self, python_path: Optional[Path] = None):
        self.python_path = python_path or find_astro_python()

    def is_available(self) -> bool:
        return self.python_path is not None and self.python_path.exists()

    def run_session(
        self,
        input_dir: Path,
        output_dir: Path,
        keep_percents: Optional[List[int]] = None,
        crop_size: Optional[int] = None,
        margin: int = 128,
        align_box_width: int = 64,
        align_search_width: int = 20,
        stab_mode: str = "Surface",
        timeout: int = 600,
        progress_callback: Optional[Callable[[str, Optional[float]], None]] = None,
    ) -> Dict[str, Any]:
        """Executa o empilhamento para uma sessão lunar completa."""
        if not self.is_available():
            raise RuntimeError(
                "Ambiente Python de astrofotografia não encontrado! "
                "Execute o setup do ambiente ou configure 'modules.astro_stack.venv_path' no config.yaml."
            )

        if keep_percents is None:
            raw_kp = config.get("modules.astro_stack.keep_percents", [10, 25, 50])
            keep_percents = list(raw_kp) if isinstance(raw_kp, (list, tuple)) else [10, 25, 50]

        kp_str = ",".join(str(p) for p in keep_percents)
        vendor_dir = MODULE_DIR.parents[2] / "vendor" / "PlanetarySystemStacker"

        cmd = [
            str(self.python_path),
            "-u",
            str(WORKER_SCRIPT),
            "--input-dir", str(input_dir),
            "--output-dir", str(output_dir),
            "--keep-percents", kp_str,
            "--margin", str(margin),
            "--align-box-width", str(align_box_width),
            "--align-search-width", str(align_search_width),
            "--stab-mode", stab_mode,
            "--timeout", str(timeout),
        ]
        if crop_size is not None:
            cmd.extend(["--crop-size", str(crop_size)])
        workers = config.get("modules.astro_stack.workers", None)
        if workers:
            cmd.extend(["--workers", str(workers)])
        if vendor_dir.exists():
            cmd.extend(["--vendor-dir", str(vendor_dir)])

        log_event(f"Iniciando empilhamento lunar para {input_dir.name} ({kp_str}%)", "info")
        if progress_callback:
            progress_callback(f"Iniciando PSS para {input_dir.name}...", None)

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        report_data: Optional[Dict[str, Any]] = None
        error_lines = []

        # Streaming do output unificado em tempo real
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            if not line and proc.poll() is not None:
                break
            if line:
                cleaned = line.strip()
                if cleaned.startswith("REPORT_JSON:"):
                    json_str = cleaned[len("REPORT_JSON:"):]
                    try:
                        report_data = json.loads(json_str)
                    except Exception:
                        pass
                elif cleaned.startswith("PROGRESS_JSON:"):
                    json_str = cleaned[len("PROGRESS_JSON:"):].strip()
                    try:
                        p_data = json.loads(json_str)
                        if progress_callback:
                            try:
                                progress_callback(p_data, p_data.get("progress_pct"))
                            except Exception:
                                progress_callback(p_data.get("msg", ""), p_data.get("progress_pct"))
                    except Exception:
                        pass
                elif cleaned.startswith("PROGRESS:"):
                    msg = cleaned[len("PROGRESS:"):].strip()
                    if progress_callback:
                        progress_callback(msg, None)
                elif cleaned.startswith("STATUS:"):
                    msg = cleaned[len("STATUS:"):].strip()
                    if progress_callback:
                        progress_callback(msg, None)
                elif cleaned.startswith("ERRO:") or cleaned.startswith("ERRO FATAL:"):
                    error_lines.append(cleaned)
                elif "Traceback (most recent call last)" in cleaned or "Error:" in cleaned:
                    error_lines.append(cleaned)

        returncode = proc.wait()

        if returncode != 0:
            err_msg = "\n".join(error_lines) or f"Código de saída {returncode}"
            log_event(f"Falha no empilhamento de {input_dir.name}: {err_msg}", "error")
            raise RuntimeError(f"Erro no empilhamento da sessão: {err_msg}")


        if report_data is None:
            # Tenta ler do report.json no diretório de saída
            report_files = list(output_dir.glob("*_report.json"))
            if report_files:
                try:
                    loaded = json.loads(report_files[-1].read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        report_data = loaded
                except Exception:
                    pass
            if report_data is None:
                report_data = {"status": "success", "session_dir": str(input_dir), "output_dir": str(output_dir)}

        log_event(f"Empilhamento concluído com sucesso para {input_dir.name}", "info")
        return report_data
