"""Production: sound and narration, captions and contrast, transparent and cropped export, presets,
chapters and subtitle tracks, themes, the web player and PowerPoint."""
import json
import shutil
import subprocess
import zipfile

import numpy as np
import pytest
from PIL import Image

import sciview as sv
from sciview import audio, checks, narration, theme
from sciview.export import TARGETS, ExportError, chapters_metadata, crop_rect, export, srt_text
from sciview.render import FrameInfo

FFPROBE = shutil.which("ffprobe")


def probe(path):
    if FFPROBE is None:
        pytest.skip("ffprobe is not installed")
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_chapters", "-of", "json", str(path)],
                       capture_output=True, text=True)
    return json.loads(r.stdout)


def tone(path, seconds=2.0, on=((0.2, 0.8), (1.2, 1.7)), freq=330):
    t = np.arange(int(seconds * audio.RATE)) / audio.RATE
    gate = np.zeros_like(t)
    for a, b in on:
        gate[(t >= a) & (t < b)] = 1
    audio.write_wav(path, (0.4 * np.sin(2 * np.pi * freq * t) * gate).astype(np.float32))
    return path


@pytest.fixture
def film(tmp_project):
    p = tmp_project
    p.set("duration", 3)
    tone(p.base_dir / "assets" / "voice.wav")
    p.add("title", text="Intro", enter="none")
    p.add("caption", text="First words", start=0.2, end=1.5)
    p.add("voice", audio="assets/voice.wav", start=0.5, end=2.5)
    s2 = p.add_scene("Results", 2, transition="crossfade", transition_duration=0.5)
    s2.add("caption", text="Second words", start=0.2, end=1.8)
    s2.add("box", size=(30, 30, 30))
    return p


# ---------------------------------------------------------------------------------------------- sound
def test_decode_mix_waveform_and_speech(film):
    f = film.base_dir / "assets" / "voice.wav"
    x = audio.decode(f)
    assert x.shape == (2 * audio.RATE, 2) and abs(audio.duration(f) - 2.0) < 1e-3
    segs = audio.speech_segments(f)
    assert len(segs) == 2 and segs[0][0] == pytest.approx(0.2, abs=0.05) and segs[1][1] == pytest.approx(1.7, abs=0.05)
    assert audio.speech_segments(f, trim=1.0) == [pytest.approx((0.2, 0.7), abs=0.05)]
    w = audio.waveform(f, 20)
    assert len(w["peaks"]) == 20 and max(w["peaks"]) == 1.0 and w["peaks"][0] == 0.0
    clips = audio.clips(film)
    assert len(clips) == 1 and clips[0]["at"] == 0.5 and clips[0]["length"] == 2.0
    pcm = audio.mix(film)
    assert len(pcm) == int(round(film.duration * audio.RATE))
    level = np.abs(pcm[:, 0])
    assert level[int(0.3 * audio.RATE)] < 1e-4 and level[int(0.75 * audio.RATE):int(1.25 * audio.RATE)].max() > 0.3
    only = audio.mix(film, scene="scene2")
    assert len(only) == 2 * audio.RATE and np.abs(only).max() < 1e-6          # scene 2 has no sound
    film.find("voice1").set("volume", 0.0)
    assert np.abs(audio.mix(film)).max() < 1e-6


def test_mixing_soundtrack_fades_and_limiter(film):
    tone(film.base_dir / "assets" / "music.wav", seconds=6, on=((0, 6),), freq=200)
    film.set("audio", "assets/music.wav")
    film.set("audio_offset", -1.0)                                   # starts 1 s into the file
    film.find("voice1").set("fade_in", 0.5)
    film.find("voice1").set("volume", 4.0)
    pcm = audio.mix(film)
    assert np.abs(pcm).max() <= 1.0 + 1e-6                           # limited, not clipped
    assert len(audio.clips(film)) == 2 and audio.clips(film)[0]["trim"] == 1.0
    with pytest.raises(audio.AudioError):
        audio.decode(film.base_dir / "assets" / "missing.wav")
    notes = []
    film.find("voice1").set("audio", "assets/missing.wav")
    audio.mix(film, warn=notes.append)
    assert notes and "not found" in notes[0]


def test_compressed_sound_is_decoded_with_ffmpeg(film, tmp_path):
    from sciview.export import find_ffmpeg
    src = film.base_dir / "assets" / "voice.wav"
    out = tmp_path / "voice.flac"
    subprocess.run([find_ffmpeg(), "-y", "-loglevel", "error", "-i", str(src), "-c:a", "flac", str(out)], check=True)
    x = audio.decode(out)
    assert abs(len(x) / audio.RATE - 2.0) < 0.1


