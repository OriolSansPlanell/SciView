"""Pinhole camera with z up. Units are whatever the scene uses (cm in the examples)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


def _norm(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else v


@dataclass
class Camera:
    """Projects 3D points to output pixels.

    ``offset`` shifts the image centre in output pixels, which is handy for
    putting a 3D scene on one side of the frame and 2D panels on the other.
    """

    eye: np.ndarray
    target: np.ndarray
    width: int
    height: int
    fov: float = 35.0  # vertical field of view, degrees
    offset: tuple[float, float] = (0.0, 0.0)
    up: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))
    near: float = 1e-3

    def __post_init__(self) -> None:
        self.eye = np.asarray(self.eye, np.float64)
        self.target = np.asarray(self.target, np.float64)
        f = _norm(self.target - self.eye)
        up = np.asarray(self.up, np.float64)
        if abs(float(np.dot(f, _norm(up)))) > 0.999:  # looking straight up/down
            up = np.array([0.0, 1.0, 0.0])
        r = _norm(np.cross(f, up))
        u = np.cross(r, f)
        self.forward, self.right, self.upv = f, r, u
        self.focal = (self.height / 2.0) / math.tan(math.radians(max(self.fov, 1e-3)) / 2.0)
        self.cx = self.width / 2.0 + self.offset[0]
        self.cy = self.height / 2.0 + self.offset[1]

    @classmethod
    def orbit(cls, target, distance: float, azimuth: float, elevation: float, fov: float,
              width: int, height: int, offset=(0.0, 0.0)) -> Camera:
        """Camera on a sphere around ``target``. Azimuth from +x towards +y, elevation up from the xy plane (degrees)."""
        az, el = math.radians(azimuth), math.radians(elevation)
        d = np.array([math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)])
        target = np.asarray(target, np.float64)
        return cls(eye=target + max(distance, 1e-6) * d, target=target, width=width,
                   height=height, fov=fov, offset=offset)

    def to_camera(self, pts) -> np.ndarray:
        """World points (N,3) to camera coordinates (x right, y up, z forward)."""
        rel = np.asarray(pts, np.float64).reshape(-1, 3) - self.eye
        return np.stack([rel @ self.right, rel @ self.upv, rel @ self.forward], axis=1)

    def project(self, pts) -> tuple[np.ndarray, np.ndarray]:
        """Return (xy pixels (N,2), depth (N,)). Points behind the camera get depth <= near."""
        c = self.to_camera(pts)
        z = c[:, 2]
        zs = np.where(z > self.near, z, self.near)
        x = self.cx + self.focal * c[:, 0] / zs
        y = self.cy - self.focal * c[:, 1] / zs
        return np.stack([x, y], axis=1), z

    def depth(self, p) -> float:
        return float((np.asarray(p, np.float64) - self.eye) @ self.forward)

    def pixel_size(self, p, length: float) -> float:
        """Approximate size in pixels of a world ``length`` at point ``p``."""
        z = self.depth(p)
        return self.focal * length / max(z, self.near)


def rotation_matrix(rx: float, ry: float, rz: float) -> np.ndarray:
    """Rotation from Euler angles in degrees, applied x, then y, then z."""
    ax, ay, az = (math.radians(a) for a in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx
