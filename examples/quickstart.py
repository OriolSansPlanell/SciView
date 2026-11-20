"""The README example: a Beer-Lambert explainer in a dozen lines.

Run:  python quickstart.py        (writes beer_lambert.sciview.json and beer_lambert.mp4)
"""
import numpy as np

import sciview as sv

film = sv.Project(title="Beer-Lambert", duration=8)

ax = film.add("axes", position=(260, 200), size=(1400, 620), x_range=(0, 5), y_range=(0, 1.05),
              x_label="thickness d (cm)", y_label="transmission T")
film.add("curve", axes=ax, expression="exp(-1.2*x)", color="teal", start=0.5)      # drawn on
dot = film.add("marker", axes=ax, x=0.0, follow="exp(-1.2*x)", label="T = {y:.2f}", start=2)
dot.key("x", 2.5, 0.0).key("x", 6.5, 4.0, ease="in_out")                           # slides along the curve

thickness = np.linspace(0.2, 4.8, 12)
film.add("scatter", axes=ax, x_values=thickness,
         y_values=np.exp(-1.2 * thickness) + np.random.normal(0, 0.02, 12), color="gold", size=5, start=4)
film.add("title", text="Beer–Lambert law", subtitle="Transmission falls exponentially with thickness")
film.add("caption", text="Each centimetre removes the same fraction of the beam.", start=3, end=7.5)

film.save("beer_lambert.sciview.json")   # open it later with: sciview edit beer_lambert.sciview.json
film.render("beer_lambert.mp4")          # or film.still(4.0, "frame.png", scale=2) for a poster figure
