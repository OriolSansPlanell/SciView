"""Render the reference frames that tests/test_visual.py compares against.

    python tools/update_golden_frames.py        # after a deliberate change to how things look

Check the new pictures (git diff shows them side by side on GitHub) before committing them.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "tests" / "golden" / "frames"
SCALE = 0.2


def cases():
    """(name, template, time) for two moments of every built-in template."""
    from sciview.server import list_templates
    for t in list_templates():
        if t.get("plugin"):
            continue
        for k, when in enumerate((t.get("thumb_time") or t["duration"] * 0.6, t["duration"] * 0.3)):
            yield f"{t['name']}_{k}", t["name"], round(float(when), 2)


def render(template: str, t: float):
    from sciview.server import instantiate_template
    with tempfile.TemporaryDirectory() as tmp:
        film = instantiate_template(template, Path(tmp))
        return film.frame(t, SCALE)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, template, t in cases():
        Image.fromarray(render(template, t)).save(OUT / f"{name}.png", optimize=True)
        print(f"wrote {name}.png ({template} at {t} s)")


if __name__ == "__main__":
    main()
