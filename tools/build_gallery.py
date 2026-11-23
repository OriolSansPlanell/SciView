"""Render every template for the documentation site's gallery: an MP4, a poster frame and the project as a zip.

    python tools/build_gallery.py docs/gallery          # run by the docs workflow before mkdocs build

The videos are not kept in git; the workflow renders them each time the site is published.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image

from sciview.export import export
from sciview.player import project_bundle
from sciview.server import instantiate_template, list_templates


def main(out_dir: str = "docs/gallery", scale: float = 0.5) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for t in list_templates():
        if t.get("plugin"):
            continue
        with tempfile.TemporaryDirectory() as tmp:
            film = instantiate_template(t["name"], Path(tmp))
            film.path = Path(tmp) / f"{t['name']}.sciview.json"
            film.save()
            video = export(film, out / f"{t['name']}.mp4", scale=scale, subtitles="soft", crf=23)
            thumb = t.get("thumb_time") or film.duration * 0.6
            Image.fromarray(film.frame(float(thumb), scale)).save(out / f"{t['name']}.jpg", quality=85)
            (out / f"{t['name']}.zip").write_bytes(project_bundle(film))
            print(f"{t['name']}: {video.stat().st_size / 1e6:.1f} MB", file=sys.stderr)
    for f in list(out.glob("*.srt")) + list(out.glob("*.vtt")):
        f.unlink()


if __name__ == "__main__":
    main(*sys.argv[1:2])
