r"""Configuração global de fixtures do pytest para o IRIS.

Garante isolamento hermético entre os testes automatizados e o ambiente real
do usuário (especialmente C:\IRIS, ~/.iris e iris/config.yaml).
"""
import atexit
import copy
import os
import sys
import tempfile
from pathlib import Path

# 1. Configuração antecipada de variáveis de ambiente para isolamento ANTES de qualquer import do IRIS
_SESSION_TEMP_DIR = tempfile.TemporaryDirectory(prefix="iris_test_env_")
_SESSION_PATH = Path(_SESSION_TEMP_DIR.name)

os.environ["IRIS_GLOBAL_DIR"] = str(_SESSION_PATH / "iris_home")
os.environ["IRIS_CONFIG_FILE"] = str(_SESSION_PATH / "config.yaml")
os.environ["IRIS_SECRETS_DIR"] = str(_SESSION_PATH / "secrets")

def _cleanup_session():
    try:
        _SESSION_TEMP_DIR.cleanup()
    except Exception:
        pass

atexit.register(_cleanup_session)

# Garante que a pasta iris/ esteja no sys.path
IRIS_DIR = Path(__file__).resolve().parent.parent
if str(IRIS_DIR) not in sys.path:
    sys.path.insert(0, str(IRIS_DIR))

import pytest
import logging

import src.core.config as config_mod
import src.core.project as project_mod
import src.core.lock as lock_mod
import src.core.logger as logger_mod
import src.modules.youtube.uploader as uploader_mod
from src.core.config import config


@pytest.fixture(autouse=True)
def isolate_iris_environment(tmp_path_factory, monkeypatch):
    """Isola completamente cada teste de ~/.iris, de C:/IRIS e de iris/config.yaml."""
    fake_global = tmp_path_factory.mktemp("iris_global")
    fake_projects = fake_global / "projects"
    fake_projects.mkdir(parents=True, exist_ok=True)
    fake_logs = fake_global / "logs"
    fake_logs.mkdir(parents=True, exist_ok=True)
    fake_db = fake_global / "db"
    fake_db.mkdir(parents=True, exist_ok=True)
    fake_central = fake_projects / "iris_central.db"
    fake_dest = tmp_path_factory.mktemp("iris_dest_root")
    fake_config_file = fake_global / "config.yaml"
    fake_secrets = fake_global / "secrets"

    # Snapshot do estado em memória das configurações
    orig_config_state = copy.deepcopy(config.config)

    # Isola diretórios de configuração e banco central
    monkeypatch.setattr(config_mod, "GLOBAL_DIR", fake_global)
    monkeypatch.setattr(config_mod, "PROJECTS_DIR", fake_projects)
    monkeypatch.setattr(config_mod, "DB_DIR", fake_db)
    monkeypatch.setattr(config_mod, "LOG_DIR", fake_logs)
    monkeypatch.setattr(config_mod, "CONFIG_FILE", fake_config_file)

    monkeypatch.setattr(project_mod, "PROJECTS_DIR", fake_projects)
    monkeypatch.setattr(project_mod, "CENTRAL_DB_PATH", fake_central)

    monkeypatch.setattr(lock_mod, "PROJECTS_DIR", fake_projects)
    monkeypatch.setattr(uploader_mod, "SECRETS_DIR", fake_secrets)

    # Isola logger para não poluir ~/.iris/logs/iris.log
    monkeypatch.setattr(logger_mod, "LOG_DIR", fake_logs)
    monkeypatch.setattr(logger_mod, "LOG_FILE", fake_logs / "iris.log")
    test_log_file = fake_logs / "test_iris.log"
    test_handler = logging.FileHandler(test_log_file, encoding="utf-8")
    test_handler.setFormatter(logger_mod.get_log_formatter())

    # Redireciona handlers do logger da Iris durante os testes
    orig_handlers = list(logger_mod.logger.handlers)
    logger_mod.logger.handlers.clear()
    logger_mod.logger.addHandler(test_handler)

    # Inicializa o banco central limpo dentro do diretório temporário
    project_mod.init_central_db(force=True)

    # Intercepta destination_root padrão para evitar escrita em C:\IRIS
    orig_config_get = config.get

    def patched_config_get(key, default=None):
        if key in ("general.destination_root", "storage.destination_root"):
            val = orig_config_get(key, default)
            # Se for o valor de produção padrão, vazio ou resíduo de outro teste, redireciona para o destino temporário atual
            if not val or val in ("C:\\IRIS", "C:/IRIS", "/caminho/para/destino") or "pytest" in str(val).lower() or "iris_test_env_" in str(val).lower():
                return str(fake_dest)
            return val
        return orig_config_get(key, default)

    monkeypatch.setattr(config, "get", patched_config_get)

    try:
        yield
    finally:
        # Restaura incondicionalmente o estado em memória das configurações
        config.config = orig_config_state

        # Restaura handlers originais do logger
        try:
            test_handler.close()
            logger_mod.logger.handlers.clear()
            for h in orig_handlers:
                logger_mod.logger.addHandler(h)
        except Exception:
            pass
