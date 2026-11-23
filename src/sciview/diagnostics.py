"""Information for a bug report, without telemetry: nothing is sent anywhere.

``sciview info`` prints it; ``sciview info --report film.sciview.json`` (or "Save a report for a bug" in the
editor's help) writes a zip with the film, what SciView found wrong with it, the versions and, if you choose,
the film's files. Attach it to an issue at https://github.com/OriolSansPlanell/SciView/issues.
"""
from __future__ import annotations

import io
import json
import platform
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

ASSET_LIMIT = 50 * 1024 * 1024
README = """SciView bug report

info.txt       versions of SciView, Python and the libraries, ffmpeg, plugins
problems.txt   what SciView finds wrong with the film
film.sciview.json   the film itself{assets}

Nothing was sent anywhere: look through these files, then attach the zip to an issue at
https://github.com/OriolSansPlanell/SciView/issues with what you did and what you expected.
"""


def info_text() -> str:
    import cv2
    import numpy
    import PIL

    from . import __version__, plugins
    from .export import default_workers, find_ffmpeg, total_memory
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
    mem = total_memory()
    lines = [f"SciView {__version__}", f"Python {platform.python_version()} on {platform.platform()}",
             f"numpy {numpy.__version__}, opencv {cv2.__version__}, pillow {PIL.__version__}, matplotlib {mpl}",
             f"ffmpeg: {ff}", f"render workers: {default_workers()}"
             + (f", memory {mem / 1024 ** 3:.1f} GB" if mem else ""),
             f"object types ({len(REGISTRY)}): {', '.join(sorted(REGISTRY))}", plugins.describe()]
    return "\n".join(lines)


def report(project: Project, include_assets: bool = False) -> bytes:
    """A zip for a bug report: the film, its problems, the versions and (optionally) its files."""
    from .model.project import iter_assets
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("info.txt", info_text() + "\n")
        problems = project.validate()
        z.writestr("problems.txt", "\n".join(problems) + "\n" if problems else "no problems found\n")
        z.writestr("film.sciview.json", json.dumps(project.to_json(), indent=2, ensure_ascii=False,
                                                   default=str))
        added, total = [], 0
        if include_assets:
            for rel in sorted(set(iter_assets(project))):
                p = Path(rel) if Path(rel).is_absolute() else project.base_dir / rel
                try:
                    files = sorted(p.parent.glob(p.name)) if any(c in rel for c in "*?[") else [p]
                    for f in files:
                        if f.is_file() and total + f.stat().st_size <= ASSET_LIMIT:
                            total += f.stat().st_size
                            arc = f.relative_to(project.base_dir).as_posix() if f.is_relative_to(
                                project.base_dir) else f"assets/{f.name}"
                            z.write(f, arc)
                            added.append(arc)
                except (OSError, ValueError):
                    continue
        note = (f"\nassets/        {len(added)} file(s) the film uses" if added else
                "\n(the film's own files are not included)")
        z.writestr("README.txt", README.format(assets=note))
    return buf.getvalue()
