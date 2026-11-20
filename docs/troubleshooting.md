# Troubleshooting

**`sciview: command not found`**
The scripts folder of your Python is not on your PATH. Use `python -m sciview edit` instead, or activate the
environment you installed into.

**The browser does not open**
Open the address printed in the terminal (`http://localhost:8765/`) yourself. If the port is busy, SciView
tries the next ones and prints the one it used; choose one with `--port 9000`.

**"ffmpeg was not found"**
SciView normally uses the ffmpeg that comes with the `imageio-ffmpeg` package. Reinstall it with
`pip install --force-reinstall imageio-ffmpeg`, install ffmpeg yourself (`brew install ffmpeg`,
`sudo apt install ffmpeg`, `winget install ffmpeg`) or point `SCIVIEW_FFMPEG` to an ffmpeg executable. PNG
frames can always be exported.

**Equations show as plain text**
Equation objects need matplotlib: `pip install matplotlib`. If matplotlib is installed, the "things to check"
list under the preview shows the parse error for the formula (mathtext supports most, not all, of LaTeX
math).

**Rendering from a script is slow or prints "parallel rendering failed"**
Rendering starts worker processes. In unusual environments (some IDE consoles, restricted clusters) that can
fail; SciView then continues in one process. Pass `workers=1` to skip the attempt.

**Images look blurry on a detector screen**
Screens use up to 640 px of the image so previews stay fast. That is plenty at 1920 x 1080; for a close-up of
a large image, use an Image object (up to 1600 px) or crop the image first.

**Text uses the wrong font or shows boxes**
Poppins and Inter are bundled; set another font in the film settings by choosing "Custom font file" and giving
the path to a `.ttf` or `.otf` file. Characters missing from the chosen font are drawn with Inter.

**I edited the project file by hand and the editor did not notice**
The editor keeps the film in memory. Use **Open** to load the file again.

**Where are my uploaded files?**
In the `assets` folder next to the project file. Copy the project file and that folder together.

**Reporting a bug**
Run `sciview info` and include its output, the project file (and assets if you can) and what you expected, in
an issue at https://github.com/OriolSansPlanell/SciView/issues.
