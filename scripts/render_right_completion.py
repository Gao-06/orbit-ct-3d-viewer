import json,numpy as np,vtk
from build_eye_fields import ROOT,surface_from_field,load_mesh,signed_distance,mesh_stats
base=ROOT/'web/aligned_scene';cfg=json.loads((base/'morph.json').read_text());ax=cfg['axes']['right'];n=ax['resolution'];s=ax['spacingMm'];o=ax['origin'];a=np.fromfile(ROOT/ax['fields'][3]['url'],dtype='<i2').reshape((n,)*3).astype(float);b=np.fromfile(ROOT/ax['fields'][4]['url'],dtype='<i2').reshape((n,)*3).astype(float)
old,_=signed_distance(load_mesh(base/'timepoint_N/right_orbit.solid.stl'),o,s,n)
models=[surface_from_field((a*.25+x*.75)*.01,o,s) for x in (old,b)]
m=models[1];c=vtk.vtkPolyDataConnectivityFilter();c.SetInputData(m);c.SetExtractionModeToAllRegions();c.Update();count=c.GetNumberOfExtractedRegions()
for i in range(count):
 c.SetExtractionModeToSpecifiedRegions();c.InitializeSpecifiedRegionList();c.AddSpecifiedRegion(i);c.Update();p=vtk.vtkMassProperties();p.SetInputData(c.GetOutput());p.Update();print(i,c.GetOutput().GetNumberOfCells(),p.GetVolume())
win=vtk.vtkRenderWindow();win.SetSize(1200,800);win.SetOffScreenRendering(1)
for row,m in enumerate(models):
 for col,d in enumerate([(18,-140,38),(140,-25,20),(0,0,140)]):
  ren=vtk.vtkRenderer();ren.SetViewport(col/3,1-(row+1)/2,(col+1)/3,1-row/2);ren.SetBackground(.96,.97,.99);win.AddRenderer(ren);mp=vtk.vtkPolyDataMapper();mp.SetInputData(m);mp.ScalarVisibilityOff();actor=vtk.vtkActor();actor.SetMapper(mp);actor.GetProperty().SetColor(.04,.65,.2);ren.AddActor(actor)
  center=(-37,-51,9);cam=ren.GetActiveCamera();cam.SetFocalPoint(*center);cam.SetPosition(*[center[k]+d[k] for k in range(3)]);cam.SetViewUp(*((0,1,0) if col==2 else (0,0,1)));cam.ParallelProjectionOn();cam.SetParallelScale(22);ren.ResetCameraClippingRange()
  txt=vtk.vtkTextActor();txt.SetInput(('Before' if row==0 else 'After')+' / 75%');txt.GetTextProperty().SetFontSize(18);txt.GetTextProperty().SetColor(.1,.1,.1);txt.SetPosition(10,10);ren.AddViewProp(txt)
win.Render();cap=vtk.vtkWindowToImageFilter();cap.SetInput(win);cap.ReadFrontBufferOff();cap.Update();w=vtk.vtkPNGWriter();w.SetFileName(str(base/'qa/right_before_after.png'));w.SetInputConnection(cap.GetOutputPort());w.Write()
