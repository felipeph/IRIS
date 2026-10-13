"""Orquestrador do subprocesso de empilhamento lunar (AstroStackRunner)."""
import json
from pathlib import Path
import subprocess
import sys
from typing import List, Dict, Any, Optional, Callable

from src.core.config import config
from src.core.logger import log_event

MODULE_DIR = Path(__file__).resolve().parent
WORKER_SCRIPT = MODULE_DIR / "worker.py"


def find_astro_python() -> Optional[Path]:
    r"""Descobre o executável Python do ambiente virtual com as dependências do astro.
    
    Ordem de busca:
    1. modules.astro_stack.python_path no config.yaml
    2. modules.astro_stack.venv_path no config.yaml
    3. iris/.venv_astro/Scripts/python.exe
    4. ~/.iris/astro_venv/Scripts/python.exe
    5. C:\code\FOTOGRAFIA\pipp-core-test\pss\.venv\Scripts\python.exe
    6. sys.executable (se possuir tifffile e PyQt5)
    """
    configured_py = config.get("modules.astro_stack.python_path")
    if configured_py and Path(configured_py).exists():
        return Path(configured_py)

    configured_venv = config.get("modules.astro_stack.venv_path")
    if configured_venv and configured_venv != "auto":
        p = Path(configured_venv)
        exe = p / "Scripts" / "python.exe" if sys.platform == "win32" else p / "bin" / "python"
        if exe.exists():
            return exe

    candidates = [
        MODULE_DIR.parents[2] / ".venv_astro" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"),
        Path.home() / ".iris" / "astro_venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python"),
        Path("C:/code/FOTOGRAFIA/pipp-core-test/pss/.venv/Scripts/python.exe"),
    ]

    for cand in candidates:
        if cand.exists():
            return cand

    # Testa se o Python atual tem as dependências mínimas
    try:
        import PyQt5  # noqa: F401
        import tifffile  # noqa: F401
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
            keep_percents = config.get("modules.astro_stack.keep_percents", [10, 25, 50])

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
        if vendor_dir.exists():
            cmd.extend(["--vendor-dir", str(vendor_dir)])

        log_event(f"Iniciando empilhamento lunar para {input_dir.name} ({kp_str}%)", "info")
        if progress_callback:
            progress_callback(f"Iniciando PSS para {input_dir.name}...", None)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        report_data: Optional[Dict[str, Any]] = None
        error_lines = []

        # Streaming do output
        while True:
            line = proc.stdout.readline()
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
                elif cleaned.startswith("PROGRESS:"):
                    msg = cleaned[len("PROGRESS:"):].strip()
                    if progress_callback:
                        progress_callback(msg, None)
                elif cleaned.startswith("STATUS:"):
                    msg = cleaned[len("STATUS:"):].strip()
                    if progress_callback:
                        progress_callback(msg, None)
                elif cleaned.startswith("ERRO:"):
                    error_lines.append(cleaned)

        stderr_output = proc.stderr.read()
        returncode = proc.wait()

        if returncode != 0:
            err_msg = "\n".join(error_lines) or stderr_output.strip() or f"Código de saída {returncode}"
            log_event(f"Falha no empilhamento de {input_dir.name}: {err_msg}", "error")
            raise RuntimeError(f"Erro no empilhamento da sessão: {err_msg}")

        if report_data is None:
            # Tenta ler do report.json no diretório de saída
            report_files = list(output_dir.glob("*_report.json"))
            if report_files:
                report_data = json.loads(report_files[-1].read_text(encoding="utf-8"))
            else:
                report_data = {"status": "success", "session_dir": str(input_dir), "output_dir": str(output_dir)}

        log_event(f"Empilhamento concluído com sucesso para {input_dir.name}", "info")
        return report_data
