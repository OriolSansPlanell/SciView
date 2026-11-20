"""Generate docs/objects.md from the object schemas, so the reference never drifts from the code.

Run from the repository root:  python tools/gen_docs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sciview.model import all_schemas  # noqa: E402

KIND = {"number": "number", "int": "whole number", "bool": "on/off", "text": "text", "longtext": "text (lines)",
        "color": "colour", "vec2": "x, y", "vec3": "x, y, z", "enum": "choice", "asset": "file", "array": "numbers",
        "ref": "object", "font": "font"}


def fmt_default(p: dict) -> str:
    d = p["default"]
    if isinstance(d, list):
        return "(" + ", ".join(f"{x:g}" if isinstance(x, (int, float)) else str(x) for x in d) + ")"
    if isinstance(d, bool):
        return "on" if d else "off"
    if isinstance(d, float):
        return f"{d:g}"
    if d == "":
        return "empty"
    s = str(d).replace("\n", " / ").replace("|", "\\|")
    return s if len(s) < 40 else s[:37] + "..."


def table(props: list[dict]) -> list[str]:
    out = ["| Property | Type | Default | Animatable | Notes |", "| --- | --- | --- | --- | --- |"]
    for p in props:
        notes = p.get("help", "").replace("|", "\\|")
        if p.get("options"):
            opts = ", ".join(f"`{o}`" for o in p["options"])
            notes = f"{notes} Options: {opts}." if notes else f"Options: {opts}."
        rng = ""
        if "min" in p or "max" in p:
            rng = f" ({p.get('min', '')}..{p.get('max', '')})"
        out.append(f"| `{p['name']}` | {KIND.get(p['kind'], p['kind'])}{rng} | {fmt_default(p)} | "
                   f"{'yes' if p['animatable'] else ''} | {notes.strip()} |")
    return out


def main() -> None:
    sc = all_schemas()
    lines = [
        "# Object reference",
        "",
        "Generated from the code by `tools/gen_docs.py`. Every property can be set in the editor's inspector, "
        "in a project file under `props`, or from Python with `film.add(type, **props)` / `obj.set(name, value)`.",
        "Animatable properties can be keyframed: `obj.key(name, time, value, ease)`.",
        "",
        "Positions of 2D objects are in pixels of the film frame (1920 x 1080 by default, origin at the top-left). "
        "3D objects use scene units (centimetres in the examples) with z pointing up.",
        "",
        "Every object also has timing: `start`, `end` (empty = until the end of the film), an enter effect and an "
        "exit effect with durations. Effects: " + ", ".join(f"`{e}`" for e in
        ["none", "fade", "slide_up", "slide_down", "slide_left", "slide_right", "pop"]) +
        "; objects that can be drawn on also accept `draw`, text objects accept `typewriter`.",
        "",
    ]
    for cat in sc["categories"]:
        types = [t for t in sc["types"] if t["category"] == cat]
        lines += [f"## {cat}", ""]
        lines += [f"- [{t['label']}](#{t['type']}) (`{t['type']}`): {t['description']}" for t in types]
        lines.append("")
        for t in types:
            lines += [f'<a id="{t["type"]}"></a>', f"### {t['label']} (`{t['type']}`)", "", t["description"], ""]
            effects = ", ".join(f"`{e}`" for e in t["effects"])
            lines += [f"Default enter effect: `{t['default_enter']}`. Effects: {effects}.", ""]
            lines += table(t["props"]) + [""]
    lines += ["## Camera (`camera`)", "", "There is one camera per film. It orbits its target point.", ""]
    lines += table(sc["camera"]["props"]) + [""]
    lines += ["## Film settings", "", "Stored under `settings` in the project file.", ""]
    lines += table(sc["settings"]) + [""]
    lines += ["## Default palette", "", "| Name | Colour |", "| --- | --- |"]
    lines += [f"| `{k}` | `{v}` |" for k, v in sc["palette"].items()]
    (ROOT / "docs" / "objects.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote docs/objects.md")


if __name__ == "__main__":
    main()
