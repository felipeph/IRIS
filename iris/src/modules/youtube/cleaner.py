import os
import gc
import time
from pathlib import Path
from typing import Tuple, Optional
from send2trash import send2trash
from rich.console import Console
from rich.prompt import Confirm

from src.core.config import config
from src.core.project import Project

console = Console()

def verify_youtube_upload_status(youtube, video_id: str) -> Tuple[bool, str]:
    """
    Verifica formalmente na YouTube Data API v3 se o vídeo foi recebido
    e aceito com sucesso pelos servidores do YouTube.
    
    Retorna:
        (True, mensagem) se status for 'uploaded', 'processed' ou 'processing'.
        (False, mensagem) se o vídeo foi rejeitado, falhou, não existe ou deu erro de API.
    """
    if not youtube or not video_id:
        return False, "Cliente YouTube ou video_id ausente."

    try:
        req = youtube.videos().list(part="id,status", id=video_id)
        resp = req.execute()
        items = resp.get("items", [])
        if not items:
            return False, f"Vídeo '{video_id}' não foi localizado no canal do YouTube."

        status_info = items[0].get("status", {})
        upload_status = status_info.get("uploadStatus", "").lower()

        if upload_status in ["uploaded", "processed"]:
            return True, f"Upload verificado com sucesso no YouTube (uploadStatus: '{upload_status}')."
        elif upload_status == "processing":
            return True, "Upload verificado no YouTube (vídeo em fase de processamento nos servidores do Google)."
        elif upload_status in ["failed", "rejected"]:
            rejection_reason = status_info.get("rejectionReason", "rejeição desconhecida")
            return False, f"Upload com falha/rejeitado no YouTube (status: '{upload_status}', motivo: '{rejection_reason}')."
        else:
            return True, f"Vídeo ativo no canal (status: '{upload_status}')."

    except Exception as e:
        return False, f"Falha na comunicação com a API do YouTube: {e}"

def delete_local_rendered_video(
    video_path: Path,
    to_trash: bool = True,
    max_retries: int = 3,
    retry_delay: float = 0.5
) -> Tuple[bool, int, str]:
    """
    Exclui com segurança o arquivo de vídeo renderizado local.
    
    Inclui mecanismo de resiliência com garbage collection forçado e retentativas
    para contornar bloqueios temporários de descritores no Windows (WinError 32 / antivírus / Explorer).
    
    Args:
        video_path: Caminho para o arquivo de vídeo.
        to_trash: Se True, envia para a Lixeira do SO (send2trash). Se False, remove permanentemente (unlink).
        max_retries: Quantidade máxima de tentativas caso ocorra PermissionError transitório.
        retry_delay: Intervalo em segundos entre tentativas.
        
    Retorna:
        (sucesso: bool, bytes_liberados: int, mensagem_erro: str)
    """
    if not video_path.exists():
        return True, 0, "Arquivo já não existe no disco."

    file_size = 0
    try:
        file_size = video_path.stat().st_size
    except Exception:
        file_size = 0

    last_err = ""
    for attempt in range(1, max_retries + 1):
        gc.collect()
        try:
            if to_trash:
                send2trash(str(video_path.resolve()))
            else:
                video_path.unlink()
            return True, file_size, ""
        except PermissionError as e:
            last_err = str(e)
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                return False, 0, f"[WinError 32 / Permissão negada após {max_retries} tentativas]: {e}"
        except Exception as e:
            return False, 0, str(e)

    return False, 0, last_err

def clean_empty_parent_dirs(file_path: Path, stop_at_dir: Path) -> int:
    """
    Remove pastas de data vazias (ex: YYYY/MM/DD) de baixo para cima,
    parando imediatamente ao encontrar qualquer pasta com conteúdo ou a raiz delimitadora.
    """
    removed_count = 0
    current = file_path.parent
    try:
        stop_resolved = stop_at_dir.resolve()
    except Exception:
        stop_resolved = stop_at_dir

    while current and current != stop_resolved and current.exists():
        try:
            current_resolved = current.resolve()
            if current_resolved == stop_resolved:
                break
            # Se diretório estiver completamente vazio
            if not any(current.iterdir()):
                current.rmdir()
                removed_count += 1
                current = current.parent
            else:
                break
        except Exception:
            break

    return removed_count

