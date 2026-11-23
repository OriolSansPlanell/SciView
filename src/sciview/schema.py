"""A JSON Schema for SciView project files (format 1.x).

The schema describes every object type and setting this SciView knows, plugin types included when their
plugins are installed. It follows the format's rules: a reader of format 1.x accepts what it does not know,
so by default extra settings, properties and object types pass. ``strict=True`` also rejects them, which is
what a file written by this version should satisfy.

    sciview schema -o sciview-1.json        # write it
    sciview schema --validate film.sciview.json
"""
from __future__ import annotations

import json
from typing import Any

from .engine.easing import EASING_NAMES
from .engine.transitions import TRANSITIONS
from .model.base import ENTER_EFFECTS, REGISTRY, Prop
from .model.migrate import FORMAT_VERSION
from .model.project import SETTINGS_PROPS, CameraRig

SCHEMA_ID = "https://oriolsansplanell.github.io/SciView/schema/sciview-1.json"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
NUMBER = {"type": "number"}


def value_schema(p: Prop) -> dict:
    """The JSON a property's value is stored as."""
    k = p.kind
    if k == "number":
        out: dict[str, Any] = dict(NUMBER)
    elif k == "int":
        out = {"type": "integer"}
    elif k == "bool":
        out = {"type": "boolean"}
    elif k in ("vec2", "vec3"):
        n = 2 if k == "vec2" else 3
        out = {"type": "array", "items": NUMBER, "minItems": n, "maxItems": n}
    elif k == "enum" and p.options:
        out = {"enum": list(p.options)}
    elif k == "array":
        out = {"anyOf": [{"type": "array", "items": NUMBER}, {"type": "string"}]}
    elif k == "color":
        out = {"type": "string", "description": "#rrggbb or a palette colour name"}
    else:                                                # text, longtext, asset, ref, font, enum without options
        out = {"type": "string"}
    words = [p.help] if p.help else []
    if p.min is not None or p.max is not None:
        words.append(f"usual range {'' if p.min is None else p.min}..{'' if p.max is None else p.max}")
    if k == "asset":
        words.append("a path relative to the project file, or a pattern such as assets/run/*.csv")
    if k == "ref":
        words.append(f"the id of {'a ' + p.ref if p.ref else 'an'} object")
    if words and "description" not in out:
        out["description"] = "; ".join(words)
    return out


def keyframes_schema(p: Prop) -> dict:
    """Keyframes of an animatable property: shared definitions per kind, so the schema stays small."""
    if f"keys_{p.kind}" in DEFS:
        return {"$ref": f"#/$defs/keys_{p.kind}"}
    return {"type": "array", "items": {"$ref": "#/$defs/keyframe"}}


def _keys_def(value: dict) -> dict:
    return {"type": "array", "items": {"allOf": [{"$ref": "#/$defs/keyframe"}, {"properties": {"v": value}}]}}


DEFS = {
    "keyframe": {"type": "object", "required": ["t", "v"],
                 "properties": {"t": NUMBER, "ease": {"enum": list(EASING_NAMES)},
                                "bez": {"type": "array", "items": NUMBER, "minItems": 4, "maxItems": 4}}},
    "keys_number": _keys_def(NUMBER),
    "keys_int": _keys_def({"type": "integer"}),
    "keys_color": _keys_def({"type": "string"}),
    "keys_vec2": _keys_def({"type": "array", "items": NUMBER, "minItems": 2, "maxItems": 2}),
    "keys_vec3": _keys_def({"type": "array", "items": NUMBER, "minItems": 3, "maxItems": 3}),
    "track": {"type": "object", "required": ["data", "column"], "properties": {
        "data": {"type": "string"}, "column": {"type": "string"}, "time": {"type": "string"}, "scale": NUMBER,
        "offset": NUMBER, "time_scale": NUMBER, "time_offset": NUMBER, "smooth": {"type": "boolean"}}},
}
TRACK = {"$ref": "#/$defs/track"}


def _props_and_keys(props: list[Prop], strict: bool) -> dict:
    animatable = [p for p in props if p.animatable]
    trackable = [p for p in props if p.kind in ("number", "int", "vec2", "vec3")]
    return {
        "props": {"type": "object", "properties": {p.name: value_schema(p) for p in props},
                  "additionalProperties": not strict},
        "keys": {"type": "object", "properties": {p.name: keyframes_schema(p) for p in animatable},
                 "additionalProperties": not strict},
        "tracks": {"type": "object", "properties": {p.name: TRACK for p in trackable},
                   "additionalProperties": not strict},
    }


