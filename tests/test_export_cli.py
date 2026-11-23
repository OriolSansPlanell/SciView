import json
import subprocess
import sys

import pytest
from _media import media_info, video

import sciview as sv
from sciview.cli import main
from sciview.export import ExportError, detect_format, ffmpeg_command


def small_film(path):
    p = sv.Project(path=path, duration=1.0, fps=10, width=320, height=180)
    p.add("box", label="box")
    p.add("caption", text="Hello", start=0, end=1)
    p.save()
    return p


def probe(path):
    from sciview.export import find_ffmpeg
    ff = find_ffmpeg()
    out = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True)
    return out.stderr


def test_detect_format():
    assert detect_format("a.mp4") == "mp4"
    assert detect_format("frames/") == "png"
    with pytest.raises(ExportError):
        detect_format("a.docx")


def test_ffmpeg_command_has_quality_and_audio(tmp_path):
    cmd = ffmpeg_command("ffmpeg", "mp4", (320, 180), 30, tmp_path / "o.mp4", crf=20, audio=tmp_path / "a.wav",
                         audio_offset=1.5, duration=4)
    s = " ".join(cmd)
    assert "-crf 20" in s and "yuv420p" in s and "-itsoffset 1.500" in s and "-c:a aac" in s and "-t 4.000" in s


def test_export_mp4_gif_png(tmp_path, has_ffmpeg):
    p = small_film(tmp_path / "f.sciview.json")
    calls = []
    mp4 = p.render(tmp_path / "f.mp4", workers=1, progress=lambda d, t, e: calls.append((d, t)), subtitles=True)
    assert mp4.stat().st_size > 1000 and calls[-1] == (10, 10)
    assert "320x180" in probe(mp4)
    assert (tmp_path / "f.srt").read_text().startswith("1\n00:00:00,000")
    gif = p.render(tmp_path / "f.gif", workers=1, scale=0.5)
    assert gif.read_bytes()[:3] == b"GIF"
    frames = p.render(tmp_path / "frames", workers=1, start=0.5)
    assert len(list(frames.glob("*.png"))) == 5


@pytest.mark.slow
def test_parallel_export_matches_frame_count(tmp_path, has_ffmpeg):
    p = small_film(tmp_path / "f.sciview.json")
    out = p.render(tmp_path / "par.mp4", workers=2)
    assert out.exists() and "Duration: 00:00:01.00" in probe(out)


def test_cli_new_check_still_render(tmp_path, has_ffmpeg, capsys):
    f = tmp_path / "demo.sciview.json"
    assert main(["new", str(f), "--template", "title_card"]) == 0
    assert json.loads(f.read_text())["objects"]
    assert main(["check", str(f)]) == 0
    assert main(["still", str(f), "-t", "3", "-o", str(tmp_path / "s.png"), "--scale", "0.25"]) == 0
    assert (tmp_path / "s.png").exists()
    assert main(["render", str(f), "-o", str(tmp_path / "d.mp4"), "--scale", "0.2", "--end", "0.5", "--workers", "1", "-q"]) == 0
    assert (tmp_path / "d.mp4").exists()
    assert main(["subtitles", str(f), "-o", str(tmp_path / "d.srt")]) == 0
    assert main(["templates"]) == 0
    assert main(["info"]) == 0
    assert "title_card" in capsys.readouterr().out


def test_cli_errors_are_friendly(tmp_path, capsys):
    assert main(["check", str(tmp_path / "missing.json")]) == 2
    assert main(["new", str(tmp_path / "x"), "--template", "nope"]) == 1


def test_module_entry_point():
    out = subprocess.run([sys.executable, "-m", "sciview", "--version"], capture_output=True, text=True)
    assert out.returncode == 0 and sv.__version__ in out.stdout


def test_cli_presets_scenes_themes_and_frame_checks(tmp_path, has_ffmpeg, capsys):
    f = tmp_path / "talk.sciview.json"
    assert main(["new", str(f), "--template", "explainer"]) == 0
    p = sv.load(f)
    assert len(p.scenes) == 3
    assert main(["render", str(f), "--for", "poster", "--time", "6", "--scale", "0.1", "-o", str(tmp_path / "p")]) == 0
    assert (tmp_path / "p.png").exists()
    assert main(["render", str(f), "--for", "vertical", "--scene", "Result", "--scale", "0.1", "--workers", "1",
                 "-q", "-o", str(tmp_path / "v.mp4")]) == 0
    assert video(media_info(tmp_path / "v.mp4"))["size"] == (108, 192)
    assert main(["render", str(f), "--transparent", "--scale", "0.1", "--end", "0.2", "--workers", "1", "-q",
                 "-o", str(tmp_path / "frames")]) == 0
    assert any((tmp_path / "frames").glob("*.png"))
    assert main(["render", str(f), "-o", str(tmp_path / "x.mp4"), "--transparent"]) == 1
    capsys.readouterr()
    assert main(["theme", "--list"]) == 0
    assert "contrast" in capsys.readouterr().out
    assert main(["theme", str(f), "--apply", "light"]) == 0
    assert sv.load(f).settings["theme"] == "Light paper"
    assert main(["theme", str(f), "--save", str(tmp_path / "kit"), "--name", "Lab"]) == 0
    assert json.loads((tmp_path / "kit.sciview-theme.json").read_text())["name"] == "Lab"
    assert main(["check", str(f), "--frames"]) == 0
    assert main(["theme", str(f), "--apply", str(tmp_path / "nope.json")]) == 2
    assert "nope.json" in capsys.readouterr().err
