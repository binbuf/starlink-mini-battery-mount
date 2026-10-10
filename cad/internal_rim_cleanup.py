"""Remove obsolete inward ledges while keeping the exterior and fin planes."""
import numpy as np
import manifold3d as mf
import trimesh
from shapely.geometry import Polygon, box
from shapely.geometry.polygon import orient

def as_solid(mesh):
    shape = mf.Manifold(mf.Mesh64(np.asarray(mesh.vertices, dtype=np.float64),
                                 np.asarray(mesh.faces, dtype=np.uint64)))
    assert shape.status() == mf.Error.NoError
    return shape

def inward_planes_from_mesh(mesh):
    centres, normals = mesh.triangles_center, mesh.face_normals
    planes = []
    for sign in (-1, 1):
        selected = ((sign*centres[:,0] > 78) & (sign*centres[:,0] < 96)
                    & (centres[:,1] > -135) & (centres[:,1] < -70)
                    & (centres[:,2] < -9.9) & (normals[:,2] > .8)
                    & (sign*normals[:,0] < -.3))
        ids = max((f for f in mesh.facets if selected[f].any()),
                  key=lambda f: mesh.area_faces[f].sum())
        planes.append((sign, normals[ids[0]], mesh.triangles[ids[0],0]))
    return planes

def cutters(parameters, inward_planes):
    profile = Polygon(parameters['internal_rim_cleanup_outer_xy_mm'])
    cavity = profile.buffer(-parameters['attachment_frame_wall_mm'], join_style='mitre')
    y0, y1 = parameters['internal_rim_cleanup_y_mm']
    z0, z1 = parameters['internal_rim_cleanup_z_mm']
    min_x = parameters['internal_rim_cleanup_min_abs_x_mm']
    results = []
    for sign, normal, point in inward_planes:
        roi = box(min_x, y0, 110, y1) if sign > 0 else box(-110, y0, -min_x, y1)
        polygon = orient(cavity.intersection(roi), sign=1)
        assert polygon.geom_type == 'Polygon' and polygon.area > 0
        cut = mf.Manifold.extrude(mf.CrossSection([np.asarray(polygon.exterior.coords[:-1])]), z1-z0).translate([0,0,z0])
        normal = np.asarray(normal); normal = normal / np.linalg.norm(normal)
        # Stay on the cavity side of the existing analytic inner fin plane.
        # A 0.0001 mm overlap avoids zero-thickness sheets at coplanar seams.
        cut = cut.trim_by_plane(normal.tolist(), float(np.dot(normal, point)) - .0001)
        results.append(cut)
    return results

def remove(mesh, parameters, inward_planes):
    result = as_solid(mesh)
    for cutter in cutters(parameters, inward_planes):
        result -= cutter
    raw = result.to_mesh64()
    output = trimesh.Trimesh(raw.vert_properties[:,:3], raw.tri_verts, process=True)
    components = output.split(only_watertight=False)
    positive = [m for m in components if m.volume > 1e-7]
    scraps = [m for m in components if m.volume <= 1e-7]
    assert len(positive) == 1
    # Coplanar boolean seams can produce paired zero-volume triangles.
    # Reject substantive extra components; discard only those numerical sheets.
    assert all(abs(m.volume) < 1e-8 and len(m.faces) <= 2 for m in scraps)
    output = positive[0]
    assert output.is_volume and len(output.split()) == 1
    return output
