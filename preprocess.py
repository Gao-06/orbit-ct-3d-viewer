import argparse, json
from pathlib import Path
import numpy as np
from PIL import Image
import pydicom

def first(v, default):
    try: return float(v[0]) if hasattr(v, '__getitem__') and not isinstance(v, (str, bytes)) else float(v)
    except Exception: return float(default)

def convert(input_dir, output_dir, width=400, center=40, series_number=None, description=None):
    items=[]
    for p in Path(input_dir).rglob('*'):
        if not p.is_file(): continue
        try: ds=pydicom.dcmread(str(p))
        except Exception: continue
        if series_number is not None and str(getattr(ds,'SeriesNumber','')).strip()!=str(series_number): continue
        if description and str(getattr(ds,'SeriesDescription','')).strip()!=description: continue
        try: z=float(ds.ImagePositionPatient[2])
        except Exception: continue
        items.append((z, ds))
    items.sort(key=lambda x:x[0], reverse=True); out=Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    manifest=[]
    for i,(z,ds) in enumerate(items,1):
        arr=ds.pixel_array.astype(np.float32)*float(getattr(ds,'RescaleSlope',1))+float(getattr(ds,'RescaleIntercept',0))
        ww=first(getattr(ds,'WindowWidth',width),width); wc=first(getattr(ds,'WindowCenter',center),center)
        img=np.uint8(np.clip((arr-(wc-ww/2))/ww,0,1)*255)
        name=f'slice_{i:03d}.png'; Image.fromarray(img).save(out/name)
        manifest.append({'index':i,'z':z,'file':name})
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return len(manifest)

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--input',required=True); ap.add_argument('--output',required=True); ap.add_argument('--series-number',type=int); ap.add_argument('--description'); ap.add_argument('--window-width',type=float,default=400); ap.add_argument('--window-center',type=float,default=40)
    a=ap.parse_args(); print(f'converted {convert(a.input,a.output,a.window_width,a.window_center,a.series_number,a.description)} slices')
