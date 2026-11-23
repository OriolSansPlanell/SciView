"""Sound for films: decoding with ffmpeg, mixing narration clips with the soundtrack, waveforms and
the parts of a recording where someone speaks.

Everything is decoded once to 48 kHz stereo float32 and kept in a small cache keyed by the file's
modification time.
"""
from __future__ import annotations

import io
import subprocess
import wave
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

RATE = 48000
_cache: OrderedDict[tuple, np.ndarray] = OrderedDict()
_CACHE_SAMPLES = RATE * 60 * 30          # about 30 minutes of stereo sound


class AudioError(RuntimeError):
    pass


def decode(path: str | Path, rate: int = RATE) -> np.ndarray:
    """A sound file as float32 samples (n, 2) at ``rate`` Hz. WAV is read directly, anything else
    (MP3, M4A, OGG, WebM from the browser ...) through ffmpeg."""
    p = Path(path)
    if not p.exists():
        raise AudioError(f"sound file not found: {p.name}")
    key = (str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size, rate)
    hit = _cache.get(key)
    if hit is not None:
        _cache.move_to_end(key)
        return hit
    data = _read_wav(p, rate) if p.suffix.lower() == ".wav" else None
    if data is None:
        data = _ffmpeg_decode(p, rate)
    _cache[key] = data
    total = sum(len(v) for v in _cache.values())
    while len(_cache) > 1 and total > _CACHE_SAMPLES:
        _, old = _cache.popitem(last=False)
        total -= len(old)
    return data


def _read_wav(p: Path, rate: int) -> np.ndarray | None:
    try:
        with wave.open(str(p), "rb") as w:
            ch, width, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(n)
    except (wave.Error, EOFError):
        return None                       # float WAV, extensible formats ...: let ffmpeg do it
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648.0
    else:
        return None
    x = x.reshape(-1, ch)
    x = np.repeat(x, 2, axis=1) if ch == 1 else x[:, :2]
    if sr != rate and len(x):
        t_new = np.arange(int(round(len(x) * rate / sr))) * (sr / rate)
        idx = np.arange(len(x))
        x = np.stack([np.interp(t_new, idx, x[:, c]) for c in range(2)], axis=1).astype(np.float32)
    return np.ascontiguousarray(x, np.float32)


def _ffmpeg_decode(p: Path, rate: int) -> np.ndarray:
    from .export import find_ffmpeg
    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(p), "-vn", "-f", "f32le",
           "-acodec", "pcm_f32le", "-ac", "2", "-ar", str(rate), "-"]
    r = subprocess.run(cmd, capture_output=True, timeout=600)
    if r.returncode != 0:
        raise AudioError(f"could not read {p.name}: {r.stderr.decode(errors='ignore').strip()[-300:]}")
    return np.frombuffer(r.stdout, np.float32).reshape(-1, 2).copy()


def duration(path: str | Path) -> float:
    return len(decode(path)) / RATE


def write_wav(path: str | Path, samples: np.ndarray, rate: int = RATE) -> Path:
    """Write float samples (n,) or (n, ch) as 16-bit WAV."""
    x = np.asarray(samples, np.float32)
    if x.ndim == 1:
        x = x[:, None]
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return Path(path)


