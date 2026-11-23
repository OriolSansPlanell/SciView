"""Narration helpers: captions lined up with a recording, captions from a script, and text-to-speech.

Text-to-speech is a plugin point. A package can provide an engine through the ``sciview.tts`` entry
point group: a callable ``speak(text, path, voice=None, rate=None) -> path`` that writes a WAV file.
Without a plugin SciView uses pyttsx3 if it is installed, else the system's own voice (``say`` on
macOS, ``espeak-ng``/``espeak`` on Linux, System.Speech through PowerShell on Windows).
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .model.base import SceneObject
    from .model.project import Project

READING_SPEED = 15.0       # characters per second for captions without a recording
MIN_CAPTION = 1.2          # seconds


class NarrationError(RuntimeError):
    pass


# --------------------------------------------------------------------------- splitting a script
def split_script(text: str, max_chars: int = 84) -> list[str]:
    """Caption lines from a script: one per line, long lines split at sentence ends, then at commas."""
    out: list[str] = []
    for para in [p.strip() for p in re.split(r"\n\s*\n|\n", text or "") if p.strip()]:
        sentences = re.split(r"(?<=[.!?…])\s+", para)
        for s in sentences:
            s = s.strip()
            while len(s) > max_chars:
                cut = max(s.rfind(", ", 0, max_chars), s.rfind("; ", 0, max_chars), s.rfind(" – ", 0, max_chars))
                if cut < max_chars // 3:
                    cut = s.rfind(" ", 0, max_chars)
                if cut <= 0:
                    break
                out.append(s[:cut + 1].strip())
                s = s[cut + 1:].strip()
            if s:
                out.append(s)
    return out


def _fit(lines: list[str], segments: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Spread caption lines over speech segments, in order, in proportion to their length."""
    if not segments:
        return []
    if len(segments) == len(lines):
        return list(segments)
    # treat the speech as one long ribbon (gaps removed) and cut it by characters
    total_speech = sum(b - a for a, b in segments)
    weights = [max(len(x), 1) for x in lines]
    wsum = float(sum(weights))
    out = []
    pos = 0.0

    def at(u: float) -> float:              # speech-time -> recording time
        acc = 0.0
        for a, b in segments:
            if u <= acc + (b - a) + 1e-9:
                return a + (u - acc)
            acc += b - a
        return segments[-1][1]

    for w in weights:
        span = total_speech * w / wsum
        a, b = at(pos), at(pos + span)
        out.append((a, max(b, a + 0.3)))
        pos += span
    return out


def captions_from_script(project: Project, text: str, scene=None, voice: SceneObject | str | None = None,
                         start: float = 0.0, **caption_props) -> list[SceneObject]:
    """Add one caption per line of ``text`` to a scene.

    With a ``voice`` clip, the captions follow the phrases of the recording (its speech segments), in
    order; without one they follow each other at a comfortable reading speed from ``start``.
    """
    from . import audio
    lines = split_script(text)
    if not lines:
        return []
    sc = project.get_scene(scene)
    times: list[tuple[float, float]] = []
    if voice is not None:
        v = project[voice] if isinstance(voice, str) else voice
        sc = project.scene_of(v)
        path = Path(v.props["audio"]) if Path(v.props["audio"]).is_absolute() else project.base_dir / v.props["audio"]
        clip_len = (v.end - v.start) if v.end is not None else None
        segs = audio.speech_segments(path, trim=float(v.props.get("trim", 0.0)), length=clip_len)
        times = [(v.start + a, v.start + b) for a, b in _fit(lines, segs)]
    if not times:
        t = start
        for line in lines:
            d = max(MIN_CAPTION, len(line) / READING_SPEED)
            times.append((t, t + d))
            t += d + 0.25
    made = []
    for line, (a, b) in zip(lines, times):
        a = min(a, sc.duration - 0.1)
        b = min(max(b, a + 0.3), sc.duration)
        made.append(project.add("caption", text=line, start=round(a, 2), end=round(b, 2), scene=sc,
                                **caption_props))
    return made


def snap_points(project: Project, scene) -> list[float]:
    """Scene times where phrases of the scene's voice clips start or end (for snapping captions)."""
    from . import audio
    sc = project.get_scene(scene)
    pts: list[float] = []
    for o in project.objects:
        if o.TYPE != "voice" or o.scene != sc.id or not o.props.get("audio"):
            continue
        path = Path(o.props["audio"]) if Path(o.props["audio"]).is_absolute() else project.base_dir / o.props["audio"]
        try:
            segs = audio.speech_segments(path, trim=float(o.props.get("trim", 0.0)),
                                         length=(o.end - o.start) if o.end is not None else None)
        except (audio.AudioError, OSError):
            continue
        for a, b in segs:
            pts += [o.start + a, o.start + b]
    return sorted(pts)


