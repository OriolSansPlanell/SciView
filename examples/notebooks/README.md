# Example notebooks

Four notebooks, each a complete workflow from the data to a finished film. Every step of the analysis becomes a
scene; the notebook shows a still of each scene as it is built, plays a preview, and renders an MP4 at the end.

| Notebook | What it shows | Film |
| --- | --- | --- |
| [01_tomography](01_tomography.ipynb) | A neutron tomography of a sandstone core: 180 radiographs, sinograms, filtered back-projection, segmentation into pores, quartz and heavy grains, porosity and pore sizes. | 5 scenes, 41 s |
| [02_fourier](02_fourier.ipynb) | A noisy vibration signal: windowed Fourier transform, peak detection, a least-squares fit of three tones with uncertainties, and spectral filtering. | 5 scenes, 46 s |
| [03_neutron_diffraction](03_neutron_diffraction.ipynb) | Neutron powder diffraction of a duplex steel: reflections, structure factors and peak shapes, a staged Rietveld refinement, lattice parameters and phase fractions. | 5 scenes, 50 s |
| [04_sciview_tour](04_sciview_tour.ipynb) | Everything SciView draws, one scene per family: 3D beamlines and meshes, charts and fits, spectra and maps, fields, images, tomography, optics, equations, matplotlib figures, keyframes and groups; then checks, themes and every export format. | 12 scenes, 87 s |

The measurements are simulated inside each notebook, so they run anywhere and every result can be checked
against the truth. Each notebook says which cell to replace to use your own data.

## Running them

```bash
pip install "sciview[all]" jupyterlab
cd examples/notebooks
jupyter lab
```

Each notebook writes its film into `films/<name>/` next to it: the project file, its `assets` folder and the
rendered video. Open a film in the editor to change colours, timing or words without touching the code:

```bash
sciview edit films/tomography/tomography.sciview.json
```

Rendering takes one to three minutes per film at half size (`scale=0.5`) on a laptop; use `scale=1` for full
HD. The tour renders in a single process because it contains a matplotlib figure drawn by the notebook.

To run them all without opening Jupyter (this is what the continuous integration does):

```bash
pip install nbclient nbformat ipykernel
python tools/run_notebooks.py
```
