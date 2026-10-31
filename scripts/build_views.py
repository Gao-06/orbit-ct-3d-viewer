from pathlib import Path
import argparse
import numpy as np
from PIL import Image

ap=argparse.ArgumentParser()
ap.add_argument('src', nargs='?', type=Path, default=Path('web/slices'))
ap.add_argument('--pixel-spacing', type=float, required=True, help='in-plane pixel spacing in mm')
ap.add_argument('--slice-spacing', type=float, required=True, help='distance between slices in mm')
args=ap.parse_args()
src=args.src; out=src/'views'; out.mkdir(parents=True,exist_ok=True)
files=sorted(src.glob('slice_*.png'))
if not files: raise SystemExit('No slices found. Run dicom_to_png.py first.')
stack=np.stack([np.asarray(Image.open(p).convert('L')) for p in files])
n,zx,zy=stack.shape
# Preserve the physical aspect ratio for orthogonal reconstructions.
pixel_spacing=args.pixel_spacing; slice_spacing=args.slice_spacing
view_h=max(1, round(n*slice_spacing/pixel_spacing))
def axial(a):
    return Image.fromarray(a).resize((512,512), Image.Resampling.BILINEAR)
def orthogonal(a):
    # a is (slice, in-plane), transpose gives horizontal in-plane and vertical depth.
    return Image.fromarray(a).resize((512,view_h), Image.Resampling.BILINEAR)
for i in range(n):
    axial(stack[i]).save(out/f'axial_{i+1:03d}.png')
for row in range(zx):
    orthogonal(stack[:,row,:]).save(out/f'coronal_{row+1:03d}.png')
for col in range(zy):
    orthogonal(stack[:,:,col]).save(out/f'sagittal_{col+1:03d}.png')
Image.fromarray(stack[n//2]).save(out/'axial.png')
Image.fromarray(stack[:,zx//2,:]).save(out/'coronal.png')
Image.fromarray(stack[:,:,zy//2]).save(out/'sagittal.png')
print(f'created 3 views from {n} slices')
