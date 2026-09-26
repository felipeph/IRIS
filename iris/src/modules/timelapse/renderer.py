import os
import sys
import time
import shutil
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional

from rich.console import Console
from rich.live import Live

from src.core.ui import PipelineUI
from src.modules.timelapse.encoder import detect_ffmpeg_encoder

console = Console()

def build_video_filter_chain(
    crop_mode: str = "bottom",
    target_w: int = 3840,
    target_h: int = 2160,
    deband_config: Optional[Dict[str, Any]] = None
) -> str:
    """
    Constrói a cadeia de filtros de vídeo (-vf) para o FFmpeg.
    Aplica crop proporcional para 16:9, scale Lanczos e filtros opcionais
    de deband e micro-grão temporal para preservação de gradientes contra a compressão do YouTube.
    """
    res_scale = f"{target_w}:{target_h}"
    if crop_mode == "center":
        crop_filter = f"crop=w='trunc(min(iw\\,ih*(16/9))/2)*2':h='trunc(min(ih\\,iw/(16/9))/2)*2':x='(iw-ow)/2':y='(ih-oh)/2',scale={res_scale}:flags=lanczos"
    elif crop_mode == "top":
        crop_filter = f"crop=w='trunc(min(iw\\,ih*(16/9))/2)*2':h='trunc(min(ih\\,iw/(16/9))/2)*2':x='(iw-ow)/2':y='0',scale={res_scale}:flags=lanczos"
    else:  # bottom
        crop_filter = f"crop=w='trunc(min(iw\\,ih*(16/9))/2)*2':h='trunc(min(ih\\,iw/(16/9))/2)*2':x='(iw-ow)/2':y='(ih-oh)',scale={res_scale}:flags=lanczos"

    filters = [crop_filter]

    if deband_config and deband_config.get("enabled", False):
        filters.append("deband=1thr=0.04:2thr=0.04:3thr=0.04:range=16:blur=true:coupling=true")
        if deband_config.get("add_grain", False):
            filters.append("noise=alls=1:allf=t")

    return ",".join(filters)

