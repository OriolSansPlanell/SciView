"""SciView in Jupyter notebooks.

``film.preview()`` shows the film as frames with a play button and a scrubber, made of plain HTML, so it
works in JupyterLab, classic notebooks, VS Code and Colab, needs no widget extension and stays in the saved
notebook. ``sciview.jupyter.edit(film)`` opens the full editor inside the notebook (on the computer that
runs the kernel). After ``%load_ext sciview``:

.. code-block:: text

    %sciview preview film --fps 12 --scale 0.3
    %sciview still film 4.5
    %sciview edit film
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import itertools
import json
import os
import shlex
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

_ids = itertools.count(1)
MAX_FRAMES = 600


class Preview:
    """Frames of a film with a play button and a scrubber, shown by Jupyter through ``_repr_html_``."""

    def __init__(self, project: Project, fps: float = 10.0, scale: float = 0.25, start: float = 0.0,
                 end: float | None = None, scene=None, quality: int = 80):
        from PIL import Image
        self.project = project
        length = project.get_scene(scene).duration if scene is not None else project.duration
        end = length if end is None else min(float(end), length)
        start = max(0.0, min(float(start), end))
        n = max(1, min(MAX_FRAMES, int(round((end - start) * fps)) + 1))
        self.times = [start + (end - start) * i / max(1, n - 1) for i in range(n)] if n > 1 else [start]
        self.fps = (n - 1) / (end - start) if n > 1 and end > start else float(fps)
        r = project.renderer()
        sid = project.get_scene(scene).id if scene is not None else None
        self.frames: list[str] = []
        for t in self.times:
            buf = io.BytesIO()
            Image.fromarray(r.frame(t, scale, scene=sid)).save(buf, "JPEG", quality=quality)
            self.frames.append(base64.b64encode(buf.getvalue()).decode("ascii"))
        self.chapters = [] if scene is not None else [(a, name) for a, _b, name in project.chapters()
                                                         if start <= a <= end]

    def _repr_html_(self) -> str:
        uid = f"sciview-preview-{next(_ids)}"
        data = json.dumps({"frames": self.frames, "times": self.times, "fps": self.fps, "chapters": self.chapters})
        title = html.escape(self.project.settings.get("title") or "SciView film")
        return f"""<div id="{uid}" style="font:13px system-ui,sans-serif;max-width:960px">
