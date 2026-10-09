import os
import sys
import time
import json
import shutil
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Dict, Any, List, Optional

from rich.console import Console
from rich.live import Live

from src.core.ui import PipelineUI
from src.modules.timelapse.encoder import detect_ffmpeg_encoder

console = Console()

def get_video_stream_info(video_path: Path) -> Dict[str, Any]:
    """
    Obtém informações técnicas do arquivo de vídeo via ffprobe:
    duração, largura, altura, fps e presença de áudio.
    """
    info = {
        "duration": 0.0,
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "has_audio": False
    }
    if not video_path.exists():
        return info

    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height,r_frame_rate,duration:format=duration",
            "-of", "json",
            str(video_path.resolve())
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=8)
        if res.returncode == 0 and res.stdout:
            data = json.loads(res.stdout)
            # Duração do container/formato
            fmt = data.get("format", {})
            if "duration" in fmt:
                try:
                    info["duration"] = float(fmt["duration"])
                except (ValueError, TypeError):
                    pass

            for s in data.get("streams", []):
                ctype = s.get("codec_type")
                if ctype == "video":
                    if "width" in s and "height" in s:
                        info["width"] = int(s["width"])
                        info["height"] = int(s["height"])
                    if "r_frame_rate" in s and "/" in s["r_frame_rate"]:
                        try:
                            num, den = s["r_frame_rate"].split("/")
                            if float(den) > 0:
                                info["fps"] = round(float(num) / float(den), 2)
                        except Exception:
                            pass
                    if info["duration"] <= 0 and "duration" in s:
                        try:
                            info["duration"] = float(s["duration"])
                        except Exception:
                            pass
                elif ctype == "audio":
                    info["has_audio"] = True
    except Exception:
        pass

    return info

def build_atempo_chain(speed: float) -> str:
    """
    Constrói a cadeia de filtros atempo para o FFmpeg.
    O filtro atempo aceita valores entre 0.5 e 2.0.
    Para velocidades fora deste intervalo, encadeia múltiplos filtros.
    """
    if abs(speed - 1.0) < 0.001:
        return ""

    filters = []
    rem = speed
    while rem > 2.0:
        filters.append("atempo=2.0000")
        rem /= 2.0
    while rem < 0.5:
        filters.append("atempo=0.5000")
        rem /= 0.5
    if abs(rem - 1.0) > 0.001:
        filters.append(f"atempo={rem:.4f}")

    return ",".join(filters)

