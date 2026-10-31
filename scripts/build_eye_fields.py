"""Build signed-distance fields for eye shape interpolation with Slicer Python.

Aligned STL endpoints are authoritative and never modified. Only derived
binary fields and an audit manifest are written; no trained model is used.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import vtk
from scipy.ndimage import distance_transform_edt
from vtk.util.numpy_support import numpy_to_vtk, vtk_to_numpy

ROOT = Path(__file__).resolve().parents[1]
DISTANCE_SCALE = 0.01


def load_mesh(path):
    reader = vtk.vtkSTLReader() if path.suffix.lower() == '.stl' else vtk.vtkOBJReader()
    reader.SetFileName(str(path))
    reader.Update()
    clean = vtk.vtkCleanPolyData()
    clean.SetInputConnection(reader.GetOutputPort())
    clean.Update()
    mesh = vtk.vtkPolyData()
    mesh.DeepCopy(clean.GetOutput())
    if mesh.GetNumberOfPoints() < 4:
        raise ValueError(f'Empty mesh: {path}')
    return mesh


def mesh_stats(mesh):
    edge = vtk.vtkFeatureEdges()
    edge.SetInputData(mesh)
    edge.BoundaryEdgesOn()
    edge.NonManifoldEdgesOn()
    edge.FeatureEdgesOff()
    edge.ManifoldEdgesOff()
    edge.Update()
    connectivity = vtk.vtkConnectivityFilter()
    connectivity.SetInputData(mesh)
    connectivity.SetExtractionModeToAllRegions()
    connectivity.Update()
    return dict(points=mesh.GetNumberOfPoints(), triangles=mesh.GetNumberOfCells(),
                boundaryOrNonManifoldEdges=edge.GetOutput().GetNumberOfCells(),
                components=connectivity.GetNumberOfExtractedRegions(), bounds=list(mesh.GetBounds()))


def signed_distance(mesh, origin, spacing, resolution):
    stencil = vtk.vtkPolyDataToImageStencil()
    stencil.SetInputData(mesh)
    stencil.SetOutputOrigin(*origin)
    stencil.SetOutputSpacing(spacing, spacing, spacing)
    stencil.SetOutputWholeExtent(0, resolution-1, 0, resolution-1, 0, resolution-1)
    stencil.Update()
    image = vtk.vtkImageStencilToImage()
    image.SetInputConnection(stencil.GetOutputPort())
    image.SetInsideValue(1)
    image.SetOutsideValue(0)
    image.SetOutputScalarTypeToUnsignedChar()
    image.Update()
    mask = vtk_to_numpy(image.GetOutput().GetPointData().GetScalars()).reshape((resolution,)*3).astype(bool)
    if not np.any(mask) or np.all(mask):
        raise ValueError('Voxelization produced an empty or unbounded solid')
    faces = (mask[0], mask[-1], mask[:,0], mask[:,-1], mask[:,:,0], mask[:,:,-1])
    if any(np.any(face) for face in faces):
        raise ValueError('Mesh reaches field boundary; increase padding')
    # High values inside, as expected by Three.js MarchingCubes at isolation=0.
    field = distance_transform_edt(mask, sampling=spacing)-distance_transform_edt(~mask, sampling=spacing)
    if np.abs(field).max()/DISTANCE_SCALE > 32767:
        raise ValueError('Signed distance exceeds int16 storage range')
    return np.rint(field/DISTANCE_SCALE).astype('<i2'), int(mask.sum())


def surface_from_field(field, origin, spacing):
    image = vtk.vtkImageData()
    image.SetDimensions(*(field.shape))
    image.SetOrigin(*origin)
    image.SetSpacing(spacing, spacing, spacing)
    values = np.ascontiguousarray(field, dtype=np.float32).ravel()
    image.GetPointData().SetScalars(numpy_to_vtk(values, deep=True))
    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(image)
    contour.SetValue(0, 0)
    contour.Update()
    result = vtk.vtkPolyData()
    result.DeepCopy(contour.GetOutput())
    return result


def sampled_surface_error(reconstructed, original, sample_count=2500):
    # Symmetric deterministic samples, not a full Hausdorff distance.
    distances = []
    for source, target in ((reconstructed, original), (original, reconstructed)):
        evaluator = vtk.vtkImplicitPolyDataDistance()
        evaluator.SetInput(target)
        points = vtk_to_numpy(source.GetPoints().GetData())
        indices = np.linspace(0, len(points)-1, min(sample_count,len(points)), dtype=int)
        distances.extend(abs(evaluator.EvaluateFunction(points[i])) for i in indices)
    errors = np.asarray(distances)
    return dict(sampleCount=len(distances), meanMm=float(errors.mean()),
                p95Mm=float(np.percentile(errors,95)), maximumSampledMm=float(errors.max()),
                method='symmetric evenly indexed vertex-to-surface samples')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeline', type=Path, default=ROOT/'web/aligned_scene/timeline.json')
    parser.add_argument('--resolution', type=int, default=80)
    parser.add_argument('--padding-mm', type=float, default=3.0)
    args = parser.parse_args()
    if not 32 <= args.resolution <= 160:
        raise ValueError('Resolution must be between 32 and 160')
    timeline_path = args.timeline.resolve()
    if not timeline_path.is_relative_to(ROOT):
        raise ValueError('Timeline and generated fields must remain inside the workspace')
    timeline = json.loads(timeline_path.read_text(encoding='utf-8'))
    if not isinstance(timeline,list) or len(timeline) < 2:
        raise ValueError('At least two aligned timeline entries are required')
    output = timeline_path.parent/'fields'
    output.mkdir(parents=True, exist_ok=True)
    report = dict(version=1, method='signed-distance', dtype='int16-le',
                  distanceScale=DISTANCE_SCALE, sign='positive-inside',
                  arrayOrder='x-fastest: z*N*N + y*N + x',
                  endpointPolicy='Use original aligned STL meshes at exact measured dates',
                  interpretation='Intermediate geometry is an illustrative interpolation, not an observed anatomical state or a reconstructed CT',
                  sourceTimelineSha256=hashlib.sha256(timeline_path.read_bytes()).hexdigest(),axes={})
    started=time.perf_counter()
    for side in ('left','right'):
        meshes=[load_mesh(ROOT/item['eyeModels'][side]) for item in timeline]
        bounds=np.asarray([m.GetBounds() for m in meshes]).reshape(len(meshes),3,2)
        minimum=bounds[:,:,0].min(axis=0)
        maximum=bounds[:,:,1].max(axis=0)
        extent=float((maximum-minimum).max()+2*args.padding_mm)
        spacing=extent/(args.resolution-1)
        origin=(minimum+maximum)/2-extent/2
        # Three.js maps voxel x to x/(N/2)-1: use N*spacing, not (N-1)*spacing.
        render_scale=args.resolution*spacing/2
        axis=dict(resolution=args.resolution,origin=origin.tolist(),spacingMm=spacing,
                  renderCenter=(origin+render_scale).tolist(),renderScale=render_scale,
                  fields=[],midpoints=[])
        previous=None
        for item,mesh in zip(timeline,meshes):
            stats=mesh_stats(mesh)
            if stats['boundaryOrNonManifoldEdges']:
                raise ValueError(f"{item['date']} {side}: mesh is not a closed manifold")
            packed,occupied=signed_distance(mesh,origin,spacing,args.resolution)
            field=packed.astype(np.float32)*DISTANCE_SCALE
            reconstruction=surface_from_field(field,origin,spacing)
            error=sampled_surface_error(reconstruction,mesh)
            if error['p95Mm']>2*spacing:
                raise ValueError(f"{item['date']} {side}: excessive reconstruction error: {error}")
            path=output/f"{item['date']}_{side}.i16"
            payload=packed.tobytes(order='C')
            path.write_bytes(payload)
            axis['fields'].append(dict(date=item['date'],url=path.relative_to(ROOT).as_posix(),
                                       bytes=len(payload),sha256=hashlib.sha256(payload).hexdigest(),
                                       sourceMesh=item['eyeModels'][side],sourceStats=stats,
                                       occupiedVoxels=occupied,voxelVolumeMm3=occupied*spacing**3,
                                       endpointReconstructionStats=mesh_stats(reconstruction),
                                       endpointSurfaceError=error))
            if previous is not None:
                midpoint=surface_from_field((previous+field)/2,origin,spacing)
                if midpoint.GetNumberOfCells()<4:
                    raise ValueError(f"{side}: empty intermediate surface before {item['date']}")
                axis['midpoints'].append(dict(toDate=item['date'],**mesh_stats(midpoint)))
            previous=field
            print(f"{item['date']} {side}: {spacing:.3f} mm grid, endpoint p95 {error['p95Mm']:.3f} mm",flush=True)
        report['axes'][side]=axis
    report['elapsedSeconds']=time.perf_counter()-started
    path=timeline_path.parent/'morph.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f"Wrote {path} in {report['elapsedSeconds']:.2f} s")


if __name__=='__main__':
    main()
