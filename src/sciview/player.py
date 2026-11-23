"""A web page that plays the film: the video, its captions, a chapter list and the project to download.

Everything is in the one HTML file by default (the video as base64), so it can be mailed, put on a
group page or added to supplementary material without anything beside it.
"""
from __future__ import annotations

import base64
import html
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

EMBED_LIMIT = 200 * 1024 * 1024        # larger videos are written next to the page
ASSET_LIMIT = 50 * 1024 * 1024          # larger project bundles are left out of the page


def project_bundle(project: Project) -> bytes:
    """The project file and the files it uses, as a zip that `sciview edit` can open once unpacked."""
    from .model.project import iter_assets
    buf = io.BytesIO()
    name = (project.path.name if project.path else "film.sciview.json")
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, json.dumps(project.to_json(), indent=2, ensure_ascii=False))
        seen = set()
        for rel in iter_assets(project):
            p = Path(rel) if Path(rel).is_absolute() else project.base_dir / rel
            files = sorted(p.parent.glob(p.name)) if any(c in rel for c in "*?[") else [p]
            for f in files:
                if f.is_file() and f not in seen:
                    seen.add(f)
                    try:
                        arc = f.relative_to(project.base_dir).as_posix()
                    except ValueError:
                        arc = f"assets/{f.name}"
                    z.write(f, arc)
    return buf.getvalue()


def export_html(project: Project, output: str | os.PathLike, *, scale: float = 1.0, crf: int = 20,
                fps: float | None = None, workers: int | None = None, embed: bool | None = None,
                progress=None, cancel=None) -> Path:
    """Render the film and write a self-contained web page with a player. Returns the page's path."""
    from PIL import Image

    from .export import export, srt_text
    out = Path(output)
    if out.suffix.lower() != ".html":
        out = out.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sciview-html-") as tmp:
        # captions as a track the viewer can switch off, not drawn into the picture
        video = export(project, Path(tmp) / "film.mp4", scale=scale, crf=crf, fps=fps, workers=workers,
                       subtitles="soft", progress=progress, cancel=cancel)
        poster_t = min(project.duration * 0.25, max(project.duration - 0.1, 0.0))
        thumb = io.BytesIO()
        Image.fromarray(project.renderer().frame(poster_t, min(scale, 0.5))).save(thumb, "JPEG", quality=82)
        data = video.read_bytes()
        if embed is None:
            embed = len(data) <= EMBED_LIMIT
        if embed:
            video_src = None
        else:
            side = out.with_suffix(".mp4")
            side.write_bytes(data)
            video_src = side.name
    bundle = project_bundle(project)
    page = _page(project, data if embed else None, video_src, thumb.getvalue(),
                 srt_text(project.captions(), vtt=True), project.chapters(),
                 bundle if len(bundle) <= ASSET_LIMIT else None)
    out.write_text(page, encoding="utf-8")
    return out


def _fmt(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m}:{s:02d}"


def _page(project: Project, video: bytes | None, video_src: str | None, poster: bytes, vtt: str,
          chapters: list, bundle: bytes | None) -> str:
    title = project.settings.get("title") or "Film"
    author = project.settings.get("author") or ""
    stem = (project.path.name.split(".")[0] if project.path else "film")
    chap_items = "".join(
        f'<li><button type="button" data-t="{a:.3f}"><span class="t">{_fmt(a)}</span>'
        f'<span class="n">{html.escape(name)}</span></button></li>' for a, _b, name in chapters)
    has_chapters = len(chapters) > 1
    payload = {
        "video": base64.b64encode(video).decode() if video is not None else None,
        "vtt": vtt if vtt.strip() != "WEBVTT" else None,
        "bundle": base64.b64encode(bundle).decode() if bundle is not None else None,
        "stem": stem,
    }
    poster_uri = "data:image/jpeg;base64," + base64.b64encode(poster).decode()
    src_attr = f' src="{html.escape(video_src)}"' if video_src else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="generator" content="SciView">