def _effect(effects) -> dict:
    return {"type": "object", "properties": {"effect": {"enum": list(effects)}, "duration": NUMBER}}


def object_schema(cls, strict: bool = False) -> dict:
    """The schema of one object type: its properties, keyframes, data tracks and effects."""
    return {"properties": {**_props_and_keys(cls.all_props(), strict),
                           "enter": _effect(cls.effects()), "exit": _effect(cls.effects())}}


def camera_schema(strict: bool = False) -> dict:
    return {"type": "object", "properties": {k: v for k, v in _props_and_keys(CameraRig.all_props(), strict).items()}}


def json_schema(strict: bool = False) -> dict:
    """The JSON Schema of a project file, for the object types registered now (plugins included)."""
    base_object = {
        "type": "object", "required": ["type"],
        "properties": {
            "id": {"type": "string"}, "type": {"type": "string"}, "name": {"type": "string"},
            "props": {"type": "object"}, "keys": {"type": "object"}, "tracks": {"type": "object"},
            "start": NUMBER, "end": {"type": ["number", "null"]},
            "enter": _effect(ENTER_EFFECTS + ("draw", "typewriter")),
            "exit": _effect(ENTER_EFFECTS + ("draw", "typewriter")),
            "visible": {"type": "boolean"}, "locked": {"type": "boolean"},
            "parent": {"type": ["string", "null"]}, "scene": {"type": "string"},
        },
        "allOf": [{"if": {"properties": {"type": {"const": t}}, "required": ["type"]},
                   "then": object_schema(cls, strict)} for t, cls in sorted(REGISTRY.items())],
    }
    if strict:
        base_object["properties"]["type"] = {"enum": sorted(REGISTRY)}
        base_object["additionalProperties"] = False
    scene = {
        "type": "object", "required": ["id"],
        "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "duration": NUMBER,
                       "transition": {"enum": list(TRANSITIONS)}, "transition_duration": NUMBER,
                       "chapter": {"type": "boolean"}, "notes": {"type": "string"}, "camera": camera_schema(strict)},
        "additionalProperties": not strict,
    }
    return {
        "$schema": DRAFT,
        "$id": SCHEMA_ID,
        "$defs": DEFS,
        "title": f"SciView project file, format {FORMAT_VERSION.split('.')[0]}.x",
        "description": "A SciView film (.sciview.json). Paths are relative to the file. Times are seconds from "
                       "the start of the object's scene. Readers keep what they do not know.",
        "type": "object",
        "required": ["sciview"],
        "properties": {
            "sciview": {"type": "string", "pattern": r"^1(\.\d+)?$", "description": "format version"},
            "settings": {"type": "object", "properties": {p.name: value_schema(p) for p in SETTINGS_PROPS},
                         "additionalProperties": not strict},
            "palette": {"type": "object", "additionalProperties": {"type": "string"}},
            "styles": {"type": "object", "additionalProperties": {"type": "object"}},
            "camera": camera_schema(strict),
            "scenes": {"type": "array", "items": scene, "minItems": 1},
            "objects": {"type": "array", "items": base_object},
            "template": {"type": "object", "description": "only in template files: how the template is listed",
                         "properties": {"title": {"type": "string"}, "description": {"type": "string"},
                                        "order": NUMBER, "thumb_time": NUMBER}},
        },
        "additionalProperties": not strict,
    }


def dumps(schema: dict | None = None) -> str:
    return json.dumps(schema or json_schema(), indent=1, ensure_ascii=False, separators=(",", ":")) + "\n"


def validate(data: dict, strict: bool = False) -> list[str]:
    """Problems found by checking ``data`` against the schema, as readable lines (empty = valid).
    Needs the ``jsonschema`` package."""
    try:
        import jsonschema
    except ImportError:
        raise ImportError('checking against the schema needs jsonschema: pip install jsonschema') from None
    v = jsonschema.Draft202012Validator(json_schema(strict))
    out = []
    for e in sorted(v.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(x) for x in e.absolute_path) or "(top)"
        out.append(f"{where}: {e.message}")
    return out
