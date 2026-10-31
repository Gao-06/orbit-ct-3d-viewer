import json
import numpy as np
import vtk
from scipy.ndimage import binary_fill_holes,binary_closing,distance_transform_edt,label
from build_eye_fields import ROOT,surface_from_field,mesh_stats
base=ROOT/'web/aligned_scene';cfg=json.loads((base/'morph.json').read_text());ax=cfg['axes']['right'];n=ax['resolution'];s=ax['spacingMm'];origin=ax['origin']
fields=[np.fromfile(ROOT/x['url'],dtype='<i2').reshape((n,)*3).astype(float)*.01 for x in ax['fields']]
models=[];titles=[]
for rad in (0,1,2,3,4):
 mask=fields[4]>0
 if rad:
  z,y,x=np.ogrid[-rad:rad+1,-rad:rad+1,-rad:rad+1];mask=binary_closing(mask,structure=x*x+y*y+z*z<=rad*rad);mask=binary_fill_holes(mask)
 field=fields[4] if rad==0 else distance_transform_edt(mask,sampling=s)-distance_transform_edt(~mask,sampling=s)
 m=surface_from_field(fields[3]*.25+field*.75,origin,s);models.append(m);titles.append(f'closing radius {rad*s:.2f} mm')
 print(rad,mesh_stats(m),'voxels',int(mask.sum()),flush=True)
 if rad:np.save(base/f'qa/right_candidate_{rad}.npy',field)
win=vtk.vtkRenderWindow();win.SetSize(1500,700);win.SetOffScreenRendering(1)
for i,m in enumerate(models):
 for row,direction in enumerate([(18,-140,38),(140,-25,20)]):
  ren=vtk.vtkRenderer();ren.SetViewport(i/5,row/2,(i+1)/5,(row+1)/2);ren.SetBackground(.96,.97,.99);win.AddRenderer(ren);mapper=vtk.vtkPolyDataMapper();mapper.SetInputData(m);a=vtk.vtkActor();a.SetMapper(mapper);a.GetProperty().SetColor(.04,.65,.2);ren.AddActor(a)
  center=(-37,-51,9);cam=ren.GetActiveCamera();cam.SetFocalPoint(*center);cam.SetPosition(*[center[k]+direction[k] for k in range(3)]);cam.SetViewUp(0,0,1);cam.ParallelProjectionOn();cam.SetParallelScale(22);ren.ResetCameraClippingRange()
  text=vtk.vtkTextActor();text.SetInput(titles[i]);text.GetTextProperty().SetFontSize(16);text.GetTextProperty().SetColor(.1,.1,.1);text.SetDisplayPosition(10,310);ren.AddViewProp(text)
win.Render();cap=vtk.vtkWindowToImageFilter();cap.SetInput(win);cap.ReadFrontBufferOff();cap.Update();w=vtk.vtkPNGWriter();w.SetFileName(str(base/'qa/right_candidates.png'));w.SetInputConnection(cap.GetOutputPort());w.Write()
