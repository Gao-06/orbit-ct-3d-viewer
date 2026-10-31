import vtk, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TARGETS=[
 (ROOT/'web/aligned_scene/timepoint_1/left_orbit.stl', ROOT/'web/aligned_scene/timepoint_1/left_orbit.repaired.stl'),
 (ROOT/'web/aligned_scene/timepoint_N/right_orbit.stl', ROOT/'web/aligned_scene/timepoint_N/right_orbit.repaired.stl'),
]

def read(path):
 r=vtk.vtkSTLReader(); r.SetFileName(str(path)); r.Update(); c=vtk.vtkCleanPolyData(); c.SetInputConnection(r.GetOutputPort()); c.Update(); out=vtk.vtkPolyData(); out.DeepCopy(c.GetOutput()); return out

def stats(m):
 e=vtk.vtkFeatureEdges(); e.SetInputData(m); e.BoundaryEdgesOn(); e.NonManifoldEdgesOn(); e.FeatureEdgesOff(); e.ManifoldEdgesOff(); e.Update()
 c=vtk.vtkConnectivityFilter(); c.SetInputData(m); c.SetExtractionModeToAllRegions(); c.Update()
 tri=vtk.vtkTriangleFilter(); tri.SetInputData(m); tri.Update(); mp=vtk.vtkMassProperties(); mp.SetInputConnection(tri.GetOutputPort()); mp.Update()
 return m.GetNumberOfPoints(),m.GetNumberOfCells(),e.GetOutput().GetNumberOfCells(),c.GetNumberOfExtractedRegions(),mp.GetVolume()/1000

def repair(mesh):
 b=mesh.GetBounds(); spacing=.25; pad=3.0
 origin=[b[0]-pad,b[2]-pad,b[4]-pad]; maxs=[b[1]+pad,b[3]+pad,b[5]+pad]
 dims=[int((maxs[i]-origin[i])/spacing)+1 for i in range(3)]
 st=vtk.vtkPolyDataToImageStencil(); st.SetInputData(mesh); st.SetOutputOrigin(*origin); st.SetOutputSpacing(spacing,spacing,spacing); st.SetOutputWholeExtent(0,dims[0]-1,0,dims[1]-1,0,dims[2]-1); st.Update()
 img=vtk.vtkImageStencilToImage(); img.SetInputConnection(st.GetOutputPort()); img.SetInsideValue(1); img.SetOutsideValue(0); img.SetOutputScalarTypeToUnsignedChar(); img.Update()
 # conservative closing: 5-voxel kernel (about 0.5 mm) to bridge thin local notches
 dil=vtk.vtkImageDilateErode3D(); dil.SetInputConnection(img.GetOutputPort()); dil.SetDilateValue(1); dil.SetErodeValue(0); dil.SetKernelSize(5,5,5); dil.Update()
 ero=vtk.vtkImageDilateErode3D(); ero.SetInputConnection(dil.GetOutputPort()); ero.SetDilateValue(0); ero.SetErodeValue(1); ero.SetKernelSize(5,5,5); ero.Update()
 contour=vtk.vtkFlyingEdges3D(); contour.SetInputConnection(ero.GetOutputPort()); contour.SetValue(0,0.5); contour.Update()
 fill=vtk.vtkFillHolesFilter(); fill.SetInputConnection(contour.GetOutputPort()); fill.SetHoleSize(4.0); fill.Update()
 clean=vtk.vtkCleanPolyData(); clean.SetInputConnection(fill.GetOutputPort()); clean.Update()
 tri=vtk.vtkTriangleFilter(); tri.SetInputConnection(clean.GetOutputPort()); tri.Update()
 return tri.GetOutput()

for src,dst in TARGETS:
 m=read(src); print('before',src.name,stats(m),flush=True)
 fixed=repair(m); print('after',stats(fixed),flush=True)
 w=vtk.vtkSTLWriter(); w.SetFileName(str(dst)); w.SetInputData(fixed); w.Write(); print('wrote',dst,flush=True)
