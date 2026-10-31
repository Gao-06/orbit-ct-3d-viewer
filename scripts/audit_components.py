import json
import vtk
import numpy as np
from vtk.util.numpy_support import vtk_to_numpy
from build_eye_fields import ROOT,load_mesh,mesh_stats
out=ROOT/'web/aligned_scene/qa';out.mkdir(exist_ok=True)
report=[]
for date,side in [('timepoint_1','left'),('timepoint_N','right')]:
 m=load_mesh(ROOT/f'web/aligned_scene/{date}/{side}_orbit.stl')
 c=vtk.vtkPolyDataConnectivityFilter();c.SetInputData(m);c.SetExtractionModeToAllRegions();c.Update();n=c.GetNumberOfExtractedRegions()
 parts=[]
 for i in range(n):
  c.SetExtractionModeToSpecifiedRegions();c.InitializeSpecifiedRegionList();c.AddSpecifiedRegion(i);c.Update()
  clean=vtk.vtkCleanPolyData();clean.SetInputConnection(c.GetOutputPort());clean.Update();p=vtk.vtkPolyData();p.DeepCopy(clean.GetOutput());parts.append(p)
 for i,p in enumerate(parts):
  tri=vtk_to_numpy(p.GetPolys().GetData()).reshape(-1,4)[:,1:]; pts=vtk_to_numpy(p.GetPoints().GetData()); signed=float(np.einsum('ij,ij->i',pts[tri[:,0]],np.cross(pts[tri[:,1]],pts[tri[:,2]])).sum()/6/1000)
  contains=[]
  for j,q in enumerate(parts):
   if i==j:continue
   sel=vtk.vtkSelectEnclosedPoints();sel.SetInputData(q);sel.SetSurfaceData(p);sel.Update();inside=vtk_to_numpy(sel.GetOutput().GetPointData().GetArray('SelectedPoints'));contains.append({'part':j,'fractionInside':float(inside.mean())})
  report.append(dict(date=date,side=side,part=i,signedVolumeCm3=signed,stats=mesh_stats(p),contains=contains))
print(json.dumps(report,indent=2));(out/'component_audit.json').write_text(json.dumps(report,indent=2))
