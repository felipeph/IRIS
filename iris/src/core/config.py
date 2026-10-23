import os
import yaml
from pathlib import Path

# Definição dos caminhos globais
GLOBAL_DIR = Path(os.environ.get("IRIS_GLOBAL_DIR", str(Path.home() / ".iris")))
LOG_DIR = GLOBAL_DIR / "logs"
DB_DIR = GLOBAL_DIR / "db"
PROJECTS_DIR = GLOBAL_DIR / "projects"

# O arquivo de configuração principal agora fica na pasta raiz do projeto (iris/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = Path(os.environ.get("IRIS_CONFIG_FILE", str(PROJECT_ROOT / "config.yaml")))

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

    @staticmethod
    def _sanitize_mojibake(data):
        """Corrige recursivamente strings corrompidas por double-encoding UTF-8 (mojibake)."""
        if isinstance(data, str):
            if any(marker in data for marker in ("Ã", "Â")):
                try:
                    candidate = data.encode("latin1").decode("utf-8")
                    return candidate
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            return data
        elif isinstance(data, dict):
            return {k: ConfigManager._sanitize_mojibake(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [ConfigManager._sanitize_mojibake(item) for item in data]
        return data

    @staticmethod
    def _get_default_stages():
        return [
            {
                "id": "ingestion",
                "name": "Ingestão de Arquivos (SD -> SSD)",
                "module": "src.modules.ingestion.stage",
                "enabled": True
            },
            {
                "id": "cleanup",
                "name": "Limpeza da Origem (Após verificação)",
                "module": "src.modules.cleanup.stage",
                "enabled": True
            },
            {
                "id": "sanitization",
                "name": "Sanitização de Metadados EXIF",
                "module": "src.modules.sanitization.stage",
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
                "id": "astro_stack",
                "name": "Empilhamento Lunar (PSS -> 8_Astro_Stack)",
                "module": "src.modules.astro_stack.stage",
                "enabled": True
            },
            {
                "id": "astro_sharpen",
                "name": "Aprimoramento Wavelets (9_Astro_Sharpening)",
                "module": "src.modules.astro_sharpen.stage",
                "enabled": True
            },
            {
                "id": "timelapse",
                "name": "Renderização de Timelapses (Fotos -> 4K)",
                "module": "src.modules.timelapse.stage",
                "enabled": True
            },
            {
                "id": "video_edit",
                "name": "Edição e Upscale 4K de Vídeos (Lanczos/GPU)",
                "module": "src.modules.video_edit.stage",
                "enabled": True
            },
            {
                "id": "youtube",
                "name": "Publicação no YouTube (Timelapses e Vídeos)",
                "module": "src.modules.youtube.stage",
                "enabled": True
            }
        ]

    def load(self):
        """Carrega as configurações do arquivo YAML. Cria um padrão se não existir."""
        if not CONFIG_FILE.exists():
            self._create_default_config()
            
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                raw_config = yaml.safe_load(f) or {}
                
            self.config = self._sanitize_mojibake(raw_config)
            has_mojibake = (raw_config != self.config)
                
            # Garante valores default caso o arquivo exista mas falte alguma chave
            if "general" not in self.config:
                self.config["general"] = {}
            gen = self.config["general"]
            gen.setdefault("theme", "dark")
            gen.setdefault("log_level", "INFO")
            gen.setdefault("destination_root", "C:\\IRIS")
            gen.setdefault("default_source", "/caminho/para/origem")
            gen.setdefault("last_project", None)
            
            if "pipeline" not in self.config:
                self.config["pipeline"] = {}
            pipe = self.config["pipeline"]
            
            has_changes = has_mojibake
            
            if "stages" not in pipe:
                pipe["stages"] = self._get_default_stages()
                has_changes = True
            else:
                existing_ids = {s.get("id") for s in pipe["stages"] if isinstance(s, dict)}
                default_stages = self._get_default_stages()
                for def_s in default_stages:
                    def_id = def_s.get("id")
                    if def_id not in existing_ids:
                        insert_idx = len(pipe["stages"])
                        if def_id in ("astro_stack", "astro_sharpen"):
                            for idx, s in enumerate(pipe["stages"]):
                                if s.get("id") == "organize":
                                    insert_idx = idx + 1
                                    if def_id == "astro_sharpen":
                                        for idx2, s2 in enumerate(pipe["stages"]):
                                            if s2.get("id") == "astro_stack":
                                                insert_idx = idx2 + 1
                                                break
                                    break
                                elif s.get("id") == "timelapse":
                                    insert_idx = idx
                                    break
                        pipe["stages"].insert(insert_idx, def_s)
                        existing_ids.add(def_id)
                        has_changes = True

            if "modules" not in self.config:
                self.config["modules"] = {}
            mods = self.config["modules"]

            if "astro_stack" not in mods:
                mods["astro_stack"] = {
                    "enabled": True,
                    "keep_percents": [10, 25, 50],
                    "margin_pixels": 128,
                    "align_box_width": 64,
                    "align_search_width": 20,
                    "stab_mode": "Surface",
                    "timeout_seconds": 600,
                    "venv_path": "auto",
                    "windows_toast": True,
                    "ntfy_topic": "iris-alerts"
                }
                has_changes = True

            if "astro_sharpen" not in mods:
                mods["astro_sharpen"] = {
                    "enabled": True,
                    "presets": ["registax_fiel", "registax_clean", "registax_iluminado", "registax_pro"],
                    "enable_clahe": True,
                    "use_limb_guard": True,
                    "windows_toast": True,
                    "ntfy_topic": "iris-alerts"
                }
                has_changes = True

            if "timelapse_long_exposure" not in mods:
                mods["timelapse_long_exposure"] = {
                    "enabled": True,
                    "render_profile": "quality",
                    "crop_mode": "center",
                    "target_width": 3840,
                    "target_height": 2160,
                    "fps": 30,
                    "frames_per_image": 1,
                    "crf": 15,
                    "deband": {
                        "enabled": True,
                        "add_grain": True
                    }
                }
                has_changes = True
            elif "frames_per_image" not in mods["timelapse_long_exposure"]:
                mods["timelapse_long_exposure"]["frames_per_image"] = 1
                has_changes = True

            if "youtube" in mods:
                if "timelapse_long_exposure_playlist" not in mods["youtube"]:
                    mods["youtube"]["timelapse_long_exposure_playlist"] = "Timelapses Longa Exposição"
                    has_changes = True

            if "bird_id" in mods:
                if "enable_burst_consensus" not in mods["bird_id"]:
                    mods["bird_id"]["enable_burst_consensus"] = True
                    has_changes = True
                if "burst_min_agreement_ratio" not in mods["bird_id"]:
                    mods["bird_id"]["burst_min_agreement_ratio"] = 0.50
                    has_changes = True
                if "enable_burst_early_exit" not in mods["bird_id"]:
                    mods["bird_id"]["enable_burst_early_exit"] = True
                    has_changes = True
                if "burst_early_exit_confirmations" not in mods["bird_id"]:
                    mods["bird_id"]["burst_early_exit_confirmations"] = 3
                    has_changes = True

            if "classification" not in self.config:
                self.config["classification"] = {}
            cls_cfg = self.config["classification"]

            if "timelapse_normal" not in cls_cfg:
                cls_cfg["timelapse_normal"] = {
                    "min_photos": 200,
                    "min_interval_seconds": 0.3,
                    "max_interval_seconds": 60.0,
                    "tolerance_ratio": 0.25,
                    "tolerance_min_seconds": 0.5,
                    "stall_factor_max": 4.0,
                    "max_stall_fraction": 0.05,
                    "min_regular_fraction": 0.90
                }
                has_changes = True

            if "timelapse_long_exposure" not in cls_cfg:
                cls_cfg["timelapse_long_exposure"] = {
                    "enabled": True,
                    "folder": "4_Timelapses_LongaExposicao",
                    "min_shutter_seconds": 5.0,
                    "min_photos": 60,
                    "max_interval_seconds": 180.0,
                    "tolerance_ratio": 0.15,
                    "tolerance_min_seconds": 3.0,
                    "stall_factor_max": 5.0,
                    "max_stall_fraction": 0.15,
                    "min_regular_fraction": 0.85
                }
                has_changes = True

            if has_changes:
                self.save()
        except Exception as e:
            print(f"Erro ao carregar configurações: {e}")
            self.config = {}

    def _create_default_config(self):
        """Cria o arquivo de configuração com valores padrão."""
        default_config = {
            "general": {
                "theme": "dark",
                "log_level": "INFO",
                "destination_root": "C:\\IRIS",
                "default_source": "/caminho/para/origem",
                "last_project": None
            },
            "pipeline": {
                "stages": self._get_default_stages()
            },
            "naming": {
                "photo_pattern": "{date}_{time}_{camera}_{resolution}_{dimensions}_{focal}_{aperture}_{shutter}_{iso}_{original}.{ext}",
                "video_pattern": "{date}_{time}_{camera}_{resolution}_{dimensions}_{fps}_{duration}_{original}.{ext}"
            },
            "classification": {
                "moon_zoom_threshold_mm": 1000.0,
                "recognize_timelapse_folders": True,
                "timelapse_min_photos": 200,
                "timelapse_min_photos_folder": 30,
                "timelapse_max_interval_seconds": 60.0,
                "timelapse_tolerance_ratio": 0.25,
                "enable_timelapse_album_samples": True,
                "timelapse_sample_interval_minutes": 10.0,
                "enable_burst_detection": True,
                "burst_interval_seconds": 1.5,
                "timelapse_normal": {
                    "min_photos": 200,
                    "min_interval_seconds": 0.3,
                    "max_interval_seconds": 60.0,
                    "tolerance_ratio": 0.25,
                    "tolerance_min_seconds": 0.5,
                    "stall_factor_max": 4.0,
                    "max_stall_fraction": 0.05,
                    "min_regular_fraction": 0.90
                },
                "timelapse_long_exposure": {
                    "enabled": True,
                    "folder": "4_Timelapses_LongaExposicao",
                    "min_shutter_seconds": 5.0,
                    "min_photos": 60,
                    "max_interval_seconds": 180.0,
                    "tolerance_ratio": 0.15,
                    "tolerance_min_seconds": 3.0,
                    "stall_factor_max": 5.0,
                    "max_stall_fraction": 0.15,
                    "min_regular_fraction": 0.85
                },
                "astro_timelapse": {
                    "min_shutter_seconds": 5.0,
                    "max_interval_seconds": 180.0,
                    "max_gap_seconds": 600.0
                }
            },
            "modules": {
                "dedup": {"enabled": True},
                "astro_stack": {
                    "enabled": True,
                    "keep_percents": [10, 25, 50],
                    "margin_pixels": 128,
                    "align_box_width": 64,
                    "align_search_width": 20,
                    "stab_mode": "Surface",
                    "timeout_seconds": 600,
                    "venv_path": "auto",
                    "windows_toast": True,
                    "ntfy_topic": "iris-alerts"
                },
                "astro_sharpen": {
                    "enabled": True,
                    "presets": ["registax_fiel", "registax_clean", "registax_iluminado", "registax_pro"],
                    "enable_clahe": True,
                    "use_limb_guard": True,
                    "windows_toast": True,
                    "ntfy_topic": "iris-alerts"
                },
                "timelapse": {
                    "enabled": True,
                    "render_profile": "fast",
                    "crop_mode": "bottom",
                    "target_width": 3840,
                    "target_height": 2160,
                    "fps": 60,
                    "frames_per_image": 1,
                    "crf": 15
                },
                "timelapse_long_exposure": {
                    "enabled": True,
                    "render_profile": "quality",
                    "crop_mode": "center",
                    "target_width": 3840,
                    "target_height": 2160,
                    "fps": 30,
                    "frames_per_image": 1,
                    "crf": 15,
                    "deband": {
                        "enabled": True,
                        "add_grain": True
                    }
                },
                "video_edit": {
                    "enabled": True,
                    "render_profile": "fast",
                    "mode": "individual",
                    "speed": 1.0,
                    "target_fps": 60,
                    "target_width": 3840,
                    "target_height": 2160,
                    "crf": 16,
                    "preset": "slow",
                    "unsharp_filter": True,
                    "deband_enabled": True,
                    "trim_enabled": True,
                    "trim_seconds": 2.0,
                    "strip_audio": False
                },
                "youtube": {
                    "enabled": True,
                    "playlist": "Timelapses",
                    "timelapse_long_exposure_playlist": "Timelapses Longa Exposição",
                    "video_playlist": "Natureza 4K UHD",
                    "privacy_status": "unlisted"
                },
                "bird_detect": {"enabled": True},
                "bird_id": {
                    "enabled": True,
                    "classifier_type": "inaturalist",
                    "min_species_confidence": 0.70,
                    "enable_burst_consensus": True,
                    "burst_min_agreement_ratio": 0.50,
                    "enable_burst_early_exit": True,
                    "burst_early_exit_confirmations": 3,
                    "rename_files": True,
                    "organize_in_subfolders": True,
                    "write_exif_tags": True,
                    "zoom_threshold_mm": 300.0,
                    "iris_crops_folder": "10_Aves/Recortes",
                    "yolo_model": "yolov8s.pt",
                    "yolo_confidence": 0.25,
                    "video_target_frames": 15,
                    "video_max_crops": 5,
                    "video_min_confident_crops": 2,
                    "inaturalist": {
                        "api_url": "https://api.inaturalist.org/v2/computervision/score_image",
                        "credentials_file": "secrets/inaturalist.json",
                        "default_lat": -20.456887,
                        "default_lng": -45.438307,
                        "positional_accuracy_meters": 25000,
                        "request_delay_seconds": 1.0,
                        "use_exif_gps": True
                    }
                },
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
