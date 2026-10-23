"""
Estágio do Pipeline: Organização Física de Aves (BirdOrganizeStage).
Executa as ações físicas de alta certeza para as aves identificadas no banco SQLite:
1. Renomeação taxonômica segura: {stem}_{Nome_PT}_{Nome_Cientifico}.{ext}
2. Movimentação física para subpasta da espécie dentro da categoria (ex: 2_AlbunsDatas/.../{Nome_PT}/)
3. Agrupamento de fotos irmãs de rajada na pasta da espécie
4. Limpeza e poda de pastas vazias residuais
5. Sincronização atômica do SQLite do projeto (items e bird_identifications)
Painel Rich Live padronizado com acompanhamento em tempo real.
"""

from datetime import datetime
import shutil
from pathlib import Path
from rich.console import Console
from rich.live import Live

from src.core.config import config
from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from src.core.cleanup import clean_empty_parent_dirs, clean_empty_directories
from src.core.ui import ProgressTracker, PipelineUI
from .action import apply_bird_physical_move, build_bird_filename

console = Console()


class BirdOrganizeStage(PipelineStage):
    """Estágio atômico de organização física e renomeação de aves identificadas."""

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
        organized_bursts: dict[str, tuple[Path, dict]] = {}

        total_records = len(records)
        tracker = ProgressTracker(total_records, mode="items")
        start_str = datetime.now().strftime("%H:%M:%S")
        stage_title = "ETAPA: ORGANIZAÇÃO FÍSICA E RENOMEAÇÃO DE AVES"

        with Live(
            PipelineUI.generate_renderable(tracker, stage_title, start_str, total_records, 0.0, "Carregando...", "Iniciando"),
            console=console,
            refresh_per_second=4
        ) as live:
            for rec in records:
                item_path_str = rec.get("item_path", "")
                item = items_by_path.get(item_path_str)
                if not item:
                    try:
                        item = items_by_path.get(str(Path(item_path_str).resolve()))
                    except Exception:
                        item = None

                cur_filename = Path(item_path_str).name if item_path_str else "desconhecido"
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_records, 0.0, cur_filename, "Organizando..."))

                if not item:
                    missing_file_count += 1
                    tracker.update(1)
                    continue

                conf = float(rec.get("confidence", 0.0))
                needs_review = bool(rec.get("needs_review", False))
                has_species = bool(rec.get("species_common") or rec.get("species_scientific"))
                is_early_exit = bool(rec.get("metadata_json", {}).get("burst_early_exit", False))

                # Permite organizar se houver espécie identificada e:
                # 1) conf >= min_confidence e não necessita revisão; OU
                # 2) Foi validado com sucesso por Early Exit de rajada (Abordagem B) com needs_review == False
                if not has_species or needs_review:
                    skipped_review_count += 1
                    tracker.update(1)
                    continue

                if conf < min_confidence and not is_early_exit:
                    skipped_review_count += 1
                    tracker.update(1)
                    continue

                try:
                    current_p = Path(item.organized_path or item.staging_path or item.original_path)
                    if not current_p.exists():
                        missing_file_count += 1
                        tracker.update(1)
                        continue

                    new_path = apply_bird_physical_move(item, project, rec, module_cfg)
                    if new_path != current_p:
                        # Atualiza o índice em memória com o novo caminho
                        items_by_path[str(new_path.resolve())] = item
                        rec["item_path"] = str(new_path.resolve())

                    b_id = getattr(item, "burst_id", "") or ""
                    if b_id and new_path.exists():
                        organized_bursts[b_id] = (new_path.parent, rec)

                    organized_count += 1
                except Exception as e:
                    console.print(f"[yellow]Aviso ao organizar fisicamente a ave {rec.get('species_common')}: {e}[/yellow]")
                finally:
                    tracker.update(1)

            # Mover e renomear fotos irmãs da mesma rajada (sem recorte individual) para a mesma subpasta da espécie
            burst_siblings_moved = 0
            dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
            old_burst_dirs_to_clean: set[Path] = set()
            rename_files = bool(module_cfg.get("rename_files", True))

            if organized_bursts:
                live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_records, 0.0, "Rajadas", "Unificando fotos irmãs de rajada..."))
                for b_id, (target_subfolder, burst_rec) in organized_bursts.items():
                    c_pt = burst_rec.get("species_common", "")
                    sci = burst_rec.get("species_scientific", "")
                    meta_dict = burst_rec.get("metadata_json", {}) if isinstance(burst_rec.get("metadata_json"), dict) else {}
                    c_en = burst_rec.get("species_common_en", "") or meta_dict.get("species_common_en", "") or meta_dict.get("common_en", "")

                    siblings = project.get_items(burst_id=b_id)
                    for sib in siblings:
                        sib_p = Path(sib.organized_path or sib.staging_path or sib.original_path)
                        if not sib_p.exists():
                            continue

                        if rename_files and (c_pt or sci):
                            new_sib_name = build_bird_filename(sib_p.name, c_pt, sci, c_en)
                        else:
                            new_sib_name = sib_p.name

                        dest_sib = target_subfolder / new_sib_name
                        if dest_sib.resolve() != sib_p.resolve():
                            old_sib_dir = sib_p.parent
                            if dest_sib.exists():
                                dest_sib = target_subfolder / f"{dest_sib.stem}_1{dest_sib.suffix}"
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
                            if old_sib_dir.resolve() != target_subfolder.resolve():
                                old_burst_dirs_to_clean.add(old_sib_dir)

            # Limpeza defensiva de pastas de rajadas originais e poda na raiz do IRIS
            for old_bdir in old_burst_dirs_to_clean:
                clean_empty_parent_dirs(old_bdir, stop_at_dir=dest_root)
            clean_empty_directories(dest_root, preserve_root=True)

            live.update(PipelineUI.generate_renderable(tracker, stage_title, start_str, total_records, 0.0, "Concluído", "Finalizando"))

        console.print(f"[bold green]OK: Organização física de aves concluída![/bold green]")
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
