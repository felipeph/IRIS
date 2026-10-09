import os
import sys
import time
import shutil
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, Optional, List

from rich.console import Console
from rich.live import Live

from src.core.ui import PipelineUI
from src.modules.timelapse.encoder import detect_ffmpeg_encoder

console = Console()

def build_video_filter_chain(
    crop_mode: str = "bottom",
    target_w: int = 3840,
    target_h: int = 2160,
    deband_config: Optional[Dict[str, Any]] = None,
    orig_w: int = 0,
    orig_h: int = 0,
    render_profile: str = "quality"
) -> str:
    """
    Constrói a cadeia de filtros de vídeo (-vf) para o FFmpeg.
    Aplica corte proporcional ou direto 1:1, scale e filtros opcionais de deband/grain.
    Mantido para retrocompatibilidade.
    """
    is_direct = bool(orig_w >= target_w and orig_h >= target_h)
    crop_m = crop_mode.lower().strip()
    if crop_m not in ("top", "center", "bottom"):
        crop_m = "bottom"

    filters = []
    if is_direct:
        if crop_m == "top":
            cy_val = "0"
        elif crop_m == "center":
            cy_val = f"(ih-{target_h})/2"
        else:
            cy_val = f"ih-{target_h}"
        filters.append(f"crop={target_w}:{target_h}:(iw-{target_w})/2:{cy_val}")
    else:
        res_scale = f"{target_w}:{target_h}"
        scale_flag = "bicubic" if render_profile == "balanced" else "lanczos"
        if crop_m == "center":
            crop_filter = f"crop=w='trunc(min(iw\\,ih*(16/9))/2)*2':h='trunc(min(ih\\,iw/(16/9))/2)*2':x='(iw-ow)/2':y='(ih-oh)/2',scale={res_scale}:flags={scale_flag}"
        elif crop_m == "top":
            crop_filter = f"crop=w='trunc(min(iw\\,ih*(16/9))/2)*2':h='trunc(min(ih\\,iw/(16/9))/2)*2':x='(iw-ow)/2':y='0',scale={res_scale}:flags={scale_flag}"
        else:  # bottom
            crop_filter = f"crop=w='trunc(min(iw\\,ih*(16/9))/2)*2':h='trunc(min(ih\\,iw/(16/9))/2)*2':x='(iw-ow)/2':y='(ih-oh)',scale={res_scale}:flags={scale_flag}"
        filters.append(crop_filter)

    if deband_config and deband_config.get("enabled", False) and render_profile == "quality":
        filters.append("deband=1thr=0.04:2thr=0.04:3thr=0.04:range=16:blur=true:coupling=true")
        if deband_config.get("add_grain", False):
            filters.append("noise=alls=1:allf=t")

    return ",".join(filters)

