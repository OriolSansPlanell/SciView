# Getting started

## Install

SciView needs Python 3.9 or newer. In a terminal:

```bash
pip install "sciview[math] @ git+https://github.com/OriolSansPlanell/SciView"
```

This installs SciView with everything it needs, including an ffmpeg binary for video export. The `math` extra
adds matplotlib, which renders LaTeX equations. If you use conda, install into your environment with the
same `pip` command.

Check the installation:

```bash
sciview info
```

It prints the versions, where ffmpeg was found and how many processor cores rendering will use.

## Your first film in the editor

1. Make a folder for the film and open a terminal there.
2. Run `sciview edit`. Your browser opens the editor at `http://localhost:8765`.
3. Pick **Imaging beamline**. The template plays a 16-second film; press <kbd>Space</kbd> to watch it.
4. Click the gold title in the preview. Its properties appear on the right. Change the text.
5. Drag the playhead to 6 s, click **Caption** in the list on the left and type your own narration. Drag
   the end of its clip on the timeline to set how long it stays.
6. Select **Detector**, open the **Image** group and upload one of your own radiographs. Set **Counts** to 30
   and keyframe **Build-up** from 0 to 1 to see it appear neutron by neutron.
7. Press <kbd>Ctrl</kbd>+<kbd>S</kbd> to save. Your film is `<name>.sciview.json`; the image you uploaded is in
   `assets/`.
8. Click **Export video**, keep **MP4** and press **Export**. The file appears next to your project and can be
   downloaded from the dialog.

Close the editor with <kbd>Ctrl</kbd>+<kbd>C</kbd> in the terminal. Open the film again with
`sciview edit <name>.sciview.json`.

## Your first film in Python

```python
import sciview as sv

film = sv.Project(title="Hello", duration=5)
film.add("title", text="Hello, neutrons", subtitle="My first SciView film")
film.add("box", center=(0, 0, 0), size=(20, 20, 20), edge_color="gold", start=1, enter="draw")
film.camera.key("azimuth", 0, -70).key("azimuth", 5, -30)
film.render("hello.mp4")
```

See the [Python guide](python-api.md) for data-driven films.

## Where to go next

* [The editor](editor.md): every panel and shortcut.
* [Object reference](objects.md): what each object can do.
* [Rendering and sharing](rendering.md): formats for slides, web and video editors; 4K and poster stills.
