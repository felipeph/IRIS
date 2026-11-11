#!/usr/bin/env python3
"""
Utilitário de Preflight para o IRIS (Imaging Resources and Integration System).
Executa uma auditoria abrangente de pré-voo no ambiente, ferramentas externas,
aceleração por hardware, modelos de IA, credenciais de APIs, armazenamento e locks.

Uso:
    python iris/scripts/preflight.py
    python iris/scripts/preflight.py --json
"""

import sys
import os
import shutil
import subprocess
import json
import argparse
from pathlib import Path
from datetime import datetime

# Garante suporte completo a UTF-8 no console do Windows
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
        if sys.stdin and hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

IRIS_DIR = Path(__file__).resolve().parents[1]
if str(IRIS_DIR) not in sys.path:
    sys.path.insert(0, str(IRIS_DIR))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

console = Console()


def check_python_environment():
    """Verifica versão do Python e pacotes essenciais."""
    results = []
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    is_py_ok = sys.version_info >= (3, 10)
    results.append({
        "item": "Versão do Python",
        "status": "OK" if is_py_ok else "FALHA",
        "details": f"Python {py_ver} ({sys.executable})"
    })

    required_modules = [
        ("cv2", "OpenCV (Processamento de Imagens)"),
        ("ultralytics", "Ultralytics YOLO (Detecção de Aves)"),
        ("torch", "PyTorch (Inferência IA)"),
        ("requests", "Requests (Comunicação HTTP / iNaturalist)"),
        ("rich", "Rich (CLI UI e Observabilidade)"),
        ("yaml", "PyYAML (Leitura e Escrita de Configurações)"),
        ("send2trash", "Send2Trash (Lixeira Segura / Zero Data Loss)"),
        ("xxhash", "xxHash (Checksum de Integridade Ultrarrápido)"),
        ("googleapiclient", "Google API Client (Upload no YouTube)"),
        ("google_auth_oauthlib", "Google Auth OAuthlib (OAuth 2.0)")
    ]

    for mod_name, label in required_modules:
        try:
            __import__(mod_name)
            results.append({"item": f"Pacote: {label}", "status": "OK", "details": "Instalado"})
        except ImportError:
            results.append({"item": f"Pacote: {label}", "status": "FALHA", "details": f"Módulo '{mod_name}' não encontrado"})

    return results


def check_astro_environment():
    """Verifica ambiente isolado de astrofotografia (.venv_astro) e PlanetarySystemStacker."""
    results = []
    
    # Caminho do executável python no .venv_astro
    astro_python = IRIS_DIR / ".venv_astro" / ("Scripts" if sys.platform == "win32" else "bin") / ("python.exe" if sys.platform == "win32" else "python")
    
    if astro_python.exists():
        results.append({
            "item": "Ambiente .venv_astro",
            "status": "OK",
            "details": f"Disponível em {astro_python}"
        })

        # Teste de importação de dependências científicas
        cmd = [str(astro_python), "-c", "import PyQt5, tifffile, scipy, astropy, rawpy, cv2; print('OK')"]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0 and "OK" in res.stdout:
                results.append({
                    "item": "Dependências Científicas (Astro)",
                    "status": "OK",
                    "details": "PyQt5, tifffile, scipy, astropy, rawpy, cv2 validados"
                })
            else:
                results.append({
                    "item": "Dependências Científicas (Astro)",
                    "status": "AVISO",
                    "details": f"Falha ao carregar: {res.stderr.strip()}"
                })
        except Exception as e:
            results.append({
                "item": "Dependências Científicas (Astro)",
                "status": "AVISO",
                "details": f"Erro de teste: {str(e)}"
            })
    else:
        results.append({
            "item": "Ambiente .venv_astro",
            "status": "AVISO",
            "details": "Não provisionado em iris/.venv_astro (Etapa 10 PSS pode falhar)"
        })

    pss_dir = IRIS_DIR / "vendor" / "PlanetarySystemStacker"
    if pss_dir.exists() and (pss_dir / "planetary_system_stacker").exists():
        results.append({
            "item": "PlanetarySystemStacker (Vendor)",
            "status": "OK",
            "details": "Repositório vendorizado presente"
        })
    else:
        results.append({
            "item": "PlanetarySystemStacker (Vendor)",
            "status": "AVISO",
            "details": "Diretório não encontrado em iris/vendor/PlanetarySystemStacker"
        })

    return results


