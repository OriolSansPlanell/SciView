"""Command line: ``sciview edit | render | still | new | check | theme | templates | subtitles | schema | mcp |
plugin | join | info``."""
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
    from .export import TARGETS
    stem = Path(a.project).name.split(".")[0]
    ext = TARGETS[a.target]["ext"] if a.target else "mp4"
    piece = ""
    if a.part:
        from .export import parse_part
        i, n = parse_part(a.part)
        piece = f".part{i}of{n}"
    out = a.output or f"{stem}{'_' + a.target if a.target else ''}{piece}.{ext}"
    if a.theme:
        for note in proj.apply_theme(a.theme):
            print(f"  theme: {note}", file=sys.stderr)
    print(f"Rendering {a.project} -> {out}", file=sys.stderr)
    t0 = time.time()
    subs = a.subtitles if a.subtitles is not None else False
    path = export(proj, out, fps=a.fps, scale=a.scale, crf=a.crf, preset=a.preset, start=a.start, end=a.end,
                  workers=a.workers, audio=not a.no_audio, subtitles=subs, transparent=a.transparent,
                  target=a.target, chapters=not a.no_chapters, scene=a.scene, time=a.time, part=a.part,
                  progress=None if a.quiet else _bar)
    if not a.quiet:
        sys.stderr.write("\n")
    print(f"Wrote {path} in {time.time() - t0:.1f} s", file=sys.stderr)
    return 0


def cmd_join(a) -> int:
    from .export import join
    from .model.project import Project
    proj = Project.load(a.project)
    out = join(proj, a.parts, a.output, audio=not a.no_audio, chapters=not a.no_chapters,
               subtitles=a.subtitles if a.subtitles is not None else False, start=a.start, end=a.end,
               scene=a.scene)
    print(f"Wrote {out} from {len(a.parts)} pieces", file=sys.stderr)
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
    if a.frames:
        from . import checks
        issues += [i["message"] for i in checks.layout_issues(proj) + checks.contrast_issues(proj)]
    print(proj)
    for i in issues:
        print(f"  - {i}")
    if not issues:
        print("  no problems found" + ("" if a.frames else " (add --frames to also check contrast and layout)"))
    return 1 if issues and a.strict else 0


def cmd_theme(a) -> int:
    from . import theme
    from .model.project import Project
    if a.list or not a.project:
        for k, d in theme.builtin().items():
            print(f"{k:10s} {d.get('name', k)}: {d.get('description', '')}")
        return 0
    proj = Project.load(a.project)
    if a.save:
        print(f"Wrote {proj.save_theme(a.save, a.name or '')}", file=sys.stderr)
        return 0
    if not a.apply:
        print("give --apply THEME or --save FILE", file=sys.stderr)
        return 2
    for note in proj.apply_theme(a.apply, restyle=not a.keep_styles):
        print(f"  note: {note}", file=sys.stderr)
    proj.save()
    print(f"Applied {proj.settings.get('theme') or a.apply} to {a.project}", file=sys.stderr)
    return 0


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
    if a.scene:
        scope["scene"] = a.scene
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


