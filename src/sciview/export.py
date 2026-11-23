"""Exporting films: MP4 (H.264), WebM (VP9), MOV (ProRes), GIF and PNG sequences.

Frames are rendered in parallel worker processes (``frame(t)`` is a pure function
of time) and piped to ffmpeg as raw RGB. No intermediate image files are written
except for PNG sequences.
"""
from __future__ import annotations

import concurrent.futures as cf
import contextlib
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import threading
import time as time_mod
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

FORMATS = {
    "mp4": "MP4 video (H.264) - slides, web, social media",
    "webm": "WebM video (VP9) - web pages; can be transparent",
    "mov": "QuickTime ProRes - for video editors; ProRes 4444 when transparent",
    "gif": "Animated GIF - quick previews, chat, README files",
    "png": "PNG image sequence - a folder of frames; can be transparent",
}

# One-click settings for common destinations. Sizes are output pixels; "crop" keeps the film's height
# and cuts the sides to the target's shape around the project's crop_x.
TARGETS: dict[str, dict] = {
    "slides": {"label": "Slides (1080p)", "ext": "mp4", "size": (1920, 1080), "crf": 18,
               "help": "Full HD MP4 for PowerPoint, Keynote and Google Slides"},
    "conference": {"label": "Conference (4K)", "ext": "mp4", "size": (3840, 2160), "crf": 16,
                   "help": "4K MP4 for large screens"},
    "poster": {"label": "Poster still (4K)", "ext": "png", "size": (3840, 2160), "still": True,
               "help": "One 4K PNG frame for posters and papers"},
    "square": {"label": "Square (social)", "ext": "mp4", "size": (1080, 1080), "crf": 20, "crop": True,
               "help": "1080 x 1080 MP4; the sides are cut (see the square guide in the preview)"},
    "vertical": {"label": "Vertical (social)", "ext": "mp4", "size": (1080, 1920), "crf": 20, "crop": True,
                 "help": "1080 x 1920 MP4 for phones; the sides are cut (see the vertical guide)"},
    "overlay": {"label": "Transparent overlay", "ext": "mov", "size": (1920, 1080), "transparent": True,
                "help": "ProRes 4444 with alpha, to lay over slides, photos or lab footage"},
    "web": {"label": "Web page", "ext": "html", "size": (1920, 1080), "crf": 20,
            "help": "One HTML page with the video, captions, chapters and the project"},
    "preview": {"label": "Preview GIF", "ext": "gif", "size": (640, 360), "fps": 15,
                "help": "Small animated GIF for chats and README files"},
}


class ExportError(RuntimeError):
    pass


class Cancelled(Exception):
    pass


def find_ffmpeg() -> str:
    """ffmpeg executable: $SCIVIEW_FFMPEG, then PATH, then the imageio-ffmpeg wheel."""
    env = os.environ.get("SCIVIEW_FFMPEG")
    if env and Path(env).exists():
        return env
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise ExportError("ffmpeg was not found. Install it (https://ffmpeg.org) or run: pip install imageio-ffmpeg")


def default_workers() -> int:
    n = os.cpu_count() or 2
    return max(1, min(8, n - 1))


def detect_format(output: str | os.PathLike) -> str:
    p = Path(output)
    ext = p.suffix.lower().lstrip(".")
    if ext in FORMATS:
        return ext
    if ext in ("", "d") or p.is_dir():
        return "png"
    raise ExportError(f"unknown output format {p.suffix!r}. Use one of: .{', .'.join(FORMATS)}")