# ---------------------------------------------------------------------------------------------- narration
def test_script_splitting_and_captions_from_a_recording(film):
    lines = narration.split_script("Short one.\nThis line is long enough to be split, because it keeps going and "
                                   "going past the limit; it really does.\n\nLast")
    assert lines[0] == "Short one." and lines[-1] == "Last" and all(len(x) <= 84 for x in lines)
    v = film.find("voice1")
    caps = narration.captions_from_script(film, "First phrase.\nSecond phrase.", voice=v, style="box")
    assert [c.scene for c in caps] == ["scene1", "scene1"] and caps[0].props["style"] == "box"
    assert caps[0].start == pytest.approx(0.7, abs=0.06) and caps[1].start == pytest.approx(1.7, abs=0.06)
    assert narration.snap_points(film, "scene1") == pytest.approx([0.7, 1.3, 1.7, 2.2], abs=0.06)
    more = narration.captions_from_script(film, "a\nbb\nccc", scene="scene2", start=0.5)   # no recording: reading speed
    assert [round(c.start, 2) for c in more][0] == 0.5 and all(c.scene == "scene2" for c in more)
    assert all(c.end <= film.scenes[1].duration for c in more)


def test_text_to_speech_plugins(film, monkeypatch):
    def fake_speak(text, path, voice=None, rate=None):
        audio.write_wav(path, np.full(int(audio.RATE * len(text) / 12), 0.05, np.float32))
        return path
    narration.register_engine("fake", fake_speak)
    try:
        assert "fake" in narration.engines()
        out = narration.speak("Hello there", film.base_dir / "x.wav", engine="fake")
        assert out.exists()
        cap = film.find("caption1")
        clips = narration.read_aloud(film, [cap], engine="fake")
        assert len(clips) == 1 and clips[0].props["script"] == "First words" and clips[0].start == cap.start
        assert (film.base_dir / clips[0].props["audio"]).exists()
        with pytest.raises(narration.NarrationError, match="unknown engine"):
            narration.speak("x", film.base_dir / "y.wav", engine="nope")
    finally:
        narration._ENGINES.pop("fake", None)


# ---------------------------------------------------------------------------------------------- captions
@pytest.mark.parametrize("style", ["plain", "box", "band", "outline", "shadow"])
def test_caption_styles_draw(style):
    p = sv.Project(duration=2, stars=0)
    p.add("caption", text="Readable words", style=style, enter="none")
    info = FrameInfo()
    img = p.renderer().frame(1.0, 0.5, info)
    assert info.issues == []
    assert img.max() > 150
    if style == "band":
        assert np.abs(img[500, 20].astype(int) - img[200, 20].astype(int)).sum() > 3       # spans the frame


def test_contrast_and_layout_checks():
    p = sv.Project(duration=4, background_style="solid", background="#0a1430", stars=0)
    dark = p.add("caption", text="Dark words on navy", color="#18284a", position=(960, 900))
    p.add("caption", text="Readable", color="#ffffff", position=(960, 980))
    boxed = p.add("caption", text="Dark but boxed", color="#18284a", style="box", background_color="#ffffff",
                  position=(960, 200))
    p.add("text", text="Off the edge", position=(1800, 500), size=60)
    p.add("text", text="Overlap A", position=(400, 300), size=60)
    p.add("text", text="Overlap B", position=(420, 310), size=60)
    found = checks.contrast_issues(p)
    assert [f["id"] for f in found] == [dark.id] and found[0]["ratio"] < 2 and found[0]["prop"] == "color"
    assert boxed.id not in {f["id"] for f in found}
    lay = checks.layout_issues(p)
    msgs = " | ".join(i["message"] for i in lay)
    assert "outside the frame" in msgs and "overlaps" in msgs
    assert checks.ratio(checks.luminance([1, 1, 1]), checks.luminance([0, 0, 0])) == pytest.approx(21)


# ---------------------------------------------------------------------------------------------- export
def test_crop_rectangles_follow_crop_x():
    p = sv.Project()
    assert crop_rect(p, (1080, 1080)) == pytest.approx((420, 0, 1080, 1080))
    p.set("crop_x", 300)
    assert crop_rect(p, (1080, 1920))[0] == 0                         # clamped to the frame
    assert crop_rect(p, (3840, 1080)) == pytest.approx((0, 270, 1920, 540))
    assert set(TARGETS) >= {"slides", "conference", "poster", "square", "vertical", "overlay", "web"}


def test_transparent_frames_have_alpha_and_logo():
    p = sv.Project(duration=2)
    p.add("rect", position=(100, 100), size=(400, 300), fill_color="#ff0000", fill_opacity=0.5, enter="none")
    rgba = p.renderer().frame(1.0, 0.5, alpha=True)
    assert rgba.shape == (540, 960, 4)
    assert rgba[10, 900, 3] == 0                                      # no background
    inside = rgba[150, 150]
    assert 110 < inside[3] < 150 and inside[0] > 240                  # half-covered, still pure red
    full = p.frame(1.0, 0.5)
    assert full[10, 900].max() < 40


