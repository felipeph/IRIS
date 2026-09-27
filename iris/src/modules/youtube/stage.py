import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from src.core.pipeline import PipelineStage
from src.core.project import Project
from src.core.config import config
from src.core.ui import PipelineUI
from src.modules.timelapse.notifier import send_windows_toast, send_ntfy_notification
from src.modules.youtube.uploader import (
    get_authenticated_service,
    build_timelapse_youtube_metadata,
    add_video_to_playlist
)

console = Console()

def wait_countdown(seconds: int, item_name: str) -> bool:
    """
    Contagem regressiva com captura de teclado sem travar a tela.
    [ENTER] = Envia imediatamente
    [P] = Pausa/Retoma
    [C] / [Q] = Cancela
    """
    msvcrt = None
    if sys.platform == "win32":
        try:
            import msvcrt
        except ImportError:
            msvcrt = None

    remaining = seconds
    paused = False

    while remaining > 0 or paused:
        if msvcrt and msvcrt.kbhit():
            ch = msvcrt.getch()
            try:
                ch_str = ch.decode('utf-8', errors='ignore').lower()
            except Exception:
                ch_str = ""

            if ch in [b'\r', b'\n', b' ']:
                console.print(f"\n[green]▶ Enviando '{item_name}' imediatamente...[/green]")
                return True
            elif ch_str in ['p', 'P']:
                paused = not paused
                if paused:
                    console.print(f"\n[yellow]⏸ Upload pausado! Pressione [P] ou [ENTER] para continuar...[/yellow]")
                else:
                    console.print(f"\n[green]▶ Retomado! Continuando contagem...[/green]")
            elif ch_str in ['c', 'C', 'q', 'Q', '\x1b']:
                console.print(f"\n[red]✖ Upload cancelado pelo usuário.[/red]")
                return False

        if not paused:
            mins, secs = divmod(remaining, 60)
            sys.stdout.write(f"\r⏳ Upload automático em: {mins:02d}:{secs:02d} | [ENTER] Enviar Já | [P] Pausar | [C] Cancelar ")
            sys.stdout.flush()
            time.sleep(1.0)
            remaining -= 1
        else:
            time.sleep(0.5)

    sys.stdout.write("\n")
    return True

