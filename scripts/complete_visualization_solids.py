"""Create visualization-only solids by removing audited enclosed inner shells.
Original meshes and measurement volumes remain unchanged.
"""
import json
import vtk
from build_eye_fields import ROOT,load_mesh,mesh_stats
base=ROOT/'web/aligned_scene'
report=[]
for date,side in [('timepoint_1','left'),('timepoint_N','right')]:
 src=base/date/f'{side}_orbit.stl';m=load_mesh(src)
 c=vtk.vtkPolyDataConnectivityFilter();c.SetInputData(m);c.SetExtractionModeToLargestRegion();c.Update()
 clean=vtk.vtkCleanPolyData();clean.SetInputConnection(c.GetOutputPort());clean.Update()
 mesh=clean.GetOutput();stats=mesh_stats(mesh)
 assert stats['components']==1 and stats['boundaryOrNonManifoldEdges']==0
 dst=base/date/f'{side}_orbit.solid.stl'
 w=vtk.vtkSTLWriter();w.SetFileName(str(dst));w.SetFileTypeToBinary();w.SetInputData(mesh);assert w.Write()==1
 mp=vtk.vtkMassProperties();mp.SetInputData(mesh);mp.Update()
 report.append(dict(date=date,side=side,source=str(src.relative_to(ROOT)).replace('\\','/'),output=str(dst.relative_to(ROOT)).replace('\\','/'),stats=stats,displayVolumeCm3=mp.GetVolume()/1000,method='Keep audited enclosing outer shell; remove internal cavity surfaces and zero-volume degenerate island; visualization only'))
(base/'qa/solid_completion.json').write_text(json.dumps(report,indent=2))
timeline=json.loads((base/'timeline.json').read_text(encoding='utf-8'))
for r in report:
 t=next(t for t in timeline if t['date']==r['date']);t['eyeModels'][r['side']]=r['output'];t.setdefault('visualizationCompletion',{})[r['side']]={'method':'enclosed-cavity-fill','sourceMesh':r['source'],'displayMesh':r['output'],'measurementUnchanged':True}
(base/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
