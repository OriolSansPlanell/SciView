"""Visual regression: every template, at two moments, must still look like its reference frame.

The references are in tests/golden/frames; after a change meant to alter the look, regenerate them with
``python tools/update_golden_frames.py`` and look at the new pictures before committing. The comparison
allows the small differences between platforms (anti-aliasing, font hinting) but not a changed picture.
"""
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import update_golden_frames as G  # noqa: E402

CASES = list(G.cases())
MIN_PSNR = 36.0          # dB at quarter size; a frame shifted by 4 px scores 22-33


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """PSNR at a quarter of the size: anti-aliasing and font-hinting differences between platforms and library
    versions average out, while a moved, missing or recoloured object still shows clearly."""
    import cv2
    size = (a.shape[1] // 4, a.shape[0] // 4)
    return psnr(cv2.resize(a, size, interpolation=cv2.INTER_AREA), cv2.resize(b, size, interpolation=cv2.INTER_AREA))


def test_every_template_has_references():
    assert len(CASES) >= 18
    missing = [n for n, _t, _w in CASES if not (G.OUT / f"{n}.png").exists()]
    assert missing == [], "run: python tools/update_golden_frames.py"


@pytest.mark.parametrize("name,template,t", CASES, ids=[c[0] for c in CASES])
def test_frames_match_the_references(name, template, t, tmp_path):
    ref = np.asarray(Image.open(G.OUT / f"{name}.png").convert("RGB"))
    got = G.render(template, t)
    assert got.shape == ref.shape
    score = similarity(got, ref)
    if score < MIN_PSNR:
        Image.fromarray(np.concatenate([ref, got], 1)).save(tmp_path / f"{name}_ref_vs_now.png")
    assert score >= MIN_PSNR, f"{name}: {score:.1f} dB (see {tmp_path})"


def test_the_comparison_notices_a_real_change():
    ref = np.asarray(Image.open(G.OUT / f"{CASES[0][0]}.png").convert("RGB")).copy()
    moved = np.roll(ref, 4, axis=1)
    assert similarity(ref, moved) < MIN_PSNR - 2
    recoloured = ref.copy()
    recoloured[60:120, 100:200] = recoloured[60:120, 100:200][..., ::-1]     # a region changes colour
    assert similarity(ref, recoloured) < MIN_PSNR or np.array_equal(recoloured, ref)
    noisy = np.clip(ref.astype(int) + np.random.default_rng(0).integers(-6, 7, ref.shape), 0, 255).astype(np.uint8)
    assert similarity(ref, noisy) > MIN_PSNR
