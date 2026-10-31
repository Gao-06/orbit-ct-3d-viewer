# CT 3D Viewer

Browser-based source code for a longitudinal CT visualization prototype. The repository publishes the complete project source code and required third-party libraries.

## Privacy and included files

This public repository contains the browser viewer, local preprocessing and data-import utilities, geometry processing and quality-assurance scripts, launch helpers, and third-party viewer libraries. It does not contain any patient case data.

Patient CT/DICOM images, slice exports, 3D meshes, segmentation labels, case timelines, measurements, screenshots, and reports are excluded. Patient-derived 3D geometry and linked examination dates can remain sensitive health information even after names are removed. Do not add case data to this public repository. Use only data approved for your local environment.

The viewer requires a compatible local dataset under `web/aligned_scene/`, including `timeline.json`, referenced model and morph assets, and CT slice data. These assets are intentionally not published, so the repository cannot display the case without separately supplied local data.

## Run the viewer

Install Python 3, then run from this directory:

```powershell
python .\scripts\serve_viewer.py --port 8765
```

Open `http://127.0.0.1:8765/index.html`. The server binds to loopback and serves the viewer and `web/` assets. The PowerShell helper is `scripts/start_viewer.ps1`. To reconstruct orthogonal PNG views, pass the acquisition pixel and slice spacing to `scripts/build_views.py` using its required command-line parameters.

## Source layout

- `index.html`, `web/viewer.mjs`, and `web/viewer.css`: browser UI, rendering, timeline, and interaction.
- `web/morph-worker.mjs` and `web/morph-surface-cleanup.mjs`: implicit-surface interpolation and display cleanup.
- `preprocess.py`, `db.py`, and `scripts/`: image conversion, data import, geometry processing, validation, and local serving utilities.
- `web/vendor/`: Three.js and viewer modules with upstream license information.

The visualization supports review and demonstration. It is not a diagnostic or treatment-planning tool.
