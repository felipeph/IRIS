import logging
import sys
from datetime import datetime
from src.core.config import config, LOG_DIR

# Configurações do arquivo de log
LOG_FILE = LOG_DIR / "iris.log"

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

    # Formato do log
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | [%(module)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler para escrever no arquivo
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # NOTA: Não adicionaremos StreamHandler padrão (para imprimir no console)
    # porque a interface gráfica (Rich) será responsável por exibir mensagens ao usuário
    # O logger serve principalmente para histórico / auditoria no arquivo.
    
    return logger

# Instância global do logger
logger = setup_logger()

def log_event(message, level="info"):
    """Função utilitária para registrar eventos rapidamente."""
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
