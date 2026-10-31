"""Extract eye meshes from Slicer OBJ files without modifying the originals."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "eye_models"

def vertices_of(path: Path):
    vertices = []
    for line in path.open(encoding="utf-8", errors="replace"):
        if line.startswith("v "):
            p = line.split()
            vertices.append(tuple(float(x) for x in p[1:4]))
    return vertices

def collect_faces(path: Path, group_index: int, spool: Path):
    group = -1
    used = set()
    with path.open(encoding="utf-8", errors="replace") as src, spool.open("w", encoding="ascii", newline="\n") as out:
        for line in src:
            if line.startswith("g "):
                group += 1
            elif line.startswith("f ") and group == group_index:
                tokens = line.split()[1:]
                out.write(" ".join(tokens) + "\n")
                used.update(int(t.split("/")[0]) for t in tokens)
    return sorted(used)

def write_mesh(path: Path, vertices, used, spool: Path, shift):
    remap = {old: i + 1 for i, old in enumerate(used)}
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# Extracted eye mesh; source OBJ preserved.\n")
        for old in used:
            x, y, z = vertices[old - 1]
            f.write(f"v {x + shift[0]:.6f} {y + shift[1]:.6f} {z + shift[2]:.6f}\n")
        for face in spool.open(encoding="ascii"):
            f.write("f " + " ".join(str(remap[int(tok.split("/")[0])]) for tok in face.split()) + "\n")

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "web" / "timeline.json").read_text(encoding="utf-8"))
    first_center = None
    for item in manifest:
        src = ROOT / item["obj"]
        vertices = vertices_of(src)
        # Slicer writes these in skull, left orbit, right orbit order.
        temp = OUT / ".faces_tmp"
        temp.mkdir(exist_ok=True)
        try:
            skull_spool = temp / "skull.faces"
            skull_indices = collect_faces(src, 0, skull_spool)
            if not skull_indices:
                raise RuntimeError(f"No skull faces found in {src}")
            skull_points = [vertices[i - 1] for i in skull_indices]
            center = tuple(sum(p[k] for p in skull_points) / len(skull_points) for k in range(3))
            if first_center is None:
                first_center = center
            shift = tuple(-center[k] for k in range(3))
            target = OUT / item["date"]
            target.mkdir(parents=True, exist_ok=True)
            if item is manifest[0]:
                write_mesh(OUT / "skull.obj", vertices, skull_indices, skull_spool, shift)
            for group_index, side in ((1, "left"), (2, "right")):
                spool = temp / f"{side}.faces"
                used = collect_faces(src, group_index, spool)
                if not used:
                    raise RuntimeError(f"No {side} orbit faces found in {src}")
                write_mesh(target / f"{side}_orbit.obj", vertices, used, spool, shift)
        finally:
            for path in temp.glob("*.faces"):
                path.unlink(missing_ok=True)
            temp.rmdir()
        item["eyeModels"] = {"left": f"web/eye_models/{item['date']}/left_orbit.obj", "right": f"web/eye_models/{item['date']}/right_orbit.obj"}
        item["skullAlignment"] = {"translation": list(shift), "reference": manifest[0]["date"]}
    (ROOT / "web" / "timeline.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"extracted {len(manifest)} timepoints to {OUT}")

if __name__ == "__main__":
    main()
