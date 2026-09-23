import logging
import sys
from datetime import datetime
from pathlib import Path
from src.core.config import config, LOG_DIR

# Configurações do arquivo de log
LOG_FILE = LOG_DIR / "iris.log"
_project_handler = None

def get_log_formatter():
    return logging.Formatter(
        '%(asctime)s | PID:%(process)-5d | %(levelname)-8s | [%(module)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def setup_logger():
    # Carrega o nível de log da configuração (padrão INFO se não existir)
    log_level_str = config.get("general.log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Cria o logger principal da Iris
    logger = logging.getLogger("Iris")
    logger.setLevel(log_level)

    # Remove handlers antigos se existirem (para evitar logs duplicados ao recarregar)
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = get_log_formatter()

    # Handler para escrever no arquivo global (com tratamento de erro)
    try:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Aviso: Não foi possível anexar o arquivo de log principal: {e}", file=sys.stderr)

    return logger

# Instância global do logger
logger = setup_logger()

def bind_project_logger(project_name: str):
    """Anexa um handler de log exclusivo para o projeto ativo."""
    global _project_handler
    log_level_str = config.get("general.log_level", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    if _project_handler:
        try:
            logger.removeHandler(_project_handler)
            _project_handler.close()
        except Exception:
            pass
        _project_handler = None

    if not project_name:
        return

    proj_log_file = LOG_DIR / f"iris_{project_name}.log"
    try:
        _project_handler = logging.FileHandler(proj_log_file, encoding='utf-8')
        _project_handler.setLevel(log_level)
        _project_handler.setFormatter(get_log_formatter())
        logger.addHandler(_project_handler)
        logger.debug(f"Logger do projeto '{project_name}' associado a {proj_log_file}")
    except Exception as e:
        logger.warning(f"Não foi possível criar log dedicado para o projeto {project_name}: {e}")

def log_event(message, level="info"):
    """Função utilitária para registrar eventos rapidamente com tolerância a falhas."""
    try:
        level = level.lower()
        if level == "debug":
            logger.debug(message)
        elif level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        elif level == "critical":
            logger.critical(message)
        else:
            logger.info(message)
    except Exception:
        # Falha de log nunca deve interromper a execução do fluxo principal
        pass
