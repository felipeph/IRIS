"""
Estágio do Pipeline: Organização Física de Aves (BirdOrganizeStage).
Executa as ações de alta certeza para as aves identificadas no banco SQLite:
1. Renomeação taxonômica tripla: [Nome_Popular_PT]_[Nome_Científico]_[Nome_Popular_EN]
2. Movimentação física para subpasta da espécie dentro da categoria (ex: 2_AlbunsDatas/.../{Nome_PT}/)
3. Injeção de metadados taxonômicos EXIF/IPTC/XMP via ExifTool
4. Sincronização atômica do SQLite do projeto (items e bird_identifications).
Casos de dúvida ou confiança < limiar permanecem inalterados no disco.
"""

from pathlib import Path
from rich.console import Console

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from .action import apply_bird_organization

console = Console()


class BirdOrganizeStage(PipelineStage):
    """Estágio atômico de organização física, renomeação e injeção EXIF de aves identificadas."""

    def run(self, project: Project, **kwargs) -> bool:
        init_central_db()

        if not project.has_items():
            console.print("[yellow]Nenhum arquivo no projeto para organizar aves.[/yellow]")
            return True

        module_cfg = config.get("modules.bird_id", {})
        if not module_cfg.get("enabled", True):
            console.print("[dim]Organização de aves desabilitada no config. Pulando.[/dim]")
            return True

        min_confidence = float(module_cfg.get("min_species_confidence", 0.70))
        records = project.list_bird_identifications()
        if not records:
            console.print("[yellow]Nenhum registro de identificação de aves encontrado no banco do projeto.[/yellow]")
            console.print("[dim]Execute primeiro a identificação (bird_id / bird_classify) antes de organizar fisicamente.[/dim]")
            return True

        # Indexar ProjectItems por seus caminhos conhecidos
        items_by_path = {}
        for it in project.get_items():
            for p_str in [it.organized_path, it.staging_path, it.original_path]:
                if p_str:
                    items_by_path[p_str] = it
                    try:
                        items_by_path[str(Path(p_str).resolve())] = it
                    except Exception:
                        pass

        organized_count = 0
        skipped_review_count = 0
        missing_file_count = 0

        console.print(f"[bold cyan]Iniciando organização física de aves ({len(records)} registros avaliados, limiar >= {min_confidence*100:.0f}%)...[/bold cyan]")

        for rec in records:
            item_path_str = rec.get("item_path", "")
            item = items_by_path.get(item_path_str)
            if not item:
                # Tenta buscar pelo resolved path
                try:
                    item = items_by_path.get(str(Path(item_path_str).resolve()))
                except Exception:
                    item = None

            if not item:
                missing_file_count += 1
                continue

            conf = float(rec.get("confidence", 0.0))
            needs_review = bool(rec.get("needs_review", False))
            has_species = bool(rec.get("species_common") or rec.get("species_scientific"))

            if not has_species or conf < min_confidence or needs_review:
                skipped_review_count += 1
                continue

            try:
                current_p = Path(item.organized_path or item.staging_path or item.original_path)
                if not current_p.exists():
                    missing_file_count += 1
                    continue

                new_path = apply_bird_organization(item, project, rec, module_cfg)
                if new_path != current_p:
                    # Atualiza o índice em memória com o novo caminho
                    items_by_path[str(new_path.resolve())] = item
                    rec["item_path"] = str(new_path.resolve())

                organized_count += 1
            except Exception as e:
                console.print(f"[yellow]Aviso ao organizar fisicamente a ave {rec.get('species_common')}: {e}[/yellow]")

        console.print(f"[bold green]OK: Organização de aves concluída![/bold green]")
        console.print(f"  [green]• Arquivos organizados com alta certeza:[/green] [bold cyan]{organized_count}[/bold cyan]")
        if skipped_review_count > 0:
            console.print(f"  [yellow]• Arquivos preservados para revisão manual (confiança < {min_confidence*100:.0f}%):[/yellow] [dim]{skipped_review_count}[/dim]")
        if missing_file_count > 0:
            console.print(f"  [dim]• Registros com arquivo físico não localizado:[/dim] {missing_file_count}")

        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdOrganizeStage(stage_id, name)
