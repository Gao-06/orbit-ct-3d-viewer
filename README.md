# CT 3D Viewer

Browser-based source code for a longitudinal CT visualization prototype. The viewer presents aligned 3D models, interpolated surfaces, linked CT views, and measurements when supplied with a compatible local dataset.

## Data and privacy

This repository contains source code and third-party viewer libraries only. It intentionally excludes patient CT images, slice exports, meshes, segmentation masks, measurements, and case metadata. No clinical dataset is included. Keep approved case data on the authorized local workstation and do not commit it to this repository.

The application expects a locally supplied `web/aligned_scene/timeline.json`, the referenced model and morph assets, and the associated slice data. Those files are not part of this code-only repository, so the viewer cannot display a case until compatible data is supplied locally.

## Run locally

Use Python 3 and serve this folder over loopback HTTP:

```powershell
python .\scripts\serve_viewer.py --port 8765
```

Then open `http://127.0.0.1:8765/index.html`. The custom server sets the JavaScript module MIME type and only serves the viewer entry point and `web/` assets.

## Included source

- `web/viewer.mjs` and `web/viewer.css`: viewer rendering and interaction.
- `web/morph-worker.mjs` and `web/morph-surface-cleanup.mjs`: surface interpolation and display cleanup.
- `web/vendor/`: Three.js and its viewer modules, with the upstream MIT license.
- `scripts/serve_viewer.py`: local-only static server.

The measurements and interpolated geometry are visualization outputs. They are not a diagnostic or treatment-planning tool.
