"""
Módulo de Revisão e Correção Manual de Espécies de Aves (IRIS Bird ID).
Permite revisar itens com baixa certeza ou classificação equivocada sem sair do IRIS.
Oferece busca no catálogo central de espécies, seleção de alternativas do modelo (Top-N),
cadastro manual de novas espécies e aplicação em lote para clipes da mesma sessão de gravação.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from src.core.pipeline import PipelineStage
from src.core.project import Project, init_central_db
from .catalog import (
    sync_species_catalog,
    search_species,
    list_species,
    get_species,
    clean_bird_text
)
from .reporter import export_bird_review_csv

console = Console()


def _format_item_duration(rec: Dict[str, Any]) -> str:
    """Extrai texto amigável de duração se for vídeo."""
    if not rec.get("is_video"):
        return ""
    meta = rec.get("metadata_json", {})
    if isinstance(meta, dict) and "duration_sec" in meta:
        sec = float(meta["duration_sec"])
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m:02d}m{s:02d}s" if m > 0 else f"{s}s"
    return ""


def _render_catalog_picker(console: Console, pre_query: str = "") -> Optional[Dict[str, Any]]:
    """Sub-fluxo interativo para pesquisar e selecionar uma espécie do catálogo global."""
    query = pre_query
    while True:
        results = search_species(query, limit=15)
        title = f"Catálogo de Espécies do IRIS [Termo: '{query}']" if query else "Catálogo de Espécies Mais Frequentes no IRIS"
        table = Table(title=f"[bold cyan]{title}[/bold cyan]", border_style="cyan", show_header=True)
        table.add_column("#", justify="center", style="bold cyan", width=4)
        table.add_column("Nome Popular", style="bold white", min_width=20)
        table.add_column("Nome Científico", style="italic yellow", min_width=22)
        table.add_column("Família", style="dim", min_width=14)
        table.add_column("Usos", justify="right", style="green", width=6)

        for i, s in enumerate(results, 1):
            table.add_row(
                str(i),
                s.get("species_common", ""),
                s.get("species_scientific", ""),
                s.get("family", "") or "-",
                str(s.get("use_count", 1))
            )

        console.print(table)
        console.print("[dim]Digite o número da espécie, ou digite novo termo de busca, ou '0' para voltar.[/dim]")
        ans = Prompt.ask("\nEscolha uma espécie pelo número ou digite para filtrar", default="1").strip()

        if ans == "0":
            return None

        if ans.isdigit():
            idx = int(ans) - 1
            if 0 <= idx < len(results):
                return results[idx]
            else:
                console.print("[red]Número fora da lista exibida.[/red]")
        else:
            query = ans


def interactive_bird_correction_flow(project: Project):
    """
    Fluxo interativo no terminal (Rich) para revisar e corrigir espécies do projeto.
    Atualiza atomicamente o SQLite local e central, sincroniza o catálogo e move os arquivos se necessário.
    """
    init_central_db()
    sync_species_catalog(project_db_path=project._project_db_file)

    filter_needs_review_only = False

    while True:
        console.clear()
        records = project.list_bird_identifications()
        if not records:
            console.print(Panel(
                f"[yellow]Nenhum registro de identificação de aves encontrado no projeto '[bold]{project.name}[/bold]'.[/yellow]\n"
                "[dim]Execute as etapas de detecção e classificação taxonômica antes de revisar.[/dim]",
                title="Revisão de Aves",
                border_style="yellow"
            ))
            Prompt.ask("\n[dim]Pressione ENTER para voltar ao menu...[/dim]")
            return

        # Estatísticas
        total_items = len(records)
        needs_review_items = [r for r in records if r.get("needs_review")]
        review_count = len(needs_review_items)

        # Cabeçalho com alertas
        alert_line = (
            f"[bold red]⚠️  {review_count} item(ns) aguardando revisão taxonômica![/bold red]"
            if review_count > 0
            else "[bold green]✓ Todas as identificações estão validadas.[/bold green]"
        )
        header_text = (
            f"[bold white]:bird: IRIS BIRD ID - REVISÃO E CORREÇÃO DE ESPÉCIES[/bold white]\n"
            f"[dim]Projeto Ativo:[/dim] [cyan][{project.name}][/cyan] | [dim]Total de Mídias:[/dim] {total_items}\n"
            f"{alert_line}"
        )
        console.print(Panel(header_text, border_style="cyan"))

        # Determina quais itens exibir baseado no filtro ativo
        displayed_records = needs_review_items if (filter_needs_review_only and review_count > 0) else records

        table = Table(
            title=f"Lista de Mídias com Aves ({'Apenas Pendentes de Revisão' if filter_needs_review_only and review_count > 0 else 'Todas as Identificações'})",
            border_style="cyan",
            show_header=True
        )
        table.add_column("Item", justify="center", style="bold cyan", width=5)
        table.add_column("Tipo", justify="center", width=7)
        table.add_column("Arquivo / Duração", style="white", min_width=25)
        table.add_column("Espécie Atribuída", style="bold yellow", min_width=24)
        table.add_column("Nome Científico", style="italic dim", min_width=22)
        table.add_column("Confiança", justify="right", width=10)
        table.add_column("Status", justify="center", width=16)
        table.add_column("Sugestões Alternativas", style="dim", min_width=20)

        for i, rec in enumerate(displayed_records, 1):
            is_vid = rec.get("is_video", False)
            tipo_icon = "🎬 Vídeo" if is_vid else "📷 Foto"
            p = Path(rec.get("item_path", ""))
            fname = p.name
            dur = _format_item_duration(rec)
            file_label = f"{fname} ({dur})" if dur else fname

            comm = rec.get("species_common") or "Desconhecido"
            sci = rec.get("species_scientific") or ""
            conf_val = float(rec.get("confidence", 0.0)) * 100
            conf_str = f"{conf_val:.1f}%"
            if conf_val < 70.0:
                conf_str = f"[yellow]{conf_str}[/yellow]"

            needs_rev = rec.get("needs_review", False)
            status_badge = "[bold red]⚠️ REVISÃO[/bold red]" if needs_rev else "[bold green]✓ Confirmado[/bold green]"

            alt_parts = []
            if rec.get("top2_common"):
                alt_parts.append(f"{rec['top2_common']} ({float(rec.get('top2_confidence', 0.0))*100:.0f}%)")
            if rec.get("top3_common"):
                alt_parts.append(f"{rec['top3_common']}")
            alt_str = ", ".join(alt_parts) if alt_parts else "-"

            table.add_row(
                str(i),
                tipo_icon,
                file_label,
                comm,
                sci,
                conf_str,
                status_badge,
                alt_str
            )

        console.print(table)
        console.print("-" * 70)

        # Menu de Opções
        console.print("  [cyan][Número][/cyan] Selecionar item para revisar/corrigir espécie")
        if review_count > 0:
            if filter_needs_review_only:
                console.print("  [cyan]T.[/cyan] :list: Mostrar TODAS as mídias do projeto")
            else:
                console.print("  [cyan]R.[/cyan] :mag: Filtrar apenas pendentes de revisão ([bold red]" + str(review_count) + "[/bold red] itens)")
        console.print("  [cyan]0 ou V.[/cyan] :arrow_left: Voltar ao menu principal do IRIS")

        choice = Prompt.ask("\nSelecione uma opção", default="1" if displayed_records else "0").strip().upper()

        if choice in ["0", "V", "VOLTAR", "SAIR"]:
            break

        if choice == "R" and review_count > 0:
            filter_needs_review_only = True
            continue

        if choice == "T":
            filter_needs_review_only = False
            continue

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(displayed_records):
                target_rec = displayed_records[idx]
                _correct_single_item_flow(project, target_rec, all_project_records=records)
            else:
                console.print("[red]Número inválido.[/red]")
                Prompt.ask("\n[dim]Pressione ENTER para continuar...[/dim]")
        else:
            console.print("[red]Opção não reconhecida.[/red]")


def _correct_single_item_flow(
    project: Project,
    rec: Dict[str, Any],
    all_project_records: List[Dict[str, Any]]
):
    """Sub-fluxo interativo para correção de um item específico."""
    console.clear()
    item_path_str = rec.get("item_path", "")
    p = Path(item_path_str)
    is_vid = rec.get("is_video", False)
    meta = rec.get("metadata_json", {}) if isinstance(rec.get("metadata_json"), dict) else {}

    dur_str = _format_item_duration(rec)
    crop_path = rec.get("crop_saved_path", "")

    info_text = (
        f"[bold cyan]Arquivo:[/bold cyan] {p.name}\n"
        f"[dim]Caminho Completo:[/dim] {item_path_str}\n"
        f"[dim]Tipo:[/dim] {'Vídeo (' + dur_str + ')' if is_vid else 'Foto'}\n"
        f"[dim]Espécie Atual:[/dim] [bold yellow]{rec.get('species_common')} ({rec.get('species_scientific')})[/bold yellow]\n"
        f"[dim]Confiança Atual:[/dim] {float(rec.get('confidence', 0.0))*100:.1f}%\n"
        f"[dim]Status:[/dim] {'[bold red]⚠️ Requer Revisão[/bold red]' if rec.get('needs_review') else '[bold green]✓ Confirmado[/bold green]'}\n"
        f"[dim]Recorte Salvo em:[/dim] {crop_path if crop_path else 'Não disponível'}"
    )
    console.print(Panel(info_text, title="[bold]Detalhes do Item Selecionado[/bold]", border_style="yellow"))

    # Sugestões rápidas disponíveis do modelo
    options: List[Dict[str, Any]] = []

    # Opção Top 1
    if rec.get("species_scientific"):
        options.append({
            "species_common": rec.get("species_common"),
            "species_scientific": rec.get("species_scientific"),
            "species_common_en": rec.get("species_common_en", ""),
            "family": rec.get("family", ""),
            "order": rec.get("order", ""),
            "confidence": rec.get("confidence", 1.0),
            "label": f"Manter como {rec.get('species_common')} ({rec.get('species_scientific')})"
        })

    # Opção Top 2
    if rec.get("top2_scientific"):
        options.append({
            "species_common": rec.get("top2_common"),
            "species_scientific": rec.get("top2_scientific"),
            "species_common_en": "",
            "family": "",
            "order": "",
            "confidence": rec.get("top2_confidence", 1.0),
            "label": f"Alternativa 2: {rec.get('top2_common')} ({rec.get('top2_scientific')}) [{float(rec.get('top2_confidence', 0.0))*100:.1f}%]"
        })

    # Opção Top 3
    if rec.get("top3_scientific"):
        options.append({
            "species_common": rec.get("top3_common"),
            "species_scientific": rec.get("top3_scientific"),
            "species_common_en": "",
            "family": "",
            "order": "",
            "confidence": rec.get("top3_confidence", 1.0),
            "label": f"Alternativa 3: {rec.get('top3_common')} ({rec.get('top3_scientific')}) [{float(rec.get('top3_confidence', 0.0))*100:.1f}%]"
        })

    console.print("\n[bold]Escolha como deseja corrigir a espécie:[/bold]")
    for i, opt in enumerate(options, 1):
        console.print(f"  [cyan]{i}.[/cyan] {opt['label']}")

    console.print("  [cyan]S.[/cyan] :books: [bold green]Buscar no Catálogo Global do IRIS (Espécies Frequentes / Busca)[/bold green]")
    console.print("  [cyan]N.[/cyan] :heavy_plus_sign: Digitar nova espécie manualmente")
    console.print("  [cyan]X.[/cyan] :wastebasket: [red]Descartar (Marcar como 'Não é ave' / Falso Positivo)[/red]")
    console.print("  [cyan]0.[/cyan] :arrow_left: Cancelar")

    choice = Prompt.ask("\nSelecione a ação", default="S").strip().upper()

    chosen_species: Optional[Dict[str, Any]] = None

    if choice == "0":
        return

    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(options):
            chosen_species = options[idx]
        else:
            console.print("[red]Opção inválida.[/red]")
            return

    elif choice == "S":
        chosen_species = _render_catalog_picker(console)
        if not chosen_species:
            return

    elif choice == "N":
        comm_input = Prompt.ask("Nome popular em português da espécie (ex: Suiriri)").strip()
        sci_input = Prompt.ask("Nome científico da espécie (ex: Tyrannus melancholicus)").strip()
        if not comm_input and not sci_input:
            console.print("[red]Nome inválido. Cancelando.[/red]")
            return
        comm_en_input = Prompt.ask("Nome popular em inglês (opcional)", default="").strip()
        fam_input = Prompt.ask("Família taxonômica (opcional)", default="").strip()
        ord_input = Prompt.ask("Ordem taxonômica (opcional)", default="").strip()

        chosen_species = {
            "species_common": comm_input or sci_input,
            "species_scientific": sci_input or comm_input,
            "species_common_en": comm_en_input,
            "family": fam_input,
            "order": ord_input
        }

    elif choice == "X":
        confirmed = Confirm.ask(f"[bold red]Tem certeza que deseja desmarcar '{p.name}' como ave?[/bold red]", default=False)
        if confirmed:
            chosen_species = {
                "species_common": "Não é ave",
                "species_scientific": "None",
                "species_common_en": "",
                "family": "",
                "order": ""
            }
        else:
            return

    if not chosen_species:
        return

    # Tela de Confirmação
    new_comm = chosen_species.get("species_common", "")
    new_sci = chosen_species.get("species_scientific", "")
    console.print()
    console.print(Panel(
        f"Item: [bold]{p.name}[/bold]\n"
        f"Espécie Anterior: [red]{rec.get('species_common')} ({rec.get('species_scientific')})[/red]\n"
        f"Nova Espécie:     [bold green]{new_comm} ({new_sci})[/bold green]\n"
        f"Status:           [bold green]Confirmado (needs_review = 0, confiança = 1.0)[/bold green]",
        title="Confirmar Correção",
        border_style="green"
    ))

    # Detecta se há outros clipes/fotos da mesma sessão/data que também precisam de correção
    contiguous_items: List[Dict[str, Any]] = []
    curr_time_str = meta.get("timestamp_s")
    for r in all_project_records:
        if r.get("item_path") == rec.get("item_path"):
            continue
        # Mesma data no nome do arquivo
        r_name = Path(r.get("item_path", "")).name
        if p.name[:10] == r_name[:10] and r.get("needs_review"):
            contiguous_items.append(r)

    batch_apply = False
    if contiguous_items:
        console.print(f"\n[cyan]💡 O IRIS detectou {len(contiguous_items)} outro(s) arquivo(s) com revisão pendente gravados na mesma data ({p.name[:10]}):[/cyan]")
        for c in contiguous_items:
            console.print(f"   • {Path(c.get('item_path','')).name} [dim]({c.get('species_common')})[/dim]")
        batch_apply = Confirm.ask("\nDeseja aplicar esta MESMA espécie para todos estes itens contíguos da sessão?", default=True)

    confirmed_final = Confirm.ask(f"\nAplicar correção agora?", default=True)
    if not confirmed_final:
        console.print("[dim]Correção cancelada.[/dim]")
        return

    # Executa a correção do item principal
    items_to_update = [rec]
    if batch_apply:
        items_to_update.extend(contiguous_items)

    updated_count = 0
    for target in items_to_update:
        t_path = target.get("item_path", "")
        res = project.correct_bird_identification(
            item_path=t_path,
            new_species=chosen_species,
            apply_physical_move=True
        )
        if res:
            updated_count += 1

    # Regera o relatório CSV atualizado
    try:
        csv_path = project.project_dir / "relatorio_aves.csv"
        export_bird_review_csv(project.list_bird_identifications(), csv_path)
    except Exception:
        pass

    console.print(f"\n[bold green]✔ Sucesso! {updated_count} item(ns) corrigido(s) para '{new_comm}'![/bold green]")
    Prompt.ask("\n[dim]Pressione ENTER para continuar...[/dim]")


class BirdCorrectionStage(PipelineStage):
    """
    Estágio do Pipeline: Revisão e Correção de Espécies de Aves.
    Permite interatividade para homologação das espécies identificadas antes da organização e renderização.
    """

    def __init__(self, stage_id: str = "bird_correction", name: str = "Revisão e Correção de Aves"):
        super().__init__(stage_id, name)

    def run(self, project: Project, **kwargs) -> bool:
        interactive = kwargs.get("interactive", True)
        if not interactive:
            # Em execução não-interativa / lote autônomo, não bloqueia o pipeline
            return True
        interactive_bird_correction_flow(project)
        return True
