# Rendering and sharing

## Formats

| Format | Use it for | Notes |
| --- | --- | --- |
| **MP4** (H.264) | PowerPoint, Keynote, Google Slides, web, social media | Plays everywhere. Quality via CRF (14 very high, 18 high, 23 standard). |
| **WebM** (VP9) | Web pages | Smaller than MP4 at the same quality; slower to encode. |
| **ProRes 422 HQ** (.mov) | Premiere, Final Cut, DaVinci Resolve | Large files, no visible compression, edits smoothly. ProRes 4444 with alpha when transparent. |
| **GIF** | README files, chat, quick previews | 15 fps and half size by default; keep it short. |
| **PNG frames** | Compositing, custom encoding, single frames | One numbered PNG per frame in a folder; RGBA when transparent. |
| **Web page** (.html) | Group pages, supplementary material, mailing a film | The video, its captions, a chapter menu and the project in one file. |
| **PowerPoint** (.pptx) | Talks | One slide per scene with its clip; needs `pip install "sciview[pptx]"`. |

From the command line:

```bash
sciview render film.sciview.json                       # film.mp4 next to the project
sciview render film.sciview.json -o film.webm
sciview render film.sciview.json -o film.gif --scale 0.4 --fps 12
sciview render film.sciview.json -o frames/ --start 3 --end 5
sciview render film.sciview.json --scale 2 --crf 16    # 3840 x 2160
sciview render film.sciview.json -o talk.pptx          # one slide per scene
sciview render film.sciview.json -o film.html          # a web page with a player
```

## Presets