def check_external_binaries():
    """Verifica a presença e versões de ffmpeg, ffprobe e exiftool no PATH."""
    results = []
    
    # FFmpeg
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        try:
            res = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=5)
            first_line = res.stdout.splitlines()[0] if res.stdout else "Disponível"
            results.append({
                "item": "FFmpeg (Codificação e Concatenação)",
                "status": "OK",
                "details": f"{first_line[:60]} ({ffmpeg_path})"
            })
        except Exception:
            results.append({
                "item": "FFmpeg (Codificação e Concatenação)",
                "status": "OK",
                "details": f"Encontrado em {ffmpeg_path}"
            })
    else:
        results.append({
            "item": "FFmpeg (Codificação e Concatenação)",
            "status": "FALHA",
            "details": "Não encontrado no PATH do sistema"
        })

    # FFprobe
    ffprobe_path = shutil.which("ffprobe")
    if ffprobe_path:
        results.append({
            "item": "FFprobe (Extração de Metadados de Vídeo)",
            "status": "OK",
            "details": f"Encontrado em {ffprobe_path}"
        })
    else:
        results.append({
            "item": "FFprobe (Extração de Metadados de Vídeo)",
            "status": "FALHA",
            "details": "Não encontrado no PATH do sistema"
        })

    # ExifTool
    exiftool_path = shutil.which("exiftool")
    if exiftool_path:
        try:
            res = subprocess.run(["exiftool", "-ver"], capture_output=True, text=True, timeout=5)
            ver = res.stdout.strip() if res.stdout else "Disponível"
            results.append({
                "item": "ExifTool (Metadados EXIF/IPTC/XMP)",
                "status": "OK",
                "details": f"v{ver} ({exiftool_path})"
            })
        except Exception:
            results.append({
                "item": "ExifTool (Metadados EXIF/IPTC/XMP)",
                "status": "OK",
                "details": f"Encontrado em {exiftool_path}"
            })
    else:
        results.append({
            "item": "ExifTool (Metadados EXIF/IPTC/XMP)",
            "status": "FALHA",
            "details": "Não encontrado no PATH do sistema"
        })

    return results


def check_hardware_acceleration():
    """Verifica e reporta o backend de aceleração por hardware detectado pelo IRIS."""
    results = []
    try:
        from src.modules.timelapse.encoder import detect_ffmpeg_encoder
        encoder_name, encoder_args = detect_ffmpeg_encoder()
        is_hw = "qsv" in encoder_name.lower() or "nvenc" in encoder_name.lower() or "amf" in encoder_name.lower()
        results.append({
            "item": "Aceleração de Vídeo FFmpeg",
            "status": "OK" if is_hw else "AVISO",
            "details": f"Encoder ativo: {encoder_name} | Args: {' '.join(encoder_args)}"
        })
    except Exception as e:
        results.append({
            "item": "Aceleração de Vídeo FFmpeg",
            "status": "AVISO",
            "details": f"Erro na sondagem: {str(e)}"
        })
    return results


def check_ai_models():
    """Verifica o modelo YOLOv8s."""
    results = []
    model_paths = [
        IRIS_DIR / "yolov8s.pt",
        IRIS_DIR.parent / "yolov8s.pt",
        Path.cwd() / "yolov8s.pt",
        Path.cwd() / "iris" / "yolov8s.pt"
    ]
    found = None
    for p in model_paths:
        if p.exists() and p.is_file():
            found = p
            break

    if found:
        size_mb = found.stat().st_size / (1024 * 1024)
        results.append({
            "item": "Modelo YOLOv8s (Aves)",
            "status": "OK",
            "details": f"{found.name} ({size_mb:.1f} MB) em {found.parent}"
        })
    else:
        results.append({
            "item": "Modelo YOLOv8s (Aves)",
            "status": "FALHA",
            "details": "Arquivo yolov8s.pt não encontrado (Etapa 6 falhará)"
        })

    return results


def check_storage_and_paths():
    """Verifica diretórios de destino e origem configurados."""
    results = []
    from src.core.config import config
    
    dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
    if dest_root.exists():
        try:
            _, _, free = shutil.disk_usage(str(dest_root))
            free_gb = free / (1024**3)
            status = "OK" if free_gb >= 20.0 else "AVISO"
            results.append({
                "item": "Destino Raiz (SSD)",
                "status": status,
                "details": f"{dest_root} ({free_gb:.1f} GB livres disponíveis)"
            })
        except Exception:
            results.append({
                "item": "Destino Raiz (SSD)",
                "status": "OK",
                "details": f"{dest_root} (Existente)"
            })
    else:
        results.append({
            "item": "Destino Raiz (SSD)",
            "status": "AVISO",
            "details": f"{dest_root} não existe (será criado no primeiro uso)"
        })

    default_src = Path(config.get("general.default_source", "G:\\DCIM"))
    if default_src.exists():
        results.append({
            "item": "Origem Padrão (SD/HD)",
            "status": "OK",
            "details": f"{default_src} acessível"
        })
    else:
        results.append({
            "item": "Origem Padrão (SD/HD)",
            "status": "INFO",
            "details": f"{default_src} não montado (normal se o cartão SD não estiver inserido)"
        })

    return results


