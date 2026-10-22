"""
Módulo de Identificação Taxonômica de Aves do IRIS (IRIS Bird ID).
Combina YOLOv8 para detecção de presença e recorte inteligente com BioCLIP para classificação fine-grained.
"""

from .detector import BirdDetector
from .classifier import BirdClassifier
from .inaturalist_client import INaturalistClient
from .stage import BirdIdStage, get_stage

__all__ = [
    "BirdDetector",
    "BirdClassifier",
    "INaturalistClient",
    "BirdIdStage",
    "get_stage",
]

