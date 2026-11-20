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
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

FORMATS = {
    "mp4": "MP4 video (H.264) - slides, web, social media",
    "webm": "WebM video (VP9) - web pages",
    "mov": "QuickTime ProRes 422 HQ - for video editors",
    "gif": "Animated GIF - quick previews, chat, README files",
    "png": "PNG image sequence - a folder of frames",
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
                   audio_volume: float = 1.0, duration: float | None = None, metadata: dict | None = None) -> list[str]:
    w, h = size
    cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", f"{fps:g}", "-i", "-"]
    has_audio = audio is not None and fmt in ("mp4", "webm", "mov")
    if has_audio:
        if audio_offset >= 0:
            cmd += ["-itsoffset", f"{audio_offset:.3f}", "-i", str(audio)]
        else:
            cmd += ["-ss", f"{-audio_offset:.3f}", "-i", str(audio)]
        cmd += ["-map", "0:v", "-map", "1:a"]
        if abs(audio_volume - 1.0) > 1e-3:
            cmd += ["-filter:a", f"volume={audio_volume:.3f}"]
    if fmt == "mp4":
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(int(crf)), "-pix_fmt", "yuv420p",
                "-movflags", "+faststart"]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k"]
    elif fmt == "webm":
        cmd += ["-c:v", "libvpx-vp9", "-crf", str(min(63, int(crf) + 14)), "-b:v", "0", "-row-mt", "1",
                "-pix_fmt", "yuv420p"]
        if has_audio:
            cmd += ["-c:a", "libopus", "-b:a", "160k"]
    elif fmt == "mov":
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


def _worker_init(project_json: dict, path: str | None, scale: float) -> None:
    import cv2

    cv2.setNumThreads(1)
    from .model.project import Project

    proj = Project.from_json(project_json, path)
    _W["renderer"] = proj.renderer()
    _W["scale"] = scale


def _worker_frame(t: float) -> bytes:
    return _W["renderer"].frame(t, _W["scale"]).tobytes()


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
                cancel: threading.Event | None = None):
    """Yield raw RGB frames in order, rendering ``workers`` frames in parallel."""
    if workers <= 1 or len(times) < 4:
        r = project.renderer()
        for t in times:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            yield r.frame(t, scale).tobytes()
        return
    ctx = mp.get_context("spawn")
    path = str(project.path) if project.path else None
    with cf.ProcessPoolExecutor(workers, mp_context=ctx, initializer=_worker_init,
                                initargs=(project.to_json(), path, scale)) as pool:
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


def export(project: Project, output: str | os.PathLike, *, fps: float | None = None, scale: float = 1.0,
           crf: int = 18, preset: str = "medium", start: float | None = None, end: float | None = None,
           workers: int | None = None, audio: bool = True, subtitles: bool = False,
           progress: Callable[[int, int, float], None] | None = None,
           cancel: threading.Event | None = None) -> Path:
    """Render ``project`` to ``output``. The format follows the extension (.mp4 .webm .mov .gif, or a folder for PNG).

    ``scale`` multiplies the resolution (0.5 = half size); ``crf`` sets H.264 quality (lower is sharper);
    ``workers`` is the number of parallel render processes (default: CPU cores - 1).
    ``progress(done, total, eta_seconds)`` is called after each frame.
    """
    from .render import out_size

    out = Path(output)
    fmt = detect_format(out)
    fps = float(fps or project.fps)
    if fmt == "gif":
        fps = min(fps, 15.0) if fps == project.fps else fps
    t0_film = max(0.0, float(start or 0.0))
    t1_film = min(project.duration, float(end)) if end is not None else project.duration
    n0 = int(round(t0_film * fps))
    n1 = max(n0 + 1, int(round(t1_film * fps)))
    times = [i / fps for i in range(n0, n1)]
    total = len(times)
    W, H = out_size(project, scale)
    workers = default_workers() if workers is None else max(1, int(workers))
    out.parent.mkdir(parents=True, exist_ok=True) if fmt != "png" else out.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()

    def report(i: int) -> None:
        if progress is not None:
            el = time.perf_counter() - started
            eta = el / max(i, 1) * (total - i)
            progress(i, total, eta)

    def frames():
        try:
            yield from iter_frames(project, times, scale, workers, cancel)
        except cf.process.BrokenProcessPool:
            sys.stderr.write("sciview: parallel rendering failed, continuing in one process\n")
            yield from iter_frames(project, times, scale, 1, cancel)

    if fmt == "png":
        import cv2

        for i, data in enumerate(frames(), 1):
            img = np.frombuffer(data, np.uint8).reshape(H, W, 3)
            cv2.imwrite(str(out / f"frame_{n0 + i - 1:05d}.png"), img[:, :, ::-1])
            report(i)
        return out

    audio_path = None
    a = project.settings.get("audio")
    if audio and a:
        ap = Path(a) if Path(a).is_absolute() else project.base_dir / a
        audio_path = ap if ap.exists() else None
    meta = {"title": project.settings.get("title"), "artist": project.settings.get("author"),
            "comment": "Made with SciView"}
    cmd = ffmpeg_command(find_ffmpeg(), fmt, (W, H), fps, out, crf, preset, audio_path,
                         float(project.settings.get("audio_offset", 0.0)) - t0_film,
                         float(project.settings.get("audio_volume", 1.0)), total / fps, meta)
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
    if code != 0:
        raise ExportError(f"ffmpeg failed ({code}): {err.decode(errors='ignore').strip()[-800:]}")
    if subtitles:
        srt = project.captions_srt()
        if srt:
            out.with_suffix(".srt").write_text(srt, encoding="utf-8")
    return out
