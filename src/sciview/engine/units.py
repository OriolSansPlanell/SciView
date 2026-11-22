"""Numbers with SI prefixes and lengths for scale bars."""
from __future__ import annotations

import math
import re

PREFIXES = [(-24, "y"), (-21, "z"), (-18, "a"), (-15, "f"), (-12, "p"), (-9, "n"), (-6, "µ"), (-3, "m"),
            (0, ""), (3, "k"), (6, "M"), (9, "G"), (12, "T"), (15, "P"), (18, "E")]
_PREFIX_EXP = {p: e for e, p in PREFIXES}
_PREFIX_EXP["u"] = -6
_PREFIX_EXP.pop("", None)
_NOT_PREFIXED = {"mol", "min", "Pa", "Gy", "Torr", "mmHg", "ppm", "Ma"}


def si(value: float, unit: str = "", digits: int = 3, space: bool = True) -> str:
    """``0.00125, 'm'`` → ``'1.25 mm'``; ``2.2e9, 'Hz'`` → ``'2.2 GHz'``. ``digits`` significant digits."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return f"{v} {unit}".strip()
    sep = " " if space and unit else ""
    if v == 0:
        return f"0{sep}{unit}"
    e3 = int(math.floor(math.log10(abs(v)) / 3)) * 3
    e3 = max(-24, min(18, e3))
    m = v / 10 ** e3
    # rounding can carry to the next prefix: 999.96 → 1000
    d = max(0, digits - 1 - int(math.floor(math.log10(abs(m)))))
    if abs(float(f"{m:.{d}f}")) >= 1000 and e3 < 18:
        e3 += 3
        m = v / 10 ** e3
        d = max(0, digits - 1 - int(math.floor(math.log10(abs(m)))))
    txt = f"{m:.{d}f}"
    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")
    return f"{txt}{sep}{dict(PREFIXES)[e3]}{unit}"


def parse_si(text: str) -> tuple[float, str]:
    """``'2.5 µm'`` → ``(2.5e-6, 'm')``; ``'300 nm'`` → ``(3e-7, 'm')``. A bare number has no unit."""
    m = re.fullmatch(r"\s*([-+0-9.eE]+)\s*([a-zA-Zµ°Å%]*)\s*", str(text))
    if not m:
        raise ValueError(f"cannot read {text!r} as a number with a unit")
    num, rest = float(m.group(1)), m.group(2)
    if len(rest) >= 2 and rest[0] in _PREFIX_EXP and rest not in _NOT_PREFIXED:
        return num * 10 ** _PREFIX_EXP[rest[0]], rest[1:]
    return num, rest


def nice_length(target: float) -> float:
    """The 1, 2 or 5 × 10ⁿ closest below ``target`` (scale bar lengths)."""
    if target <= 0 or not math.isfinite(target):
        return 1.0
    mag = 10 ** math.floor(math.log10(target))
    for m in (5, 2, 1):
        if m * mag <= target * (1 + 1e-9):
            return m * mag
    return mag


def format_number(value: float, spec: str) -> str:
    """``format()`` plus the SI specs ``si``, ``.2si`` and ``si:m`` (digits, then unit)."""
    m = re.fullmatch(r"(?:\.(\d+))?si(?::(.*))?", spec or "")
    if m:
        return si(value, m.group(2) or "", int(m.group(1) or 3))
    return format(value, spec or "g")