def ffmpeg_command(ffmpeg: str, fmt: str, size: tuple[int, int], fps: float, output: Path, crf: int = 18,
                   preset: str = "medium", audio: Path | None = None, audio_offset: float = 0.0,
                   audio_volume: float = 1.0, duration: float | None = None, metadata: dict | None = None,
                   *, alpha: bool = False, chapters: Path | None = None, subtitles: Path | None = None) -> list[str]:
    """The ffmpeg command that turns raw frames on stdin into ``output``.

    ``alpha``: frames are RGBA (ProRes 4444, VP9 with alpha). ``chapters``: an ffmetadata file with
    chapter markers. ``subtitles``: an .srt file embedded as a subtitle track (soft subtitles).
    """
    w, h = size
    if alpha and fmt not in ("mov", "webm"):
        raise ExportError(f"{fmt.upper()} cannot be transparent; use .mov (ProRes 4444), .webm or PNG frames")
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo",
           "-pix_fmt", "rgba" if alpha else "rgb24", "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-"]
    container = fmt in ("mp4", "webm", "mov")
    has_audio = audio is not None and container
    n_in = 1
    maps = ["-map", "0:v"]
    if has_audio:
        if audio_offset >= 0:
            cmd += ["-itsoffset", f"{audio_offset:.3f}", "-i", str(audio)]
        else:
            cmd += ["-ss", f"{-audio_offset:.3f}", "-i", str(audio)]
        maps += ["-map", f"{n_in}:a"]
        n_in += 1
        if abs(audio_volume - 1.0) > 1e-3:
            cmd += ["-filter:a", f"volume={audio_volume:.3f}"]
    if subtitles is not None and container:
        cmd += ["-i", str(subtitles)]
        maps += ["-map", f"{n_in}:s"]
        n_in += 1
    if chapters is not None and container:
        cmd += ["-i", str(chapters)]
        maps += ["-map_chapters", str(n_in)]
        n_in += 1
    if n_in > 1 or chapters is not None:
        cmd += maps
    if subtitles is not None and container:
        cmd += ["-c:s", "webvtt" if fmt == "webm" else "mov_text", "-metadata:s:s:0", "language=eng"]
    if fmt == "mp4":
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(int(crf)), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart"]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
    elif fmt == "webm":
        cmd += ["-c:v", "libvpx-vp9", "-crf", str(min(63, int(crf) + 14)), "-b:v", "0", "-row-mt", "1",
                "-pix_fmt", "yuva420p" if alpha else "yuv420p"]
        if alpha:
            cmd += ["-auto-alt-ref", "0"]
        if has_audio:
            cmd += ["-c:a", "libopus", "-b:a", "160k"]
    elif fmt == "mov":
        if alpha:
            cmd += ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-alpha_bits", "16"]
        else:
            cmd += ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"]
        if has_audio:
            cmd += ["-c:a", "pcm_s16le"]
    elif fmt == "gif":
        cmd += ["-vf", "split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
                "-loop", "0"]
    else:  # pragma: no cover
        raise ExportError(f"ffmpeg cannot write {fmt}")
    if has_audio and duration:
        cmd += ["-t", f"{duration:.3f}"]
    for k, v in (metadata or {}).items():
        if v:
            cmd += ["-metadata", f"{k}={v}"]
    cmd.append(str(output))
    return cmd


# --------------------------------------------------------------------------- workers
_W: dict = {}


def _worker_init(project_json: dict, path: str | None, scale: float, opts: dict | None = None) -> None:
    import cv2

    cv2.setNumThreads(1)
    from .model.project import Project

    proj = Project.from_json(project_json, path)
    _W["renderer"] = proj.renderer()
    _W["renderer"].hide_captions = bool((opts or {}).get("hide_captions"))
    _W["scale"] = scale
    _W["opts"] = {k: v for k, v in (opts or {}).items() if k in ("alpha", "crop", "scene") and v}


def _worker_frame(t: float) -> bytes:
    return _W["renderer"].frame(t, _W["scale"], **_W["opts"]).tobytes()


@contextlib.contextmanager
def _main_hidden():
    """Hide the user's __main__ from 'spawn' while workers start.

    Workers only need sciview, and re-importing a user script that calls ``render()`` at
    top level (no ``if __name__ == "__main__":``) would otherwise start the render again in
    every worker on macOS and Windows.
    """
    main = sys.modules.get("__main__")
    saved = {}
    if main is not None:
        for attr in ("__file__", "__spec__"):
            if hasattr(main, attr):
                saved[attr] = getattr(main, attr)
        with contextlib.suppress(AttributeError, TypeError):
            if "__file__" in saved:
                del main.__file__
            if "__spec__" in saved:
                main.__spec__ = None
    try:
        yield
    finally:
        for attr, val in saved.items():
            setattr(main, attr, val)


