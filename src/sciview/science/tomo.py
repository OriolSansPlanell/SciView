"""Tomography in a few lines: a test phantom, its sinogram, and filtered back-projection.

Plain NumPy + OpenCV, written to be read (and to make films), not to compete with tomopy or ASTRA.
Angles are in degrees; images are square; the rotation axis is the image centre.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

# modified Shepp-Logan (Toft 1996): value, half-axes a, b, centre x, y, rotation (degrees)
_SHEPP_LOGAN = [
    (1.00, 0.6900, 0.9200, 0.00, 0.0000, 0), (-0.80, 0.6624, 0.8740, 0.00, -0.0184, 0),
    (-0.20, 0.1100, 0.3100, 0.22, 0.0000, -18), (-0.20, 0.1600, 0.4100, -0.22, 0.0000, 18),
    (0.10, 0.2100, 0.2500, 0.00, 0.3500, 0), (0.10, 0.0460, 0.0460, 0.00, 0.1000, 0),
    (0.10, 0.0460, 0.0460, 0.00, -0.1000, 0), (0.10, 0.0460, 0.0230, -0.08, -0.6050, 0),
    (0.10, 0.0230, 0.0230, 0.00, -0.6060, 0), (0.10, 0.0230, 0.0460, 0.06, -0.6050, 0),
]


def phantom(n: int = 256) -> np.ndarray:
    """The modified Shepp-Logan head phantom, (n, n) float32 in 0..1."""
    n = int(n)
    c = (np.arange(n) + 0.5) / n * 2 - 1
    x, y = np.meshgrid(c, -c)
    img = np.zeros((n, n), np.float64)
    for val, a, b, x0, y0, phi in _SHEPP_LOGAN:
        t = math.radians(phi)
        xr = (x - x0) * math.cos(t) + (y - y0) * math.sin(t)
        yr = -(x - x0) * math.sin(t) + (y - y0) * math.cos(t)
        img[(xr / a) ** 2 + (yr / b) ** 2 <= 1] += val
    return np.clip(img, 0, 1).astype(np.float32)


def angles(count: int, span: float = 180.0) -> np.ndarray:
    """``count`` equally spaced angles over ``span`` degrees, without repeating the end."""
    return np.arange(int(count)) * (float(span) / max(int(count), 1))


def _rotate(img: np.ndarray, deg: float) -> np.ndarray:
    n = img.shape[0]
    M = cv2.getRotationMatrix2D(((n - 1) / 2, (n - 1) / 2), float(deg), 1.0)
    return cv2.warpAffine(img, M, (n, n), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def _circle(n: int) -> np.ndarray:
    c = np.arange(n) - (n - 1) / 2
    return (c[None, :] ** 2 + c[:, None] ** 2 <= (n / 2) ** 2).astype(np.float32)


def radon(image: np.ndarray, angles_deg) -> np.ndarray:
    """Sinogram (n_angles, n): line integrals through a square image at each angle.

    Row ``i`` is what a detector below the sample records (rays travelling down the image) once the
    sample has turned ``angles_deg[i]`` degrees clockwise as seen on screen: the same sense as the
    ``rotation`` of an image object, so a turning image and its sinogram stay in step.
    """
    img = np.asarray(image, np.float32)
    if img.ndim != 2 or img.shape[0] != img.shape[1]:
        img = square(img)
    img = img * _circle(img.shape[0])
    return np.stack([_rotate(img, -a).sum(axis=0) for a in np.asarray(angles_deg, np.float64)]).astype(np.float32)


def square(img: np.ndarray, n: int | None = None) -> np.ndarray:
    """Pad a 2D image to a centred square (and resize it to n × n)."""
    img = np.asarray(img, np.float32)
    if img.ndim == 3:
        img = img[..., :3].mean(axis=2)
    h, w = img.shape
    m = max(h, w)
    out = np.zeros((m, m), np.float32)
    out[(m - h) // 2:(m - h) // 2 + h, (m - w) // 2:(m - w) // 2 + w] = img
    if n and n != m:
        out = cv2.resize(out, (int(n), int(n)), interpolation=cv2.INTER_AREA if n < m else cv2.INTER_LINEAR)
    return out


def filter_sinogram(sino: np.ndarray, kind: str = "ramp") -> np.ndarray:
    """Apply the reconstruction filter along the detector axis (ramp, shepp-logan, cosine, hann or none)."""
    sino = np.asarray(sino, np.float64)
    if kind in ("none", "", None):
        return sino
    n = sino.shape[1]
    size = max(64, 1 << int(math.ceil(math.log2(2 * n))))
    # ramp from the spatial-domain kernel (no DC offset), as in Kak & Slaney
    k = np.concatenate([np.arange(1, size // 2 + 1, 2), np.arange(size // 2 - 1, 0, -2)])
    f = np.zeros(size)
    f[0] = 0.25
    f[1::2] = -1 / (np.pi * k) ** 2
    ramp = 2 * np.real(np.fft.fft(f))
    w = np.fft.fftfreq(size) * 2 * np.pi
    if kind == "shepp-logan":
        with np.errstate(invalid="ignore", divide="ignore"):
            ramp *= np.where(w == 0, 1.0, np.sin(w / 2) / (w / 2))
    elif kind == "cosine":
        ramp *= np.cos(w / 2)
    elif kind == "hann":
        ramp *= 0.5 + 0.5 * np.cos(w)
    elif kind != "ramp":
        raise ValueError(f"unknown filter {kind!r}: ramp, shepp-logan, cosine, hann or none")
    padded = np.zeros((sino.shape[0], size))
    padded[:, :n] = sino
    return np.real(np.fft.ifft(np.fft.fft(padded, axis=1) * ramp, axis=1))[:, :n]


def backproject(projection: np.ndarray, angle_deg: float, n: int) -> np.ndarray:
    """Smear one (filtered) projection back across an n × n image at its angle."""
    smear = np.tile(np.asarray(projection, np.float32)[None, :], (n, 1))
    return _rotate(smear, angle_deg)


def fbp(sino: np.ndarray, angles_deg, filter: str = "ramp", cumulative: bool = False) -> np.ndarray:
    """Filtered back-projection of a sinogram from :func:`radon`.

    Returns the (n, n) reconstruction, or with ``cumulative=True`` an (n_angles, n, n) stack whose
    image ``k`` uses only the first k + 1 projections: the picture building up angle by angle.
    """
    sino = np.asarray(sino, np.float32)
    ang = np.asarray(angles_deg, np.float64)
    n = sino.shape[1]
    filt = filter_sinogram(sino, filter).astype(np.float32)
    span = (ang[-1] - ang[0]) * len(ang) / max(len(ang) - 1, 1) if len(ang) > 1 else 180.0
    norm = math.pi * (span / 180.0) / (2 * len(ang)) if len(ang) else 1.0
    mask = _circle(n)
    acc = np.zeros((n, n), np.float32)
    stack = np.zeros((len(ang), n, n), np.float32) if cumulative else None
    for i, (row, a) in enumerate(zip(filt, ang)):
        acc += backproject(row, a, n)
        if stack is not None:
            stack[i] = acc * (norm * len(ang) / (i + 1)) * mask
    return stack if cumulative else acc * norm * mask