def build_render_cmd(
    clip_paths: List[Path],
    clip_infos: List[Dict[str, Any]],
    output_video_path: Path,
    trim_starts: List[float],
    trimmed_durs: List[float],
    speed: float,
    target_fps: int,
    target_w: int,
    target_h: int,
    render_profile: str,
    encoder_name: str,
    encoder_args: List[str],
    has_any_audio: bool,
    force_software: bool = False
) -> Tuple[List[str], bool, bool]:
    """
    Constrói a linha de comando do FFmpeg com base no perfil de renderização.
    Retorna (cmd, unsharp_used, deband_used).
    """
    profile = render_profile.lower().strip()
    if profile not in ["fast", "balanced", "quality"]:
        profile = "fast"

    use_qsv_hw = (profile == "fast" and "qsv" in encoder_name.lower() and not force_software)
    atempo_str = build_atempo_chain(speed) if has_any_audio else ""

    # 1. PERFIL FAST COM ACELERAÇÃO DE HARDWARE INTEL QSV
    if use_qsv_hw:
        unsharp_used = False
        deband_used = False
        hw_vpp_filter = f"vpp_qsv=w={target_w}:h={target_h}:scale_mode=hq:framerate={target_fps}"

        if len(clip_paths) == 1:
            p = clip_paths[0]
            s_trim = trim_starts[0]
            d_trim = trimmed_durs[0]

            input_args = ["-hwaccel", "qsv", "-hwaccel_output_format", "qsv"]
            if s_trim > 0:
                input_args.extend(["-ss", f"{s_trim:.3f}"])
            if d_trim > 0 and d_trim < clip_infos[0]["duration"]:
                input_args.extend(["-t", f"{d_trim:.3f}"])
            input_args.extend(["-i", str(p.resolve())])

            filter_args = ["-vf", f"setpts=(1/{speed:.6f})*PTS,{hw_vpp_filter}"]
            if has_any_audio:
                if atempo_str:
                    filter_args.extend(["-af", atempo_str])
                audio_args = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
            else:
                audio_args = ["-an"]

            cmd = [
                "ffmpeg", "-y", "-hide_banner",
                *input_args,
                *filter_args,
                *audio_args,
                "-colorspace", "bt709",
                "-color_trc", "bt709",
                "-color_primaries", "bt709",
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                "-nostats",
                *encoder_args,
                str(output_video_path.resolve())
            ]
            return cmd, unsharp_used, deband_used

        else:
            # Múltiplos clipes em QSV Hardware
            input_args = []
            filter_parts = []
            v_concat_inputs = []
            a_concat_inputs = []

            for idx, (p, inf, s_trim, d_trim) in enumerate(zip(clip_paths, clip_infos, trim_starts, trimmed_durs)):
                input_args.extend(["-hwaccel", "qsv", "-hwaccel_output_format", "qsv", "-i", str(p.resolve())])
                end_trim = s_trim + d_trim if d_trim > 0 else inf["duration"]
                v_trim_str = f"trim=start={s_trim:.3f}:end={end_trim:.3f},setpts=PTS-STARTPTS" if s_trim > 0 else "setpts=PTS-STARTPTS"
                filter_parts.append(f"[{idx}:v]{v_trim_str}[v{idx}]")
                v_concat_inputs.append(f"[v{idx}]")

                if has_any_audio and inf["has_audio"]:
                    a_trim_str = f"atrim=start={s_trim:.3f}:end={end_trim:.3f},asetpts=PTS-STARTPTS" if s_trim > 0 else "asetpts=PTS-STARTPTS"
                    filter_parts.append(f"[{idx}:a]{a_trim_str}[a{idx}]")
                    a_concat_inputs.append(f"[a{idx}]")

            n_clips = len(clip_paths)
            filter_parts.append("".join(v_concat_inputs) + f"concat=n={n_clips}:v=1:a=0[vcat]")
            filter_parts.append(f"[vcat]setpts=(1/{speed:.6f})*PTS,{hw_vpp_filter}[vout]")

            if has_any_audio and len(a_concat_inputs) == n_clips:
                filter_parts.append("".join(a_concat_inputs) + f"concat=n={n_clips}:v=0:a=1[acat]")
                if atempo_str:
                    filter_parts.append(f"[acat]{atempo_str}[aout]")
                else:
                    filter_parts.append("[acat]anull[aout]")
                map_args = ["-map", "[vout]", "-map", "[aout]"]
                audio_args = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
            else:
                map_args = ["-map", "[vout]"]
                audio_args = ["-an"]

            full_filter_complex = ";".join(filter_parts)
            cmd = [
                "ffmpeg", "-y", "-hide_banner",
                *input_args,
                "-filter_complex", full_filter_complex,
                *map_args,
                *audio_args,
                "-colorspace", "bt709",
                "-color_trc", "bt709",
                "-color_primaries", "bt709",
                "-movflags", "+faststart",
                "-progress", "pipe:1",
                "-nostats",
                *encoder_args,
                str(output_video_path.resolve())
            ]
            return cmd, unsharp_used, deband_used

    # 2. PERFIS DE SOFTWARE OU FALLBACK (fast sem QSV, balanced, quality)
    v_chain = []
    if profile == "fast":
        unsharp_used = False
        deband_used = False
        v_chain.append(f"setpts=(1/{speed:.6f})*PTS")
        v_chain.append(f"fps=fps={target_fps}:round=near")
        v_chain.append(f"scale={target_w}:{target_h}:flags=bicubic")
    elif profile == "balanced":
        unsharp_used = True
        deband_used = False
        # Unsharp leve 3x3 na resolução nativa 1080p antes do upscale
        v_chain.append("unsharp=luma_msize_x=3:luma_msize_y=3:luma_amount=0.5:chroma_msize_x=3:chroma_msize_y=3:chroma_amount=0.0")
        v_chain.append(f"setpts=(1/{speed:.6f})*PTS")
        v_chain.append(f"fps=fps={target_fps}:round=near")
        v_chain.append(f"scale={target_w}:{target_h}:flags=bicubic+accurate_rnd")
    else:  # quality
        unsharp_used = True
        deband_used = True
        # Unsharp 5x5 + Deband 16-bit na resolução nativa 1080p antes do upscale Lanczos (economia de 75% CPU)
        v_chain.append("unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount=0.8:chroma_msize_x=5:chroma_msize_y=5:chroma_amount=0.0")
        v_chain.append("deband=1thr=0.04:2thr=0.04:3thr=0.04:range=16:blur=true:coupling=true")
        v_chain.append(f"setpts=(1/{speed:.6f})*PTS")
        v_chain.append(f"fps=fps={target_fps}:round=near")
        v_chain.append(f"scale={target_w}:{target_h}:flags=lanczos+accurate_rnd+full_chroma_int")

    v_filter_common = ",".join(v_chain)

    if len(clip_paths) == 1:
        p = clip_paths[0]
        s_trim = trim_starts[0]
        d_trim = trimmed_durs[0]

        input_args = []
        if s_trim > 0:
            input_args.extend(["-ss", f"{s_trim:.3f}"])
        if d_trim > 0 and d_trim < clip_infos[0]["duration"]:
            input_args.extend(["-t", f"{d_trim:.3f}"])
        input_args.extend(["-i", str(p.resolve())])

        filter_args = ["-vf", v_filter_common]
        if has_any_audio:
            if atempo_str:
                filter_args.extend(["-af", atempo_str])
            audio_args = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
        else:
            audio_args = ["-an"]

        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            *input_args,
            *filter_args,
            *audio_args,
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_trc", "bt709",
            "-color_primaries", "bt709",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            "-nostats",
            *encoder_args,
            str(output_video_path.resolve())
        ]
        return cmd, unsharp_used, deband_used

    else:
        input_args = []
        filter_parts = []
        v_concat_inputs = []
        a_concat_inputs = []

        for idx, (p, inf, s_trim, d_trim) in enumerate(zip(clip_paths, clip_infos, trim_starts, trimmed_durs)):
            input_args.extend(["-i", str(p.resolve())])
            end_trim = s_trim + d_trim if d_trim > 0 else inf["duration"]
            v_trim_str = f"trim=start={s_trim:.3f}:end={end_trim:.3f},setpts=PTS-STARTPTS" if s_trim > 0 else "setpts=PTS-STARTPTS"
            filter_parts.append(f"[{idx}:v]{v_trim_str}[v{idx}]")
            v_concat_inputs.append(f"[v{idx}]")

            if has_any_audio and inf["has_audio"]:
                a_trim_str = f"atrim=start={s_trim:.3f}:end={end_trim:.3f},asetpts=PTS-STARTPTS" if s_trim > 0 else "asetpts=PTS-STARTPTS"
                filter_parts.append(f"[{idx}:a]{a_trim_str}[a{idx}]")
                a_concat_inputs.append(f"[a{idx}]")

        n_clips = len(clip_paths)
        if has_any_audio and len(a_concat_inputs) == n_clips:
            concat_str = "".join(v_concat_inputs) + "".join(a_concat_inputs) + f"concat=n={n_clips}:v=1:a=1[vcat][acat]"
            filter_parts.append(concat_str)
            filter_parts.append(f"[vcat]{v_filter_common}[vout]")
            if atempo_str:
                filter_parts.append(f"[acat]{atempo_str}[aout]")
            else:
                filter_parts.append("[acat]anull[aout]")
            map_args = ["-map", "[vout]", "-map", "[aout]"]
            audio_args = ["-c:a", "aac", "-b:a", "320k", "-ar", "48000"]
        else:
            concat_str = "".join(v_concat_inputs) + f"concat=n={n_clips}:v=1:a=0[vcat]"
            filter_parts.append(concat_str)
            filter_parts.append(f"[vcat]{v_filter_common}[vout]")
            map_args = ["-map", "[vout]"]
            audio_args = ["-an"]

        full_filter_complex = ";".join(filter_parts)
        cmd = [
            "ffmpeg", "-y", "-hide_banner",
            *input_args,
            "-filter_complex", full_filter_complex,
            *map_args,
            *audio_args,
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_trc", "bt709",
            "-color_primaries", "bt709",
            "-movflags", "+faststart",
            "-progress", "pipe:1",
            "-nostats",
            *encoder_args,
            str(output_video_path.resolve())
        ]
        return cmd, unsharp_used, deband_used

