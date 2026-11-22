"""Loading user files: images, data tables, meshes, volumes and molecules. Results are cached by path and mtime."""
from __future__ import annotations

import csv
import glob
import os
import re
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
ARRAY_EXT = {".npy"}
TABLE_EXT = {".csv", ".tsv", ".txt", ".dat", ".npz", ".npy"}
MESH_EXT = {".stl", ".obj"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
VOLUME_EXT = {".h5", ".hdf5", ".nxs"}
MOLECULE_EXT = {".pdb", ".xyz", ".ent"}
SEQUENCE_CHARS = set("*?[")


def is_sequence(path: str) -> bool:
    """True for a file pattern such as ``assets/scan/*.tif`` (one file per step)."""
    return any(c in SEQUENCE_CHARS for c in str(path))


def asset_kind(path: str) -> str:
    if is_sequence(path):
        return "sequence"
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in MESH_EXT:
        return "mesh"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VOLUME_EXT:
        return "volume"
    if ext in MOLECULE_EXT:
        return "molecule"
    if ext == ".npy":
        return "array"
    if ext in TABLE_EXT:
        return "table"
    return "other"


def natural_key(s: str):
    """Sort ``step_2`` before ``step_10``."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


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
        """Modification time of a file (0 if missing): part of cache keys derived from it.
        For a sequence pattern: a value that changes when any matching file changes."""
        if is_sequence(rel):
            return hash(tuple((f, self.stamp(f)) for f in self.sequence(rel)))
        try:
            return self.resolve(rel).stat().st_mtime_ns
        except OSError:
            return 0

    # ------------------------------------------------------------------ sequences
    def sequence(self, pattern: str) -> list[str]:
        """Files matching a pattern, relative to the project folder, in natural order (step_2 before step_10)."""
        base = str(self.base_dir)
        full = pattern if os.path.isabs(pattern) else os.path.join(base, pattern)
        files = [f for f in glob.glob(full) if os.path.isfile(f)]
        out = []
        for f in files:
            try:
                out.append(os.path.relpath(f, base).replace(os.sep, "/"))
            except ValueError:          # another drive on Windows
                out.append(f)
        return sorted(out, key=natural_key)

    def sequence_file(self, pattern: str, index: float) -> tuple[str, str, float]:
        """The files either side of a fractional step index, and how far between them (0..1)."""
        files = self.sequence(pattern)
        if not files:
            raise AssetError(f"no files match {pattern}")
        i = min(max(float(index), 0.0), len(files) - 1.0)
        lo = int(i)
        hi = min(lo + 1, len(files) - 1)
        return files[lo], files[hi], i - lo

    # ------------------------------------------------------------------ volumes
    def volume(self, rel: str, dataset: str = "") -> np.ndarray:
        """A 3D float32 array (z, y, x): .npy, a multi-page TIFF, an HDF5 dataset, or a sequence of 2D images."""
        if is_sequence(rel):
            files = self.sequence(rel)
            if not files:
                raise AssetError(f"no files match {rel}")
            key = ("volume_seq", rel, self.stamp(rel))
            return self._cached(key, lambda: _stack([self.image(f) for f in files], rel))
        key = self._key("volume", rel, dataset)
        return self._cached(key, lambda: load_volume(self.resolve(rel), dataset))

    def volume_reduced(self, rel: str, dataset: str, max_side: int) -> np.ndarray:
        vol = self.volume(rel, dataset)
        if max(vol.shape) <= max_side:
            return vol
        key = ("volume_rs", rel, dataset, self.stamp(rel), int(max_side))

        def make():
            f = int(np.ceil(max(vol.shape) / max_side))
            return block_reduce(vol, f)
        return self._cached(key, make)

    # ------------------------------------------------------------------ molecules
    def molecule(self, rel: str) -> Molecule:
        key = self._key("molecule", rel)
        return self._cached(key, lambda: load_molecule(self.resolve(rel)))

    def memo(self, key: tuple, factory):
        """Cache any derived object (particle tables, colormapped images ...)."""
        return self._cached(("memo",) + key, factory)


# --------------------------------------------------------------------------- loaders
def _stack(images: list, name: str) -> np.ndarray:
    imgs = [im if im.ndim == 2 else im[..., :3].mean(axis=2) for im in images]
    shapes = {im.shape for im in imgs}
    if len(shapes) != 1:
        raise AssetError(f"the images of {name} have different sizes: {sorted(shapes)}")
    return np.stack(imgs, 0).astype(np.float32)


def block_reduce(vol: np.ndarray, f: int) -> np.ndarray:
    """Average f×f×f blocks (edges padded by repetition)."""
    if f <= 1:
        return vol
    pad = [(0, (-n) % f) for n in vol.shape]
    v = np.pad(vol, pad, mode="edge")
    z, y, x = (n // f for n in v.shape)
    return v.reshape(z, f, y, f, x, f).mean(axis=(1, 3, 5)).astype(np.float32)


def load_volume(path: Path, dataset: str = "") -> np.ndarray:
    ext = path.suffix.lower()
    if ext == ".npy":
        arr = np.load(path, allow_pickle=False, mmap_mode="r")
        if arr.ndim == 4 and arr.shape[-1] in (1, 3, 4):
            arr = np.asarray(arr[..., :3]).mean(axis=-1)
        if arr.ndim != 3:
            raise AssetError(f"{path.name} holds a {arr.ndim}D array; a volume needs 3 dimensions (z, y, x)")
        return np.array(arr, np.float32)            # a writable copy, not the memory map
    if ext in (".tif", ".tiff"):
        try:
            import tifffile
            arr = tifffile.imread(str(path))
        except ImportError:
            from PIL import ImageSequence
            with Image.open(path) as im:
                arr = np.stack([np.asarray(fr.convert("F") if fr.mode not in ("I;16", "F") else fr, np.float32)
                                for fr in ImageSequence.Iterator(im)])
        arr = np.asarray(arr)
        if arr.ndim == 4 and arr.shape[-1] in (3, 4):
            arr = arr[..., :3].mean(axis=-1)
        if arr.ndim != 3:
            raise AssetError(f"{path.name} is a single image; a volume needs a multi-page TIFF stack")
        return arr.astype(np.float32)
    if ext in VOLUME_EXT:
        try:
            import h5py
        except ImportError:
            raise AssetError("reading HDF5 files needs h5py: pip install h5py") from None
        with h5py.File(path, "r") as f:
            name = dataset.strip()
            if not name:
                found = []
                f.visititems(lambda n, o: found.append(n) if isinstance(o, h5py.Dataset) and o.ndim == 3 else None)
                if not found:
                    raise AssetError(f"{path.name} has no 3D dataset")
                name = found[0]
            if name not in f:
                raise AssetError(f"{path.name} has no dataset {name!r}")
            arr = np.asarray(f[name], np.float32)
        if arr.ndim != 3:
            raise AssetError(f"dataset {name!r} in {path.name} is {arr.ndim}D, not 3D")
        return arr
    raise AssetError(f"{path.name}: volumes are read from .npy, multi-page .tif, .h5 or a file pattern like slices/*.png")


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


# --------------------------------------------------------------------------- molecules
COVALENT_RADIUS = {  # Å, Cordero et al. 2008 (common elements)
    "H": 0.31, "He": 0.28, "Li": 1.28, "Be": 0.96, "B": 0.84, "C": 0.76, "N": 0.71, "O": 0.66, "F": 0.57,
    "Ne": 0.58, "Na": 1.66, "Mg": 1.41, "Al": 1.21, "Si": 1.11, "P": 1.07, "S": 1.05, "Cl": 1.02, "Ar": 1.06,
    "K": 2.03, "Ca": 1.76, "Ti": 1.60, "V": 1.53, "Cr": 1.39, "Mn": 1.39, "Fe": 1.32, "Co": 1.26, "Ni": 1.24,
    "Cu": 1.32, "Zn": 1.22, "Ga": 1.22, "Ge": 1.20, "As": 1.19, "Se": 1.20, "Br": 1.20, "Kr": 1.16, "Rb": 2.20,
    "Sr": 1.95, "Zr": 1.75, "Mo": 1.54, "Ag": 1.45, "Cd": 1.44, "In": 1.42, "Sn": 1.39, "Sb": 1.39, "Te": 1.38,
    "I": 1.39, "Xe": 1.40, "Cs": 2.44, "Ba": 2.15, "La": 2.07, "Gd": 1.96, "Pt": 1.36, "Au": 1.36, "Hg": 1.32,
    "Pb": 1.46, "Bi": 1.48, "U": 1.96,
}


class Molecule:
    """Atoms (element, position in Å, residue info) and bonds (index pairs)."""

    def __init__(self, elements: list[str], xyz: np.ndarray, names: list[str] | None = None,
                 residues: list[int] | None = None, chains: list[str] | None = None,
                 bonds: np.ndarray | None = None, hetero: list[bool] | None = None,
                 resnames: list[str] | None = None):
        self.elements = elements
        self.xyz = np.asarray(xyz, np.float64).reshape(-1, 3)
        self.names = names or list(elements)
        self.residues = residues or [0] * len(elements)
        self.chains = chains or ["A"] * len(elements)
        self.hetero = hetero or [False] * len(elements)
        self.resnames = resnames or [""] * len(elements)
        self.bonds = guess_bonds(self.elements, self.xyz) if bonds is None or len(bonds) == 0 else bonds

    def __len__(self) -> int:
        return len(self.elements)

    def backbone(self) -> list[tuple[str, np.ndarray]]:
        """Indices of the alpha carbons (proteins) or phosphorus atoms (nucleic acids), per chain."""
        out: dict[str, list] = {}
        for i, (n, ch) in enumerate(zip(self.names, self.chains)):
            if not self.hetero[i] and n.strip().upper() in ("CA", "P") and self.elements[i] in ("C", "P"):
                out.setdefault(ch, []).append(i)
        return [(ch, np.asarray(v, np.int64)) for ch, v in out.items() if len(v) >= 2]


def _element(sym: str) -> str:
    sym = re.sub(r"[^A-Za-z]", "", sym)
    if not sym:
        return "C"
    sym = sym[0].upper() + sym[1:].lower()
    if sym in COVALENT_RADIUS:
        return sym
    return sym[0] if sym[0] in COVALENT_RADIUS else "C"


def guess_bonds(elements: list[str], xyz: np.ndarray, tolerance: float = 0.45) -> np.ndarray:
    """Bonds between atoms closer than the sum of their covalent radii plus a tolerance (Å)."""
    n = len(elements)
    if n < 2:
        return np.zeros((0, 2), np.int64)
    r = np.array([COVALENT_RADIUS.get(e, 0.77) for e in elements])
    cell = 2 * r.max() + tolerance
    keys = np.floor(xyz / cell).astype(np.int64)
    grid: dict[tuple, list[int]] = {}
    for i, k in enumerate(map(tuple, keys)):
        grid.setdefault(k, []).append(i)
    pairs = []
    offs = [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)]
    for k, members in grid.items():
        cand = [j for o in offs for j in grid.get((k[0] + o[0], k[1] + o[1], k[2] + o[2]), [])]
        cand = np.asarray(cand)
        for i in members:
            js = cand[cand > i]
            if len(js) == 0:
                continue
            d = np.linalg.norm(xyz[js] - xyz[i], axis=1)
            ok = (d > 0.4) & (d < r[js] + r[i] + tolerance)
            pairs.extend((i, int(j)) for j in js[ok])
    return np.asarray(pairs, np.int64).reshape(-1, 2)


def load_molecule(path: Path) -> Molecule:
    ext = path.suffix.lower()
    text = path.read_text(encoding="utf-8", errors="ignore")
    if ext == ".xyz":
        lines = text.splitlines()
        try:
            n = int(lines[0].split()[0])
        except (IndexError, ValueError):
            raise AssetError(f"{path.name}: the first line of an XYZ file is the number of atoms") from None
        els, pos = [], []
        for line in lines[2:2 + n]:
            tok = line.split()
            if len(tok) >= 4:
                els.append(_element(tok[0]))
                pos.append([float(t) for t in tok[1:4]])
        if not els:
            raise AssetError(f"{path.name} has no atoms")
        return Molecule(els, np.asarray(pos))
    els, pos, names, res, chains, serial, het, resn = [], [], [], [], [], {}, [], []
    conect = []
    for line in text.splitlines():
        rec = line[:6].strip()
        if rec in ("ATOM", "HETATM"):
            try:
                x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            except ValueError:
                continue
            name = line[12:16].strip()
            el = line[76:78].strip() if len(line) >= 78 and line[76:78].strip() else name
            if line[16:17] not in (" ", "A", ""):        # keep the first alternate location only
                continue
            try:
                serial[int(line[6:11])] = len(els)
            except ValueError:
                pass
            els.append(_element(el))
            pos.append([x, y, z])
            names.append(name)
            chains.append(line[21:22].strip() or "A")
            het.append(rec == "HETATM")
            resn.append(line[17:20].strip())
            try:
                res.append(int(line[22:26]))
            except ValueError:
                res.append(0)
        elif rec == "CONECT":
            nums = [int(line[i:i + 5]) for i in range(6, len(line.rstrip()), 5) if line[i:i + 5].strip().isdigit()]
            conect += [(nums[0], m) for m in nums[1:]]
        elif rec == "ENDMDL":
            break
    if not els:
        raise AssetError(f"{path.name} has no ATOM or HETATM records")
    xyz = np.asarray(pos)
    bonds = guess_bonds(els, xyz)
    extra = [(serial[a], serial[b]) for a, b in conect if a in serial and b in serial]
    if extra:
        allb = {tuple(sorted(p)) for p in map(tuple, bonds)} | {tuple(sorted(p)) for p in extra}
        bonds = np.asarray(sorted(allb), np.int64).reshape(-1, 2)
    return Molecule(els, xyz, names, res, chains, bonds, het, resn)