def execute_post_upload_cleanup(
    project: Project,
    video_path: Path,
    video_id: str,
    job_type: str,
    youtube=None,
    interactive: bool = True,
    ui_console: Optional[Console] = None
) -> bool:
    """
    Orquestra o ciclo completo de verificação na API do YouTube e limpeza do vídeo local 4K.
    
    Args:
        project: Instância ativa do Project.
        video_path: Caminho do arquivo .mp4 local (timelapse ou upscale).
        video_id: ID do vídeo retornado pelo YouTube.
        job_type: 'timelapse' ou 'edited_video'.
        youtube: Cliente autenticado da YouTube API v3.
        interactive: Se True, pergunta confirmação caso auto_cleanup esteja desativado.
        ui_console: Console Rich para saída formatada (opcional).
    """
    c = ui_console or console
    yt_config = config.get("modules.youtube", {})

    cleanup_enabled = yt_config.get("cleanup_local_videos", True)
    if not cleanup_enabled:
        return True

    if not video_path.exists():
        # Se o arquivo já foi apagado, apenas assegura que o DB está marcado
        if job_type == "timelapse":
            project.mark_timelapse_local_deleted(str(video_path.resolve()))
        else:
            project.mark_edited_video_local_deleted(str(video_path.resolve()))
        return True

    file_size_bytes = video_path.stat().st_size
    file_mb = file_size_bytes / (1024**2)
    file_gb = file_size_bytes / (1024**3)

    c.print(f"\n[bold cyan]🔍 Verificando integridade no YouTube antes da limpeza de disco...[/bold cyan]")

    # 1. Verificação formal na API do YouTube
    verified, verify_msg = verify_youtube_upload_status(youtube, video_id)
    if not verified:
        c.print(f"[bold red]❌ ATENÇÃO: Verificação de upload falhou! O arquivo local NÃO será apagado.[/bold red]")
        c.print(f"[red]Motivo: {verify_msg}[/red]")
        return False

    c.print(f"[green]✔ {verify_msg}[/green]")

    # 2. Resolução de preferências de limpeza
    to_trash = yt_config.get("cleanup_to_trash", True)
    auto_clean = yt_config.get("auto_cleanup_videos", False)

    target_action_label = "enviar para a Lixeira" if to_trash else "apagar permanentemente"
    
    if interactive and not auto_clean:
        type_desc = "Timelapse 4K" if job_type == "timelapse" else "Vídeo Upscale 4K"
        prompt_text = (
            f"\n[bold yellow]🗑 Deseja {target_action_label} o arquivo local de {type_desc} "
            f"'{video_path.name}' ({file_gb:.2f} GB) já verificado no YouTube?[/bold yellow]"
        )
        should_clean = Confirm.ask(prompt_text, default=True)
        if not should_clean:
            c.print(f"[dim]Arquivo local '{video_path.name}' preservado no SSD a pedido do usuário.[/dim]")
            return True
    else:
        c.print(f"[bold yellow]⚡ Limpeza pós-upload ativada: {target_action_label} '{video_path.name}' ({file_gb:.2f} GB)...[/bold yellow]")

    # 3. Execução da exclusão física
    ok, bytes_freed, err = delete_local_rendered_video(video_path, to_trash=to_trash)
    if not ok:
        c.print(f"[bold red]Erro ao remover vídeo local: {err}[/bold red]")
        return False

    # 4. Atualização no banco de dados local e central
    if job_type == "timelapse":
        project.mark_timelapse_local_deleted(str(video_path.resolve()))
    else:
        project.mark_edited_video_local_deleted(str(video_path.resolve()))

    # 5. Remoção de pastas de data vazias residuais
    dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
    root_category_dir = dest_root / ("6_Produzidos" if job_type == "timelapse" else "7_Video_Editado_4K")
    clean_empty_parent_dirs(video_path, root_category_dir)

    dest_desc = "Lixeira do Windows" if to_trash else "Exclusão Definitiva"
    c.print(f"[bold green]✔ Limpeza concluída: {file_gb:.2f} GB liberados no SSD ({dest_desc})![/bold green]")
    return True
