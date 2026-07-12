"""Сборка финального mp4 через системный FFmpeg.

Два режима:
- render_video()          — одна статичная картинка (обложка) + аудио (fallback,
                             когда визуальный ряд не сгенерирован).
- render_video_segments() — несколько картинок AI-визуального ряда, каждая
                             с лёгким эффектом Ken Burns (плавный zoom), показывается
                             свою долю длительности, склеивается в один mp4 + аудио.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from app.core.config import settings


class RenderError(RuntimeError):
    pass


def _ffmpeg_available() -> bool:
    return shutil.which(settings.ffmpeg_path) is not None or Path(settings.ffmpeg_path).exists()


def render_video(
    *,
    image_path: Path,
    audio_path: Path,
    out_path: Path,
) -> str:
    """Сводит статичную картинку + аудио в mp4 (H.264 + AAC).

    Длительность ролика = длительности аудио (-shortest).
    """
    if not _ffmpeg_available():
        raise RenderError(
            f"FFmpeg не найден (FFMPEG_PATH={settings.ffmpeg_path}). "
            "Установите FFmpeg и/или укажите путь в .env."
        )
    if not audio_path.exists():
        raise RenderError(f"Нет аудиофайла для рендера: {audio_path}")
    if not image_path.exists():
        raise RenderError(f"Нет картинки для рендера: {image_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        settings.ffmpeg_path,
        "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1280:720",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    logger.info("FFmpeg рендер -> {out}", out=out_path)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RenderError(f"FFmpeg ошибка: {proc.stderr[-800:]}")
    return str(out_path)


def _run_ffmpeg(cmd: list[str], step: str) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # На Windows FFmpeg с зацикленным входом (-loop 1) и ограничением по
        # времени (-t) иногда завершается с кодом ≠ 0 (сигнал 15 = SIGTERM от
        # самого FFmpeg при достижении нужной длины). Если выходной файл создан
        # и не пустой — считаем рендер успешным.
        out_path = Path(cmd[-1]) if cmd else None
        if out_path and out_path.exists() and out_path.stat().st_size > 1024:
            logger.debug(
                "FFmpeg вернул код {rc} для шага '{step}', но файл создан "
                "({sz} байт) — считаем успехом (signal 15 на Windows).",
                rc=proc.returncode, step=step, sz=out_path.stat().st_size,
            )
            return
        raise RenderError(f"FFmpeg ошибка ({step}): {proc.stderr[-800:]}")


# Пресеты цветокора. "warm" — тёплый мягкий (по умолчанию): чуть приподнят
# красный канал, опущен синий + пастельная "приглушённость" контраста.
_GRADES: dict[str, str] = {
    "off": "",
    "warm": "colorbalance=rs=0.08:bs=-0.08,eq=contrast=0.96:saturation=1.05",
    "cold": "colorbalance=rs=-0.06:bs=0.08,eq=contrast=1.0:saturation=0.92",
    "vintage": "curves=preset=vintage,eq=saturation=0.85",
    "bw": "hue=s=0,eq=contrast=1.05",
}

# Фиксированный зум для режима панорамы — запас холста, по которому "едет" камера
_PAN_ZOOM = 1.12

# Лёгкая виньетка — мягкое затемнение углов, "уютный" кадр
_VIGNETTE = "vignette=angle=PI/5"

# Лёгкое плёночное зерно (временнОй шум) — маскирует бандинг на тёмных градиентах
_GRAIN = "noise=alls=6:allf=t"

# (ширина_выхода, высота_выхода, ширина_холста, высота_холста)
# Холст чуть больше выхода — zoompan «скользит» по нему при зуме/кене,
# и до зума 1.25 картинка только даунскейлится (без потери резкости).
_RESOLUTIONS: dict[str, tuple[int, int, int, int]] = {
    "720p":  (1280, 720,  1600,  900),
    "1080p": (1920, 1080, 2400, 1350),
    "1440p": (2560, 1440, 3200, 1800),
}

# Скорость зума для старых пресетов (% зума в секунду) — совместимость
# со старыми render_params, где скорость задавалась словом, а не числом.
_LEGACY_ZOOM_SPEEDS: dict[str, float] = {
    "subtle": 0.625,
    "normal": 2.0,
    "strong": 5.0,
}

# Максимальный зум — равен запасу холста (1.25), чтобы zoompan никогда
# не апскейлил картинку (иначе появляется мыло)
_ZOOM_CAP = 1.25

# Качество кодирования: CRF 18 (визуально без потерь) вместо дефолтного 23,
# который на ultrafast заметно «шакалил» картинку.
_X264_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]

# Длительность кроссфейда/затемнения между сегментами, сек
_XFADE_DUR = 1.0
_DIP_DUR = 0.6


def _zoom_smoothing_frames(zoom_speed: float) -> int:
    """Окно временного сглаживания (tmix) для zoompan-движения камеры.

    Проблема: ffmpeg zoompan округляет позицию кропа до целого пикселя. При
    медленном зуме сабпиксельный сдвиг за кадр накапливается несколько кадров
    подряд без видимых изменений, а затем "перепрыгивает" сразу на пиксель —
    вместо плавного движения получается заметная "лесенка" (именно то, что
    выглядит как "дёрганое" приближение). tmix усредняет N соседних кадров,
    превращая эти скачки в плавный микро-блендинг (незаметный на глаз, т.к.
    кадры и так почти идентичны на медленном зуме).

    На высоких скоростях реальное движение между кадрами уже достаточно
    большое, чтобы "лесенка" не была заметна — там усреднение только вносило
    бы лишний motion blur, поэтому окно сужается до нуля.
    """
    if zoom_speed <= 0.5:
        return 7
    if zoom_speed <= 1.0:
        return 5
    if zoom_speed <= 2.0:
        return 3
    return 0


def _ken_burns_segment(
    image_path: Path,
    duration_sec: float,
    out_path: Path,
    fps: int = 25,
    particles_dir: Path | None = None,
    resolution: str = "720p",
    zoom_enabled: bool = True,
    zoom_speed: float = 0.3,
    zoom_direction: str = "in",
    grade: str = "warm",
    vignette: bool = False,
    grain: bool = False,
    dip: bool = False,
    force_full_fps: bool = False,
    static_fps: int = 2,
) -> None:
    """Один сегмент: картинка с эффектом Ken Burns + опциональные эффекты.

    zoom_speed     — скорость зума в процентах кадра в секунду (0.3 = очень медленно).
    Зум всегда направлен в ЦЕНТР кадра (x/y-выражения zoompan), а не в угол.
    zoom_direction — "in"/"out" (зум) или "pan_left"/"pan_right" (панорама:
                     фиксированный зум {_PAN_ZOOM}, камера медленно едет вбок).
    grade          — пресет цветокора: "off"/"warm"/"cold"/"vintage"/"bw".
    particles_dir  — если задана, поверх кадра аддитивно (screen-блендом)
                     накладывается зацикленная анимация частиц (светлячки/искры/пыль).
    dip            — плавное затемнение в начале и конце сегмента (переход "dip to black").
    force_full_fps — кодировать статичные сегменты на полном fps (нужно для
                     кроссфейдов/зерна, где 2 fps дал бы рывки).
    """
    out_w, out_h, canvas_w, canvas_h = _RESOLUTIONS.get(resolution, _RESOLUTIONS["720p"])
    frames = max(1, round(duration_sec * fps))

    post: list[str] = []
    grade_vf = _GRADES.get(grade, _GRADES["warm"])
    if grade_vf:
        post.append(grade_vf)
    if vignette:
        post.append(_VIGNETTE)
    if grain:
        post.append(_GRAIN)
    if dip:
        d = min(_DIP_DUR, duration_sec / 3)
        post.append(f"fade=t=in:st=0:d={d:.3f}")
        post.append(f"fade=t=out:st={max(0.0, duration_sec - d):.3f}:d={d:.3f}")
    post_vf = ("," + ",".join(post)) if post else ""

    if not zoom_enabled:
        # Статичная картинка — минимальный fps, кодируем намного быстрее
        # (кроме случаев, когда нужен полный fps для плавных переходов/зерна)
        effective_fps = fps if force_full_fps else static_fps
        base_vf = f"scale={out_w}:{out_h}:flags=lanczos{post_vf}"
    elif zoom_direction in ("pan_left", "pan_right"):
        effective_fps = fps
        # Панорама: зум фиксированный, x едет по запасу холста от края до края.
        # on идёт 1..frames — нормируем в прогресс 0..1.
        prog = f"((on-1)/{max(frames - 1, 1)})"
        if zoom_direction == "pan_right":
            x_expr = f"(iw-iw/zoom)*{prog}"
        else:
            x_expr = f"(iw-iw/zoom)*(1-{prog})"
        smooth = _zoom_smoothing_frames(1.0)  # панорама — фиксированная "нормальная" скорость
        smooth_vf = f",tmix=frames={smooth}" if smooth else ""
        base_vf = (
            f"scale={canvas_w}:{canvas_h}:flags=lanczos,"
            f"zoompan=z='{_PAN_ZOOM}':x='{x_expr}':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={out_w}x{out_h}:fps={fps}{smooth_vf}{post_vf}"
        )
    else:
        effective_fps = fps
        # Приращение на кадр из скорости "% в секунду"; предел зума — по запасу
        # холста, чтобы не апскейлить (мыло), и не дальше нужного за сегмент
        zoom_inc = zoom_speed / 100.0 / fps
        zoom_max = min(_ZOOM_CAP, 1.0 + zoom_speed / 100.0 * duration_sec)
        # Якорим зум в центр кадра (по умолчанию zoompan уводит в левый верхний угол)
        center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        if zoom_direction == "out":
            # Начинаем с zoom_max, плавно уменьшаем до 1.0
            zoom_expr = f"if(eq(on,1),{zoom_max:.5f},max(zoom-{zoom_inc:.7f},1.0))"
        else:
            # zoom-in: от 1.0 до zoom_max
            zoom_expr = f"min(zoom+{zoom_inc:.7f},{zoom_max:.5f})"
        smooth = _zoom_smoothing_frames(zoom_speed)
        smooth_vf = f",tmix=frames={smooth}" if smooth else ""
        base_vf = (
            f"scale={canvas_w}:{canvas_h}:flags=lanczos,"
            f"zoompan=z='{zoom_expr}':{center}:d={frames}:s={out_w}x{out_h}:fps={fps}{smooth_vf}{post_vf}"
        )

    if particles_dir is None:
        cmd = [
            settings.ffmpeg_path, "-y",
            "-loop", "1", "-framerate", str(effective_fps), "-i", str(image_path),
            "-t", f"{duration_sec:.3f}",
            "-r", str(effective_fps),
            "-vf", f"{base_vf},format=yuv420p",
            *_X264_ARGS, "-tune", "stillimage", "-an",
            str(out_path),
        ]
        _run_ffmpeg(cmd, f"ken-burns {image_path.name}")
        return

    pattern = str(particles_dir / "frame_%04d.png")
    # ВАЖНО: blend=screen должен работать в RGB (format=gbrp). В YUV "чёрный"
    # фон частиц имеет нейтральную цветность 128 (не 0), и screen задирает
    # оба хрома-канала по всему кадру — картинка заливается розово-фиолетовым.
    # В RGB чёрный = 0, screen с чёрным = no-op, светятся только сами частицы.
    cmd = [
        settings.ffmpeg_path, "-y",
        "-loop", "1", "-i", str(image_path),
        "-stream_loop", "-1", "-framerate", "25", "-i", pattern,
        "-t", f"{duration_sec:.3f}",
        "-filter_complex",
        f"[0:v]{base_vf},format=gbrp[bg];"
        f"[1:v]scale={out_w}:{out_h}:flags=lanczos,format=gbrp[fx];"
        "[bg][fx]blend=all_mode=screen:all_opacity=0.55,format=yuv420p[out]",
        "-map", "[out]",
        *_X264_ARGS, "-tune", "stillimage", "-an",
        str(out_path),
    ]
    _run_ffmpeg(cmd, f"ken-burns+particles {image_path.name}")


def render_video_segments(
    *,
    images: list[tuple[Path, float]],
    audio_path: Path | None,
    out_path: Path,
    particles: bool | str = "off",
    resolution: str = "720p",
    zoom: str = "subtle",
    zoom_speed: float | None = None,
    zoom_direction: str = "in",
    warm_grade: bool = True,
    grade: str | None = None,
    vignette: bool = False,
    grain: bool = False,
    transition: str = "none",
    fade_in: bool = False,
    fade_out: bool = False,
    check_cancel: Callable[[], None] | None = None,
) -> str:
    """Собирает mp4 из нескольких картинок (визуальный ряд) с Ken Burns + аудио.

    images        — список (путь_к_картинке, длительность_сек), показываются по порядку.
    resolution    — "720p" (1280×720), "1080p" (1920×1080), "1440p".
    zoom          — "off" = без зума; любое другое значение = зум включён.
    zoom_speed    — скорость зума, % кадра в секунду (0.3 = очень медленно).
                    None = взять из старого пресета zoom (subtle/normal/strong).
    zoom_direction— "in" (к центру), "out" (от центра), "alternate"
                    (чётные сегменты приближают, нечётные отдаляют) или "pan"
                    (панорама: боковой дрейф, направление чередуется по сегментам).
    warm_grade    — тёплый цветокор (устаревшее, используйте grade).
    grade         — пресет цветокора "off"/"warm"/"cold"/"vintage"/"bw";
                    None = вывести из warm_grade (True→warm, False→off).
    vignette      — мягкое затемнение углов.
    grain         — лёгкое плёночное зерно.
    transition    — "none" (резкая склейка), "dip" (затемнение между сегментами),
                    "fade" (плавный кроссфейд).
    fade_in/out   — появление из чёрного в начале / уход в чёрный в конце видео.
    particles     — "off" / "embers" (искры огня) / "fireflies" (светлячки) /
                    "dust" (пылинки). bool принимается для совместимости (True = embers).
    audio_path    — None = собрать видео без звука (превью монтажа).
    """
    if not _ffmpeg_available():
        raise RenderError(
            f"FFmpeg не найден (FFMPEG_PATH={settings.ffmpeg_path}). "
            "Установите FFmpeg и/или укажите путь в .env."
        )
    if audio_path is not None and not audio_path.exists():
        raise RenderError(f"Нет аудиофайла для рендера: {audio_path}")
    missing = [str(p) for p, _ in images if not p.exists()]
    if missing:
        raise RenderError(f"Не найдены картинки визуального ряда: {missing}")
    if not images:
        raise RenderError("Пустой список картинок визуального ряда")

    if isinstance(particles, bool):
        particles = "embers" if particles else "off"
    particles_dir: Path | None = None
    if particles != "off":
        from app.services import particle_gen

        particles_dir = particle_gen.ensure_particle_frames(kind=particles)

    zoom_enabled = zoom != "off"
    if zoom_speed is None:
        zoom_speed = _LEGACY_ZOOM_SPEEDS.get(zoom, 0.3)
    zoom_speed = max(0.05, min(5.0, float(zoom_speed)))
    if grade is None:
        grade = "warm" if warm_grade else "off"

    durations = [max(d, 0.5) for _, d in images]
    total_dur = sum(durations)
    # Кроссфейд/зерно требуют полного fps даже на статике (2 fps дал бы рывки)
    force_full_fps = transition != "none" or grain
    use_xfade = transition == "fade" and len(images) > 1
    xfade_dur = min(_XFADE_DUR, min(durations) / 2) if use_xfade else 0.0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="yas_segments_") as tmp:
        tmp_dir = Path(tmp)
        segment_files: list[Path] = []
        for i, (img, _) in enumerate(images):
            if check_cancel:
                check_cancel()
            seg = tmp_dir / f"seg_{i:03d}.mp4"
            if zoom_direction == "alternate":
                seg_direction = "in" if i % 2 == 0 else "out"
            elif zoom_direction == "pan":
                seg_direction = "pan_right" if i % 2 == 0 else "pan_left"
            else:
                seg_direction = zoom_direction
            # Для кроссфейда каждый сегмент (кроме последнего) кодируется длиннее
            # на длительность фейда — xfade "съедает" перекрытие, итоговая длина
            # снова равна сумме исходных длительностей (и длине аудио).
            enc_dur = durations[i]
            if use_xfade and i < len(images) - 1:
                enc_dur += xfade_dur
            _ken_burns_segment(
                img, enc_dur, seg,
                particles_dir=particles_dir,
                resolution=resolution,
                zoom_enabled=zoom_enabled,
                zoom_speed=zoom_speed,
                zoom_direction=seg_direction,
                grade=grade,
                vignette=vignette,
                grain=grain,
                dip=(transition == "dip"),
                force_full_fps=force_full_fps,
            )
            segment_files.append(seg)

        video_only = tmp_dir / "video_only.mp4"
        if use_xfade:
            if check_cancel:
                check_cancel()
            # Цепочка xfade: offset каждого перехода — накопленная сумма
            # исходных (не удлинённых) длительностей предыдущих сегментов
            inputs: list[str] = []
            for seg in segment_files:
                inputs += ["-i", str(seg)]
            chains: list[str] = []
            prev = "[0:v]"
            offset = 0.0
            for i in range(1, len(segment_files)):
                offset += durations[i - 1]
                label = "[vout]" if i == len(segment_files) - 1 else f"[vx{i}]"
                chains.append(
                    f"{prev}[{i}:v]xfade=transition=fade:duration={xfade_dur:.3f}:offset={offset:.3f}{label}"
                )
                prev = label
            _run_ffmpeg(
                [
                    settings.ffmpeg_path, "-y",
                    *inputs,
                    "-filter_complex", ";".join(chains),
                    "-map", "[vout]",
                    *_X264_ARGS, "-an",
                    str(video_only),
                ],
                "xfade concat",
            )
        else:
            concat_list = tmp_dir / "concat.txt"
            concat_list.write_text(
                "\n".join(f"file '{seg.as_posix()}'" for seg in segment_files), encoding="utf-8"
            )
            _run_ffmpeg(
                [
                    settings.ffmpeg_path, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", str(concat_list),
                    "-c", "copy",
                    str(video_only),
                ],
                "concat",
            )

        # Fade in/out всего видео требует перекодирования на этапе мукса;
        # без них видео просто копируется (быстро, без потери качества)
        fades: list[str] = []
        if fade_in:
            fades.append("fade=t=in:st=0:d=1.5")
        if fade_out:
            fades.append(f"fade=t=out:st={max(0.0, total_dur - 2.5):.3f}:d=2.5")
        if fades:
            video_args = ["-vf", ",".join(fades) + ",format=yuv420p", *_X264_ARGS]
        else:
            video_args = ["-c:v", "copy"]
        if audio_path is None:
            # Превью-режим: без звуковой дорожки
            _run_ffmpeg(
                [
                    settings.ffmpeg_path, "-y",
                    "-i", str(video_only),
                    *video_args, "-an",
                    "-movflags", "+faststart",
                    str(out_path),
                ],
                "finalize (no audio)",
            )
        else:
            _run_ffmpeg(
                [
                    settings.ffmpeg_path, "-y",
                    "-i", str(video_only),
                    "-i", str(audio_path),
                    *video_args,
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                    "-shortest",
                    str(out_path),
                ],
                "mux audio",
            )
    logger.info("FFmpeg рендер визуального ряда ({n} картинок) -> {out}", n=len(images), out=out_path)
    return str(out_path)


def mix_background_music(
    video_path: Path,
    music_path: Path,
    out_path: Path,
    volume: float = 0.15,
) -> str:
    """Добавляет фоновую музыку к готовому mp4.

    Музыка зацикливается/обрезается по длине видео.
    volume — громкость музыки относительно голоса (0.0–1.0, обычно 0.1–0.2).
    """
    if not _ffmpeg_available():
        raise RenderError(f"FFmpeg не найден (FFMPEG_PATH={settings.ffmpeg_path}).")
    if not video_path.exists():
        raise RenderError(f"Видео не найдено: {video_path}")
    if not music_path.exists():
        raise RenderError(f"Музыкальный файл не найден: {music_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    vol = max(0.0, min(1.0, volume))
    # stream_loop -1 зацикливает музыку; amix смешивает и нормализует
    cmd = [
        settings.ffmpeg_path, "-y",
        "-i", str(video_path),
        "-stream_loop", "-1", "-i", str(music_path),
        "-filter_complex",
        f"[1:a]volume={vol:.3f}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]",
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    _run_ffmpeg(cmd, "mix music")
    logger.info("Музыка подмикширована (vol={v:.2f}): {out}", v=vol, out=out_path)
    return str(out_path)


def prepend_intro_audio(intro_path: Path, main_path: Path, out_path: Path) -> None:
    """Склеивает интро-аудио + основное аудио в один файл через FFmpeg."""
    if not _ffmpeg_available():
        raise RenderError(f"FFmpeg не найден (FFMPEG_PATH={settings.ffmpeg_path}).")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(f"file '{intro_path.as_posix()}'\n")
        f.write(f"file '{main_path.as_posix()}'\n")
        concat_list = f.name
    _run_ffmpeg(
        [
            settings.ffmpeg_path, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c", "copy",
            str(out_path),
        ],
        "concat intro+main audio",
    )
    logger.info("Интро склеено: {intro} + {main} -> {out}", intro=intro_path.name, main=main_path.name, out=out_path)