class YouTubeUploadStage(PipelineStage):
    """
    Etapa 6: Publicação oficial de vídeos gerados no canal do YouTube.
    Executa upload resumable em blocos com acompanhamento Rich em tempo real
    e registra o link/ID no banco de dados do projeto e banco central.
    """

    def run(self, project: Project, interactive: bool = True, **kwargs) -> bool:
        yt_config = config.get("modules.youtube", {})
        if not yt_config.get("enabled", True):
            console.print("[dim]Módulo do YouTube desativado no config.yaml. Etapa ignorada.[/dim]")
            return True

        # 1. Buscar vídeos prontos para upload neste projeto
        pending_videos = project.get_timelapses(status="rendered")

        if not pending_videos:
            uploaded = project.get_timelapses(status="uploaded")
            if uploaded:
                console.print(f"[green]Todos os vídeos do projeto '{project.name}' já foram publicados no YouTube ({len(uploaded)} vídeo(s)).[/green]")
                force = kwargs.get("force_upload", False)
                if not force and kwargs.get("interactive", False):
                    from rich.prompt import Confirm
                    force = Confirm.ask(
                        f"[yellow]Deseja realizar novamente o upload desses {len(uploaded)} vídeo(s) para o YouTube?[/yellow]",
                        default=False
                    )
                if force:
                    pending_videos = uploaded
                else:
                    return True
            else:
                console.print(f"[cyan]Nenhum vídeo pendente de upload no projeto '{project.name}'. Etapa concluída.[/cyan]")
                return True

        console.print(f"\n[bold cyan]=== Etapa 6: Publicação no YouTube ({len(pending_videos)} vídeo(s) pendente(s)) ===[/bold cyan]")

        # 2. Autenticação na API
        youtube = get_authenticated_service()
        if not youtube:
            console.print("[bold red]ERRO: Falha ao autenticar na YouTube Data API. Verifique se client_secrets.json existe em secrets/.[/bold red]")
            return False

        success_count = 0
        error_count = 0

        for idx, record in enumerate(pending_videos, 1):
            video_path = Path(record["output_video_path"])
            if not video_path.exists():
                console.print(f"[red]Arquivo de vídeo não encontrado no disco: {video_path}[/red]")
                error_count += 1
                continue

            metadata = build_timelapse_youtube_metadata(video_path, record, yt_config, project=project)
            file_size = video_path.stat().st_size
            file_mb = file_size / (1024**2)

            meta_data = record.get("metadata_json") or {}
            cam_desc = meta_data.get("camera_model") or "Câmera"
            photos_desc = f"{record.get('photo_count', 0):,} fotos"
            dur_desc = f"{record.get('duration_seconds', 0.0):.1f}s"
            real_sec = meta_data.get("real_duration_seconds", 0.0)
            real_desc = f" | Tempo Real: {int(round(real_sec))}s" if real_sec > 0 else ""

            # Exibir Card de Metadados
            card_info = (
                f"[bold cyan]Arquivo:[/bold cyan]     {video_path.name} ({file_mb:.1f} MB)\n"
                f"[bold cyan]Título:[/bold cyan]      {metadata['title']}\n"
                f"[bold cyan]Ficha Técnica:[/bold cyan]{cam_desc} | {photos_desc} | {dur_desc}{real_desc}\n"
                f"[bold cyan]Privacidade:[/bold cyan] {metadata['privacy_status'].upper()}\n"
                f"[bold cyan]Playlist:[/bold cyan]    {yt_config.get('playlist', 'Timelapses')}"
            )
            console.print(Panel(card_info, title=f"Upload [{idx}/{len(pending_videos)}]", border_style="red"))

            # Controle de countdown / confirmação
            if interactive:
                interval_s = yt_config.get("stage_interval_seconds", 180)
                if not wait_countdown(interval_s, video_path.name):
                    console.print("[yellow]Upload deste vídeo foi pulado pelo usuário.[/yellow]")
                    continue
            else:
                time.sleep(2.0)

            # Preparar upload resumable
            body = {
                "snippet": {
                    "title": metadata["title"],
                    "description": metadata["description"],
                    "tags": metadata["tags"],
                    "categoryId": metadata["category_id"]
                },
                "status": {
                    "privacyStatus": metadata["privacy_status"],
                    "selfDeclaredMadeForKids": False
                }
            }

            chunk_size = 8 * 1024 * 1024  # 8MB
            try:
                media = MediaFileUpload(str(video_path), chunksize=chunk_size, resumable=True)
                request = youtube.videos().insert(
                    part=",".join(body.keys()),
                    body=body,
                    media_body=media
                )
            except Exception as e:
                console.print(f"[red]Erro ao preparar upload: {e}[/red]")
                error_count += 1
                continue

            # Upload com barra de progresso Rich
            start_time = time.time()
            start_str = datetime.now().strftime("%H:%M:%S")
            response = None
            retry_count = 0
            uploaded_bytes = 0

            with Live(PipelineUI.generate_upload_renderable(
                stage_title="ETAPA 6: PUBLICAÇÃO NO YOUTUBE (OAUTH 2.0)",
                start_str=start_str,
                video_title=metadata["title"],
                video_filename=video_path.name,
                total_bytes=file_size,
                uploaded_bytes=0,
                speed_str="0.0 MB/s",
                elapsed_str="0:00:00",
                eta_str="--:--:--",
                previsao_fim_str="--:--:--",
                status_msg="Conectando aos servidores do Google..."
            ), console=console, refresh_per_second=4) as live:

                while response is None:
                    try:
                        status, response = request.next_chunk()
                        if status:
                            uploaded_bytes = int(status.total_size * status.progress()) if status.total_size else uploaded_bytes
                            elapsed_sec = max(0.1, time.time() - start_time)
                            speed_mb = (uploaded_bytes / (1024**2)) / elapsed_sec
                            speed_str = f"{speed_mb:.2f} MB/s"
                            elapsed_str = str(timedelta(seconds=int(elapsed_sec)))

                            rem_bytes = max(0, file_size - uploaded_bytes)
                            if speed_mb > 0 and rem_bytes > 0:
                                eta_sec = (rem_bytes / (1024**2)) / speed_mb
                                eta_str = str(timedelta(seconds=int(eta_sec)))
                                end_dt = datetime.now() + timedelta(seconds=int(eta_sec))
                                previsao_str = end_dt.strftime("%H:%M:%S")
                            else:
                                eta_str = "0:00:00" if rem_bytes == 0 else "--:--:--"
                                previsao_str = datetime.now().strftime("%H:%M:%S")

                            live.update(PipelineUI.generate_upload_renderable(
                                stage_title="ETAPA 6: PUBLICAÇÃO NO YOUTUBE (OAUTH 2.0)",
                                start_str=start_str,
                                video_title=metadata["title"],
                                video_filename=video_path.name,
                                total_bytes=file_size,
                                uploaded_bytes=uploaded_bytes,
                                speed_str=speed_str,
                                elapsed_str=elapsed_str,
                                eta_str=eta_str,
                                previsao_fim_str=previsao_str,
                                status_msg="Transmitindo dados (Resumable Upload)..."
                            ))
                            retry_count = 0

                    except HttpError as e:
                        if e.resp.status in [500, 502, 503, 504] and retry_count < 5:
                            retry_count += 1
                            time.sleep(min(2 ** retry_count, 30))
                        else:
                            console.print(f"\n[red]Erro HTTP da YouTube API ({e.resp.status}): {e}[/red]")
                            break
                    except Exception as e:
                        if retry_count < 5:
                            retry_count += 1
                            time.sleep(min(2 ** retry_count, 30))
                        else:
                            console.print(f"\n[red]Erro na transmissão de vídeo: {e}[/red]")
                            break

            if response and "id" in response:
                video_id = response["id"]
                video_url = f"https://youtu.be/{video_id}"

                # Adicionar à playlist configurada
                playlist_target = yt_config.get("playlist", "Timelapses")
                add_video_to_playlist(youtube, video_id, playlist_target, privacy=metadata["privacy_status"])

                # Atualizar banco do projeto e banco central
                project.update_timelapse_youtube(str(video_path.resolve()), video_id, video_url)

                # Notificações
                topic = yt_config.get("ntfy_topic", "timelapse-studio-2026")
                enable_toast = yt_config.get("windows_toast", True)

                if enable_toast:
                    send_windows_toast(
                        "IRIS - Vídeo no YouTube!",
                        f"Vídeo: {video_path.name}\nLink: {video_url}"
                    )

                if topic:
                    send_ntfy_notification(
                        topic=topic,
                        title="📺 IRIS: Vídeo Publicado no YouTube!",
                        message=f"📁 Projeto: {project.name}\n🎞️ Vídeo: {video_path.name}\n🔗 Link: {video_url}",
                        tags=["youtube", "tv", "white_check_mark"],
                        priority="high",
                        actions=[f"view, Assistir no YouTube, {video_url}"]
                    )

                console.print(f"\n[bold green]✔ Vídeo publicado com sucesso![/bold green]")
                console.print(f"🔗 [bold cyan]Link Oficial: {video_url}[/bold cyan]")
                success_count += 1
            else:
                console.print(f"[bold red]✖ Falha no envio do vídeo '{video_path.name}'.[/bold red]")
                error_count += 1

        if error_count > 0:
            console.print(f"[yellow]Etapa 6 finalizada com {error_count} erro(s).[/yellow]")
            return False

        console.print(f"[bold green]Etapa 6 concluída com sucesso! ({success_count} vídeo(s) publicado(s)).[/bold green]")
        return True

def get_stage(stage_id: str, name: str) -> PipelineStage:
    return YouTubeUploadStage(stage_id, name)
