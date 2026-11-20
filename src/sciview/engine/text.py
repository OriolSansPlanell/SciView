"""Text rendering with a small, scientist-friendly markup.

Markup (works in every text field):

* ``H_2O``, ``^6LiF``      one lowered/raised character
* ``x_{max}``, ``e^{-x}``   lowered/raised groups
* ``\\alpha``, ``\\mu``, ``\\AA``, ``\\deg``, ``\\to``, ``\\pm`` ... symbols
* ``**bold**``             bold run
* ``\\_``, ``\\^``, ``\\*``, ``\\\\``  literal characters

Characters missing from the chosen font (Greek in Poppins, for instance) are
drawn with the bundled Inter font, so labels never show empty boxes.
"""
from __future__ import annotations

import io
import os
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"

FAMILIES: dict[str, dict[str, str]] = {
    "Poppins": {"light": "Poppins-Light.ttf", "regular": "Poppins-Regular.ttf",
                "medium": "Poppins-Medium.ttf", "bold": "Poppins-Bold.ttf"},
    "Inter": {"light": "Inter-Regular.otf", "regular": "Inter-Regular.otf",
              "medium": "Inter-Medium.otf", "bold": "Inter-Bold.otf"},
}
WEIGHTS = ("light", "regular", "medium", "bold")
FALLBACK_FAMILY = "Inter"

SYMBOLS: dict[str, str] = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "zeta": "ζ", "eta": "η",
    "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π",
    "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ",
    "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
    "deg": "°", "circ": "°", "pm": "±", "mp": "∓", "times": "×", "cdot": "·", "div": "÷", "minus": "−",
    "to": "→", "rightarrow": "→", "leftarrow": "←", "leftrightarrow": "↔", "uparrow": "↑", "downarrow": "↓",
    "Rightarrow": "⇒", "approx": "≈", "neq": "≠", "leq": "≤", "geq": "≥", "ll": "≪", "gg": "≫",
    "infty": "∞", "AA": "Å", "hbar": "ℏ", "sqrt": "√", "partial": "∂", "nabla": "∇", "int": "∫",
    "sum": "∑", "prod": "∏", "prime": "′", "propto": "∝", "sim": "∼", "ell": "ℓ", "dagger": "†",
    "bullet": "•", "micro": "µ", "permil": "‰", "langle": "⟨", "rangle": "⟩", "degC": "°C",
    "cdots": "⋯", "ldots": "…", "in": "∈", "forall": "∀", "exists": "∃", "equiv": "≡",
}


# --------------------------------------------------------------------------- fonts
def font_path(family: str, weight: str = "regular") -> str:
    """Path of a bundled family/weight, or ``family`` itself if it is a font file path."""
    if family and os.path.isfile(family):
        return family
    fam = FAMILIES.get(family) or FAMILIES["Poppins"]
    return str(FONT_DIR / fam.get(weight, fam["regular"]))


@lru_cache(maxsize=256)
def get_font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, max(1, int(size)))


@lru_cache(maxsize=32)
def _notdef_signature(path: str) -> bytes:
    return _glyph_signature(path, "￿")


_TEXT_LOCK = threading.RLock()  # FreeType faces are shared and not thread-safe


def _glyph_signature(path: str, ch: str) -> bytes:
    f = get_font(path, 24)
    im = Image.new("L", (64, 48))
    with _TEXT_LOCK:
        ImageDraw.Draw(im).text((8, 36), ch, font=f, fill=255, anchor="ls")
    return im.tobytes()


@lru_cache(maxsize=16384)
def has_glyph(path: str, ch: str) -> bool:
    if ch.isspace():
        return True
    return _glyph_signature(path, ch) != _notdef_signature(path)


# --------------------------------------------------------------------------- markup
@dataclass(frozen=True)
class Run:
    text: str
    level: int = 0      # -1 subscript, 0 baseline, +1 superscript
    bold: bool = False


