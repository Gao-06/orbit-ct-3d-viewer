"""Import manually aligned Slicer models without registering or recentering dates.

Run with Slicer's PythonSlicer.exe (VTK, NumPy and SimpleITK are required).
The MRB, original OBJs and existing web/timeline.json are read-only inputs.
Only web/aligned_scene is generated. No ICP, nonrigid fit, or landmark estimate
is performed: Kabsch recovers an ALREADY hardened transform from identical
vertex indices, then every vertex is checked against the scene model.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import SimpleITK as sitk
import vtk
from vtk.util.numpy_support import vtk_to_numpy, numpy_to_vtk, numpy_to_vtkIdTypeArray

ROOT = Path(__file__).resolve().parents[1]
SIDES = ('skull', 'left', 'right')


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def refs(node):
    result = {}
    for item in node.get('references', '').split(';'):
        if ':' in item:
            key, value = item.split(':', 1)
            result[key] = value
    if node.get('transformNodeRef'):
        result['transform'] = node.get('transformNodeRef')
    if node.get('storageNodeRef'):
        result['storage'] = node.get('storageNodeRef')
    return result


def unpack_scene(archive, cache, archive_hash):
    cache.mkdir(parents=True, exist_ok=True)
    stamp_path = cache / 'archive-manifest.json'
    stamp = json.loads(stamp_path.read_text(encoding='utf-8')) if stamp_path.exists() else {}
    with zipfile.ZipFile(archive) as bundle:
        scenes = [n for n in bundle.namelist() if n.lower().endswith('.mrml')]
        if len(scenes) != 1:
            raise ValueError('Expected exactly one MRML scene in MRB')
        scene_name = scenes[0]
        scene = ET.fromstring(bundle.read(scene_name))
        by_id = {n.get('id'): n for n in scene if n.get('id')}
        base = PurePosixPath(scene_name).parent
        storage_paths = {}
        entries = []
        for node in scene:
            if node.tag not in ('ModelStorage', 'TransformStorage'):
                continue
            name = node.get('fileName')
            if not name:
                continue
            relative = PurePosixPath(name.replace('\\', '/'))
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Unsafe storage path in MRML')
            member = str(base / relative)
            info = bundle.getinfo(member)
            target = (cache / Path(*relative.parts)).resolve()
            if not target.is_relative_to(cache.resolve()):
                raise ValueError('Cache path escapes output directory')
            target.parent.mkdir(parents=True, exist_ok=True)
            reusable = (stamp.get('archiveSha256') == archive_hash and target.exists()
                        and target.stat().st_size == info.file_size)
            if not reusable:
                temporary = target.with_suffix(target.suffix + '.tmp')
                with bundle.open(member) as src, temporary.open('wb') as dst:
                    shutil.copyfileobj(src, dst, 8 * 1024 * 1024)
                os.replace(temporary, target)
            storage_paths[node.get('id')] = target
            entries.append({'member': member, 'bytes': info.file_size, 'crc32': info.CRC})
        # Save the small scene for reproducibility; never extract unrelated patient volumes.
        (cache / 'scene.mrml').write_bytes(bundle.read(scene_name))
    save_json(stamp_path, {'archiveSha256': archive_hash, 'entries': entries})
    return scene, by_id, storage_paths


def read_polydata(path, obj=False):
    reader = vtk.vtkOBJReader() if obj else vtk.vtkPolyDataReader()
    reader.SetFileName(str(path))
    if not obj:
        reader.ReadAllFieldsOn()
        reader.ReadAllScalarsOn()
        reader.ReadAllNormalsOn()
        reader.ReadAllVectorsOn()
    reader.Update()
    poly = vtk.vtkPolyData()
    poly.DeepCopy(reader.GetOutput())
    if not poly.GetNumberOfPoints() or not poly.GetNumberOfPolys():
        raise ValueError(f'Empty model: {path.name}')
    if poly.GetNumberOfCells() != poly.GetNumberOfPolys():
        raise ValueError('Mixed vertex/line/strip models are not supported')
    offsets = vtk_to_numpy(poly.GetPolys().GetOffsetsArray())
    if not np.all(np.diff(offsets) == 3):
        raise ValueError('Source must consist of triangles; refusing to change its topology')
    if poly.GetCellData().GetArray('GroupIds') is None:
        raise ValueError('Missing preserved OBJ GroupIds; cannot safely identify structures')
    return poly


def points(poly):
    return vtk_to_numpy(poly.GetPoints().GetData()).astype(np.float64, copy=False)


def triangles(poly):
    return vtk_to_numpy(poly.GetPolys().GetConnectivityArray()).reshape(-1, 3)


def groups(poly):
    return vtk_to_numpy(poly.GetCellData().GetArray('GroupIds')).astype(np.int32)


def signature(poly):
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(triangles(poly), dtype='<i8').tobytes())
    digest.update(np.ascontiguousarray(groups(poly), dtype='<i4').tobytes())
    names = poly.GetFieldData().GetAbstractArray('MaterialNames')
    materials = sorted(names.GetValue(i) for i in range(names.GetNumberOfValues())) if names else []
    return {'pointCount': poly.GetNumberOfPoints(), 'triangleCount': poly.GetNumberOfPolys(),
            'topologySha256': digest.hexdigest(), 'materialNames': materials}


def source_group_labels(path, poly):
    # OBJ declares the preserved group/material relation; VTK MaterialIds has a
    # NO_MATERIAL offset and must NOT be used as a naive MaterialNames index.
    declarations = []
    source_space = None
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.startswith('#') and 'SPACE=' in line:
                source_space = line.split('SPACE=', 1)[1].strip().split()[0]
            elif line.startswith('g '):
                declarations.append({'groupName': line[2:].strip()})
            elif line.startswith('usemtl '):
                if not declarations:
                    raise ValueError('Material declared before a group')
                declarations[-1]['materialName'] = line.split(None, 1)[1].strip()
    if source_space != 'LPS':
        raise ValueError(f'Expected explicit source SPACE=LPS, found {source_space!r}')
    if len(declarations) != 3 or set(np.unique(groups(poly))) != {0, 1, 2}:
        raise ValueError('Expected skull, left_orbit and right_orbit OBJ groups')
    xyz = points(poly)
    faces = triangles(poly)
    group_ids = groups(poly)
    result = {}
    for group_id, side in enumerate(SIDES):
        used = np.unique(faces[group_ids == group_id])
        center = xyz[used].mean(axis=0)
        result[side] = {**declarations[group_id], 'groupId': group_id,
                        'sourcePointCount': int(len(used)),
                        'sourceTriangleCount': int(np.count_nonzero(group_ids == group_id)),
                        'sourceCentroidLPS': center.tolist()}
    # Existing source group convention is also checked against patient LPS sides.
    if result['left']['sourceCentroidLPS'][0] <= result['right']['sourceCentroidLPS'][0]:
        raise ValueError('Source eye group order contradicts patient LPS left/right')
    result['provenance'] = 'Original OBJ group order skull,left_orbit,right_orbit; material names preserved; LPS side order checked'
    return result


def apply(matrix, xyz):
    return xyz @ matrix[:3, :3].T + matrix[:3, 3]


def recover_hardened_transform(original, stored, tolerance):
    a, b = points(original), points(stored)
    ids = np.unique(np.linspace(0, len(a) - 1, min(12000, len(a))).astype(np.int64))
    ac, bc = a[ids].mean(axis=0), b[ids].mean(axis=0)
    u, _, vt = np.linalg.svd((a[ids] - ac).T @ (b[ids] - bc))
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1] *= -1
        rotation = vt.T @ u.T
    matrix = np.eye(4)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = bc - rotation @ ac
    total_squared = 0.0
    maximum = 0.0
    for start in range(0, len(a), 100000):
        residual = np.linalg.norm(apply(matrix, a[start:start + 100000]) - b[start:start + 100000], axis=1)
        total_squared += float(residual @ residual)
        maximum = max(maximum, float(residual.max()))
    rms = float(np.sqrt(total_squared / len(a)))
    if maximum > tolerance:
        raise ValueError(f'Original vertex correspondence is not a rigid match: maximum residual {maximum:.6g} mm')
    return matrix, {'rmsMm': rms, 'maxMm': maximum, 'checkedVertices': len(a),
                    'rotationDeterminant': float(np.linalg.det(rotation)),
                    'acceptanceMaxMm': tolerance,
                    'method': 'Kabsch recovery of existing hardened transform from verified identical topology; no registration'}


def affine_from_itk(path):
    transform = sitk.ReadTransform(str(path))
    if not transform.IsLinear():
        raise ValueError('Nonlinear transform found; inverse matrix would be invalid')
    origin = np.asarray(transform.TransformPoint((0.0, 0.0, 0.0)))
    matrix = np.eye(4)
    matrix[:3, 3] = origin
    for axis in range(3):
        unit = np.zeros(3)
        unit[axis] = 1
        matrix[:3, axis] = np.asarray(transform.TransformPoint(tuple(unit))) - origin
    probes = np.array([[1., 2., 3.], [-73., 41., 24.], [19., -112., -58.]])
    actual = np.array([transform.TransformPoint(tuple(p)) for p in probes])
    if not np.allclose(apply(matrix, probes), actual, atol=1e-7, rtol=0):
        raise ValueError('Transform failed affine reconstruction check')
    return matrix


def parent_to_world_lps(node, by_id, storage_paths, seen=None):
    seen = set() if seen is None else seen
    parent_id = refs(node).get('transform')
    if not parent_id:
        return np.eye(4), []
    if parent_id in seen:
        raise ValueError('Cycle in MRML parent transforms')
    seen.add(parent_id)
    parent = by_id[parent_id]
    storage_id = refs(parent).get('storage')
    if not storage_id or storage_id not in storage_paths:
        raise ValueError('Transform lacks a supported storage file')
    from_parent_lps = affine_from_itk(storage_paths[storage_id])
    # ITK files use a resampling (from-parent) LPS transform. MRML display
    # geometry needs the inverse (model-to-parent). Never apply both directions.
    to_parent_lps = np.linalg.inv(from_parent_lps)
    higher, chain = parent_to_world_lps(parent, by_id, storage_paths, seen)
    entry = {'nodeId': parent_id, 'storage': storage_paths[storage_id].name,
             'itkFromParentLPS': from_parent_lps.ravel().tolist(),
             'appliedToParentLPS': to_parent_lps.ravel().tolist()}
    return higher @ to_parent_lps, [entry] + chain


def submesh(poly, group_id, matrix):
    selected_faces = triangles(poly)[groups(poly) == group_id]
    used, inverse = np.unique(selected_faces, return_inverse=True)
    xyz = apply(matrix, points(poly)[used])
    output = vtk.vtkPolyData()
    vtk_points = vtk.vtkPoints()
    vtk_points.SetData(numpy_to_vtk(np.ascontiguousarray(xyz), deep=True))
    output.SetPoints(vtk_points)
    faces = np.ascontiguousarray(inverse.reshape(-1, 3), dtype=np.int64)
    cells = vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0, faces.size + 1, 3, dtype=np.int64), deep=True),
                  numpy_to_vtkIdTypeArray(faces.ravel(), deep=True))
    output.SetPolys(cells)
    # Original triangle winding/topology are retained. STL stores face normals;
    # the writer recomputes them from the transformed triangle vertices.
    return output


def write_stl(path, poly):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.stl.tmp')
    writer = vtk.vtkSTLWriter()
    writer.SetFileName(str(temporary))
    writer.SetInputData(poly)
    writer.SetFileTypeToBinary()
    if writer.Write() != 1:
        raise IOError(f'Unable to write {path.name}')
    expected_bytes = 84 + 50 * poly.GetNumberOfPolys()
    if temporary.stat().st_size != expected_bytes:
        raise IOError('STL triangle/byte count mismatch')
    reader = vtk.vtkSTLReader()
    reader.SetFileName(str(temporary))
    reader.MergingOff()
    reader.Update()
    loaded = reader.GetOutput()
    if loaded.GetNumberOfPolys() != poly.GetNumberOfPolys():
        raise IOError('STL read-back changed triangle count')
    bound_error = float(np.max(np.abs(np.asarray(loaded.GetBounds()) - np.asarray(poly.GetBounds()))))
    if bound_error > 0.001:
        raise IOError(f'STL coordinate quantization error too large: {bound_error}')
    os.replace(temporary, path)
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': expected_bytes,
            'pointCount': poly.GetNumberOfPoints(), 'triangleCount': poly.GetNumberOfPolys(),
            'boundsWebMm': list(poly.GetBounds()), 'stlReadbackBoundErrorMm': bound_error}



def sample_surface(poly, sample_count=6000):
    xyz = points(poly)
    faces = triangles(poly)
    pi = np.unique(np.linspace(0, len(xyz) - 1, min(sample_count, len(xyz))).astype(np.int64))
    fi = np.unique(np.linspace(0, len(faces) - 1, min(sample_count, len(faces))).astype(np.int64))
    return np.vstack((xyz[pi], xyz[faces[fi]].mean(axis=1)))


def distance_to_surface(xyz, surface):
    locator = vtk.vtkStaticCellLocator()
    locator.SetDataSet(surface)
    locator.BuildLocator()
    closest = [0.0, 0.0, 0.0]
    cell_id, sub_id, squared = vtk.mutable(0), vtk.mutable(0), vtk.mutable(0.0)
    values = np.empty(len(xyz), dtype=np.float64)
    for i, point in enumerate(xyz):
        locator.FindClosestPoint(point, closest, cell_id, sub_id, squared)
        values[i] = float(squared)
    return np.sqrt(values)


def display_skull(poly):
    decimator = vtk.vtkDecimatePro()
    decimator.SetInputData(poly)
    decimator.SetTargetReduction(0.7)
    decimator.PreserveTopologyOn()
    decimator.SplittingOff()
    decimator.BoundaryVertexDeletionOff()
    decimator.SetErrorIsAbsolute(True)
    decimator.SetAbsoluteError(0.003)
    decimator.AccumulateErrorOn()
    decimator.Update()
    reduced = vtk.vtkPolyData()
    reduced.DeepCopy(decimator.GetOutput())
    forward = distance_to_surface(sample_surface(poly), reduced)
    backward = distance_to_surface(sample_surface(reduced), poly)
    errors = np.concatenate((forward, backward))
    accepted = float(errors.max()) <= 0.5
    report = {'sourcePointCount': poly.GetNumberOfPoints(),
              'sourceTriangleCount': poly.GetNumberOfPolys(),
              'candidatePointCount': reduced.GetNumberOfPoints(),
              'candidateTriangleCount': reduced.GetNumberOfPolys(),
              'accepted': accepted,
              'method': 'vtkDecimatePro PreserveTopologyOn; display copy only',
              'targetReduction': 0.7, 'absoluteErrorParameterMm': 0.003,
              'sampledSymmetricDistanceMaxMm': float(errors.max()),
              'sampledSymmetricDistanceP95Mm': float(np.percentile(errors, 95)),
              'checkedSamples': len(errors), 'acceptanceSampledMaxMm': 0.5,
              'errorScope': 'Deterministic samples of vertices and triangle centroids, not an exhaustive Hausdorff bound'}
    print(f"Skull display triangles {poly.GetNumberOfPolys()} -> {reduced.GetNumberOfPolys()}; sampled error {errors.max():.4f} mm", flush=True)
    return (reduced if accepted else poly), report


def eye_measurements(poly):
    edges = vtk.vtkFeatureEdges()
    edges.SetInputData(poly)
    edges.BoundaryEdgesOn()
    edges.NonManifoldEdgesOn()
    edges.FeatureEdgesOff()
    edges.ManifoldEdgesOff()
    edges.Update()
    invalid_edges = edges.GetOutput().GetNumberOfCells()
    xyz = points(poly)
    xyz = xyz - xyz.mean(axis=0)
    faces = triangles(poly)
    signed_mm3 = np.einsum('ij,ij->i', xyz[faces[:, 0]],
                          np.cross(xyz[faces[:, 1]], xyz[faces[:, 2]])).sum() / 6
    return {'source': 'Aligned closed surface mesh; distinct from CSV labelmap measurements',
            'boundaryOrNonManifoldEdges': invalid_edges,
            'closedSurface': invalid_edges == 0,
            'volumeCm3': float(abs(signed_mm3) / 1000) if invalid_edges == 0 else None}


def stored_transform_cross_checks(scene, storage_paths, matched):
    by_node = {entry['node'].get('id'): entry for entry in matched.values()}
    result = []
    for node in scene:
        if node.tag != 'Transform':
            continue
        node_refs = refs(node)
        moving = by_node.get(node_refs.get('spatialRegistrationMoving'))
        storage_path = storage_paths.get(node_refs.get('storage'))
        if moving is None or storage_path is None:
            continue
        stored = affine_from_itk(storage_path)
        inverse = np.linalg.inv(stored)
        result.append({'transformNodeId': node.get('id'),
                       'movingDate': moving['item']['date'],
                       'inverseFileVsRecoveredHardenedMaxMatrixDifference': float(np.abs(inverse - moving['hardened']).max()),
                       'forwardFileVsRecoveredHardenedMaxMatrixDifference': float(np.abs(stored - moving['hardened']).max()),
                       'purpose': 'Independent direction check against preserved vertex correspondence for a hardened model'})
    return result


def run(args):
    out = args.output.resolve()
    if not out.is_relative_to(ROOT.resolve()) or out == ROOT.resolve():
        raise ValueError('Output must be a dedicated subdirectory of this workspace')
    out.mkdir(parents=True, exist_ok=True)
    archive_hash = sha256_file(args.scene)
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    scene, by_id, storage_paths = unpack_scene(args.scene, out / 'source-cache', archive_hash)
    originals = {}
    for item in manifest:
        original_path = ROOT / item['obj']
        original = read_polydata(original_path, obj=True)
        sig = signature(original)
        key = (sig['pointCount'], sig['triangleCount'], sig['topologySha256'])
        if key in originals:
            raise ValueError('Two original dates have identical topology; explicit date mapping is required')
        labels = source_group_labels(original_path, original)
        originals[key] = {'item': item, 'signature': sig, 'groups': labels,
                          'path': original_path}
        print(f"Indexed original {item['date']}: {sig['pointCount']} points", flush=True)
    matched = {}
    for node in scene:
        if node.tag != 'Model':
            continue
        storage_id = refs(node).get('storage')
        if storage_id not in storage_paths:
            continue
        storage = by_id[storage_id]
        if storage.get('coordinateSystem') != 'LPS':
            raise ValueError('Only explicitly LPS model storage is supported')
        stored = read_polydata(storage_paths[storage_id])
        sig = signature(stored)
        key = (sig['pointCount'], sig['triangleCount'], sig['topologySha256'])
        if key not in originals:
            raise ValueError(f"Scene model {node.get('name')} has no exact original topology match")
        source = originals[key]
        if sig['materialNames'] != source['signature']['materialNames']:
            raise ValueError('Material identifiers differ despite matching topology')
        date = source['item']['date']
        if date in matched:
            raise ValueError('Two scene nodes matched the same date')
        original = read_polydata(source['path'], obj=True)
        hardened, fit = recover_hardened_transform(original, stored, args.max_residual_mm)
        parent_matrix, chain = parent_to_world_lps(node, by_id, storage_paths)
        native_to_scene = parent_matrix @ hardened
        matched[date] = {**source, 'node': node, 'storagePath': storage_paths[storage_id],
                         'hardened': hardened, 'fit': fit, 'parentMatrix': parent_matrix,
                         'nativeToScene': native_to_scene, 'transformChain': chain}
        print(f"Matched {node.get('name')} -> {date}; max residual {fit['maxMm']:.3g} mm; parent transforms {len(chain)}", flush=True)
    if set(matched) != {item['date'] for item in manifest}:
        raise ValueError('Scene does not contain exactly one matched model for every timeline date')
    reference = matched[manifest[0]['date']]
    ref_poly = read_polydata(reference['storagePath'])
    ref_skull = submesh(ref_poly, reference['groups']['skull']['groupId'], reference['parentMatrix'])
    bounds = np.asarray(ref_skull.GetBounds()).reshape(3, 2)
    common_center = bounds.mean(axis=1)
    center_matrix = np.eye(4)
    center_matrix[:3, 3] = -common_center
    skull_copy = submesh(ref_poly, reference['groups']['skull']['groupId'], center_matrix @ reference['parentMatrix'])
    skull_copy, skull_reduction = display_skull(skull_copy)
    shared_skull = write_stl(out / 'skull.stl', skull_copy)
    shared_skull['displaySimplification'] = skull_reduction
    report = {'schemaVersion': 1, 'caseLabel': 'case',
              'sourceScene': {'fileName': args.scene.name, 'sha256': archive_hash,
                              'bytes': args.scene.stat().st_size, 'mtimeUnix': args.scene.stat().st_mtime},
              'coordinateSystem': 'LPS, millimetres; one shared display-centering translation',
              'referenceDate': reference['item']['date'], 'commonCenterSceneLPS': common_center.tolist(),
              'registrationPerformed': False, 'sharedSkull': shared_skull, 'timepoints': [],
              'storedTransformDirectionCrossChecks': stored_transform_cross_checks(scene, storage_paths, matched),
              'notes': ['Original MRB and OBJs were opened read-only.',
                        'Manual alignment is preserved exactly; skulls are not automatically re-registered.',
                        'The fixed skull comes from the first chronological date.',
                        'Existing source measurement values are retained, not recomputed by this importer.',
                        'All original Table.tsv measurements currently repeat the same values; validate them before interpreting volume trends.']}
    new_manifest = copy.deepcopy(manifest)
    for item in new_manifest:
        entry = matched[item['date']]
        stored = read_polydata(entry['storagePath'])
        native_to_web = center_matrix @ entry['nativeToScene']
        scene_to_web = center_matrix @ entry['parentMatrix']
        web_to_native = np.linalg.inv(native_to_web)
        paths = {}
        exports = {}
        for side in ('left', 'right'):
            mesh = submesh(stored, entry['groups'][side]['groupId'], scene_to_web)
            exports[side] = write_stl(out / item['date'] / f'{side}_orbit.stl', mesh)
            exports[side]['geometricMeasurement'] = eye_measurements(mesh)
            paths[side] = exports[side]['path']
        # This supersedes the obsolete per-date centroid alignment.
        item.pop('skullAlignment', None)
        item['eyeModels'] = paths
        item['sharedSkull'] = shared_skull['path']
        item['meshMeasurements'] = {side: exports[side]['geometricMeasurement'] for side in ('left', 'right')}
        item['alignment'] = {'source': 'manual-slicer-scene', 'coordinateSystem': 'LPS',
                             'matrixOrder': 'row-major', 'referenceDate': reference['item']['date'],
                             'commonCenterSceneLPS': common_center.tolist(),
                             'nativeLPSToWeb': native_to_web.ravel().tolist(),
                             'webToNativeLPS': web_to_native.ravel().tolist(),
                             'nativeLPSToSceneLPS': entry['nativeToScene'].ravel().tolist()}
        # Validate inverse mapping against original vertices after all transformations.
        sample = points(stored)[::max(1, stored.GetNumberOfPoints() // 1000)]
        mapped = apply(web_to_native, apply(scene_to_web, sample))
        returned = apply(native_to_web, mapped)
        roundtrip_error = float(np.max(np.linalg.norm(returned - apply(scene_to_web, sample), axis=1)))
        if roundtrip_error > 1e-6:
            raise ValueError('Coordinate inverse round trip failed')
        report['timepoints'].append({'date': item['date'], 'sceneNodeId': entry['node'].get('id'),
                                    'sceneNodeName': entry['node'].get('name'),
                                    'sceneStorage': entry['storagePath'].name,
                                    'sourceObj': item['obj'], 'sourceSignature': entry['signature'],
                                    'groups': entry['groups'], 'hardenedRecovery': entry['fit'],
                                    'hardenedNativeToStoredLPS': entry['hardened'].ravel().tolist(),
                                    'parentTransformChain': entry['transformChain'],
                                    'alignment': item['alignment'], 'exports': exports,
                                    'inverseRoundtripMaxMm': roundtrip_error})
        print(f"Exported {item['date']} eyes; inverse error {roundtrip_error:.3g} mm", flush=True)
    # Publish metadata last, only after all validation passes.
    save_json(out / 'import-report.json', report)
    save_json(out / 'timeline.json', new_manifest)
    print(f'Created {out / "timeline.json"}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'web' / 'timeline.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'web' / 'aligned_scene')
    parser.add_argument('--max-residual-mm', type=float, default=0.02)
    run(parser.parse_args())