def cmd_schema(a) -> int:
    import json

    from . import plugins, schema
    plugins.load()
    if a.validate:
        bad = 0
        for f in a.validate:
            try:
                data = json.loads(Path(f).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                print(f"{f}: cannot read: {exc}", file=sys.stderr)
                bad += 1
                continue
            errors = schema.validate(data, strict=a.strict)
            print(f"{f}: {'valid' if not errors else f'{len(errors)} problem(s)'}")
            for e in errors[:50]:
                print(f"  {e}")
            bad += bool(errors)
        return 1 if bad else 0
    text = schema.dumps(schema.json_schema(strict=a.strict))
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"Wrote {a.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


def cmd_plugin(a) -> int:
    from . import plugins
    if a.action == "new":
        from .scaffold import new_plugin
        root = new_plugin(a.name, a.folder)
        print(f"Wrote {root}. Install it with: pip install -e {root}")
        return 0
    print(plugins.describe())
    return 0 if all(r["ok"] for r in plugins.info()) else 1


def cmd_info(a) -> int:
    from .diagnostics import info_text, report
    if a.report:
        from .model.project import Project
        proj = Project.load(a.report)
        out = Path(a.output or "sciview-report.zip")
        out.write_bytes(report(proj, include_assets=a.assets))
        print(f"Wrote {out}: look through it, then attach it to an issue at "
              f"https://github.com/OriolSansPlanell/SciView/issues", file=sys.stderr)
        return 0
    print(info_text())
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
    r.add_argument("--scale", type=float, help="resolution factor (0.5 = half size, 2 = 4K); with --for, a factor "
                                                 "of the preset's size")
    r.add_argument("--fps", type=float)
    r.add_argument("--crf", type=int, default=None, help="quality, lower is sharper (default 18, or the preset's)")
    r.add_argument("--preset", default="medium", help="x264 preset: veryfast ... slow")
    r.add_argument("--start", type=float, help="first second to render")
    r.add_argument("--end", type=float, help="last second to render")
    r.add_argument("--workers", type=int, help="parallel render processes (default: cores - 1)")
    r.add_argument("--for", dest="target", choices=["slides", "conference", "poster", "square", "vertical", "overlay",
                                                     "web", "preview"],
                   help="preset: slides (1080p MP4), conference (4K), poster (4K still), square / vertical (social, "
                        "cropped), overlay (transparent ProRes), web (HTML page), preview (GIF)")
    r.add_argument("--subtitles", nargs="?", const="file", choices=["off", "file", "soft", "embed"],
                   help="captions: file (.srt/.vtt beside the video), soft (a track viewers can switch off, not "
                        "drawn), embed (drawn and as a track)")
    r.add_argument("--transparent", action="store_true", help="no background: ProRes 4444 .mov, .webm or PNG frames")
    r.add_argument("--scene", help="render one scene on its own (id or name)")
    r.add_argument("--time", type=float, help="for a still (.png output or --for poster): the moment to show")
    r.add_argument("--theme", help="apply a theme first (dark, light, contrast or a .sciview-theme.json)")
    r.add_argument("--no-chapters", action="store_true", help="no chapter markers from scenes")
    r.add_argument("--part", metavar="I/N", help="render only piece I of N (video alone), e.g. on several "
                                                "computers; put the pieces together with: sciview join")
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
    c.add_argument("--frames", action="store_true",
                   help="also look at frames: text that is hard to read, text that overlaps, objects outside the frame")
    c.set_defaults(func=cmd_check)

    th = sub.add_parser("theme", help="list, apply or save themes (palette, look, font, logo, styles)")
    th.add_argument("project", nargs="?")
    th.add_argument("--apply", help="dark, light, contrast or a .sciview-theme.json")
    th.add_argument("--save", help="write the project's look as a .sciview-theme.json")
    th.add_argument("--name", help="name of the saved theme")
    th.add_argument("--keep-styles", action="store_true", help="do not restyle the objects already in the film")
    th.add_argument("--list", action="store_true", help="list the built-in themes")
    th.set_defaults(func=cmd_theme)

    st = sub.add_parser("subtitles", help="export captions as an .srt subtitle file")
    st.add_argument("project")
    st.add_argument("-o", "--output")
    st.set_defaults(func=cmd_subtitles)

    m = sub.add_parser("mcp", help="let an AI assistant build the film (MCP server on stdin/stdout)")
    m.add_argument("project", nargs="?", help="project file to edit (saved after every change)")
    m.add_argument("--editor", help="drive a running editor instead, e.g. http://localhost:8765")
    m.add_argument("--time", type=float, nargs=2, metavar=("START", "END"), help="only change this time window")
    m.add_argument("--ids", help="only change these objects (comma-separated ids) and new ones")
    m.add_argument("--scene", help="only change this scene (name or id)")
    m.add_argument("--no-save", action="store_true", help="file mode: do not save after each change")
    m.set_defaults(func=cmd_mcp)

    jn = sub.add_parser("join", help="join pieces rendered with render --part, adding sound and chapters")
    jn.add_argument("project")
    jn.add_argument("parts", nargs="+", help="the pieces, in order")
    jn.add_argument("-o", "--output", required=True)
    jn.add_argument("--subtitles", nargs="?", const="file", choices=["off", "file", "soft", "embed"])
    jn.add_argument("--start", type=float, help="as given to render")
    jn.add_argument("--end", type=float, help="as given to render")
    jn.add_argument("--scene", help="as given to render")
    jn.add_argument("--no-audio", action="store_true")
    jn.add_argument("--no-chapters", action="store_true")
    jn.set_defaults(func=cmd_join)

    sc = sub.add_parser("schema", help="the JSON Schema of project files, or check files against it")
    sc.add_argument("-o", "--output", help="write the schema to this file (default: print it)")
    sc.add_argument("--validate", nargs="+", metavar="FILE", help="check project files against the schema")
    sc.add_argument("--strict", action="store_true",
                    help="also reject settings, properties and types this SciView does not know")
    sc.set_defaults(func=cmd_schema)

    pl = sub.add_parser("plugin", help="list installed plugins, or start a new one")
    pl.add_argument("action", choices=["list", "new"], nargs="?", default="list")
    pl.add_argument("name", nargs="?", help="for new: the plugin's name, e.g. spectroscopy")
    pl.add_argument("--folder", default=".", help="for new: where to write it (default: here)")
    pl.set_defaults(func=cmd_plugin)

    i = sub.add_parser("info", help="versions, ffmpeg location, object types and plugins; or a bug report")
    i.add_argument("--report", metavar="PROJECT", help="write a zip for a bug report about this film")
    i.add_argument("-o", "--output", help="where to write the report (default: sciview-report.zip)")
    i.add_argument("--assets", action="store_true", help="put the film's files in the report too")
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
    except (RuntimeError, OSError) as exc:   # ExportError, ThemeError, AudioError, a file that exists ...
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
