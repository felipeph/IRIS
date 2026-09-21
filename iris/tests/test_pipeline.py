import pytest
from unittest.mock import patch, MagicMock
from src.core.pipeline import PipelineRunner, PipelineStage
from src.core.project import Project

class DummyStage(PipelineStage):
    def run(self, project: Project) -> bool:
        project.current_stage_id = self.stage_id
        return True

class FailingStage(PipelineStage):
    def run(self, project: Project) -> bool:
        return False

@pytest.fixture
def dummy_project():
    return Project("dummy_proj", "/caminho/teste")

@patch("importlib.import_module")
def test_pipeline_runner_initialization(mock_import_module):
    """Testa se o runner lê do config dinamicamente."""
    from src.core.config import config
    original_config = dict(config.config)
    try:
        config.config["pipeline"] = {
            "stages": [
                {"id": "dummy", "name": "Dummy Stage", "module": "dummy.module", "enabled": True},
                {"id": "disabled", "name": "Disabled", "module": "disabled.module", "enabled": False}
            ]
        }
        
        # Simula o import_module
        mock_mod = MagicMock()
        mock_mod.get_stage.return_value = DummyStage("dummy", "Dummy Stage")
        mock_import_module.return_value = mock_mod
        
        runner = PipelineRunner()
        
        assert len(runner.stages) == 1
        assert runner.stages[0].stage_id == "dummy"
        mock_import_module.assert_called_once_with("dummy.module")
    finally:
        config.config = original_config


def test_pipeline_execution(dummy_project):
    """Garante que a execução roda as etapas corretamente."""
    runner = PipelineRunner()
    
    stage1 = DummyStage("s1", "Stage 1")
    stage2 = DummyStage("s2", "Stage 2")
    runner.stages = [stage1, stage2]
    
    with patch("src.core.project.Project.save") as mock_save:
        runner.run_project(dummy_project)
        
        # current_stage_id deve ser o último stage após sucesso
        assert dummy_project.current_stage_id == "s2"
        # O save deve ser chamado por cada stage que obteve sucesso
        assert mock_save.call_count == 2

def test_pipeline_failure_stops_execution(dummy_project):
    """Se uma etapa falhar, as seguintes não devem rodar."""
    runner = PipelineRunner()
    
    stage1 = FailingStage("s1", "Fails")
    stage2 = DummyStage("s2", "Should not run")
    runner.stages = [stage1, stage2]
    
    with patch("src.core.project.Project.save") as mock_save:
        runner.run_project(dummy_project)
        assert dummy_project.current_stage_id == "" # Não atualizou
        mock_save.assert_not_called()

def test_pipeline_resume(dummy_project):
    """Garante que retoma de onde parou."""
    runner = PipelineRunner()
    stage1 = DummyStage("s1", "Stage 1")
    stage2 = DummyStage("s2", "Stage 2")
    runner.stages = [stage1, stage2]
    
    # Simula que o projeto já concluiu a etapa 1
    dummy_project.current_stage_id = "s1"
    
    with patch.object(stage1, "run") as mock_run1, patch.object(stage2, "run", return_value=True) as mock_run2:
        runner.run_project(dummy_project)
        
        mock_run1.assert_not_called() # Pula a s1
        mock_run2.assert_called_once() # Roda a s2
