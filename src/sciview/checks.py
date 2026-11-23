"""Checks that need to look at frames: text contrast against what is behind it, and layout (text that
overlaps other text, objects that leave the frame). Used by ``sciview check --frames``, the editor's
problem list and the AI assistant's render-and-check loop.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from .model.project import Project

TEXT_TYPES = ("caption", "title", "text", "equation", "legend", "panel")
AA, AA_LARGE = 4.5, 3.0          # WCAG 2 minimum contrast for body text and for large text


def luminance(rgb) -> np.ndarray:
    """WCAG relative luminance of sRGB colours in 0..1 (any shape ending in 3)."""
    c = np.asarray(rgb, np.float64)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def ratio(l1, l2) -> np.ndarray:
    hi, lo = np.maximum(l1, l2), np.minimum(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def _visible_times(project: Project, obj, scene) -> list[float]:
    s, e = obj.span(scene.duration)
    e = min(e, scene.duration)
    if e <= s:
        return []
    settle = min(obj.enter_duration if obj.enter_effect != "none" else 0.0, (e - s) / 2)
    a = s + settle + 0.05
    b = e - (obj.exit_duration if obj.exit_effect != "none" and obj.end is not None else 0.0) - 0.05
    if b <= a:
        return [(s + e) / 2]
    return [a, (a + b) / 2, b] if b - a > 2.0 else [(a + b) / 2]


def _text_color(project: Project, obj, scene, t: float, renderer):
    from .model.context import RenderContext
    view = project.view(scene)
    ctx = RenderContext(view, renderer.assets, t, 1.0, *project.size, None)
    v = obj.resolve(t, ctx)
    col = v.get("color") if "color" in obj.prop_map() else v.get("title_color")
    return None if col is None else np.asarray(col, np.float64)[:3]


def contrast_issues(project: Project, scale: float = 0.5, ids: list[str] | None = None) -> list[dict]:
    """Text whose colour does not stand out from what is behind it.

    For each text object at a few moments while it is fully shown, the frame is drawn without any text
    and the colour of the text is compared with every pixel behind it; the worst tenth of the area
    decides. WCAG asks for 4.5:1, or 3:1 for large text (24 px, or 19 px bold).
    """
    from .render import FrameInfo
    r = project.renderer()
    texts = [o for o in project.objects
             if o.TYPE in ("caption", "title", "text") and o.visible and (ids is None or o.id in ids)]
    out: list[dict] = []
    saved = r.hide_ids
    try:
        for sc in project.scenes:
            mine = [o for o in texts if o.scene == sc.id]
            moments: dict[float, list] = {}
            for o in mine:
                for t in _visible_times(project, o, sc):
                    moments.setdefault(round(t, 2), []).append(o)
            text_ids = frozenset(o.id for o in project.objects if o.scene == sc.id and o.TYPE in TEXT_TYPES)
            worst: dict[str, dict] = {}
            for t, objs in sorted(moments.items()):
                info = FrameInfo()
                r.hide_ids = saved
                r.frame(t, scale, info, scene=sc.id)
                boxes = {b["id"]: b for b in info.boxes}
                r.hide_ids = text_ids
                bg = r.frame(t, scale, scene=sc.id).astype(np.float64) / 255.0
                s = bg.shape[1] / project.size[0]
                for o in objs:
                    b = boxes.get(o.id)
                    col = _text_color(project, o, sc, t, r)
                    if b is None or col is None:
                        continue
                    x0, y0 = max(0, int(b["x0"] * s)), max(0, int(b["y0"] * s))
                    x1, y1 = min(bg.shape[1], int(b["x1"] * s) + 1), min(bg.shape[0], int(b["y1"] * s) + 1)
                    if x1 - x0 < 2 or y1 - y0 < 2:
                        continue
                    behind = bg[y0:y1, x0:x1].reshape(-1, 3)
                    back = o.backing(o.resolve(t, _ctx(project, sc, r, t))) if hasattr(o, "backing") else None
                    if back is not None:
                        bc = np.asarray(back[0], np.float64)[:3]
                        behind = behind * (1 - back[1]) + bc * back[1]
                    rr = float(np.percentile(ratio(luminance(col), luminance(behind)), 10))
                    size = float(o.props.get("size", o.props.get("title_size", 30)))
                    bold = o.props.get("weight", "regular") in ("bold", "semibold", "black")
                    need = AA_LARGE if size >= 24 or (bold and size >= 19) else AA
                    if rr < need and (o.id not in worst or rr < worst[o.id]["ratio"]):
                        worst[o.id] = {"id": o.id, "prop": "color", "t": t, "scene": sc.id, "ratio": round(rr, 2),
                                       "need": need,
                                       "message": f"{o.name}: contrast {rr:.1f}:1 with what is behind it at "
                                                  f"{t:.1f} s (aim for {need:g}:1); choose a lighter or darker "
                                                  "colour, or a box or outline caption style"}
            out.extend(worst.values())
    finally:
        r.hide_ids = saved
    return out


def _ctx(project, scene, renderer, t):
    from .model.context import RenderContext
    return RenderContext(project.view(scene), renderer.assets, t, 1.0, *project.size, None)


def sample_times(project: Project, scene, limit: int = 8) -> list[float]:
    """Moments worth looking at in a scene: shortly after things appear, and its middle."""
    ts = {round(scene.duration / 2, 2)}
    for o in project.objects:
        if o.scene == scene.id and not o.IS_GROUP and o.TYPE != "voice":
            for t in _visible_times(project, o, scene)[:1]:
                ts.add(round(t, 2))
    ts = sorted(ts)
    if len(ts) > limit:
        idx = np.linspace(0, len(ts) - 1, limit).round().astype(int)
        ts = [ts[i] for i in sorted(set(idx))]
    return ts


def layout_issues(project: Project, scale: float = 0.25) -> list[dict]:
    """Text that overlaps other text, and 2D objects that reach outside the frame."""
    from .render import FrameInfo
    r = project.renderer()
    W, H = project.size
    seen: set[tuple] = set()
    out: list[dict] = []
    for sc in project.scenes:
        for t in sample_times(project, sc):
            info = FrameInfo()
            r.frame(t, scale, info, scene=sc.id)
            boxes = [b for b in info.boxes if not b.get("group")]
            objs = {b["id"]: project.find(b["id"]) for b in boxes}
            for b in boxes:
                o = objs[b["id"]]
                if o is None or o.IS_3D:
                    continue
                w, h = b["x1"] - b["x0"], b["y1"] - b["y0"]
                outside = max(0.0, -b["x0"]) + max(0.0, b["x1"] - W) + max(0.0, -b["y0"]) + max(0.0, b["y1"] - H)
                if outside > 0.04 * max(w, h, 1) and ("out", o.id) not in seen:
                    seen.add(("out", o.id))
                    out.append({"id": o.id, "prop": "position", "t": t, "scene": sc.id,
                                "message": f"{o.name} reaches outside the frame at {t:.1f} s"})
            texts = [b for b in boxes if objs[b["id"]] is not None and objs[b["id"]].TYPE in TEXT_TYPES]
            for i, a in enumerate(texts):
                for b in texts[i + 1:]:
                    ix = min(a["x1"], b["x1"]) - max(a["x0"], b["x0"])
                    iy = min(a["y1"], b["y1"]) - max(a["y0"], b["y0"])
                    if ix <= 0 or iy <= 0:
                        continue
                    small = min((a["x1"] - a["x0"]) * (a["y1"] - a["y0"]), (b["x1"] - b["x0"]) * (b["y1"] - b["y0"]))
                    oa, ob = objs[a["id"]], objs[b["id"]]
                    if oa.TYPE == "panel" or ob.TYPE == "panel":
                        continue                      # text on a card is the point of a card
                    key = ("overlap",) + tuple(sorted((oa.id, ob.id)))
                    if ix * iy > 0.12 * max(small, 1) and key not in seen:
                        seen.add(key)
                        out.append({"id": ob.id, "prop": "position", "t": t, "scene": sc.id,
                                    "message": f"{ob.name} overlaps {oa.name} at {t:.1f} s"})
    return out


def frame_issues(project: Project) -> list[dict]:
    return layout_issues(project) + contrast_issues(project)