<style>
  :root {{ --ink: #e8eef8; --muted: #8da0bd; --deep: #050b16; --panel: #0d1726; --line: #1f2d44; --accent: #6cb4fc; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--deep); color: var(--ink); font: 16px/1.5 system-ui, -apple-system, "Segoe UI",
         Roboto, sans-serif; }}
  main {{ max-width: 1200px; margin: 0 auto; padding: 32px 20px 48px; }}
  header h1 {{ font-size: 1.6rem; line-height: 1.25; margin: 0 0 4px; font-weight: 650; }}
  header p {{ margin: 0 0 20px; color: var(--muted); }}
  .stage {{ display: grid; grid-template-columns: {"minmax(0, 1fr) 260px" if has_chapters else "minmax(0, 1fr)"};
           gap: 20px; align-items: start; }}
  video {{ width: 100%; display: block; background: #000; border-radius: 6px; }}
  nav h2 {{ font-size: .95rem; margin: 0 0 8px; color: var(--muted); font-weight: 600; }}
  nav ol {{ list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--line); }}
  nav li {{ border-bottom: 1px solid var(--line); }}
  nav button {{ all: unset; box-sizing: border-box; width: 100%; display: flex; gap: 12px; padding: 9px 6px;
               cursor: pointer; border-radius: 4px; }}
  nav button:hover, nav button[aria-current="true"] {{ background: var(--panel); }}
  nav button[aria-current="true"] .n {{ color: var(--accent); }}
  nav button:focus-visible, .links a:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
  .t {{ font-variant-numeric: tabular-nums; color: var(--muted); min-width: 3.2em; }}
  .links {{ display: flex; flex-wrap: wrap; gap: 18px; margin-top: 18px; font-size: .95rem; }}
  .links a {{ color: var(--accent); text-decoration: none; }}
  .links a:hover {{ text-decoration: underline; }}
  footer {{ margin-top: 28px; color: var(--muted); font-size: .85rem; }}
  @media (max-width: 800px) {{ .stage {{ grid-template-columns: minmax(0, 1fr); }} }}
</style>
</head>
<body>
<main>
  <header>
    <h1>{html.escape(title)}</h1>
    {f"<p>{html.escape(author)}</p>" if author else "<p></p>"}
  </header>
  <div class="stage">
    <video id="film" controls playsinline preload="metadata" poster="{poster_uri}"{src_attr}></video>
    {f'<nav aria-label="Chapters"><h2>Chapters</h2><ol id="chapters">{chap_items}</ol></nav>' if has_chapters else ""}
  </div>
  <div class="links">
    <a id="dlVideo" href="#" download="{html.escape(stem)}.mp4">Download the video</a>
    {'<a id="dlProject" href="#" download="' + html.escape(stem) + '-project.zip">Download the SciView project</a>' if bundle else ""}
  </div>
  <footer>Made with SciView. Open the project with <code>sciview edit</code> after unpacking it.</footer>
</main>
<script id="payload" type="application/json">{json.dumps(payload)}</script>
<script>
(() => {{
  const data = JSON.parse(document.getElementById('payload').textContent);
  const v = document.getElementById('film');
  const blobUrl = (b64, type) => {{
    const bin = atob(b64); const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([bytes], {{ type }}));
  }};
  if (data.video) {{ const u = blobUrl(data.video, 'video/mp4'); v.src = u; document.getElementById('dlVideo').href = u; }}
  else {{ document.getElementById('dlVideo').href = v.getAttribute('src'); }}
  if (data.vtt) {{
    const tr = document.createElement('track');
    Object.assign(tr, {{ kind: 'captions', label: 'Captions', srclang: 'en', default: true }});
    tr.src = URL.createObjectURL(new Blob([data.vtt], {{ type: 'text/vtt' }}));
    v.append(tr);
  }}
  const proj = document.getElementById('dlProject');
  if (proj && data.bundle) proj.href = blobUrl(data.bundle, 'application/zip');
  const items = [...document.querySelectorAll('#chapters button')];
  items.forEach((b) => b.addEventListener('click', () => {{ v.currentTime = Number(b.dataset.t) + 0.01; v.play(); }}));
  v.addEventListener('timeupdate', () => {{
    let cur = null;
    for (const b of items) if (Number(b.dataset.t) <= v.currentTime + 0.05) cur = b;
    items.forEach((b) => b.setAttribute('aria-current', b === cur ? 'true' : 'false'));
  }});
}})();
</script>
</body>
</html>
"""