def render_edited_video(
    clip_paths: List[Path],
    output_video_path: Path,
    config: Dict[str, Any]
) -> Tuple[bool, str, str, Dict[str, Any]]:
    """
    Renderiza vídeo 4K UHD com controle de velocidade, FPS, trimming e perfis de renderização.
    Perfis suportados:
      - 'fast': Aceleração máxima por hardware Intel QSV (VPP upscale 4K, zero filtros software)
      - 'balanced': Equilíbrio com unsharp leve 3x3 em 1080p pré-upscale bicúbico
      - 'quality': Máxima qualidade com unsharp 5x5 + deband 16-bit em 1080p pré-upscale Lanczos 4K
    Retorna (sucesso, encoder_utilizado, mensagem_erro, render_stats).
    """
    if not clip_paths:
        return False, "", "Nenhum clipe informado para renderização.", {}

    speed = max(0.1, float(config.get("speed", 1.0)))
    target_fps = int(config.get("target_fps", 60))
    target_w = int(config.get("target_width", 3840))
    target_h = int(config.get("target_height", 2160))
    crf = int(config.get("crf", 16))
    preset = config.get("preset", "slow")
    trim_enabled = bool(config.get("trim_enabled", True))
    trim_sec = float(config.get("trim_seconds", 2.0))
    strip_audio = bool(config.get("strip_audio", False))
    render_profile = str(config.get("render_profile", "fast")).lower().strip()
    if render_profile not in ["fast", "balanced", "quality"]:
        render_profile = "fast"

    # Detecta encoder com aceleração por GPU ou CPU
    encoder_name, encoder_args = detect_ffmpeg_encoder(preset=preset, crf=crf)

    # Inspeciona clipes
    clip_infos = [get_video_stream_info(p) for p in clip_paths]
    has_any_audio = any(inf["has_audio"] for inf in clip_infos) and not strip_audio

    # Calcula duração total esperada
    total_orig_dur = 0.0
    trimmed_durs = []
    trim_starts = []
    for inf in clip_infos:
        d = inf["duration"]
        total_orig_dur += d
        if trim_enabled and trim_sec > 0 and d > (2 * trim_sec + 1.0):
            trim_starts.append(trim_sec)
            trimmed_durs.append(d - (2 * trim_sec))
        else:
            trim_starts.append(0.0)
            trimmed_durs.append(d)

    total_trimmed_dur = sum(trimmed_durs) if trimmed_durs else total_orig_dur
    expected_final_dur = total_trimmed_dur / speed if speed > 0 else total_trimmed_dur
    total_expected_frames = max(1, int(round(expected_final_dur * target_fps)))

    output_video_path.parent.mkdir(parents=True, exist_ok=True)

    cmd, unsharp_active, deband_active = build_render_cmd(
        clip_paths=clip_paths,
        clip_infos=clip_infos,
        output_video_path=output_video_path,
        trim_starts=trim_starts,
        trimmed_durs=trimmed_durs,
        speed=speed,
        target_fps=target_fps,
        target_w=target_w,
        target_h=target_h,
        render_profile=render_profile,
        encoder_name=encoder_name,
        encoder_args=encoder_args,
        has_any_audio=has_any_audio,
        force_software=False
    )

    # Execução e monitoramento com Rich UI
    start_time = time.time()
    start_str = datetime.now().strftime("%H:%M:%S")
    resolution_label = f"{target_w}x{target_h} (4K UHD) [Speed {speed}x | {render_profile.upper()}]"
    output_name = output_video_path.name

    stderr_lines = []
    def capture_stderr(proc):
        try:
            for l in iter(proc.stderr.readline, ''):
                if l:
                    stderr_lines.append(l)
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
        current_speed_str = "0.0x"

        with Live(PipelineUI.generate_video_renderable(
            stage_title="ETAPA 6: EDIÇÃO E UPSCALE DE VÍDEO 4K (GPU/CPU)",
            start_str=start_str,
            total_photos=len(clip_paths),
            total_frames=total_expected_frames,
            current_frame=0,
            fps_target=target_fps,
            current_fps=0.0,
            current_speed="0.0x",
            encoder_name=encoder_name,
            resolution=resolution_label,
            output_name=output_name,
            status_msg="Iniciando transcodificação FFmpeg...",
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
                    except Exception:
                        pass
                elif line.startswith("fps="):
                    try:
                        current_fps = float(line.split("=", 1)[1].strip())
                    except Exception:
                        pass
                elif line.startswith("speed="):
                    try:
                        current_speed_str = line.split("=", 1)[1].strip()
                    except Exception:
                        pass
                elif line.startswith("progress="):
                    elapsed_sec = max(0.1, time.time() - start_time)
                    elapsed_str = str(timedelta(seconds=int(elapsed_sec)))

                    remaining_frames = max(0, total_expected_frames - current_frame)
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
                        stage_title="ETAPA 6: EDIÇÃO E UPSCALE DE VÍDEO 4K (GPU/CPU)",
                        start_str=start_str,
                        total_photos=len(clip_paths),
                        total_frames=total_expected_frames,
                        current_frame=min(current_frame, total_expected_frames),
                        fps_target=target_fps,
                        current_fps=current_fps,
                        current_speed=current_speed_str,
                        encoder_name=encoder_name,
                        resolution=resolution_label,
                        output_name=output_name,
                        status_msg="Renderizando vídeo 4K...",
                        elapsed_str=elapsed_str,
                        eta_str=eta_str,
                        previsao_fim_str=previsao_str
                    ))

            process.wait()
            t_err.join(timeout=2.0)

        render_sec = time.time() - start_time
        if process.returncode == 0 and output_video_path.exists() and output_video_path.stat().st_size > 1000:
            final_size = output_video_path.stat().st_size
            avg_fps = (current_frame / render_sec) if render_sec > 0 else 0.0

            stats = {
                "render_profile": render_profile,
                "render_time_seconds": round(render_sec, 2),
                "avg_fps": round(avg_fps, 1),
                "encoder": encoder_name,
                "final_size_bytes": final_size,
                "final_duration_seconds": round(expected_final_dur, 2),
                "speed_factor": speed,
                "target_fps": target_fps,
                "deband_enabled": deband_active,
                "unsharp_enabled": unsharp_active,
                "audio_stripped": not has_any_audio,
                "trim_seconds": trim_sec if trim_enabled else 0.0
            }
            return True, encoder_name, "", stats
        else:
            err_msg = "".join(stderr_lines[-20:]) if stderr_lines else f"Código de saída {process.returncode}"
            return False, encoder_name, err_msg, {}

    except Exception as e:
        if process and process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass
        return False, encoder_name, str(e), {}
