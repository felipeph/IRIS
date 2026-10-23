"""
Módulo de Identificação Taxonômica de Aves do IRIS (IRIS Bird ID).
Arquitetura modular em 3 etapas atômicas:
1. BirdDetectStage: Detecção de presença via YOLOv8 e extração de recortes.
2. BirdClassifyStage: Identificação taxonômica via iNaturalist API / BioCLIP e persistência no SQLite/CSV.
3. BirdOrganizeStage: Organização física em subpastas por espécie, renomeação e tags EXIF.
"""

from .detector import BirdDetector
from .classifier import BirdClassifier
from .inaturalist_client import INaturalistClient
from .detect_stage import BirdDetectStage
from .classify_stage import BirdClassifyStage
from .organize_stage import BirdOrganizeStage
from .burst_consensus import aggregate_burst_species
from .stage import BirdIdStage, get_stage

__all__ = [
    "BirdDetector",
    "BirdClassifier",
    "INaturalistClient",
    "BirdDetectStage",
    "BirdClassifyStage",
    "BirdOrganizeStage",
    "BirdIdStage",
    "get_stage",
    "aggregate_burst_species",
]