def parse_markup(text: str) -> list[list[Run]]:
    """Split marked-up text into lines of styled runs."""
    lines: list[list[Run]] = [[]]
    bold = False
    i, n = 0, len(text)

    def push(s: str, level: int = 0) -> None:
        if not s:
            return
        line = lines[-1]
        if line and line[-1].level == level and line[-1].bold == bold:
            line[-1] = Run(line[-1].text + s, level, bold)
        else:
            line.append(Run(s, level, bold))

    def read_atom(j: int) -> tuple[str, int]:
        """Read one character, a {group} or a \\symbol starting at j."""
        if j >= n:
            return "", j
        if text[j] == "{":
            depth, k = 1, j + 1
            while k < n and depth:
                depth += {"{": 1, "}": -1}.get(text[k], 0)
                k += 1
            return expand_symbols(text[j + 1:k - 1]), k
        if text[j] == "\\":
            k = j + 1
            while k < n and text[k].isalpha():
                k += 1
            name = text[j + 1:k]
            if name in SYMBOLS:
                return SYMBOLS[name], k
            if k == j + 1 and k < n:
                return text[k], k + 1
            return text[j:k], k
        return text[j], j + 1

    while i < n:
        c = text[i]
        if c == "\n":
            lines.append([])
            i += 1
        elif c == "*" and text.startswith("**", i):
            bold = not bold
            i += 2
        elif c in "_^" and i + 1 < n and not text[i + 1].isspace():
            s, i = read_atom(i + 1)
            push(s, -1 if c == "_" else 1)
        elif c == "\\":
            s, i = read_atom(i)
            push(s)
        else:
            j = i
            while j < n and text[j] not in "\n*_^\\":
                j += 1
            if j == i:  # a lone marker character
                j = i + 1
            push(text[i:j])
            i = j
    return lines