def test_export_mp4_with_sound_chapters_and_soft_subtitles(film):
    out = export(film, film.base_dir / "f.mp4", scale=0.25, workers=1, subtitles="soft")
    d = probe(out)
    kinds = [s["codec_type"] for s in d["streams"]]
    assert kinds.count("video") == 1 and "audio" in kinds and "subtitle" in kinds
    assert [c["tags"]["title"] for c in d["chapters"]] == ["Scene 1", "Results"]
    assert float(d["chapters"][1]["start_time"]) == pytest.approx(2.75, abs=0.02)
    srt = (film.base_dir / "f.srt").read_text()
    assert "First words" in srt and "00:00:02,700 --> 00:00:04,300" in srt
    assert (film.base_dir / "f.vtt").read_text().startswith("WEBVTT")


def test_transparent_and_cropped_exports(film):
    mov = export(film, film.base_dir / "o.mov", scale=0.25, workers=1, transparent=True, end=1)
    v = [s for s in probe(mov)["streams"] if s["codec_type"] == "video"][0]
    assert v["codec_name"] == "prores" and v["pix_fmt"].startswith("yuva444")
    frames = export(film, film.base_dir / "png", scale=0.1, workers=1, transparent=True, end=0.2)
    first = sorted(frames.glob("*.png"))[0]
    assert Image.open(first).mode == "RGBA"
    sq = export(film, film.base_dir / "sq", target="square", scale=0.25, workers=1, end=0.5)
    v = [s for s in probe(sq)["streams"] if s["codec_type"] == "video"][0]
    assert sq.suffix == ".mp4" and (v["width"], v["height"]) == (270, 270)
    still = export(film, film.base_dir / "poster", target="poster", scale=0.1, time=1.0)
    assert still.suffix == ".png" and Image.open(still).size == (384, 216)          # a tenth of 4K
    with pytest.raises(ExportError, match="cannot be transparent"):
        export(film, film.base_dir / "x.mp4", transparent=True)
    with pytest.raises(ExportError, match="subtitles must be"):
        export(film, film.base_dir / "x.mp4", subtitles="loud")


def test_scene_export_and_parallel_workers_with_options(film):
    one = export(film, film.base_dir / "s2.mp4", scene="Results", scale=0.1, workers=1)
    d = probe(one)
    v = [s for s in d["streams"] if s["codec_type"] == "video"][0]
    assert float(v["duration"]) == pytest.approx(2.0, abs=0.1) and not d.get("chapters")
    par = export(film, film.base_dir / "par", scale=0.1, workers=2, transparent=True, end=0.3)
    seq = export(film, film.base_dir / "seq", scale=0.1, workers=1, transparent=True, end=0.3)
    for a, b in zip(sorted(par.glob("*.png")), sorted(seq.glob("*.png"))):
        assert np.array_equal(np.asarray(Image.open(a)), np.asarray(Image.open(b)))


def test_metadata_helpers():
    meta = chapters_metadata([(0, 2.5, "Intro; part=1"), (2.5, 6, "Results")], 1.0, 5.0)
    assert meta.startswith(";FFMETADATA1") and "START=1500" in meta and "title=Intro\\; part\\=1" in meta
    assert srt_text([(0.5, 1.0, "a"), (9, 10, "late")], 0.0, 5.0).count("-->") == 1


# ---------------------------------------------------------------------------------------------- themes
def test_builtin_themes_apply_and_restyle(film):
    assert list(theme.builtin())[0] == "dark" and {"light", "contrast"} <= set(theme.builtin())
    cap = film.find("caption1")
    locked = film.find("caption2")
    locked.locked = True
    notes = film.apply_theme("contrast")
    assert notes == [] and film.settings["theme"] == "High contrast" and film.settings["background"] == "#000000"
    assert cap.props["style"] == "box" and locked.props.get("style", "plain") == "plain"
    assert film.add("caption").props["style"] == "box"                    # new objects get the styles
    assert film.add("caption", style="plain").props["style"] == "plain"   # given values win
    film.apply_theme("dark", restyle=False)
    assert film.styles == {} and cap.props["style"] == "box"
    with pytest.raises(theme.ThemeError):
        film.apply_theme("no-such-theme")


