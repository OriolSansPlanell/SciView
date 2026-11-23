"""PowerPoint export: one slide per scene with the scene's clip filling the slide.

The clip starts by itself when the slide is shown; the scene's notes, what its voice clips say and its
captions become the speaker notes. Needs python-pptx (``pip install "sciview[pptx]"``).
"""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

_P = "http://schemas.openxmlformats.org/presentationml/2006/main"

_AUTOPLAY = """<p:timing xmlns:p="{p}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>
<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/>
</p:cond></p:stCondLst><p:childTnLst><p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>
<p:childTnLst><p:par><p:cTn id="5" presetID="1" presetClass="mediacall" presetSubtype="0" fill="hold" nodeType="afterEffect">
<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:cmd type="call" cmd="playFrom(0.0)"><p:cBhvr>
<p:cTn id="6" dur="{ms}" fill="hold"/><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:cmd></p:childTnLst>
</p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn>
<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>
<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>
<p:video><p:cMediaNode vol="80000"><p:cTn id="7" fill="hold" display="0"><p:stCondLst><p:cond delay="indefinite"/>
</p:stCondLst></p:cTn><p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cMediaNode></p:video></p:childTnLst></p:cTn>
</p:par></p:tnLst></p:timing>"""


def scene_notes(project: Project, scene) -> str:
    """Speaker notes for a scene: its notes, then what its voice clips say, then its captions."""
    from .engine.text import plain_text
    parts = []
    if scene.notes.strip():
        parts.append(scene.notes.strip())
    scripts = [o.props.get("script", "").strip() for o in project.objects
               if o.scene == scene.id and o.TYPE == "voice" and o.props.get("script", "").strip()]
    if scripts:
        parts.append("\n".join(scripts))
    caps = [plain_text(o.get("text")).strip() for o in sorted(project.objects, key=lambda o: o.start)
            if o.scene == scene.id and o.TYPE == "caption" and o.visible and o.get("text")]
    if caps and not scripts:
        parts.append("\n".join(caps))
    return "\n\n".join(parts)


def _autoplay(slide, spid: int, seconds: float) -> None:
    old = slide._element.find(f"{{{_P}}}timing")
    from lxml import etree  # comes with python-pptx
    new = etree.fromstring(_AUTOPLAY.format(p=_P, ms=int(round(seconds * 1000)), spid=spid))
    if old is not None:
        slide._element.replace(old, new)
    else:
        slide._element.append(new)


def export_pptx(project: Project, output: str | os.PathLike, *, scale: float = 1.0, crf: int = 20,
                fps: float | None = None, workers: int | None = None, autoplay: bool = True,
                progress=None, cancel=None) -> Path:
    """Write a .pptx with one slide per scene. Returns its path."""
    from PIL import Image

    from .export import ExportError, export
    try:
        from pptx import Presentation
        from pptx.util import Emu
    except ImportError:
        raise ExportError('PowerPoint export needs python-pptx: pip install "sciview[pptx]"') from None
    out = Path(output)
    if out.suffix.lower() != ".pptx":
        out = out.with_suffix(".pptx")
    out.parent.mkdir(parents=True, exist_ok=True)
    W, H = project.size
    prs = Presentation()
    prs.slide_width = Emu(12192000)                       # 13.33 inches, PowerPoint's widescreen
    prs.slide_height = Emu(int(round(12192000 * H / W)))
    fps = float(fps or project.fps)
    frames = [max(1, int(round(sc.duration * fps))) for sc in project.scenes]
    total, done = sum(frames), 0

    with tempfile.TemporaryDirectory(prefix="sciview-pptx-") as tmp:
        for i, sc in enumerate(project.scenes):
            def step(n, _tot, _eta, base=done):
                if progress is not None:
                    progress(base + n, total, 0.0)
            clip = export(project, Path(tmp) / f"scene{i + 1}.mp4", scene=sc.id, scale=scale, crf=crf, fps=fps,
                          workers=workers, subtitles="off", chapters=False, progress=step, cancel=cancel)
            done += frames[i]
            poster = io.BytesIO()
            Image.fromarray(project.renderer().frame(sc.duration * 0.5, min(scale, 1.0), scene=sc.id)).save(
                poster, "PNG")
            poster.seek(0)
            slide = prs.slides.add_slide(prs.slide_layouts[6])
            slide._element.cSld.set("name", sc.name)
            movie = slide.shapes.add_movie(str(clip), 0, 0, prs.slide_width, prs.slide_height,
                                           poster_frame_image=poster, mime_type="video/mp4")
            movie.name = sc.name
            if autoplay:
                _autoplay(slide, movie.shape_id, sc.duration)
            notes = scene_notes(project, sc)
            if notes:
                slide.notes_slide.notes_text_frame.text = notes
        prs.core_properties.title = project.settings.get("title") or ""
        prs.core_properties.author = project.settings.get("author") or ""
        prs.save(str(out))
    return out


__all__ = ["export_pptx", "scene_notes"]
