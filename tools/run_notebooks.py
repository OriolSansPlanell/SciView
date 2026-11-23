"""Run the example notebooks from top to bottom and fail if a cell raises.

    python tools/run_notebooks.py                       # every notebook in examples/notebooks
    python tools/run_notebooks.py 02_fourier.ipynb      # some of them
    python tools/run_notebooks.py --save                # also write the new outputs into the notebooks

Each notebook runs in its own folder, with a fresh kernel, the way a reader runs it. Needs nbclient, nbformat
and ipykernel (``pip install nbclient nbformat ipykernel``).
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

FOLDER = Path(__file__).resolve().parents[1] / "examples" / "notebooks"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("notebooks", nargs="*", help="notebook names (default: all)")
    parser.add_argument("--save", action="store_true", help="write the outputs back into the notebooks")
    parser.add_argument("--timeout", type=int, default=1800, help="seconds allowed per cell")
    args = parser.parse_args()
    paths = [FOLDER / n for n in args.notebooks] if args.notebooks else sorted(FOLDER.glob("*.ipynb"))
    failed = []
    for path in paths:
        nb = nbformat.read(path, as_version=4)
        client = NotebookClient(nb, timeout=args.timeout, kernel_name="python3",
                                resources={"metadata": {"path": str(path.parent)}})
        t0 = time.time()
        try:
            client.execute()
        except CellExecutionError as exc:
            failed.append(path.name)
            print(f"FAILED {path.name}\n{exc}", file=sys.stderr)
            continue
        print(f"ok     {path.name} ({time.time() - t0:.0f} s)")
        if args.save:
            nbformat.write(nb, path)
    if failed:
        print(f"{len(failed)} notebook(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