def test_theme_files_with_logo_round_trip(film, tmp_path):
    logo = Image.new("RGBA", (200, 80), (255, 207, 74, 255))
    logo.save(film.base_dir / "assets" / "logo.png")
    film.set("logo", "assets/logo.png")
    film.set("logo_position", "top-left")
    film.palette["gold"] = "#123456"
    path = film.save_theme(tmp_path / "kit" / "group.json", name="Our group")
    assert path.name == "group.sciview-theme.json" and (path.parent / "logo.png").exists()
    other = sv.Project(path=tmp_path / "other" / "film.sciview.json", duration=2)
    assert other.apply_theme(path) == []
    assert other.settings["logo"] == "assets/theme/logo.png" and other.palette["gold"] == "#123456"
    assert (tmp_path / "other" / "assets" / "theme" / "logo.png").exists()
    img = other.frame(1.0, 0.5)
    assert tuple(img[30, 30]) == pytest.approx((255, 207, 74), abs=30)            # the logo, top left
    one_file = theme.embed_files(film, theme.from_project(film, "Embedded"))
    assert one_file["logo"]["image"].startswith("data:image/png;name=logo.png;base64,")
    third = sv.Project(path=tmp_path / "third" / "film.sciview.json")
    third.apply_theme(one_file)
    assert (tmp_path / "third" / "assets" / "theme" / "logo.png").exists()
    film.set("logo_scenes", "first")
    a, b = film.frame(1.0, 0.25), film.frame(4.0, 0.25)
    assert a[8:16, 8:16].mean() > b[8:16, 8:16].mean() + 50            # only the first scene shows it
    bad = tmp_path / "bad.sciview-theme.json"
    bad.write_text('{"name": "x"}')
    with pytest.raises(theme.ThemeError, match="not a SciView theme"):
        theme.load(bad)


# ---------------------------------------------------------------------------------------------- web page, PowerPoint
def test_web_player_page(film):
    page = export(film, film.base_dir / "player.html", scale=0.1, workers=1)
    html = page.read_text()
    data = json.loads(html.split('<script id="payload" type="application/json">')[1].split("</script>")[0])
    assert data["video"] and data["vtt"].startswith("WEBVTT") and data["bundle"]
    assert html.count('data-t="') == 2 and "Results" in html
    with zipfile.ZipFile(__import__("io").BytesIO(__import__("base64").b64decode(data["bundle"]))) as z:
        names = z.namelist()
    assert any(n.endswith(".sciview.json") for n in names) and "assets/voice.wav" in names


def test_powerpoint_one_slide_per_scene(film):
    pptx = pytest.importorskip("pptx")
    film.scenes[0].notes = "Start with the question."
    film.find("voice1").set("script", "These are the first words.")
    out = export(film, film.base_dir / "talk.pptx", scale=0.1, workers=1)
    prs = pptx.Presentation(str(out))
    slides = list(prs.slides)
    assert len(slides) == 2
    assert slides[0].notes_slide.notes_text_frame.text == "Start with the question.\n\nThese are the first words."
    assert slides[1].notes_slide.notes_text_frame.text == "Second words"
    xml = slides[0]._element.xml
    assert 'cmd="playFrom(0.0)"' in xml and 'nodeType="afterEffect"' in xml
    with zipfile.ZipFile(out) as z:
        assert sum(1 for n in z.namelist() if n.endswith(".mp4")) == 2


# ---------------------------------------------------------------------------------------------- editor server
def test_editor_server_routes_for_production(film):
    import threading
    import urllib.request

    from sciview.server import make_server
    film.save()
    srv = make_server(film, film.base_dir, port=0)
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def get(path):
        with urllib.request.urlopen(base + path, timeout=60) as r:
            return r.headers.get("Content-Type"), r.read()

    def post(path, body):
        r = urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST",
                                   headers={"X-SciView": "1", "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read())
    try:
        ct, raw = get("/api/waveform?path=assets/voice.wav&bins=50")
        w = json.loads(raw)
        assert len(w["peaks"]) == 50 and len(w["segments"]) == 2
        ct, wav = get("/api/mix")
        assert ct == "audio/wav" and wav[:4] == b"RIFF"
        themes = json.loads(get("/api/themes")[1])
        assert themes["themes"][0]["name"] == "dark"
        st = json.loads(get("/api/state")[1])
        assert "square" in st["targets"] and "pptx" in st["formats"] and st["schema"]["transitions"]["crossfade"]
        r = post("/api/transform", {"op": "apply_theme", "project": film.to_json(), "theme": "light"})
        assert r["project"]["settings"]["theme"] == "Light paper"
        r = post("/api/transform", {"op": "script_captions", "project": film.to_json(), "text": "One.\nTwo.",
                                    "scene": "scene1", "voice": "voice1"})
        assert r["added"] == 2
        assert json.loads(get("/api/checks")[1])["issues"] == []
        ct, img = get("/api/frame?t=0.5&scale=0.25&scene=scene2")
        assert ct == "image/jpeg"
        try:
            post("/api/transform", {"op": "apply_theme", "project": film.to_json(), "theme": "../../etc/passwd"})
            raise AssertionError("a theme outside the project folder must be refused")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
    finally:
        srv.session.stop.set()
        srv.shutdown()
        srv.server_close()