def iter_frames(project: Project, times: list[float], scale: float, workers: int,
                cancel: threading.Event | None = None, opts: dict | None = None):
    """Yield raw frames in order, rendering ``workers`` frames in parallel.

    ``opts``: ``alpha`` (RGBA frames), ``crop`` (x, y, w, h design pixels), ``hide_captions``.
    """
    opts = dict(opts or {})
    frame_opts = {k: v for k, v in opts.items() if k in ("alpha", "crop", "scene") and v}
    if workers <= 1 or len(times) < 4:
        r = project.renderer()
        saved = getattr(r, "hide_captions", False)
        r.hide_captions = bool(opts.get("hide_captions"))
        try:
            for t in times:
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                yield r.frame(t, scale, **frame_opts).tobytes()
        finally:
            r.hide_captions = saved
        return
    ctx = mp.get_context("spawn")
    path = str(project.path) if project.path else None
    with cf.ProcessPoolExecutor(workers, mp_context=ctx, initializer=_worker_init,
                                initargs=(project.to_json(), path, scale, opts)) as pool:
        pending: deque = deque()
        it = iter(times)
        with _main_hidden():  # all workers are started by these first submissions
            for _ in range(workers * 2):
                t = next(it, None)
                if t is None:
                    break
                pending.append(pool.submit(_worker_frame, t))
        while pending:
            if cancel is not None and cancel.is_set():
                for f in pending:
                    f.cancel()
                raise Cancelled()
            data = pending.popleft().result()
            t = next(it, None)
            if t is not None:
                pending.append(pool.submit(_worker_frame, t))
            yield data


def uses_script_figures(project: Project) -> bool:
    from . import figures
    return any(o.TYPE == "figure" and figures.get(o.props.get("callback", "")) for o in project.objects)


def crop_rect(project: Project, size: tuple[int, int]) -> tuple[float, float, float, float]:
    """The part of the frame (x, y, w, h in design pixels) that a target of ``size`` shows: the full height
    and the width that gives the target's shape, around the project's ``crop_x``."""
    W, H = project.size
    tw, th = size
    if tw / th >= W / H:                       # wider than the film: full width, cut top and bottom
        h = W * th / tw
        return 0.0, (H - h) / 2, float(W), h
    w = H * tw / th
    cx = float(project.settings.get("crop_x", -1))
    cx = W / 2 if cx < 0 else cx
    x = min(max(cx - w / 2, 0.0), W - w)
    return x, 0.0, w, float(H)


def chapters_metadata(chapters: list[tuple[float, float, str]], t0: float, t1: float) -> str:
    lines = [";FFMETADATA1"]
    for a, b, title in chapters:
        a, b = max(a, t0), min(b, t1)
        if b - a < 0.05:
            continue
        safe = "".join("\\" + c if c in "=;#\\\n" else c for c in title)
        lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(round((a - t0) * 1000))}",
                  f"END={int(round((b - t0) * 1000))}", f"title={safe}"]
    return "\n".join(lines) + "\n"