def render_timelapse_video(
    sequence_dir: Path,
    output_video_path: Path,
    photo_count: int,
    config: Dict[str, Any]
) -> Tuple[bool, str, str]:
    """
    Renderiza vídeo timelapse 4K UHD via FFmpeg demuxer image2 com corte e escala Lanczos.
    Exibe barra de progresso Rich e captura métricas de hardware em tempo real.
    Retorna (sucesso, encoder_utilizado, mensagem_erro).
    """
    fps = config.get("fps", 60)
    frames_per_image = max(1, config.get("frames_per_image", 1))
    crf = config.get("crf", 15)
    preset = config.get("preset", "ultrafast")
    crop_mode = config.get("crop_mode", "bottom")
    target_w = config.get("target_width", 3840)
    target_h = config.get("target_height", 2160)

    deband_cfg = config.get("deband")
    if deband_cfg is None:
        deband_cfg = {"enabled": True, "add_grain": True}

    # 1. Detecta acelerador
    encoder_name, encoder_args = detect_ffmpeg_encoder(preset=preset, crf=crf)

    # 2. Configura filtros de Crop, Lanczos Scale, Deband e Grain
    video_filter = build_video_filter_chain(
        crop_mode=crop_mode,
        target_w=target_w,
        target_h=target_h,
        deband_config=deband_cfg
    )

    input_pattern = (sequence_dir / "%06d.jpg").as_posix()
    input_fps = f"{fps}/{frames_per_image}"
    input_args = ["-f", "image2", "-framerate", str(input_fps), "-start_number", "1", "-i", input_pattern]

    youtube_flags = [
        "-colorspace", "bt709",
        "-color_trc", "bt709",
        "-color_primaries", "bt709",
        "-movflags", "+faststart",
        "-an"
    ]

    output_video_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y", "-hide_banner",
        *input_args,
        "-vf", video_filter,
        "-r", str(fps),
        "-pix_fmt", "yuv420p",
        "-progress", "pipe:1",
        "-nostats",
        *encoder_args,
        *youtube_flags,
        str(output_video_path.resolve())
    ]

    total_frames = max(1, photo_count * frames_per_image)
    start_time = time.time()
    start_str = datetime.now().strftime("%H:%M:%S")

    deband_label = ""
    if deband_cfg.get("enabled", False):
        deband_label = " [Deband+Grain]" if deband_cfg.get("add_grain", False) else " [Deband]"

    resolution_label = f"{target_w}x{target_h} ({'4K UHD' if target_h >= 2160 else 'HD'}){deband_label}"
    output_name = output_video_path.name

    stderr_lines = []
    def capture_stderr(proc):
        try:
            for line in iter(proc.stderr.readline, ''):
                if line:
                    stderr_lines.append(line)
        except Exception:
            pass

    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1
        )

        t_err = threading.Thread(target=capture_stderr, args=(process,), daemon=True)
        t_err.start()

        current_frame = 0
        current_fps = 0.0
        current_speed = "0.0x"

        with Live(PipelineUI.generate_video_renderable(
            stage_title="ETAPA 5: RENDERIZAÇÃO DE TIMELAPSE 4K (GPU/CPU)",
            start_str=start_str,
            total_photos=photo_count,
            total_frames=total_frames,
            current_frame=0,
            fps_target=fps,
            current_fps=0.0,
            current_speed="0.0x",
            encoder_name=encoder_name,
            resolution=resolution_label,
            output_name=output_name,
            status_msg="Iniciando encoder FFmpeg...",
            elapsed_str="0:00:00",
            eta_str="--:--:--",
            previsao_fim_str="--:--:--"
        ), console=console, refresh_per_second=4) as live:

            for line in process.stdout:
                line = line.strip()
                if not line:
                    continue
                if line.startswith("frame="):
                    try:
                        current_frame = int(line.split("=", 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("fps="):
                    try:
                        current_fps = float(line.split("=", 1)[1].strip())
                    except (ValueError, IndexError):
                        pass
                elif line.startswith("speed="):
                    try:
                        current_speed = line.split("=", 1)[1].strip()
                    except IndexError:
                        pass
                elif line.startswith("progress="):
                    elapsed_sec = max(0.1, time.time() - start_time)
                    elapsed_str = str(timedelta(seconds=int(elapsed_sec)))

                    remaining_frames = max(0, total_frames - current_frame)
                    effective_fps = current_fps if current_fps > 0 else (current_frame / elapsed_sec)

                    if effective_fps > 0 and remaining_frames > 0:
                        eta_sec = remaining_frames / effective_fps
                        eta_str = str(timedelta(seconds=int(eta_sec)))
                        end_dt = datetime.now() + timedelta(seconds=int(eta_sec))
                        previsao_str = end_dt.strftime("%H:%M:%S")
                    else:
                        eta_str = "0:00:00" if remaining_frames == 0 else "--:--:--"
                        previsao_str = datetime.now().strftime("%H:%M:%S")

                    live.update(PipelineUI.generate_video_renderable(
                        stage_title="ETAPA 5: RENDERIZAÇÃO DE TIMELAPSE 4K (GPU/CPU)",
                        start_str=start_str,
                        total_photos=photo_count,
                        total_frames=total_frames,
                        current_frame=min(current_frame, total_frames),
                        fps_target=fps,
                        current_fps=current_fps,
                        current_speed=current_speed,
                        encoder_name=encoder_name,
                        resolution=resolution_label,
                        output_name=output_name,
                        status_msg="Codificando vídeo...",
                        elapsed_str=elapsed_str,
                        eta_str=eta_str,
                        previsao_fim_str=previsao_str
                    ))

            process.wait()
            t_err.join(timeout=2.0)

            if process.returncode == 0 and output_video_path.exists():
                live.update(PipelineUI.generate_video_renderable(
                    stage_title="ETAPA 5: RENDERIZAÇÃO DE TIMELAPSE 4K (GPU/CPU)",
                    start_str=start_str,
                    total_photos=photo_count,
                    total_frames=total_frames,
                    current_frame=total_frames,
                    fps_target=fps,
                    current_fps=current_fps,
                    current_speed=current_speed,
                    encoder_name=encoder_name,
                    resolution=resolution_label,
                    output_name=output_name,
                    status_msg="Renderização concluída com sucesso!",
                    elapsed_str=str(timedelta(seconds=int(time.time() - start_time))),
                    eta_str="0:00:00",
                    previsao_fim_str=datetime.now().strftime("%H:%M:%S")
                ))
                return True, encoder_name, ""
            else:
                err_detail = "".join(stderr_lines[-8:]) if stderr_lines else f"Código {process.returncode}"
                return False, encoder_name, err_detail

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠ Renderização interrompida pelo usuário.[/yellow]")
        if process:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        if output_video_path.exists():
            try:
                output_video_path.unlink()
            except Exception:
                pass
        return False, encoder_name, "Interrompido pelo usuário"

    except Exception as e:
        return False, encoder_name, str(e)
