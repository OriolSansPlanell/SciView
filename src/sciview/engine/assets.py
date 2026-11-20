"""Loading user files: images, data tables and meshes. Results are cached by path and mtime."""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
ARRAY_EXT = {".npy"}
TABLE_EXT = {".csv", ".tsv", ".txt", ".dat", ".npz", ".npy"}
MESH_EXT = {".stl", ".obj"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}


def asset_kind(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in MESH_EXT:
        return "mesh"
    if ext in AUDIO_EXT:
        return "audio"
    if ext == ".npy":
        return "array"
    if ext in TABLE_EXT:
        return "table"
    return "other"


class AssetError(ValueError):
    pass


class AssetStore:
    """Resolves project-relative asset paths and caches what it loads."""

    def __init__(self, base_dir: str | os.PathLike | None = None):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self._cache: dict[tuple, Any] = {}

    def resolve(self, rel: str) -> Path:
        p = Path(rel)
        if not p.is_absolute():
            p = self.base_dir / p
        return p

    def _key(self, kind: str, rel: str, *extra) -> tuple:
        p = self.resolve(rel)
        try:
            mt = p.stat().st_mtime_ns
        except OSError:
            raise AssetError(f"file not found: {rel}") from None
        return (kind, str(p), mt) + extra

    def _cached(self, key, loader):
        if key not in self._cache:
            if len(self._cache) > 256:
                self._cache.clear()
            self._cache[key] = loader()
        return self._cache[key]

    # ------------------------------------------------------------------ images
    def image(self, rel: str) -> np.ndarray:
        """Float32 array: (h,w) for single-channel data, (h,w,3|4) for colour, values 0..1
        (single-channel data from .npy or float TIFF keeps its own units)."""
        key = self._key("image", rel)
        return self._cached(key, lambda: load_image(self.resolve(rel)))

    def image_resized(self, rel: str, max_side: int) -> np.ndarray:
        import cv2

        img = self.image(rel)
        h, w = img.shape[:2]
        if max(h, w) <= max_side:
            return img
        key = self._key("image_rs", rel, int(max_side))

        def load():
            f = max_side / max(h, w)
            return cv2.resize(img, (max(1, int(w * f)), max(1, int(h * f))), interpolation=cv2.INTER_AREA)
        return self._cached(key, load)

    # ------------------------------------------------------------------ tables
    def table(self, rel: str) -> dict[str, np.ndarray]:
        key = self._key("table", rel)
        return self._cached(key, lambda: load_table(self.resolve(rel)))

    def column(self, rel: str, col: str | int) -> np.ndarray:
        tab = self.table(rel)
        names = list(tab)
        c = str(col).strip()
        if c in tab:
            return tab[c]
        if c.lstrip("-").isdigit() and -len(names) <= int(c) < len(names):
            return tab[names[int(c)]]
        lower = {k.lower(): k for k in names}
        if c.lower() in lower:
            return tab[lower[c.lower()]]
        raise AssetError(f"column {col!r} not in {rel} (columns: {', '.join(names)})")

    # ------------------------------------------------------------------ meshes
    def mesh(self, rel: str) -> tuple[np.ndarray, np.ndarray]:
        key = self._key("mesh", rel)
        return self._cached(key, lambda: load_mesh(self.resolve(rel)))

    def stamp(self, rel: str) -> int:
        """Modification time of a file (0 if missing): part of cache keys derived from it."""
        try:
            return self.resolve(rel).stat().st_mtime_ns
        except OSError:
            return 0

    def memo(self, key: tuple, factory):
        """Cache any derived object (particle tables, colormapped images ...)."""
        return self._cached(("memo",) + key, factory)


# --------------------------------------------------------------------------- loaders
def load_image(path: Path) -> np.ndarray:
    ext = path.suffix.lower()
    if ext == ".npy":
        arr = np.load(path, allow_pickle=False)
        arr = np.asarray(arr, np.float32)
        if arr.ndim == 3 and arr.shape[2] in (3, 4) and arr.max() > 1.0:
            arr = arr / 255.0
        return arr
    with Image.open(path) as im:
        im.load()
        if im.mode in ("I;16", "I;16B", "I;16L", "I"):
            arr = np.asarray(im, np.float32)
            hi = 65535.0 if im.mode.startswith("I;16") else max(float(arr.max()), 1.0)
            return arr / hi
        if im.mode == "F":
            return np.asarray(im, np.float32)
        if im.mode in ("L", "1"):
            return np.asarray(im.convert("L"), np.float32) / 255.0
        if im.mode in ("RGBA", "LA", "P"):
            return np.asarray(im.convert("RGBA"), np.float32) / 255.0
        return np.asarray(im.convert("RGB"), np.float32) / 255.0


def load_table(path: Path) -> dict[str, np.ndarray]:
    """Columns of a CSV/TSV/whitespace table, .npy (columns by index) or .npz (arrays by key)."""
    ext = path.suffix.lower()
    if ext == ".npz":
        with np.load(path, allow_pickle=False) as z:
            return {k: np.asarray(z[k], np.float64).ravel() for k in z.files}
    if ext == ".npy":
        arr = np.asarray(np.load(path, allow_pickle=False), np.float64)
        if arr.ndim == 1:
            return {"0": arr}
        return {str(i): arr[:, i] for i in range(arr.shape[1])}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        if ext == ".tsv" or "\t" in sample:
            rows = list(csv.reader(fh, delimiter="\t"))
        elif "," in sample or ";" in sample:
            delim = ";" if sample.count(";") > sample.count(",") else ","
            rows = list(csv.reader(fh, delimiter=delim))
        else:
            rows = [line.split() for line in fh if line.strip() and not line.lstrip().startswith("#")]
    rows = [r for r in rows if r and not (r[0].lstrip().startswith("#"))]
    if not rows:
        raise AssetError(f"{path.name} is empty")

    def isnum(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    header = rows[0]
    if all(isnum(c) for c in header if c.strip()):
        names = [str(i) for i in range(len(header))]
        body = rows
    else:
        names = [h.strip() or str(i) for i, h in enumerate(header)]
        body = rows[1:]
    cols: dict[str, list[float]] = {n: [] for n in names}
    for r in body:
        for i, n in enumerate(names):
            v = r[i].strip() if i < len(r) else ""
            try:
                cols[n].append(float(v))
            except ValueError:
                cols[n].append(np.nan)
    return {n: np.asarray(v, np.float64) for n, v in cols.items()}


def load_mesh(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Vertices (N,3) and triangle indices (M,3) from STL (ASCII/binary) or OBJ."""
    ext = path.suffix.lower()
    if ext == ".obj":
        verts, faces = [], []
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.startswith("v "):
                    verts.append([float(v) for v in line.split()[1:4]])
                elif line.startswith("f "):
                    idx = [int(tok.split("/")[0]) for tok in line.split()[1:]]
                    idx = [i - 1 if i > 0 else len(verts) + i for i in idx]
                    for k in range(1, len(idx) - 1):  # fan triangulation
                        faces.append([idx[0], idx[k], idx[k + 1]])
        return np.asarray(verts, np.float64), np.asarray(faces, np.int64).reshape(-1, 3)
    data = path.read_bytes()
    if data[:5] == b"solid" and b"facet" in data[:1024]:
        tris = []
        for line in data.decode("utf-8", "ignore").splitlines():
            s = line.strip()
            if s.startswith("vertex"):
                tris.append([float(v) for v in s.split()[1:4]])
        v = np.asarray(tris, np.float64).reshape(-1, 3)
    else:
        n = int(np.frombuffer(data[80:84], np.uint32)[0])
        rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
        arr = np.frombuffer(data[84:84 + n * 50], rec)
        v = arr["v"].reshape(-1, 3).astype(np.float64)
    # merge duplicate vertices
    uniq, inv = np.unique(np.round(v, 6), axis=0, return_inverse=True)
    return uniq, inv.reshape(-1, 3)