def wav_bytes(samples: np.ndarray, rate: int = RATE) -> bytes:
    buf = io.BytesIO()
    x = np.asarray(samples, np.float32)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(buf, "wb") as w:
        w.setnchannels(x.shape[1] if x.ndim > 1 else 1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


# --------------------------------------------------------------------------- clips and mixing
def clips(project: Project, scene=None) -> list[dict]:
    """Every sound placed in the film: the soundtrack and the voice clips, in film time.

    With ``scene``, only that scene's clips (and the soundtrack), in the scene's own time.

    Each is ``{"path", "at", "trim", "length", "volume", "fade_in", "fade_out", "id"}``; ``length`` is
    None for "until the file ends".
    """
    out = []
    a = project.settings.get("audio")
    only = project.get_scene(scene) if scene is not None else None
    shift = project.scene_start(only) if only is not None else 0.0
    if a:
        off = float(project.settings.get("audio_offset", 0.0)) - shift
        out.append({"id": None, "path": _abs(project, a), "at": max(0.0, off), "trim": max(0.0, -off),
                    "length": None, "volume": float(project.settings.get("audio_volume", 1.0)),
                    "fade_in": 0.0, "fade_out": 0.0})
    for sc, start, _end in project.timeline():
        if only is not None:
            if sc is not only:
                continue
            start = 0.0
        for o in project.objects:
            if o.TYPE != "voice" or o.scene != sc.id or not o.visible or not o.props.get("audio"):
                continue
            s, e = o.span(sc.duration)
            e = min(e, sc.duration)
            if e <= s:
                continue
            out.append({"id": o.id, "path": _abs(project, o.props["audio"]), "at": start + s,
                        "trim": float(o.props.get("trim", 0.0)), "length": e - s,
                        "volume": float(o.props.get("volume", 1.0)), "fade_in": float(o.props.get("fade_in", 0.0)),
                        "fade_out": float(o.props.get("fade_out", 0.0))})
    return out


def _abs(project: Project, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else project.base_dir / p


def mix(project: Project, start: float = 0.0, end: float | None = None, rate: int = RATE,
        warn=None, scene=None) -> np.ndarray:
    """All the film's sound between ``start`` and ``end`` (film seconds) as float32 (n, 2).

    With ``scene``: that scene's sound, ``start`` and ``end`` in its own time."""
    if end is None:
        end = project.get_scene(scene).duration if scene is not None else project.duration
    n = max(0, int(round((end - start) * rate)))
    out = np.zeros((n, 2), np.float32)
    for c in clips(project, scene):
        try:
            x = decode(c["path"], rate)
        except (AudioError, OSError) as exc:
            if warn is not None:
                warn(str(exc))
            continue
        i0 = int(round(c["trim"] * rate))
        seg = x[i0:]
        if c["length"] is not None:
            seg = seg[:int(round(c["length"] * rate))]
        if not len(seg):
            continue
        seg = seg * c["volume"]
        if c["fade_in"] > 0 or c["fade_out"] > 0:
            env = np.ones(len(seg), np.float32)
            fi, fo = int(c["fade_in"] * rate), int(c["fade_out"] * rate)
            if fi > 0:
                env[:fi] = np.linspace(0, 1, min(fi, len(seg)), dtype=np.float32)[:len(env[:fi])]
            if fo > 0:
                env[-fo:] = np.minimum(env[-fo:], np.linspace(1, 0, min(fo, len(seg)), dtype=np.float32))
            seg = seg * env[:, None]
        at = int(round((c["at"] - start) * rate))
        a0, s0 = max(0, at), max(0, -at)
        k = min(n - a0, len(seg) - s0)
        if k > 0:
            out[a0:a0 + k] += seg[s0:s0 + k]
    peak = float(np.abs(out).max()) if n else 0.0
    if peak > 1.0:                        # gentle limiter instead of clipping
        out = np.tanh(out / peak * 1.4) / np.tanh(1.4) * min(peak, 1.0)
    return out


def has_sound(project: Project) -> bool:
    return bool(clips(project))


# --------------------------------------------------------------------------- analysis
def waveform(path: str | Path, bins: int = 800, trim: float = 0.0, length: float | None = None) -> dict:
    """Peak levels for drawing: ``{"peaks": [0..1] * bins, "seconds": length}``."""
    x = decode(path)
    i0 = int(trim * RATE)
    x = x[i0:] if length is None else x[i0:i0 + int(length * RATE)]
    mono = np.abs(x).max(axis=1) if len(x) else np.zeros(0, np.float32)
    bins = max(1, min(int(bins), 20000))
    if len(mono) == 0:
        return {"peaks": [0.0] * bins, "seconds": 0.0}
    edges = np.linspace(0, len(mono), bins + 1).astype(int)
    peaks = np.array([mono[a:b].max() if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])], np.float32)
    top = float(peaks.max()) or 1.0
    return {"peaks": [round(float(v), 3) for v in np.sqrt(peaks / top)], "seconds": len(mono) / RATE}


def speech_segments(path: str | Path, min_gap: float = 0.35, min_length: float = 0.25,
                    trim: float = 0.0, length: float | None = None) -> list[tuple[float, float]]:
    """Where someone speaks in a recording: (start, end) in seconds from ``trim``.

    The level is measured in 20 ms windows; speech is what rises 12 dB above the background noise (the
    quietest tenth of the recording). Pauses shorter than ``min_gap`` do not split a phrase.
    """
    x = decode(path)
    i0 = int(trim * RATE)
    x = x[i0:] if length is None else x[i0:i0 + int(length * RATE)]
    if len(x) < RATE // 10:
        return []
    mono = x.mean(axis=1)
    win = RATE // 50
    n = len(mono) // win
    rms = np.sqrt((mono[:n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    floor = float(np.percentile(db, 10))
    peak = float(np.percentile(db, 98))
    thr = max(floor + 12.0, peak - 35.0, -60.0)
    on = db > thr
    segs: list[list[float]] = []
    i = 0
    while i < n:
        if on[i]:
            j = i
            while j < n and on[j]:
                j += 1
            a, b = i * 0.02, j * 0.02
            if segs and a - segs[-1][1] < min_gap:
                segs[-1][1] = b
            else:
                segs.append([a, b])
            i = j
        else:
            i += 1
    return [(round(a, 3), round(b, 3)) for a, b in segs if b - a >= min_length]