def build_timelapse_render_cmd(
    input_pattern: str,
    output_video_path: Path,
    fps: int,
    frames_per_image: int,
    orig_w: int = 0,
    orig_h: int = 0,
    target_w: int = 3840,
    target_h: int = 2160,
    crop_mode: str = "bottom",
    render_profile: str = "fast",
    encoder_name: str = "h264_qsv (Intel Quick Sync)",
    encoder_args: Optional[List[str]] = None,
    deband_cfg: Optional[Dict[str, Any]] = None,
    force_software: bool = False
) -> Tuple[List[str], bool, bool]:
    """
    Constrói a linha de comando do FFmpeg para renderização de timelapse de acordo com o perfil.
    Aplica corte direto 1:1 sem redimensionamento quando orig_w >= target_w e orig_h >= target_h.
    Retorna (cmd, is_direct_crop, deband_used).
    """
    profile = render_profile.lower().strip()
    if profile not in ("fast", "balanced", "quality"):
        profile = "fast"

    if encoder_args is None:
        encoder_args = ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "15"]

    input_fps = f"{fps}/{frames_per_image}"
    youtube_flags = [
        "-colorspace", "bt709",
        "-color_trc", "bt709",
        "-color_primaries", "bt709",
        "-movflags", "+faststart",
        "-an"
    ]

    is_direct_crop = bool(orig_w >= target_w and orig_h >= target_h)
    crop_m = crop_mode.lower().strip()
    if crop_m not in ("top", "center", "bottom"):
        crop_m = "bottom"

    use_qsv_hw = (profile == "fast" and not force_software and "qsv" in encoder_name.lower())

    if use_qsv_hw:
        # Pipeline 100% em hardware Intel QSV (mjpeg_qsv decode + vpp_qsv crop/scale + h264_qsv encode)
        input_args = [
            "-hwaccel", "qsv",
            "-hwaccel_output_format", "qsv",
            "-c:v", "mjpeg_qsv",
            "-f", "image2",
            "-framerate", str(input_fps),
            "-start_number", "1",
            "-i", input_pattern
        ]

        if is_direct_crop:
            # Corte Direto 1:1 Sem Redimensionamento (Zero-Scaling no VPP da GPU)
            if crop_m == "top":
                cy_expr = "0"
            elif crop_m == "center":
                cy_expr = f"(ih-{target_h})/2"
            else:  # bottom
                cy_expr = f"ih-{target_h}"
            vpp_filter = f"vpp_qsv=cw={target_w}:ch={target_h}:cx=(iw-{target_w})/2:cy={cy_expr}:w={target_w}:h={target_h}"
        else:
            # Imagem menor que 4K: Corte proporcional 16:9 + upscale HQ em hardware
            if crop_m == "top":
                vpp_cy = "0"
            elif crop_m == "center":
                vpp_cy = "(ih-ch)/2"
            else:  # bottom
                vpp_cy = "ih-ch"
            vpp_filter = f"vpp_qsv=cw=trunc(min(iw\\,ih*(16/9))/2)*2:ch=trunc(min(ih\\,iw/(16/9))/2)*2:cx=(iw-cw)/2:cy={vpp_cy}:w={target_w}:h={target_h}:scale_mode=hq"

        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            *input_args,
            "-vf", vpp_filter,
            "-r", str(fps),
            "-progress", "pipe:1",
            "-nostats",
            *encoder_args,
            *youtube_flags,
            str(output_video_path.resolve())
        ]
        return cmd, is_direct_crop, False

    # Pipeline Software / CPU (balanced ou quality)
    input_args = [
        "-f", "image2",
        "-framerate", str(input_fps),
        "-start_number", "1",
        "-i", input_pattern
    ]

    filters = []
    if is_direct_crop:
        # Corte direto 1:1 sem redimensionamento
        if crop_m == "top":
            cy_val = "0"
        elif crop_m == "center":
            cy_val = f"(ih-{target_h})/2"
        else:  # bottom
            cy_val = f"ih-{target_h}"
        filters.append(f"crop={target_w}:{target_h}:(iw-{target_w})/2:{cy_val}")
    else:
        # Corte proporcional 16:9 + scale
        scale_flag = "bicubic" if profile == "balanced" else "lanczos"
        if crop_m == "top":
            sw_cy = "0"
        elif crop_m == "center":
            sw_cy = "(ih-oh)/2"
        else:  # bottom
            sw_cy = "ih-oh"
        crop_scale = f"crop=w='trunc(min(iw\\,ih*(16/9))/2)*2':h='trunc(min(ih\\,iw/(16/9))/2)*2':x='(iw-ow)/2':y='{sw_cy}',scale={target_w}:{target_h}:flags={scale_flag}"
        filters.append(crop_scale)

    deband_used = False
    if profile == "quality" and deband_cfg and deband_cfg.get("enabled", False):
        filters.append("deband=1thr=0.04:2thr=0.04:3thr=0.04:range=16:blur=true:coupling=true")
        deband_used = True
        if deband_cfg.get("add_grain", False):
            filters.append("noise=alls=1:allf=t")

    video_filter = ",".join(filters)

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
    return cmd, is_direct_crop, deband_used