def check_credentials_and_apis():
    """Verifica credenciais do iNaturalist e YouTube."""
    results = []
    
    # 1. iNaturalist
    inat_candidates = [
        IRIS_DIR / "secrets" / "inaturalist.json",
        IRIS_DIR.parent / "secrets" / "inaturalist.json",
        Path.cwd() / "secrets" / "inaturalist.json",
        Path.cwd() / "iris" / "secrets" / "inaturalist.json"
    ]
    inat_found = next((p for p in inat_candidates if p.exists()), None)
    if inat_found:
        try:
            with open(inat_found, "r", encoding="utf-8") as f:
                cdata = json.load(f)
            has_user = bool(cdata.get("username") and cdata.get("password"))
            has_jwt = bool(cdata.get("jwt_token"))
            mode_str = "Sessão Automática (User/Pass)" if has_user else ("JWT Manual" if has_jwt else "Incompleto")
            results.append({
                "item": "iNaturalist API v2",
                "status": "OK",
                "details": f"Credenciais presentes ({mode_str}) em {inat_found.name}"
            })
        except Exception as e:
            results.append({
                "item": "iNaturalist API v2",
                "status": "AVISO",
                "details": f"Arquivo corrompido: {str(e)}"
            })
    else:
        results.append({
            "item": "iNaturalist API v2",
            "status": "AVISO",
            "details": "secrets/inaturalist.json ausente (Etapa 7 falhará se online)"
        })

    # 2. YouTube OAuth
    yt_secrets = IRIS_DIR / "secrets" / "client_secrets.json"
    yt_token = IRIS_DIR / "secrets" / "token.json"
    
    if yt_token.exists():
        try:
            from google.oauth2.credentials import Credentials
            creds = Credentials.from_authorized_user_file(str(yt_token))
            status_desc = "Válido" if creds.valid else ("Expirado (com refresh)" if creds.refresh_token else "Inválido")
            results.append({
                "item": "YouTube Data API v3",
                "status": "OK",
                "details": f"Token OAuth {status_desc} ({yt_token.name})"
            })
        except Exception as e:
            results.append({
                "item": "YouTube Data API v3",
                "status": "AVISO",
                "details": f"Erro no token: {str(e)}"
            })
    elif yt_secrets.exists():
        results.append({
            "item": "YouTube Data API v3",
            "status": "INFO",
            "details": "client_secrets.json presente, requer login inicial (consentimento web)"
        })
    else:
        results.append({
            "item": "YouTube Data API v3",
            "status": "AVISO",
            "details": "Credenciais OAuth ausentes (Etapa 14 desabilitada ou falhará)"
        })

    return results


def check_database_and_locks():
    """Verifica banco SQLite central e travas ativas de projetos."""
    results = []
    from src.core.config import PROJECTS_DIR
    from src.core.project import CENTRAL_DB_PATH, list_open_projects, get_last_active_project, get_project

    # Banco Central
    if CENTRAL_DB_PATH.exists():
        results.append({
            "item": "Banco Central SQLite",
            "status": "OK",
            "details": f"{CENTRAL_DB_PATH} ({CENTRAL_DB_PATH.stat().st_size // 1024} KB)"
        })
    else:
        results.append({
            "item": "Banco Central SQLite",
            "status": "AVISO",
            "details": "iris_central.db não encontrado (será inicializado no primeiro projeto)"
        })

    # Travas ativas
    lock_files = list(PROJECTS_DIR.glob("*.lock")) if PROJECTS_DIR.exists() else []
    active_locks = []
    stale_locks = []

    for lk in lock_files:
        try:
            with open(lk, "r", encoding="utf-8") as f:
                ldata = json.load(f)
            pid = ldata.get("pid")
            pname = ldata.get("project_name", lk.stem)
            
            # Verifica se PID está ativo
            pid_alive = False
            if pid:
                if sys.platform == "win32":
                    res = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
                    pid_alive = str(pid) in res.stdout
                else:
                    try:
                        os.kill(pid, 0)
                        pid_alive = True
                    except OSError:
                        pid_alive = False

            if pid_alive:
                active_locks.append((pname, pid))
            else:
                stale_locks.append((pname, pid, lk))
        except Exception:
            stale_locks.append((lk.stem, None, lk))

    if active_locks:
        desc = ", ".join([f"'{p}' (PID {pid})" for p, pid in active_locks])
        results.append({
            "item": "Processos Concorrentes (Locks)",
            "status": "INFO",
            "details": f"Em execução ativa: {desc}"
        })
    elif stale_locks:
        results.append({
            "item": "Processos Concorrentes (Locks)",
            "status": "AVISO",
            "details": f"{len(stale_locks)} trava(s) órfã(s) detectada(s) (PIDs inativos)"
        })
    else:
        results.append({
            "item": "Processos Concorrentes (Locks)",
            "status": "OK",
            "details": "Nenhum bloqueio concorrente ativo"
        })

    # Último projeto acessado
    last_proj_name = get_last_active_project()
    if last_proj_name:
        p = get_project(last_proj_name)
        if p:
            stage_str = p.current_stage_id if p.current_stage_id else "Novo / Não iniciado"
            items_cnt = p.get_items_count()
            results.append({
                "item": "Último Projeto Acessado",
                "status": "OK",
                "details": f"'{p.name}' | Estágio: {stage_str} | Mídias: {items_cnt}"
            })

    return results


