"""Close the narrow cavity entrance in the last right display model; keep source data."""
import json
import numpy as np
import vtk
from scipy.ndimage import binary_closing,binary_fill_holes,distance_transform_edt
from build_eye_fields import ROOT,load_mesh,signed_distance,surface_from_field,mesh_stats
base=ROOT/'web/aligned_scene';cfg=json.loads((base/'morph.json').read_text());axis=cfg['axes']['right'];n=axis['resolution'];s=axis['spacingMm'];origin=axis['origin']
src=base/'timepoint_N/right_orbit.solid.stl';field,_=signed_distance(load_mesh(src),origin,s,n);mask=field>0
r=4;z,y,x=np.ogrid[-r:r+1,-r:r+1,-r:r+1];closed=binary_fill_holes(binary_closing(mask,structure=x*x+y*y+z*z<=r*r))
assert not np.any(mask & ~closed), 'Unexpected loss of occupied voxels'
f=distance_transform_edt(closed,sampling=s)-distance_transform_edt(~closed,sampling=s)
m=surface_from_field(f,origin,s);assert mesh_stats(m)['components']==1
m.GetPointData().SetScalars(None)
dst=base/'timepoint_N/right_orbit.completed.stl';w=vtk.vtkSTLWriter();w.SetFileName(str(dst));w.SetInputData(m);w.SetFileTypeToBinary();assert w.Write()==1
p=base/'timeline.json';timeline=json.loads(p.read_text(encoding='utf-8'));t=next(t for t in timeline if t['date']=='timepoint_N');t['eyeModels']['right']=dst.relative_to(ROOT).as_posix();t['visualizationCompletion']['right'].update(method='close-narrow-cavity-entrance-and-fill',displayMesh=dst.relative_to(ROOT).as_posix(),closingRadiusMm=r*s)
for item in timeline:
 item['displayMeasurements']={}
 for side in ('left','right'):
  mesh=load_mesh(ROOT/item['eyeModels'][side]);mp=vtk.vtkMassProperties();mp.SetInputData(mesh);mp.Update();item['displayMeasurements'][side]={'volumeCm3':mp.GetVolume()/1000,'sourceMesh':item['eyeModels'][side],'interpretation':'Visualization mesh volume, not a clinical measurement'}
p.write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf-8')
report={'spacingMm':s,'radiusMm':r*s,'addedVoxels':int((closed & ~mask).sum()),'originalOccupiedVoxels':int(mask.sum()),'stats':mesh_stats(m),'displayVolumeCm3':t['displayMeasurements']['right']['volumeCm3']};(base/'qa/right_completion.json').write_text(json.dumps(report,indent=2));print(report)