`--for` (or a preset button in the editor's export dialog) chooses the format, size and quality for a
destination:

| Preset | Output |
| --- | --- |
| `slides` | MP4, 1920 × 1080 |
| `conference` | MP4, 3840 × 2160 |
| `poster` | one PNG frame, 3840 × 2160 (`--time` picks the moment) |
| `square` | MP4, 1080 × 1080, cut from the middle of the frame |
| `vertical` | MP4, 1080 × 1920, cut from the middle of the frame |
| `overlay` | ProRes 4444 with transparency |
| `web` | the web page |
| `preview` | GIF, 640 × 360, 15 fps |

```bash
sciview render film.sciview.json --for vertical -o phone.mp4   # 1080 x 1920
sciview render film.sciview.json --for poster --time 12.5  # one 4K frame
sciview render film.sciview.json --for square --scale 0.5  # half the preset's size: 540 x 540
```

With a preset, `--scale` is a factor of the preset's size. Square and vertical films keep the middle of the
frame; set **Crop centre** (`crop_x`, in design pixels) in the film settings to keep another part, and use
the square and vertical guides in the editor to see what stays. Layout for the full frame first, with the
essentials in the middle third.

## Scenes and chapters

Each scene marked as a chapter becomes a chapter marker in MP4, WebM and ProRes files: video players (VLC,
QuickTime, mpv, most web players) list them and jump to them. `--no-chapters` leaves them out.
`--scene NAME` renders one scene on its own, from its start to its end, with its sound:

```bash
sciview render film.sciview.json --scene Results -o results.mp4
```

## Transparent video

`--transparent` (or **Transparent background** in the export dialog) drops the background, starfield and
vignette, so the film can be laid over slides, photographs or lab footage. Only some formats carry
transparency:

* **ProRes 4444** `.mov`: for video editors (Premiere, Final Cut, DaVinci Resolve) and Keynote.
* **WebM** (VP9 with alpha): for web pages; Chrome and Firefox play it with transparency.
* **PNG frames**: RGBA images for compositing.

Glow and soft edges keep their transparency, so they blend with whatever is behind them.

```bash
sciview render film.sciview.json --transparent -o overlay.mov
```

## Resolution and layout

Layout is in pixels of the film size set in the film settings (1920 x 1080 by default). `--scale` renders the
same layout at another resolution: 0.5 for drafts, 2 for 4K. For square or vertical versions of a 16:9 film
use the presets below; for a film designed square or vertical from the start, change the width and height in
the film settings first (positions are in those units).

## Speed

Each frame is independent, so `render` uses all processor cores but one (`--workers` to change that). As a
guide, the templates take 30 to 180 ms per 1920 x 1080 frame on one core, so a 30-second film at 30 fps
renders in about a minute on an 8-core laptop. Draft at `--scale 0.5` first.

Big frames need memory: about 1 GB per render process at 4K and 3.4 GB at 8K. SciView therefore starts fewer
processes when they would need more than 60 % of the computer's memory, and says so.

### Rendering on several computers

A long film at 4K can be shared between computers (or cluster nodes) and put together afterwards:

```bash
sciview render talk.sciview.json --for conference --part 1/4      # talk_conference.part1of4.mp4
sciview render talk.sciview.json --for conference --part 2/4      # on another computer, and so on
sciview join talk.sciview.json talk_conference.part*of4.mp4 -o talk_4k.mp4 --subtitles soft
```

Each piece holds only video; `join` puts them together without re-encoding and adds the sound, the chapter
markers and the subtitles. Render every piece with the same options. In Python:
`export(film, "p1.mp4", part=(1, 4))` and `sciview.export.join(film, pieces, "film.mp4")`.

The editor's preview has three qualities: **Draft** (480 px), **Normal** (960 px) and **Full** (1920 px).
During playback it switches to a faster quality automatically; pause to see the chosen quality.

Objects that look the same from one frame to the next (no running keyframe or effect, no dependence on
time, and for 3D objects a still camera) are drawn once into a cached layer and reused, both in the preview
and when exporting. The cache never changes a pixel: the test suite checks every template against an
uncached render. It notices changed values, palette and files on disk, and keeps at most 256 MB per
renderer. While you pause, the editor also renders the next half second in the background, and while you
play the next three seconds, so scrubbing and playback show cached frames.

Some objects take more work: an isosurface of a large volume is computed once per threshold (lower
**Max size** or raise **Smoothness** while drafting), and a Matplotlib figure redrawn by a Python function runs
that function at every frame. Films with such figures render in a single process, because the function lives
in your script and cannot be sent to other processes. Mark a figure that does not change with `still=True` so
it is drawn once and cached.

## Sound

Set **Audio** in the film settings (or drop an audio file on the preview) to add music or narration under the
whole film; **Audio offset** delays it. Voice clips (recorded in the editor, or any audio file) play inside
their scene. Exports mix the soundtrack and every voice clip, with their volumes and fades, and keep the mix
from clipping; MP4, WebM, ProRes, the web page and the PowerPoint clips include it. `--no-audio` leaves it
out. The video always keeps the film's duration.

## Subtitles and accessibility

Captions are narration, and there are four ways to export them (`--subtitles MODE`, or **Captions** in the
export dialog):

| Mode | Captions are |
| --- | --- |
| `off` | drawn in the picture only |
| `file` | drawn, and written next to the video as `.srt` and `.vtt` files (YouTube, most players and slide tools read them) |
| `soft` | a subtitle track in the video that viewers can switch on and off, not drawn |
| `embed` | drawn, and also a subtitle track |

`sciview subtitles film.sciview.json` writes only the `.srt` file. Captions keep everything readable for
people who watch with the sound off, which is how many talk recordings are watched; give them a **box** or
**band** style over busy pictures. `sciview check --frames` (or **Check readability and layout** in the
editor) finds text that does not stand out enough from what is behind it, measured as the contrast ratio used
by accessibility guidelines (4.5 for normal text), text that overlaps and objects outside the frame.

## Stills for papers and posters

```bash
sciview still film.sciview.json -t 6.5 --scale 2      # 3840 px wide PNG
```

In the editor, the camera button under the preview saves the current frame at full size. For printed figures,
switch the film to **Light for papers** in the film settings: white background, darker palette, less glow.

## A web page with the film

`-o film.html` (or the **Web page** preset) writes one HTML file holding the video, a poster frame, the
captions as a track viewers can switch off, a chapter menu and a download button for the project with its
files (a zip that `sciview edit` opens once unpacked). It needs nothing beside it, so it can be mailed, put on
a group page or added to a paper's supplementary material. Videos over 200 MB are written next to the page
instead, and projects whose files exceed 50 MB are left out of the page.

## PowerPoint

`-o talk.pptx` writes one slide per scene, each with that scene's clip filling the slide and set to play when
the slide appears. The speaker notes hold the scene's notes, then what its voice clips say (their scripts),
or its captions. Install the extra first: `pip install "sciview[pptx]"`. Rearrange or add slides as you like
afterwards; the clips are ordinary videos.

## ffmpeg and its licence

SciView writes videos with [ffmpeg](https://ffmpeg.org), which it runs as a separate program: the one from the
`imageio-ffmpeg` package by default, or the one on your PATH, or the one `SCIVIEW_FFMPEG` points to. SciView
itself does not contain ffmpeg and stays under the MIT licence, and the licence of ffmpeg does not apply to
the films you make.

The usual ffmpeg builds include the x264 encoder and are then under the GPL. If your institution needs an
LGPL-only ffmpeg, point `SCIVIEW_FFMPEG` to one: SciView notices that x264 is missing and encodes MP4 files with
OpenH264, the operating system's encoder (macOS, Windows) or a graphics card's, and as a last resort with
MPEG-4 part 2, which every player reads. ProRes, WebM (VP9), GIF and PNG do not depend on x264.

## Putting videos in slides

* **PowerPoint**: Insert > Video > This Device, choose the MP4. Set it to start automatically if you want it
  to play when the slide appears.
* **Keynote**: drag the MP4 onto the slide.
* **Google Slides**: upload the MP4 to Google Drive first, then Insert > Video > Google Drive.
* **LaTeX Beamer**: the `media9` or `multimedia` packages embed MP4s; many people instead link to the file.

Keep the film's resolution at 1920 x 1080 for 16:9 slides.
