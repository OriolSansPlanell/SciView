# Rendering and sharing

## Formats

| Format | Use it for | Notes |
| --- | --- | --- |
| **MP4** (H.264) | PowerPoint, Keynote, Google Slides, web, social media | Plays everywhere. Quality via CRF (14 very high, 18 high, 23 standard). |
| **WebM** (VP9) | Web pages | Smaller than MP4 at the same quality; slower to encode. |
| **ProRes 422 HQ** (.mov) | Premiere, Final Cut, DaVinci Resolve | Large files, no visible compression, edits smoothly. |
| **GIF** | README files, chat, quick previews | 15 fps and half size by default; keep it short. |
| **PNG frames** | Compositing, custom encoding, single frames | One numbered PNG per frame in a folder. |

From the command line:

```bash
sciview render film.sciview.json                       # film.mp4 next to the project
sciview render film.sciview.json -o film.webm
sciview render film.sciview.json -o film.gif --scale 0.4 --fps 12
sciview render film.sciview.json -o frames/ --start 3 --end 5
sciview render film.sciview.json --scale 2 --crf 16    # 3840 x 2160
```

## Resolution and layout

Layout is in pixels of the film size set in the film settings (1920 x 1080 by default). `--scale` renders the
same layout at another resolution: 0.5 for drafts, 2 for 4K. To make a square or vertical film, change the
width and height in the film settings first; positions are in those units.

## Speed

Each frame is independent, so `render` uses all processor cores but one (`--workers` to change that). As a
guide, a busy 1920 x 1080 frame takes 0.2 to 0.6 s on one core. A 30-second film at 30 fps on an 8-core laptop
renders in about a minute or two. Draft at `--scale 0.5` first.

The editor's preview has three qualities: **Draft** (480 px), **Normal** (960 px) and **Full** (1920 px).
During playback it switches to a faster quality automatically; pause to see the chosen quality.

Objects that look the same from one frame to the next (no running keyframe or effect, no dependence on
time, and for 3D objects a still camera) are drawn once into a cached layer and reused, both in the preview
and when exporting. The cache never changes a pixel: the test suite checks every template against an
uncached render. It notices changed values, palette and files on disk, and keeps at most 256 MB per
renderer. While you pause, the editor also renders the next half second in the background, and while you
play the next three seconds, so scrubbing and playback show cached frames.

## Sound

Set **Audio** in the film settings (or drop an audio file on the preview) to add narration or music; **Audio
offset** delays it. The editor plays it in sync with the preview, and MP4, WebM and ProRes exports include it.
The video always keeps the film's duration.

## Subtitles and accessibility

Captions are narration. `sciview subtitles film.sciview.json` (or the checkbox in the export dialog) writes
them as an `.srt` file that video players, YouTube and most slide tools can show. Captions also stay readable
for people who watch with the sound off, which is how many talk recordings are watched.

## Stills for papers and posters

```bash
sciview still film.sciview.json -t 6.5 --scale 2      # 3840 px wide PNG
```

In the editor, the camera button under the preview saves the current frame at full size. For printed figures,
switch the film to **Light for papers** in the film settings: white background, darker palette, less glow.

## Putting videos in slides

* **PowerPoint**: Insert > Video > This Device, choose the MP4. Set it to start automatically if you want it
  to play when the slide appears.
* **Keynote**: drag the MP4 onto the slide.
* **Google Slides**: upload the MP4 to Google Drive first, then Insert > Video > Google Drive.
* **LaTeX Beamer**: the `media9` or `multimedia` packages embed MP4s; many people instead link to the file.

Keep the film's resolution at 1920 x 1080 for 16:9 slides.
