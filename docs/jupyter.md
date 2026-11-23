# Notebooks

SciView works in Jupyter (JupyterLab, classic notebooks, VS Code, Colab) without any extension.

## Preview a film

```python
import sciview as sv

film = sv.load("talk.sciview.json")
film.preview()                          # play and scrub: 10 frames per second at 480 x 270
film.preview(fps=15, scale=0.4, start=8, end=14)
film.preview(scene="Result")            # one scene on its own
```

The preview is plain HTML with the frames inside, so it plays without a running kernel and stays in the saved
notebook (and in the HTML or PDF you export from it). Keep it short and small: every frame is stored, up to
600 of them. Chapter buttons under the scrubber jump to the scenes.

One frame as a picture: `sciview.jupyter.still(film, 4.5)` (a JPEG, so a notebook can hold many of them;
`Still(film, 4.5)` gives a PNG), or `PIL.Image.fromarray(film.frame(4.5, 0.5))`. The preview's frames are JPEGs
too, and it shows its first frame even where scripts do not run, such as GitHub's notebook viewer.

## The editor inside the notebook

```python
from sciview import jupyter

ed = jupyter.edit(film)                 # the full editor, in the notebook
# ... edit ...
film = ed.film                          # take the edited film back into Python
ed.stop()
```

The editor works on its own copy of the film: assign `ed.film` back when you are done. It is served on the
computer that runs the kernel, so it shows when the notebook and the kernel run on the same machine. For a
kernel on a remote machine, forward the port over SSH as for the [editor](editor.md#using-the-editor-on-a-remote-machine),
or set `SCIVIEW_ALLOWED_HOSTS` to the name of the proxy in front of it.

## Magics

```python
%load_ext sciview
```

```text
%sciview preview film --fps 12 --scale 0.3
%sciview preview talk.sciview.json --start 5 --end 9
%sciview still film 4.5
%sciview edit film                      # the editor is kept in _sciview_editor
```

`film` is a variable holding a film, or the path of a `.sciview.json` file.

## Example notebooks

[examples/notebooks](https://github.com/OriolSansPlanell/SciView/tree/main/examples/notebooks) holds four complete
workflows, each from the data to a rendered film, with a still of every scene as it is built:

* **Tomography**: radiographs of a sandstone core, sinograms, filtered back-projection, segmentation, porosity.
* **Fourier analysis**: a noisy vibration signal, its spectrum, peak detection, a fit of three tones, filtering.
* **Neutron diffraction**: a two-phase steel, its powder pattern and a staged Rietveld refinement.
* **A tour of SciView**: one scene per family of objects, then checks, themes and every export format.

The data are simulated inside each notebook, so they run anywhere; each says which cell to replace to use your
own data. `python tools/run_notebooks.py` runs them all without opening Jupyter.
