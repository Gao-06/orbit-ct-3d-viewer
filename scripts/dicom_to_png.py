"""Convert a selected DICOM series to ordered windowed PNG frames."""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path
import numpy as np
try:
    import pydicom
    from PIL import Image
except ImportError as exc:
    raise SystemExit("Install dependencies first: python -m pip install pydicom pillow numpy") from exc

def window(arr, center, width):
    lo, hi = center - width / 2.0, center + width / 2.0
    return np.clip((arr.astype(np.float32) - lo) / max(width, 1e-6), 0, 1)

def convert(input_dir: Path, output_dir: Path, series_number: int | None = None, description: str | None = None, width: float = 400, center: float = 40):
    records=[]
    for path in input_dir.rglob("*"):
        if not path.is_file(): continue
        try: ds=pydicom.dcmread(path, force=True, stop_before_pixels=False)
        except Exception: continue
        if series_number is not None and str(getattr(ds,"SeriesNumber","")) != str(series_number): continue
        if description and str(getattr(ds,"SeriesDescription","")) != description: continue
        try: z=float(ds.ImagePositionPatient[2])
        except Exception: continue
        records.append((z,path,ds))
    records.sort(key=lambda x:x[0], reverse=True)
    if not records: raise RuntimeError("No matching DICOM slices; check the optional series filters")
    output_dir.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,(z,path,ds) in enumerate(records,1):
        arr=ds.pixel_array.astype(np.float32)
        slope=float(getattr(ds,"RescaleSlope",1)); intercept=float(getattr(ds,"RescaleIntercept",0))
        png=(window(arr*slope+intercept,center,width)*255).astype(np.uint8)
        name=f"slice_{i:03d}.png"; Image.fromarray(png,mode="L").save(output_dir/name)
        rows.append({"index":i,"z":z,"source":str(path),"output":name})
    with (output_dir/"index.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
    print(f"converted {len(rows)} slices -> {output_dir}")

if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("input_dir",type=Path); ap.add_argument("--output-dir",type=Path,default=Path("web/slices")); ap.add_argument("--series-number",type=int); ap.add_argument("--description"); ap.add_argument("--window-width",type=float,default=400); ap.add_argument("--window-center",type=float,default=40); args=ap.parse_args(); convert(args.input_dir,args.output_dir,series_number=args.series_number,description=args.description,width=args.window_width,center=args.window_center)
