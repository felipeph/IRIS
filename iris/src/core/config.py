import os
import yaml
from pathlib import Path

# Definição dos caminhos globais
GLOBAL_DIR = Path.home() / ".iris"
LOG_DIR = GLOBAL_DIR / "logs"
DB_DIR = GLOBAL_DIR / "db"
PROJECTS_DIR = GLOBAL_DIR / "projects"

# O arquivo de configuração principal agora fica na pasta raiz do projeto (iris/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = PROJECT_ROOT / "config.yaml"

class ConfigManager:
    def __init__(self):
        self.config = {}
        self._ensure_directories()
        self.load()

    def _ensure_directories(self):
        """Garante que a estrutura global de diretórios exista."""
        GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        DB_DIR.mkdir(parents=True, exist_ok=True)
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

    def load(self):
        """Carrega as configurações do arquivo YAML. Cria um padrão se não existir."""
        if not CONFIG_FILE.exists():
            self._create_default_config()
            
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.config = yaml.safe_load(f) or {}
                
            # Garante valores default caso o arquivo exista mas falte alguma chave
            if "general" not in self.config:
                self.config["general"] = {}
            gen = self.config["general"]
            gen.setdefault("theme", "dark")
            gen.setdefault("log_level", "INFO")
            gen.setdefault("destination_root", "/caminho/para/destino")
            gen.setdefault("default_source", "/caminho/para/origem")
            gen.setdefault("last_project", None)
            
            if "pipeline" not in self.config:
                self.config["pipeline"] = {}
            pipe = self.config["pipeline"]
            if "stages" not in pipe:
                pipe["stages"] = [
                    {
                        "id": "ingestion",
                        "name": "Ingestão de Arquivos (SD -> SSD)",
                        "module": "src.modules.ingestion.stage",
                        "enabled": True
                    },
                    {
                        "id": "planning",
                        "name": "Planejamento e Metadados (Staging)",
                        "module": "src.modules.planning.stage",
                        "enabled": True
                    },
                    {
                        "id": "organize",
                        "name": "Organização Física (SSD)",
                        "module": "src.modules.organize.stage",
                        "enabled": True
                    },
                    {
                        "id": "cleanup",
                        "name": "Limpeza da Origem (Após verificação)",
                        "module": "src.modules.cleanup.stage",
                        "enabled": True
                    }
                ]
                self.save()  # Auto-save para popular o disco
        except Exception as e:
            print(f"Erro ao carregar configurações: {e}")
            self.config = {}

    def _create_default_config(self):
        """Cria o arquivo de configuração com valores padrão."""
        default_config = {
            "general": {
                "theme": "dark",
                "log_level": "INFO",
                "destination_root": "/caminho/para/destino",
                "default_source": "/caminho/para/origem",
                "last_project": None
            },
            "pipeline": {
                "stages": [
                    {
                        "id": "ingestion",
                        "name": "Ingestão de Arquivos (SD -> SSD)",
                        "module": "src.modules.ingestion.stage",
                        "enabled": True
                    },
                    {
                        "id": "planning",
                        "name": "Planejamento e Metadados (Staging)",
                        "module": "src.modules.planning.stage",
                        "enabled": True
                    },
                    {
                        "id": "organize",
                        "name": "Organização Física (SSD)",
                        "module": "src.modules.organize.stage",
                        "enabled": True
                    },
                    {
                        "id": "cleanup",
                        "name": "Limpeza da Origem (Após verificação)",
                        "module": "src.modules.cleanup.stage",
                        "enabled": True
                    }
                ]
            },
            "naming": {
                "photo_pattern": "{date}_{time}_{camera}_{resolution}_{dimensions}_{focal}_{aperture}_{shutter}_{iso}_{original}.{ext}",
                "video_pattern": "{date}_{time}_{camera}_{resolution}_{dimensions}_{fps}_{duration}_{original}.{ext}"
            },
            "classification": {
                "moon_zoom_threshold_mm": 1000.0,
                "timelapse_min_photos": 300,
                "timelapse_max_interval_seconds": 60.0,
                "timelapse_tolerance_ratio": 1.5,
                "enable_burst_detection": False,
                "burst_interval_seconds": 1.5
            },
            "modules": {
                "dedup": {"enabled": True},
                "timelapse": {"enabled": True},
                "bird_detect": {"enabled": True},
                "cleanup": {"auto_clean": False}
            }
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(default_config, f, default_flow_style=False, allow_unicode=True)
            
    def save(self):
        """Salva o estado atual das configurações no disco de forma atômica."""
        temp_file = CONFIG_FILE.with_suffix(".tmp")
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            os.replace(temp_file, CONFIG_FILE)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise e

    def get(self, key, default=None):
        """Obtém uma configuração usando navegação por pontos (ex: 'general.theme')"""
        keys = key.split('.')
        val = self.config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def set(self, key, value):
        """Define uma configuração usando navegação por pontos."""
        keys = key.split('.')
        d = self.config
        for k in keys[:-1]:
            if k not in d or not isinstance(d[k], dict):
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
        self.save()

# Instância global para ser importada por outros módulos
config = ConfigManager()
