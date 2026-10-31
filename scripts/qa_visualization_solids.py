import json
import numpy as np
import vtk
from build_eye_fields import ROOT,load_mesh,signed_distance,surface_from_field,mesh_stats
base=ROOT/'web/aligned_scene';cfg=json.loads((base/'morph.json').read_text());ax=cfg['axes']['left'];n=ax['resolution'];origin=ax['origin'];s=ax['spacingMm']
old,_=signed_distance(load_mesh(base/'timepoint_1/left_orbit.stl'),origin,s,n)
new=np.fromfile(ROOT/ax['fields'][2]['url'],dtype='<i2').reshape((n,)*3)
b=np.fromfile(ROOT/ax['fields'][3]['url'],dtype='<i2').reshape((n,)*3)
f=.39
meshes=[surface_from_field((a*(1-f)+b*f)*.01,origin,s) for a in (old,new)]
win=vtk.vtkRenderWindow();win.SetSize(1440,900);win.SetOffScreenRendering(1);win.SetMultiSamples(0)
for row,m in enumerate(meshes):
 for col,direction in enumerate([(18,-140,38),(140,-25,20),(0,0,140)]):
  ren=vtk.vtkRenderer();ren.SetViewport(col/3,1-(row+1)/2,(col+1)/3,1-row/2);ren.SetBackground(.96,.97,.99);win.AddRenderer(ren)
  mapper=vtk.vtkPolyDataMapper();mapper.SetInputData(m);actor=vtk.vtkActor();actor.SetMapper(mapper);actor.GetProperty().SetColor(.9,.05,.04);ren.AddActor(actor)
  center=(36,-52,12);cam=ren.GetActiveCamera();cam.SetFocalPoint(*center);cam.SetPosition(*[center[i]+direction[i] for i in range(3)]);cam.SetViewUp(*( (0,1,0) if col==2 else (0,0,1)));cam.ParallelProjectionOn();cam.SetParallelScale(24);ren.ResetCameraClippingRange()
  text=vtk.vtkTextActor();text.SetInput(('BEFORE: cavity retained' if row==0 else 'AFTER: visualization solid')+'\n39% blend / '+['front-oblique','side','top'][col]);text.GetTextProperty().SetFontSize(19);text.GetTextProperty().SetColor(.1,.1,.1);text.SetDisplayPosition(12,393);ren.AddActor2D(text)
win.Render();capture=vtk.vtkWindowToImageFilter();capture.SetInput(win);capture.ReadFrontBufferOff();capture.Update();writer=vtk.vtkPNGWriter();writer.SetFileName(str(base/'qa/cavity_before_after.png'));writer.SetInputConnection(capture.GetOutputPort());writer.Write()
checks=[]
for side,axis in cfg['axes'].items():
 fs=[np.fromfile(ROOT/item['url'],dtype='<i2').reshape((n,)*3).astype(float) for item in axis['fields']]
 for i in range(len(fs)-1):
  for fraction in (.1,.25,.39,.5,.75,.9):
   m=surface_from_field((fs[i]*(1-fraction)+fs[i+1]*fraction)*.01,axis['origin'],axis['spacingMm']);st=mesh_stats(m);checks.append(dict(side=side,pair=i,fraction=fraction,**st))
(base/'qa/solid_interpolation_checks.json').write_text(json.dumps(checks,indent=2))
bad=[x for x in checks if x['components']!=1 or x['boundaryOrNonManifoldEdges']!=0]
print('checked',len(checks),'intermediate surfaces; failures',len(bad));print(json.dumps(bad))
