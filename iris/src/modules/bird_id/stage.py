"""
Estágio do Pipeline: Identificação de Espécies de Aves (BirdIdStage).
Fachada de compatibilidade retroativa para os estágios atômicos:
- detect_stage.py (BirdDetectStage)
- classify_stage.py (BirdClassifyStage)
- organize_stage.py (BirdOrganizeStage)
"""

from typing import Optional
from rich.console import Console

from src.core.pipeline import PipelineStage
from src.core.project import Project

from .detect_stage import BirdDetectStage
from .classify_stage import BirdClassifyStage
from .organize_stage import BirdOrganizeStage

console = Console()


class BirdIdStage(PipelineStage):
    """
    Fachada retrocompatível: executa a classificação taxonômica (ou o fluxo composto
    caso os recortes ainda não tenham sido gerados).
    """

    def __init__(self, stage_id: str = "bird_id", name: str = "Identificação de Aves"):
        super().__init__(stage_id, name)
        self.detect_stage = BirdDetectStage("bird_detect", "Detecção e Recorte de Aves (YOLOv8)")
        self.classify_stage = BirdClassifyStage(stage_id, name)
        self.organize_stage = BirdOrganizeStage("bird_organize", "Organização Física de Aves (Subpastas + EXIF)")

    def run(self, project: Project, **kwargs) -> bool:
        # Se ainda não houver recortes registrados no banco, executa a detecção prévia
        records = project.list_bird_identifications()
        has_crops = any(bool(r.get("crop_saved_path")) for r in records)

        if not has_crops and project.has_items():
            console.print("[dim]Recortes de aves não detectados previamente. Executando detecção prévia automática...[/dim]")
            ok_detect = self.detect_stage.run(project, **kwargs)
            if not ok_detect:
                return False

        # Executa a classificação taxonômica
        return self.classify_stage.run(project, **kwargs)


def get_stage(stage_id: str, name: str) -> PipelineStage:
    if stage_id == "bird_detect":
        return BirdDetectStage(stage_id, name)
    elif stage_id == "bird_organize":
        return BirdOrganizeStage(stage_id, name)
    elif stage_id in ["bird_id", "bird_classify"]:
        return BirdClassifyStage(stage_id, name)
    return BirdIdStage(stage_id, name)