# --------------------------------------------------------------------------- text-to-speech
def _plugins() -> dict[str, Callable]:
    try:
        from importlib.metadata import entry_points
        eps = entry_points(group="sciview.tts")
    except Exception:  # pragma: no cover
        return {}
    out = {}
    for ep in eps:
        try:
            out[ep.name] = ep.load()
        except Exception as exc:  # a broken plugin must not break SciView
            sys.stderr.write(f"sciview: text-to-speech plugin {ep.name!r} failed to load: {exc}\n")
    return out


_ENGINES: dict[str, Callable] = {}


def register_engine(name: str, speak: Callable) -> None:
    """Make a text-to-speech engine available (the same as an entry point, from Python)."""
    _ENGINES[name] = speak


def _pyttsx3(text: str, path: Path, voice=None, rate=None) -> Path:
    import pyttsx3
    eng = pyttsx3.init()
    if voice:
        eng.setProperty("voice", voice)
    if rate:
        eng.setProperty("rate", int(rate))
    eng.save_to_file(text, str(path))
    eng.runAndWait()
    return path


def _system(text: str, path: Path, voice=None, rate=None) -> Path:
    if sys.platform == "darwin" and shutil.which("say"):
        aiff = path.with_suffix(".aiff")
        cmd = ["say", "-o", str(aiff)] + (["-v", voice] if voice else []) + (["-r", str(int(rate))] if rate else [])
        subprocess.run(cmd + [text], check=True, timeout=300)
        from .export import find_ffmpeg
        subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-i", str(aiff), str(path)], check=True, timeout=300)
        aiff.unlink(missing_ok=True)
        return path
    for exe in ("espeak-ng", "espeak"):
        if shutil.which(exe):
            cmd = [exe, "-w", str(path)] + (["-v", voice] if voice else []) + (["-s", str(int(rate))] if rate else [])
            subprocess.run(cmd + [text], check=True, timeout=300)
            return path
    if sys.platform == "win32" and shutil.which("powershell"):
        safe = text.replace("'", "''")
        out = str(path).replace("'", "''")
        script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  + (f"$s.SelectVoice('{voice}'); " if voice else "")
                  + f"$s.SetOutputToWaveFile('{out}'); $s.Speak('{safe}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=300)
        return path
    raise NarrationError("no text-to-speech engine found: pip install pyttsx3, or install espeak-ng (Linux)")


def engines() -> list[str]:
    """Names of the text-to-speech engines that can be used here, best first."""
    names = list(_ENGINES) + list(_plugins())
    try:
        import pyttsx3  # noqa: F401
        names.append("pyttsx3")
    except Exception:
        pass
    if (sys.platform == "darwin" and shutil.which("say")) or shutil.which("espeak-ng") or shutil.which("espeak") \
            or (sys.platform == "win32" and shutil.which("powershell")):
        names.append("system")
    return names


def speak(text: str, path: str | Path, voice: str | None = None, rate: float | None = None,
          engine: str | None = None) -> Path:
    """Read ``text`` aloud into a WAV file at ``path`` with the first available engine (or ``engine``)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    table: dict[str, Callable] = {**_ENGINES, **_plugins(), "pyttsx3": _pyttsx3, "system": _system}
    order = [engine] if engine else engines()
    if not order:
        raise NarrationError("no text-to-speech engine found: pip install pyttsx3, or install espeak-ng (Linux)")
    errors = []
    for name in order:
        fn = table.get(name)
        if fn is None:
            errors.append(f"{name}: unknown engine")
            continue
        try:
            out = Path(fn(text, path, voice=voice, rate=rate) or path)
            if out.exists() and out.stat().st_size > 44:
                return out
            errors.append(f"{name}: wrote no sound")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise NarrationError("text-to-speech failed: " + "; ".join(errors))


def read_aloud(project: Project, captions: list[SceneObject] | None = None, folder: str = "assets/voice",
               voice: str | None = None, rate: float | None = None, engine: str | None = None) -> list[SceneObject]:
    """Make a voice clip for each caption (all captions if none are given) by reading it aloud.

    Each clip starts with its caption; a caption is lengthened if its clip is longer.
    """
    from . import audio
    from .engine.text import plain_text
    caps = captions if captions is not None else [o for o in project.objects if o.TYPE == "caption"]
    made = []
    for c in caps:
        text = plain_text(c.get("text")).strip()
        if not text:
            continue
        rel = f"{folder}/{c.id}.wav"
        speak(text, project.base_dir / rel, voice=voice, rate=rate, engine=engine)
        length = audio.duration(project.base_dir / rel)
        sc = project.scene_of(c)
        end = min(sc.duration, c.start + length)
        v = project.add("voice", name=f"Voice: {text[:24]}", audio=rel, script=text, start=c.start, end=end, scene=sc)
        if c.end is not None and c.end < end:
            c.end = end
        made.append(v)
    return made
