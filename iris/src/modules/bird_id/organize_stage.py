"""
Estágio do Pipeline: Organização Física de Aves (BirdOrganizeStage).
Executa as ações de alta certeza para as aves identificadas no banco SQLite:
1. Renomeação taxonômica tripla: [Nome_Popular_PT]_[Nome_Científico]_[Nome_Popular_EN]
2. Movimentação física para subpasta da espécie dentro da categoria (ex: 2_AlbunsDatas/.../{Nome_PT}/)
3. Injeção de metadados taxonômicos EXIF/IPTC/XMP via ExifTool
4. Sincronização atômica do SQLite do projeto (items e bird_identifications).
Casos de dúvida ou confiança < limiar permanecem inalterados no disco.
"""

import shutil
from pathlib import Path
from rich.console import Console

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from src.core.cleanup import clean_empty_parent_dirs, clean_empty_directories
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
        organized_bursts: dict[str, Path] = {}

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

                b_id = getattr(item, "burst_id", "") or ""
                if b_id and new_path.exists():
                    organized_bursts[b_id] = new_path.parent

                organized_count += 1
            except Exception as e:
                console.print(f"[yellow]Aviso ao organizar fisicamente a ave {rec.get('species_common')}: {e}[/yellow]")

        # Mover fotos irmãs da mesma rajada (sem recorte individual) para a mesma subpasta da espécie
        burst_siblings_moved = 0
        dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
        old_burst_dirs_to_clean: set[Path] = set()

        for b_id, target_subfolder in organized_bursts.items():
            siblings = project.get_items(burst_id=b_id)
            for sib in siblings:
                sib_p = Path(sib.organized_path or sib.staging_path or sib.original_path)
                if sib_p.exists() and sib_p.parent.resolve() != target_subfolder.resolve():
                    old_sib_dir = sib_p.parent
                    dest_sib = target_subfolder / sib_p.name
                    if not dest_sib.exists():
                        shutil.move(str(sib_p), str(dest_sib))
                        sib.organized_path = str(dest_sib.resolve())
                        sib.target_filename = dest_sib.name
                        try:
                            sib.relative_dest_dir = str(dest_sib.parent.relative_to(dest_root))
                        except Exception:
                            pass
                        project.save_item(sib)
                        items_by_path[str(dest_sib.resolve())] = sib
                        burst_siblings_moved += 1
                        old_burst_dirs_to_clean.add(old_sib_dir)

        # Limpeza defensiva de pastas de rajadas originais e poda na raiz do IRIS
        for old_bdir in old_burst_dirs_to_clean:
            clean_empty_parent_dirs(old_bdir, stop_at_dir=dest_root)
        clean_empty_directories(dest_root, preserve_root=True)

        console.print(f"[bold green]OK: Organização de aves concluída![/bold green]")
        console.print(f"  [green]• Arquivos organizados com alta certeza:[/green] [bold cyan]{organized_count}[/bold cyan]")
        if burst_siblings_moved > 0:
            console.print(f"  [green]• Fotos irmãs de rajada unificadas na subpasta da espécie:[/green] [bold cyan]{burst_siblings_moved}[/bold cyan]")
        if skipped_review_count > 0:
            console.print(f"  [yellow]• Arquivos preservados para revisão manual (confiança < {min_confidence*100:.0f}%):[/yellow] [dim]{skipped_review_count}[/dim]")
        if missing_file_count > 0:
            console.print(f"  [dim]• Registros com arquivo físico não localizado:[/dim] {missing_file_count}")

        return True


def get_stage(stage_id: str, name: str) -> PipelineStage:
    return BirdOrganizeStage(stage_id, name)
