"""Preserve the retained example mesh as a faceted CAD solid.

The cut removes the port region containing a nonmanifold edge. The two
zero-volume two-triangle components are excluded explicitly, with an audit.
No vertex positions are scaled, smoothed, or fitted.
"""
from pathlib import Path
import json
import time
import cadquery as cq
import trimesh
from OCP.BRepLib import BRepLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid

ROOT = Path(__file__).resolve().parents[1]


def clipped_reference(cut_y=-38.0):
    mesh = trimesh.load(ROOT / "docs/example-mount/exterior.stl", force="mesh")
    components = sorted(mesh.split(only_watertight=False), key=lambda m: len(m.faces), reverse=True)
    assert [len(c.faces) for c in components] == [22330, 2, 2]
    assert all(abs(c.volume) < 1e-7 for c in components[1:])
    clipped = components[0].slice_plane([0, cut_y, 0], [0, -1, 0], cap=True)
    assert clipped.is_volume and len(clipped.split()) == 1
    return clipped


def to_solid(mesh):
    faces = []
    start = time.monotonic()
    for triangle in mesh.triangles:
        wire = cq.Wire.makePolygon([cq.Vector(*point) for point in triangle], close=True)
        faces.append(cq.Face.makeFromWires(wire))
    print(f"Created {len(faces)} CAD triangle faces in {time.monotonic()-start:.1f}s", flush=True)
    sewn = cq.Shell.makeShell(faces)
    shells = sewn.Shells()
    print("Boundary shells", len(shells), flush=True)
    builder = BRepBuilderAPI_MakeSolid()
    for shell in shells:
        builder.Add(shell.wrapped)
    solid = cq.Solid(builder.Solid())
    BRepLib.OrientClosedSolid_s(solid.wrapped)
    assert solid.isValid(), "Faceted reference CAD solid is invalid"
    assert abs(solid.Volume()-mesh.volume) < 0.02
    print(f"Sewn solid in {time.monotonic()-start:.1f}s; cleaning coplanar faces", flush=True)
    cleaned = solid.clean()
    assert cleaned.isValid() and len(cleaned.Solids()) == 1
    assert abs(cleaned.Volume()-mesh.volume) < 0.02
    print(f"Cleaned to {len(cleaned.Faces())} faces in {time.monotonic()-start:.1f}s", flush=True)
    return cleaned


if __name__ == "__main__":
    mesh = clipped_reference()
    solid = to_solid(mesh)
    out = ROOT / "cad/out"
    out.mkdir(exist_ok=True)
    solid.exportBrep(str(out / "reference_retained.brep"))
    (out / "reference_retained_audit.json").write_text(json.dumps({
        "cut_y_mm": -38, "removed_zero_volume_components": 2,
        "source_vertex_movement_mm": 0, "retained_mesh_triangles": len(mesh.faces),
        "solid_valid": solid.isValid(), "cad_faces": len(solid.Faces()),
        "mesh_volume_mm3": mesh.volume, "cad_volume_mm3": solid.Volume(),
    }, indent=2), encoding="utf-8")
