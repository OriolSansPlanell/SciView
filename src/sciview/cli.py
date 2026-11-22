"""Command line: ``sciview edit | render | still | new | check | templates | subtitles | mcp | info``."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__

_last = [0.0]


def _bar(done: int, total: int, eta: float) -> None:
    now = time.time()
    if done < total and now - _last[0] < 0.25:
        return
    _last[0] = now
    w = 32
    f = done / max(total, 1)
    m, s = divmod(int(eta), 60)
    sys.stderr.write(f"\r  [{'#' * int(f * w):<{w}}] {done}/{total} frames  {f * 100:5.1f}%  eta {m:d}:{s:02d} ")
    sys.stderr.flush()


def cmd_edit(a) -> int:
    from .server import serve
    serve(a.project, host=a.host, port=a.port, open_browser=not a.no_browser, template=a.template)
    return 0


def cmd_render(a) -> int:
    from .export import export
    from .model.project import Project
    proj = Project.load(a.project)
    for issue in proj.validate():
        print(f"  note: {issue}", file=sys.stderr)
    out = a.output or str(Path(a.project).name.split(".")[0] + ".mp4")
    print(f"Rendering {a.project} -> {out}", file=sys.stderr)
    t0 = time.time()
    path = export(proj, out, fps=a.fps, scale=a.scale, crf=a.crf, preset=a.preset, start=a.start, end=a.end,
                  workers=a.workers, audio=not a.no_audio, subtitles=a.subtitles,
                  progress=None if a.quiet else _bar)
    if not a.quiet:
        sys.stderr.write("\n")
    print(f"Wrote {path} in {time.time() - t0:.1f} s", file=sys.stderr)
    return 0


def cmd_still(a) -> int:
    from .model.project import Project
    proj = Project.load(a.project)
    times = a.time or [proj.duration / 2]
    stem = Path(a.project).name.split(".")[0]
    for t in times:
        out = a.output if (a.output and len(times) == 1) else f"{stem}_{t:06.2f}s.png"
        proj.still(t, out, a.scale)
        print(f"Wrote {out}", file=sys.stderr)
    return 0


def cmd_new(a) -> int:
    from .model.project import Project
    from .server import instantiate_template, list_templates
    path = Path(a.path)
    if not path.name.endswith(".json"):
        path = path.with_name(path.name + ".sciview.json")
    if path.exists() and not a.force:
        print(f"{path} exists (use --force to overwrite)", file=sys.stderr)
        return 1
    names = [t["name"] for t in list_templates()]
    if a.template != "blank" and a.template not in names:
        print(f"unknown template {a.template!r}. Templates: blank, {', '.join(names)}", file=sys.stderr)
        return 1
    base = path.resolve().parent
    proj = instantiate_template(a.template, base) if a.template != "blank" else Project()
    proj.save(path)
    print(f"Created {path}. Open it with: sciview edit {path}", file=sys.stderr)
    return 0


def cmd_templates(a) -> int:
    from .server import list_templates
    print(f"{'blank':<16} An empty film")
    for t in list_templates():
        print(f"{t['name']:<16} {t['title']}: {t['description']}")
    return 0


def cmd_check(a) -> int:
    from .model.project import Project
    proj = Project.load(a.project)
    issues = proj.validate()
    print(proj)
    for i in issues:
        print(f"  - {i}")
    if not issues:
        print("  no problems found")
    return 1 if issues and a.strict else 0


def cmd_subtitles(a) -> int:
    from .model.project import Project
    proj = Project.load(a.project)
    out = a.output or str(Path(a.project).name.split(".")[0] + ".srt")
    Path(out).write_text(proj.captions_srt(), encoding="utf-8")
    print(f"Wrote {out} ({len(proj.captions())} captions)", file=sys.stderr)
    return 0


def cmd_mcp(a) -> int:
    from .agent.mcp import EditorBackend, FileBackend, serve_stdio
    scope = {}
    if a.time:
        scope["time"] = [float(a.time[0]), float(a.time[1])]
    if a.ids:
        scope["ids"] = [x.strip() for x in a.ids.split(",") if x.strip()]
    if a.editor:
        backend = EditorBackend(a.editor, scope)
    elif a.project:
        backend = FileBackend(a.project, scope, autosave=not a.no_save)
    else:
        print("error: give a project file, or --editor URL for a running editor", file=sys.stderr)
        return 2
    print(f"SciView {__version__} MCP server ready ({'editor ' + a.editor if a.editor else a.project})", file=sys.stderr)
    serve_stdio(backend)
    return 0


def cmd_info(a) -> int:
    import platform

    import cv2
    import numpy
    import PIL

    from .export import default_workers, find_ffmpeg
    from .model import REGISTRY
    try:
        ff = find_ffmpeg()
    except Exception as exc:
        ff = f"missing ({exc})"
    try:
        import matplotlib
        mpl = matplotlib.__version__
    except Exception:
        mpl = "not installed (Equation objects need it)"
    print(f"SciView {__version__}\nPython {platform.python_version()} on {platform.platform()}")
    print(f"numpy {numpy.__version__}, opencv {cv2.__version__}, pillow {PIL.__version__}, matplotlib {mpl}")
    print(f"ffmpeg: {ff}\nrender workers: {default_workers()}")
    print(f"object types ({len(REGISTRY)}): {', '.join(sorted(REGISTRY))}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sciview", description="Make scientific explainer videos.")
    p.add_argument("--version", action="version", version=f"sciview {__version__}")
    sub = p.add_subparsers(dest="cmd")

    e = sub.add_parser("edit", help="open the editor in your browser")
    e.add_argument("project", nargs="?", help="project file to open or create")
    e.add_argument("--template", help="start a new project from a template")
    e.add_argument("--port", type=int, default=8765)
    e.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 to reach it from another machine (careful)")
    e.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    e.set_defaults(func=cmd_edit)

    r = sub.add_parser("render", help="render a project to a video, GIF or PNG frames")
    r.add_argument("project")
    r.add_argument("-o", "--output", help="output file (.mp4 .webm .mov .gif) or folder for PNG frames")
    r.add_argument("--scale", type=float, default=1.0, help="resolution factor (0.5 = half size, 2 = 4K)")
    r.add_argument("--fps", type=float)
    r.add_argument("--crf", type=int, default=18, help="quality, lower is sharper (default 18)")
    r.add_argument("--preset", default="medium", help="x264 preset: veryfast ... slow")
    r.add_argument("--start", type=float, help="first second to render")
    r.add_argument("--end", type=float, help="last second to render")
    r.add_argument("--workers", type=int, help="parallel render processes (default: cores - 1)")
    r.add_argument("--subtitles", action="store_true", help="also write captions as .srt")
    r.add_argument("--no-audio", action="store_true")
    r.add_argument("-q", "--quiet", action="store_true")
    r.set_defaults(func=cmd_render)

    s = sub.add_parser("still", help="save single frames as PNG")
    s.add_argument("project")
    s.add_argument("-t", "--time", type=float, nargs="*", help="time(s) in seconds")
    s.add_argument("-o", "--output")
    s.add_argument("--scale", type=float, default=1.0, help="2 gives a 3840 px wide image for posters")
    s.set_defaults(func=cmd_still)

    n = sub.add_parser("new", help="create a project file from a template")
    n.add_argument("path")
    n.add_argument("--template", default="blank")
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_new)

    t = sub.add_parser("templates", help="list templates")
    t.set_defaults(func=cmd_templates)

    c = sub.add_parser("check", help="look for problems in a project")
    c.add_argument("project")
    c.add_argument("--strict", action="store_true", help="exit with code 1 if there are problems")
    c.set_defaults(func=cmd_check)

    st = sub.add_parser("subtitles", help="export captions as an .srt subtitle file")
    st.add_argument("project")
    st.add_argument("-o", "--output")
    st.set_defaults(func=cmd_subtitles)

    m = sub.add_parser("mcp", help="let an AI assistant build the film (MCP server on stdin/stdout)")
    m.add_argument("project", nargs="?", help="project file to edit (saved after every change)")
    m.add_argument("--editor", help="drive a running editor instead, e.g. http://localhost:8765")
    m.add_argument("--time", type=float, nargs=2, metavar=("START", "END"), help="only change this time window")
    m.add_argument("--ids", help="only change these objects (comma-separated ids) and new ones")
    m.add_argument("--no-save", action="store_true", help="file mode: do not save after each change")
    m.set_defaults(func=cmd_mcp)

    i = sub.add_parser("info", help="versions, ffmpeg location and object types")
    i.set_defaults(func=cmd_info)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        args = parser.parse_args(["edit"] + (argv or []))
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