def expand_symbols(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\":
            k = i + 1
            while k < len(s) and s[k].isalpha():
                k += 1
            name = s[i + 1:k]
            if name in SYMBOLS:
                out.append(SYMBOLS[name])
                i = k
                continue
            if k == i + 1 and k < len(s):
                out.append(s[k])
                i = k + 1
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


def plain_text(text: str) -> str:
    """Markup removed: what a screen reader or subtitle file should show."""
    return "\n".join("".join(r.text for r in line) for line in parse_markup(text))


# --------------------------------------------------------------------------- rendering
@dataclass
class TextImage:
    mask: np.ndarray      # float32 (h, w) coverage 0..1
    width: int
    height: int
    baseline: float       # y of the first baseline from the top of the mask
    pad: int


def _chunks(run_text: str, main: str, fallback: str) -> list[tuple[str, str]]:
    """Split text into (substring, font path) pieces by glyph availability."""
    out: list[tuple[str, str]] = []
    for ch in run_text:
        p = main if has_glyph(main, ch) else fallback
        if out and out[-1][1] == p:
            out[-1] = (out[-1][0] + ch, p)
        else:
            out.append((ch, p))
    return out


def _run_font(run: Run, family: str, weight: str, size: float):
    w = "bold" if run.bold else weight
    s = size * (0.68 if run.level else 1.0)
    main = font_path(family, w)
    fb = font_path(FALLBACK_FAMILY, "bold" if w == "bold" else ("medium" if w == "medium" else "regular"))
    return main, fb, max(1, int(round(s)))


def _run_width(run: Run, family: str, weight: str, size: float) -> float:
    main, fb, s = _run_font(run, family, weight, size)
    return sum(get_font(p, s).getlength(t) for t, p in _chunks(run.text, main, fb))


def _wrap(lines: list[list[Run]], family: str, weight: str, size: float, max_width: float) -> list[list[Run]]:
    out: list[list[Run]] = []
    for line in lines:
        tokens: list[Run] = []
        for r in line:
            parts = r.text.split(" ")
            for k, p in enumerate(parts):
                if p:
                    tokens.append(Run(p, r.level, r.bold))
                if k < len(parts) - 1:
                    tokens.append(Run(" ", r.level, r.bold))
        cur: list[Run] = []
        width = 0.0
        for tok in tokens:
            tw = _run_width(tok, family, weight, size)
            if cur and tok.text != " " and width + tw > max_width:
                while cur and cur[-1].text == " ":
                    cur.pop()
                out.append(cur)
                cur, width = [], 0.0
            if not cur and tok.text == " ":
                continue
            cur.append(tok)
            width += tw
        out.append(cur)
    return out


@lru_cache(maxsize=4096)
def render_text(text: str, size: float, family: str = "Poppins", weight: str = "regular",
                align: str = "left", line_spacing: float = 1.25, max_width: float = 0.0) -> TextImage:
    """Render marked-up text to a coverage mask. ``size`` and ``max_width`` are output pixels.

    Small sizes are drawn at 2-3x and downsampled: glyph hinting at 8-20 px otherwise
    produces uneven letter spacing.
    """
    size = max(1.0, float(size))
    factor = 3 if size < 14 else 2 if size < 30 else 1
    if factor > 1:
        import cv2
        big = _render_text(text, size * factor, family, weight, align, line_spacing, max_width * factor)
        h, w = big.mask.shape
        H, W = max(1, int(np.ceil(h / factor))), max(1, int(np.ceil(w / factor)))
        padded = np.zeros((H * factor, W * factor), np.float32)
        padded[:h, :w] = big.mask
        mask = cv2.resize(padded, (W, H), interpolation=cv2.INTER_AREA)
        return TextImage(mask, W, H, big.baseline / factor, int(round(big.pad / factor)))
    return _render_text(text, size, family, weight, align, line_spacing, max_width)


def _render_text(text: str, size: float, family: str, weight: str, align: str, line_spacing: float,
                 max_width: float) -> TextImage:
    lines = parse_markup(text)
    if max_width and max_width > 0:
        lines = _wrap(lines, family, weight, size, max_width)
    base_font = get_font(font_path(family, weight), int(round(size)))
    ascent, descent = base_font.getmetrics()
    lh = size * line_spacing
    pad = int(np.ceil(size * 0.25)) + 2
    widths = [sum(_run_width(r, family, weight, size) for r in line) for line in lines]
    W = int(np.ceil(max(widths + [1.0]))) + 2 * pad
    H = int(np.ceil(ascent + descent + lh * (len(lines) - 1))) + 2 * pad
    im = Image.new("L", (W, H), 0)
    draw = ImageDraw.Draw(im)
    for li, line in enumerate(lines):
        base_y = pad + ascent + li * lh
        x = pad + {"center": (W - 2 * pad - widths[li]) / 2, "right": W - 2 * pad - widths[li]}.get(align, 0.0)
        for r in line:
            main, fb, s = _run_font(r, family, weight, size)
            dy = {-1: 0.22 * size, 1: -0.38 * size}.get(r.level, 0.0)
            for t, p in _chunks(r.text, main, fb):
                f = get_font(p, s)
                draw.text((x, base_y + dy), t, font=f, fill=255, anchor="ls")
                x += f.getlength(t)
    mask = np.asarray(im, np.float32) / 255.0
    return TextImage(mask, W, H, pad + ascent, pad)


_MATH_LOCK = threading.Lock()
_MATH_CACHE: dict[tuple, TextImage] = {}
MATH_ERRORS: dict[tuple, str] = {}


def render_math(tex: str, size: float, fontset: str = "dejavusans") -> TextImage | None:
    """Render a LaTeX-style formula with matplotlib's mathtext (no LaTeX install needed).

    Returns None if matplotlib is missing or the formula cannot be parsed (the reason is
    kept in ``MATH_ERRORS``). Only successful renders are cached; matplotlib is not
    thread-safe, so calls are serialised.
    """
    key = (tex, round(float(size), 2), fontset)
    hit = _MATH_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        from matplotlib import mathtext
        from matplotlib.font_manager import FontProperties
    except Exception:
        MATH_ERRORS[key] = "matplotlib is not installed (pip install matplotlib)"
        return None
    src = tex.strip()
    if not (src.startswith("$") and src.endswith("$")):
        src = f"${src}$"
    buf = io.BytesIO()
    dpi = 100
    try:
        with _MATH_LOCK:
            prop = FontProperties(size=max(1.0, size) * 72.0 / dpi, math_fontfamily=fontset)
            mathtext.math_to_image(src, buf, prop=prop, dpi=dpi, format="png", color="black")
    except Exception as exc:
        MATH_ERRORS[key] = str(exc).strip().splitlines()[-1] if str(exc).strip() else type(exc).__name__
        return None
    buf.seek(0)
    rgba = np.asarray(Image.open(buf).convert("RGBA"), np.float32) / 255.0
    # black ink on an (opaque or transparent) white page -> coverage
    gray = rgba[..., :3].mean(axis=2) * rgba[..., 3] + (1 - rgba[..., 3])
    pad = 4
    mask = np.pad(np.clip(1.0 - gray, 0, 1), pad)
    h, w = mask.shape
    out = TextImage(mask, w, h, h - pad, pad)
    if len(_MATH_CACHE) > 512:
        _MATH_CACHE.clear()
    _MATH_CACHE[key] = out
    return out
