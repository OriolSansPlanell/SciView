"""Bug reports: a zip with the film, its problems and the versions; nothing is sent anywhere."""
import io
import json
import zipfile

import sciview as sv
from sciview import diagnostics
from sciview.cli import main


def test_report_zip(tmp_project):
    tmp_project.add("image", image="assets/ramp.png")
    tmp_project.add("image", image="assets/missing.png")
    tmp_project.save()
    z = zipfile.ZipFile(io.BytesIO(diagnostics.report(tmp_project)))
    names = set(z.namelist())
    assert {"README.txt", "info.txt", "problems.txt", "film.sciview.json"} <= names
    assert "missing.png" in z.read("problems.txt").decode()
    assert f"SciView {sv.__version__}" in z.read("info.txt").decode()
    assert len(json.loads(z.read("film.sciview.json"))["objects"]) == 2
    assert not any(n.startswith("assets/") for n in names)
    with_files = zipfile.ZipFile(io.BytesIO(diagnostics.report(tmp_project, include_assets=True)))
    assert "assets/ramp.png" in with_files.namelist()


def test_info_and_report_commands(tmp_project, tmp_path, capsys):
    tmp_project.add("image", image="assets/ramp.png")
    tmp_project.save()
    assert main(["info"]) == 0
    out = capsys.readouterr().out
    assert "ffmpeg:" in out and "plugins:" in out
    target = tmp_path / "r.zip"
    assert main(["info", "--report", str(tmp_project.path), "-o", str(target), "--assets"]) == 0
    assert "assets/ramp.png" in zipfile.ZipFile(target).namelist()