def run_preflight():
    """Executa todas as checagens e gera a tabela Rich."""
    all_checks = []
    
    sections = [
        ("1. Ambiente Python & Dependências", check_python_environment),
        ("2. Astrofotografia & PSS (.venv_astro)", check_astro_environment),
        ("3. Binários & Ferramentas Externas", check_external_binaries),
        ("4. Aceleração por Hardware (GPU/QSV)", check_hardware_acceleration),
        ("5. Modelos de Inteligência Artificial", check_ai_models),
        ("6. Armazenamento & Unidades de Disco", check_storage_and_paths),
        ("7. Credenciais & Autenticação de APIs", check_credentials_and_apis),
        ("8. Persistência SQLite & Concorrência", check_database_and_locks),
    ]

    header_text = (
        "[bold white]:airplane: IRIS PREFLIGHT CHECK - AUDITORIA PRÉ-VOO DO AMBIENTE[/bold white]\n"
        f"[dim]Horário da Checagem:[/dim] [cyan]{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}[/cyan]\n"
        f"[dim]Diretório do IRIS:[/dim] [dim cyan]{IRIS_DIR}[/dim cyan]"
    )
    console.print(Panel(header_text, expand=False, border_style="cyan"))

    total_failures = 0
    total_warnings = 0

    for section_title, check_fn in sections:
        table = Table(title=f"🔹 [bold]{section_title}[/bold]", border_style="blue", show_header=True, header_style="bold cyan")
        table.add_column("Verificação / Recurso", style="white", min_width=32)
        table.add_column("Status", justify="center", min_width=10)
        table.add_column("Detalhes & Diagnóstico", style="dim white")

        checks = check_fn()
        for c in checks:
            status = c["status"]
            if status == "OK":
                status_formatted = "[bold green]✔ OK[/bold green]"
            elif status == "FALHA":
                status_formatted = "[bold red]✖ FALHA[/bold red]"
                total_failures += 1
            elif status == "AVISO":
                status_formatted = "[bold yellow]⚠ AVISO[/bold yellow]"
                total_warnings += 1
            else:
                status_formatted = "[bold cyan]ℹ INFO[/bold cyan]"

            table.add_row(c["item"], status_formatted, c["details"])
            all_checks.append(c)

        console.print(table)
        console.print()

    # Resumo Final
    if total_failures == 0:
        summary_title = "[bold green]✔ PREFLIGHT CONCLUÍDO COM SUCESSO - AMBIENTE PRONTO PARA EXECUÇÃO[/bold green]"
        summary_border = "green"
        summary_msg = (
            f"[bold green]Todas as verificações críticas foram aprovadas![/bold green]\n"
            f"[dim]Avisos não-bloqueantes:[/dim] {total_warnings}\n\n"
            "[white]O sistema IRIS pode ser executado com segurança total (Zero Data Loss).[/white]"
        )
    else:
        summary_title = f"[bold red]✖ PREFLIGHT REPROVADO ({total_failures} FALHAS CRÍTICAS)[/bold red]"
        summary_border = "red"
        summary_msg = (
            f"[bold red]Existem {total_failures} dependências críticas ausentes que impedirão o pipeline de rodar.[/bold red]\n"
            f"[dim]Avisos adicionais:[/dim] {total_warnings}\n\n"
            "[yellow]Corrija as falhas indicadas acima antes de iniciar o processamento de mídias.[/yellow]"
        )

    console.print(Panel(summary_msg, title=summary_title, border_style=summary_border, expand=False))
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditoria Pré-Voo do IRIS")
    parser.add_argument("--json", action="store_true", help="Exporta relatório em formato JSON puro")
    args = parser.parse_args()

    if args.json:
        # Modo JSON para automação
        checks = {}
        for name, fn in [
            ("python", check_python_environment),
            ("astro", check_astro_environment),
            ("binaries", check_external_binaries),
            ("hardware", check_hardware_acceleration),
            ("ai_models", check_ai_models),
            ("storage", check_storage_and_paths),
            ("credentials", check_credentials_and_apis),
            ("database", check_database_and_locks),
        ]:
            checks[name] = fn()
        print(json.dumps(checks, indent=2, ensure_ascii=False))
        sys.exit(0)
    else:
        sys.exit(run_preflight())
