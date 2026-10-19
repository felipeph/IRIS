r"""Configuração global de fixtures do pytest para o IRIS.

Garante isolamento hermético entre os testes automatizados e o ambiente real
do usuário (especialmente C:\IRIS e ~/.iris).
"""
import pytest
from pathlib import Path
import sys

# Garante que a pasta iris/ esteja no sys.path
IRIS_DIR = Path(__file__).resolve().parent.parent
if str(IRIS_DIR) not in sys.path:
    sys.path.insert(0, str(IRIS_DIR))

import src.core.config as config_mod
import src.core.project as project_mod
from src.core.config import config


@pytest.fixture(autouse=True)
def isolate_iris_environment(tmp_path_factory, monkeypatch):
    """Isola completamente o ambiente de testes de ~/.iris e de C:/IRIS."""
    fake_global = tmp_path_factory.mktemp("iris_global")
    fake_projects = fake_global / "projects"
    fake_projects.mkdir(parents=True, exist_ok=True)
    fake_central = fake_projects / "iris_central.db"
    fake_dest = tmp_path_factory.mktemp("iris_dest_root")

    # Isola diretórios de configuração e banco central
    monkeypatch.setattr(config_mod, "GLOBAL_DIR", fake_global)
    monkeypatch.setattr(config_mod, "PROJECTS_DIR", fake_projects)
    monkeypatch.setattr(config_mod, "DB_DIR", fake_global / "db")
    monkeypatch.setattr(config_mod, "LOG_DIR", fake_global / "logs")

    monkeypatch.setattr(project_mod, "PROJECTS_DIR", fake_projects)
    monkeypatch.setattr(project_mod, "CENTRAL_DB_PATH", fake_central)

    # Inicializa o banco central limpo dentro do diretório temporário
    project_mod.init_central_db(force=True)

    # Intercepta destination_root padrão para evitar escrita em C:\IRIS
    orig_config_get = config.get

    def patched_config_get(key, default=None):
        if key in ("general.destination_root", "storage.destination_root"):
            val = orig_config_get(key, default)
            # Se for o valor de produção padrão ou vazio, redireciona para o destino temporário
            if not val or val in ("C:\\IRIS", "C:/IRIS", "/caminho/para/destino"):
                return str(fake_dest)
            return val
        return orig_config_get(key, default)

    monkeypatch.setattr(config, "get", patched_config_get)