def render_timelapse_video(
    sequence_dir: Path,
    output_video_path: Path,
    photo_count: int,
    config: Dict[str, Any],
    orig_w: int = 0,
    orig_h: int = 0,
    force_software: bool = False
) -> Tuple[bool, str, str, Dict[str, Any]]:
    """
    Renderiza vídeo timelapse 4K UHD via FFmpeg demuxer image2 de acordo com o perfil configurado.
    Suporta aceleração por hardware Intel QSV (perfil fast com corte direto 1:1 sem redimensionamento)
    e modos balanced e quality com fallback automático transparente.
    Exibe barra de progresso Rich e captura métricas de hardware em tempo real.
    Retorna (sucesso, encoder_utilizado, mensagem_erro, render_stats).
    """
    fps = config.get("fps", 60)
    frames_per_image = max(1, config.get("frames_per_image", 1))
    crf = config.get("crf", 15)
    preset = config.get("preset", "ultrafast")
    crop_mode = config.get("crop_mode", "bottom")
    target_w = config.get("target_width", 3840)
    target_h = config.get("target_height", 2160)
    render_profile = config.get("render_profile", "fast").lower().strip()
    if render_profile not in ("fast", "balanced", "quality"):
        render_profile = "fast"

    deband_cfg = config.get("deband")
    if deband_cfg is None:
        deband_cfg = {"enabled": True, "add_grain": True}

    # 1. Detecta acelerador
    encoder_name, encoder_args = detect_ffmpeg_encoder(preset=preset, crf=crf, force_cpu=force_software)

    input_pattern = (sequence_dir / "%06d.jpg").as_posix()

    output_video_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Constrói comando do FFmpeg via perfil
    cmd, is_direct_crop, deband_used = build_timelapse_render_cmd(
        input_pattern=input_pattern,
        output_video_path=output_video_path,
        fps=fps,
        frames_per_image=frames_per_image,
        orig_w=orig_w,
        orig_h=orig_h,
        target_w=target_w,
        target_h=target_h,
        crop_mode=crop_mode,
        render_profile=render_profile,
        encoder_name=encoder_name,
        encoder_args=encoder_args,
        deband_cfg=deband_cfg,
        force_software=force_software
    )

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
                elapsed_sec = round(time.time() - start_time, 2)
                render_stats = {
                    "render_time_seconds": elapsed_sec,
                    "total_frames": total_frames,
                    "avg_fps": round(total_frames / max(0.001, elapsed_sec), 1),
                    "encoder": encoder_name,
                    "render_profile": render_profile,
                    "is_direct_crop": is_direct_crop,
                    "target_width": target_w,
                    "target_height": target_h,
                    "orig_width": orig_w,
                    "orig_height": orig_h,
                    "fps": fps,
                    "frames_per_image": frames_per_image,
                    "crop_mode": crop_mode,
                    "crf": crf,
                    "preset": preset,
                    "deband_enabled": deband_used,
                    "deband_grain": bool(deband_cfg.get("add_grain", False) if deband_used else False),
                }
                return True, encoder_name, "", render_stats
            else:
                err_detail = "".join(stderr_lines[-8:]) if stderr_lines else f"Código {process.returncode}"
                # Fallback automático: se falhou no modo fast por hardware, tenta via software
                if render_profile == "fast" and not force_software:
                    console.print("\n[yellow]⚠ Falha no decodificador de hardware QSV (mjpeg_qsv). Acionando fallback automático para decodificação em software...[/yellow]")
                    return render_timelapse_video(
                        sequence_dir=sequence_dir,
                        output_video_path=output_video_path,
                        photo_count=photo_count,
                        config=config,
                        orig_w=orig_w,
                        orig_h=orig_h,
                        force_software=True
                    )
                return False, encoder_name, err_detail, {}

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
        return False, encoder_name, "Interrompido pelo usuário", {}

    except Exception as e:
        return False, encoder_name, str(e), {}