<img alt="{title}" style="width:100%;display:block;background:#000;border-radius:4px">
<div style="display:flex;gap:8px;align-items:center;margin-top:6px">
<button type="button" class="play" aria-label="Play" style="min-width:64px">Play</button>
<input type="range" min="0" max="{len(self.frames) - 1}" value="0" step="1" aria-label="Time" style="flex:1">
<span class="t" style="font-variant-numeric:tabular-nums;min-width:64px;text-align:right"></span></div>
<div class="ch" style="display:flex;gap:6px;flex-wrap:wrap;margin-top:4px"></div></div>
<script>(function(){{const d={data};const root=document.getElementById("{uid}");
const img=root.querySelector("img"),range=root.querySelector("input"),lab=root.querySelector(".t"),
btn=root.querySelector(".play");let timer=null;
function show(i){{i=Math.max(0,Math.min(d.frames.length-1,i));range.value=i;
img.src="data:image/jpeg;base64,"+d.frames[i];lab.textContent=d.times[i].toFixed(2)+" s";}}
function stop(){{clearInterval(timer);timer=null;btn.textContent="Play";}}
btn.onclick=function(){{if(timer){{stop();return;}}if(+range.value>=d.frames.length-1)show(0);
btn.textContent="Pause";timer=setInterval(function(){{const i=+range.value+1;
if(i>=d.frames.length){{stop();return;}}show(i);}},1000/d.fps);}};
range.oninput=function(){{stop();show(+range.value);}};
d.chapters.forEach(function(c){{const b=document.createElement("button");b.type="button";b.textContent=c[1];
b.onclick=function(){{stop();let i=0;while(i<d.times.length-1&&d.times[i]<c[0]-1e-6)i++;show(i);}};
root.querySelector(".ch").appendChild(b);}});show(0);}})();</script>"""

    def __len__(self) -> int:
        return len(self.frames)


def preview(project: Project, fps: float = 10.0, scale: float = 0.25, start: float = 0.0,
            end: float | None = None, scene=None) -> Preview:
    """A scrubbable preview for a notebook: ``fps`` frames per second of film at ``scale`` of full size
    (0.25 = 480 x 270), at most 600 frames. Draft first; every frame is stored in the notebook."""
    return Preview(project, fps=fps, scale=scale, start=start, end=end, scene=scene)


class Still:
    """One frame, shown by Jupyter as a PNG."""

    def __init__(self, project: Project, t: float, scale: float = 0.5):
        from PIL import Image
        buf = io.BytesIO()
        Image.fromarray(project.frame(t, scale)).save(buf, "PNG")
        self.png = buf.getvalue()

    def _repr_png_(self) -> bytes:
        return self.png


class InlineEditor:
    """The SciView editor running for this kernel, shown in the notebook as a frame.

    ``.film`` is the film as it is in the editor now (the editor works on its own copy: assign it back with
    ``film = ed.film``); ``.stop()`` ends it. The editor is served on this computer only, so it shows when
    the notebook and the kernel run on the same machine (use an SSH tunnel for a remote kernel).
    """

    def __init__(self, project: Project, port: int = 0, height: int = 760):
        from .server import make_server
        project.path = project.path or project.base_dir / "untitled.sciview.json"
        self.srv = make_server(project, project.base_dir, port=port)
        self.srv.session.start_background(autosave_interval=30, prefetch=True)
        self.thread = threading.Thread(target=self.srv.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        self.thread.start()
        self.port = self.srv.server_address[1]
        self.url = f"http://localhost:{self.port}/"
        self.height = int(height)

    @property
    def film(self) -> Project:
        return self.srv.session.project

    def stop(self) -> None:
        self.srv.session.stop.set()
        self.srv.shutdown()
        self.srv.server_close()

    def _repr_html_(self) -> str:
        return (f'<iframe src="{self.url}" title="SciView editor" style="width:100%;height:{self.height}px;'
                f'border:1px solid #888;border-radius:4px" allow="microphone; clipboard-read; clipboard-write">'
                f'</iframe><div style="font:12px system-ui,sans-serif;opacity:.7">SciView editor at '
                f'<a href="{self.url}" target="_blank">{self.url}</a>: take the result back with '
                f'<code>film = ed.film</code>; <code>ed.stop()</code> ends it.</div>')


def edit(project: Project, port: int = 0, height: int = 760) -> InlineEditor:
    """Open the editor inside the notebook: ``ed = sciview.jupyter.edit(film)``."""
    return InlineEditor(project, port=port, height=height)


# ---------------------------------------------------------------------------------------------- %sciview
def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="%sciview", add_help=False)
    ap.add_argument("action", choices=["preview", "still", "edit"])
    ap.add_argument("film", help="a variable holding a film, or a .sciview.json path")
    ap.add_argument("time", nargs="?", type=float, default=None)
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--scale", type=float, default=None)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--scene", default=None)
    ap.add_argument("--port", type=int, default=0)
    return ap


def sciview_magic(line: str, namespace: dict):
    """What ``%sciview ...`` runs; returns the object Jupyter shows."""
    from .model.project import Project
    # posix=False keeps Windows paths' backslashes; the quotes it leaves are taken off here
    words = [w[1:-1] if len(w) > 1 and w[0] == w[-1] and w[0] in "\"'" else w
             for w in shlex.split(line, posix=os.name != "nt")]
    try:
        a = _parser().parse_args(words)
    except SystemExit:
        raise ValueError("usage: %sciview preview|still|edit FILM [TIME] [--fps N] [--scale S] [--start A] "
                         "[--end B] [--scene NAME]") from None
    film = namespace.get(a.film)
    if film is None:
        if a.film.endswith(".json"):
            film = Project.load(a.film)
        else:
            raise NameError(f"no variable called {a.film!r} (give a film, or the path of a .sciview.json)")
    if not isinstance(film, Project):
        raise TypeError(f"{a.film} is a {type(film).__name__}, not a SciView film")
    if a.action == "preview":
        return preview(film, fps=a.fps, scale=a.scale or 0.25, start=a.start, end=a.end, scene=a.scene)
    if a.action == "still":
        return Still(film, film.duration / 2 if a.time is None else a.time, a.scale or 0.5)
    ed = edit(film, port=a.port)
    namespace["_sciview_editor"] = ed
    return ed


def load_ipython_extension(ipython) -> None:
    def magic(line):
        return sciview_magic(line, ipython.user_ns)
    magic.__doc__ = sciview_magic.__doc__ + "\n\n" + (__doc__ or "")
    ipython.register_magic_function(magic, magic_kind="line", magic_name="sciview")