def srt_text(captions: list[tuple[float, float, str]], t0: float = 0.0, t1: float = 1e12, vtt: bool = False) -> str:
    def ts(x: float) -> str:
        ms = int(round(max(0.0, x) * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        sec, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{sec:02d}{'.' if vtt else ','}{ms:03d}"
    blocks = []
    for a, b, text in captions:
        a, b = max(a, t0), min(b, t1)
        if b > a and text.strip():
            n = len(blocks) + 1
            blocks.append(("" if vtt else f"{n}\n") + f"{ts(a - t0)} --> {ts(b - t0)}\n{text.strip()}\n")
    body = "\n".join(blocks)
    return ("WEBVTT\n\n" + body) if vtt else body


SUBTITLE_MODES = ("off", "file", "soft", "embed")


def export(project: Project, output: str | os.PathLike, *, fps: float | None = None, scale: float | None = None,
           crf: int | None = None, preset: str = "medium", start: float | None = None, end: float | None = None,
           workers: int | None = None, audio: bool = True, subtitles: bool | str = False,
           transparent: bool = False, target: str | None = None, crop=None, chapters: bool = True,
           time: float | None = None, scene=None, progress: Callable[[int, int, float], None] | None = None,
           cancel: threading.Event | None = None) -> Path:
    """Render ``project`` to ``output``. The format follows the extension: .mp4 .webm .mov .gif, a folder for
    PNG frames, .png/.jpg for one still, .html for a web page with a player, .pptx for slides.

    ``target`` applies a preset from :data:`TARGETS` (``"slides"``, ``"square"``, ``"overlay"`` ...).
    ``scale`` multiplies the resolution (0.5 = half size; with a target, half the target's size);
    ``crf`` sets quality (lower is sharper);
    ``workers`` is the number of parallel render processes (default: CPU cores - 1).
    ``transparent`` drops the background (ProRes 4444 .mov, .webm or PNG). ``crop`` is True (the target's
    shape) or (x, y, w, h) in design pixels. ``subtitles``: ``"off"``, ``"file"`` (an .srt next to the
    video; True means this), ``"soft"`` (a subtitle track instead of captions drawn in the picture) or
    ``"embed"`` (both drawn and as a track). Scenes marked as chapters become chapter markers.
    ``scene`` renders one scene on its own (its own time, no transitions), with its sound.
    ``progress(done, total, eta_seconds)`` is called after each frame.
    """
    from .render import out_size

    out = Path(output)
    tg = dict(TARGETS[target]) if target else {}
    if target and target not in TARGETS:  # pragma: no cover - KeyError above
        raise ExportError(f"unknown target {target!r}")
    if target and not out.suffix and tg.get("ext") not in ("png",):
        out = out.with_suffix("." + tg["ext"])
    ext = out.suffix.lower().lstrip(".")
    transparent = bool(transparent or tg.get("transparent"))
    if crf is None:
        crf = int(tg.get("crf", 18))
    if fps is None and tg.get("fps"):
        fps = float(tg["fps"])
    rect = None
    if crop is True or (crop is None and tg.get("crop")):
        rect = crop_rect(project, tg.get("size", project.size))
    elif crop:
        rect = tuple(float(c) for c in crop)
    if tg.get("size"):
        # with a preset, scale is a factor of the preset's size: 1 = its size, 0.5 = half of it
        base = tg["size"][1] / (rect[3] if rect else project.size[1])
        if not rect:
            base = min(base, tg["size"][0] / project.size[0])
        scale = base * (1.0 if scale is None else float(scale))
    scale = 1.0 if scale is None else float(scale)

    if ext == "html":
        from .player import export_html
        return export_html(project, out, scale=scale, crf=crf, fps=fps, workers=workers, progress=progress,
                           cancel=cancel)
    if ext == "pptx":
        from .slides import export_pptx
        return export_pptx(project, out, scale=scale, crf=crf, fps=fps, workers=workers, progress=progress,
                           cancel=cancel)
    if tg.get("still") or (ext in ("png", "jpg", "jpeg") and time is not None):
        return export_still(project, out, project.duration / 2 if time is None else float(time), scale,
                            transparent, rect)

    fmt = detect_format(out)
    fps = float(fps or project.fps)
    if fmt == "gif":
        if transparent:
            raise ExportError("GIF cannot be transparent; use .mov, .webm or a folder of PNG frames")
        fps = min(fps, 15.0) if fps == project.fps else fps
    if transparent and fmt == "mp4":
        raise ExportError("MP4 cannot be transparent; use .mov (ProRes 4444), .webm or a folder of PNG frames")
    mode = "file" if subtitles is True else ("off" if not subtitles else str(subtitles))
    if mode not in SUBTITLE_MODES:
        raise ExportError(f"subtitles must be one of {', '.join(SUBTITLE_MODES)}")
    only = project.get_scene(scene) if scene is not None else None
    length = only.duration if only is not None else project.duration
    t0_film = max(0.0, float(start or 0.0))
    t1_film = min(length, float(end)) if end is not None else length
    n0 = int(round(t0_film * fps))
    n1 = max(n0 + 1, int(round(t1_film * fps)))
    times = [i / fps for i in range(n0, n1)]
    total = len(times)
    W, H = out_size(project, scale)
    if rect is not None:
        s_px = W / project.size[0]
        W, H = int(round(rect[2] * s_px / 2)) * 2, int(round(rect[3] * s_px / 2)) * 2
    workers = default_workers() if workers is None else max(1, int(workers))
    if uses_script_figures(project):
        workers = 1          # figure functions live in this process; render processes cannot call them
    out.parent.mkdir(parents=True, exist_ok=True) if fmt != "png" else out.mkdir(parents=True, exist_ok=True)
    opts = {"alpha": transparent, "crop": rect, "hide_captions": mode == "soft",
            "scene": only.id if only is not None else None}
    channels = 4 if transparent else 3

    started = time_mod.perf_counter()

    def report(i: int) -> None:
        if progress is not None:
            el = time_mod.perf_counter() - started
            eta = el / max(i, 1) * (total - i)
            progress(i, total, eta)

    def frames():
        try:
            yield from iter_frames(project, times, scale, workers, cancel, opts)
        except cf.process.BrokenProcessPool:
            sys.stderr.write("sciview: parallel rendering failed, continuing in one process\n")
            yield from iter_frames(project, times, scale, 1, cancel, opts)

    if fmt == "png":
        import cv2

        for i, data in enumerate(frames(), 1):
            img = np.frombuffer(data, np.uint8).reshape(H, W, channels)
            conv = cv2.COLOR_RGBA2BGRA if channels == 4 else cv2.COLOR_RGB2BGR
            cv2.imwrite(str(out / f"frame_{n0 + i - 1:05d}.png"), cv2.cvtColor(img, conv))
            report(i)
        return out

    import tempfile
    tmp = tempfile.TemporaryDirectory(prefix="sciview-")
    audio_path = None
    caps = project.captions(only)
    try:
        from . import audio as audio_mod
        if audio and fmt != "gif" and audio_mod.has_sound(project):
            notes: list[str] = []
            pcm = audio_mod.mix(project, t0_film, t1_film, warn=notes.append, scene=only)
            for n in notes:
                sys.stderr.write(f"sciview: {n}\n")
            if len(pcm) and np.abs(pcm).max() > 0:
                audio_path = audio_mod.write_wav(Path(tmp.name) / "sound.wav", pcm)
        chapters_path = None
        marks = project.chapters()
        if chapters and only is None and fmt != "gif" and sum(1 for sc in project.scenes if sc.chapter) > 1:
            chapters_path = Path(tmp.name) / "chapters.txt"
            chapters_path.write_text(chapters_metadata(marks, t0_film, t1_film), encoding="utf-8")
        subs_path = None
        if mode in ("soft", "embed") and caps and fmt != "gif":
            subs_path = Path(tmp.name) / "captions.srt"
            subs_path.write_text(srt_text(caps, t0_film, t1_film), encoding="utf-8")
        meta = {"title": project.settings.get("title"), "artist": project.settings.get("author"),
                "comment": "Made with SciView"}
        cmd = ffmpeg_command(find_ffmpeg(), fmt, (W, H), fps, out, crf, preset, audio_path, 0.0, 1.0, total / fps,
                             meta, alpha=transparent, chapters=chapters_path, subtitles=subs_path)
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        err = b""
        try:
            for i, data in enumerate(frames(), 1):
                try:
                    proc.stdin.write(data)
                except BrokenPipeError:
                    break
                report(i)
            proc.stdin.close()
            err = proc.stderr.read()
            code = proc.wait()
        except BaseException:
            proc.kill()
            proc.wait()
            if out.exists():
                out.unlink()
            raise
    finally:
        tmp.cleanup()
    if code != 0:
        raise ExportError(f"ffmpeg failed ({code}): {err.decode(errors='ignore').strip()[-800:]}")
    if mode in ("file", "soft", "embed") and caps:
        out.with_suffix(".srt").write_text(srt_text(caps, t0_film, t1_film), encoding="utf-8")
        out.with_suffix(".vtt").write_text(srt_text(caps, t0_film, t1_film, vtt=True), encoding="utf-8")
    return out


def export_still(project: Project, output: str | os.PathLike, t: float, scale: float = 1.0,
                 transparent: bool = False, crop=None) -> Path:
    """One frame as PNG (or JPG), optionally transparent or cropped."""
    from PIL import Image
    out = Path(output)
    if out.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        out = out.with_suffix(".png")
    if transparent and out.suffix.lower() != ".png":
        raise ExportError("only PNG stills can be transparent")
    out.parent.mkdir(parents=True, exist_ok=True)
    img = project.renderer().frame(t, scale, alpha=transparent, crop=crop)
    Image.fromarray(img).save(out)
    return out
