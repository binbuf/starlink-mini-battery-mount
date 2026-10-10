"""Local backing inside the two track breakthroughs, fitted to the Mini."""
import numpy as np
import manifold3d as md
import trimesh
from build_design import P, box
from generate_mount import mesh_shape
from generate_mount_v3 import difference


def bounding_meshes():
    (xa, xb), (ya, yb), (za, zb) = P['track_backing_bounds_positive_mm']
    return [mesh_shape(box(*((-xb, -xa) if sign < 0 else (xa, xb)),
                           ya, yb, za, zb)) for sign in (-1, 1)]


def make(precise, official):
    tools = [precise, official]
    for axis in range(3):
        for sign in (-1, 1):
            relief = precise.copy()
            delta = np.zeros(3)
            delta[axis] = sign * P['mating_clearance_axes_mm']
            relief.apply_translation(delta)
            tools.append(relief)
    return [difference(patch, tools) for patch in bounding_meshes()]


def join(body, patches):
    # Join in float64: re-unioning the complete faceted rail in float32 can
    # create duplicate zero-thickness sheets at existing coplanar seams.
    def manifold(mesh):
        result=md.Manifold(md.Mesh64(np.asarray(mesh.vertices,dtype=np.float64),
                                   np.asarray(mesh.faces,dtype=np.uint64)))
        assert result.status()==md.Error.NoError
        return result
    result=manifold(body)
    for patch in patches:
        result+=manifold(patch)
    mesh=result.to_mesh64()
    return trimesh.Trimesh(mesh.vert_properties[:,:3],mesh.tri_verts,process=True)
