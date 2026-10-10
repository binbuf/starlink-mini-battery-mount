"""Build a faceted solid with shared topology, avoiding sewing tiny triangles."""
import time
import numpy as np
import cadquery as cq
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeEdge,
                              BRepBuilderAPI_MakeWire, BRepBuilderAPI_MakeFace,
                              BRepBuilderAPI_MakeSolid)
from OCP.TopoDS import TopoDS, TopoDS_Shell
from OCP.gp import gp_Pnt, gp_Pln, gp_Dir
from OCP.BRepLib import BRepLib


def convert(mesh):
    start = time.monotonic()
    builder = BRep_Builder()
    verts = [BRepBuilderAPI_MakeVertex(gp_Pnt(*p)).Vertex() for p in mesh.vertices]
    for v in verts:
        builder.UpdateVertex(v, 1e-9)
    edges = {}
    shells = []
    # Boundary components include the oriented inner cavity shell.
    groups = mesh.face_adjacency
    import trimesh
    components = trimesh.graph.connected_components(groups, nodes=np.arange(len(mesh.faces)))
    for indices in components:
        shell = TopoDS_Shell()
        builder.MakeShell(shell)
        for index in indices:
            ids = mesh.faces[index]
            wire = BRepBuilderAPI_MakeWire()
            for a, b in zip(ids, np.roll(ids, -1)):
                key = (min(a, b), max(a, b))
                if key not in edges:
                    edges[key] = BRepBuilderAPI_MakeEdge(verts[key[0]], verts[key[1]]).Edge()
                    builder.UpdateEdge(edges[key], 1e-9)
                edge = edges[key] if a < b else TopoDS.Edge_s(edges[key].Reversed())
                wire.Add(edge)
            p = mesh.vertices[ids]
            normal = np.cross(p[1]-p[0], p[2]-p[0])
            magnitude=np.linalg.norm(normal)
            assert magnitude>0, 'Exactly degenerate triangle'
            plane = gp_Pln(gp_Pnt(*p[0]), gp_Dir(*(normal/magnitude)))
            face = BRepBuilderAPI_MakeFace(plane, wire.Wire(), True).Face()
            builder.Add(shell, face)
        shells.append(shell)
    maker = BRepBuilderAPI_MakeSolid()
    for shell in shells:
        maker.Add(shell)
    solid = cq.Solid(maker.Solid())
    BRepLib.OrientClosedSolid_s(solid.wrapped)
    print('Shared topology', len(edges), 'edges', len(shells), 'shells',
          'valid', solid.isValid(), 'volume', solid.Volume(),
          'seconds', round(time.monotonic()-start, 1), flush=True)
    solid.exportBrep(str(__import__('pathlib').Path(__file__).parent/'out/shared_debug.brep'))
    assert solid.isValid()
    assert abs(solid.Volume()-mesh.volume) < .02
    # Coplanar merging is optional and costly for fine contact triangulations.
    # Larger meshes already form a valid closed solid with shared topology.
    if len(mesh.faces)<60000:
        cleaned = solid.clean()
        if cleaned.isValid() and abs(cleaned.Volume()-mesh.volume) < .02:
            solid = cleaned
    return solid
