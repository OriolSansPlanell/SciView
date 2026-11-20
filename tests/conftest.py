import shutil

import pytest

import sciview as sv


@pytest.fixture
def tmp_project(tmp_path):
    """A small project saved in a temporary folder, with one image and one table asset."""
    import numpy as np
    from PIL import Image

    (tmp_path / "assets").mkdir()
    img = (np.linspace(0, 255, 64 * 64).reshape(64, 64)).astype("uint8")
    Image.fromarray(img).save(tmp_path / "assets" / "ramp.png")
    (tmp_path / "assets" / "data.csv").write_text("x,y,z\n0,0,0\n1,1,1\n2,4,2\n3,9,3\n", encoding="utf-8")
    p = sv.Project(path=tmp_path / "film.sciview.json", duration=2.0, title="Test film")
    return p


@pytest.fixture
def has_ffmpeg():
    from sciview.export import find_ffmpeg
    try:
        find_ffmpeg()
    except Exception:
        pytest.skip("ffmpeg not available")
    return True


def pytest_report_header(config):
    return f"sciview {sv.__version__}; ffmpeg: {shutil.which('ffmpeg') or 'via imageio-ffmpeg or missing'}"
