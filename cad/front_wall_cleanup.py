"""Square the lower display end wall to the flat battery floor."""
import numpy as np
import manifold3d as mf


def cuboid(bounds):
    lo, hi = np.asarray(bounds, dtype=float).T
    return mf.Manifold.cube(hi-lo).translate(lo)


def tools(parameters, inward_planes):
    spec = parameters.get('square_lower_front_wall')
    if not spec:
        return [], []
    wall = cuboid(spec['wall_fill_bounds_mm'])
    floor = cuboid(spec['floor_fill_bounds_mm'])
    cut = cuboid(spec['interior_trim_bounds_mm'])
    half = spec['central_half_width_mm']
    central = cut ^ cuboid([[-half, half], [-180, 20], [-50, 30]])
    # Outside the central bay, retain the original inclined fin surfaces.
    for _, normal, point in inward_planes:
        cut = cut.trim_by_plane(normal.tolist(), float(normal @ point)-.0001)
    cut += central
    lo, hi = np.asarray(parameters['display_access_bounds_mm']).T.copy()
    hi[1] = spec['interior_trim_bounds_mm'][1][1] + .0001
    wall -= mf.Manifold.cube(hi-lo).translate(lo)
    return [wall, floor], [cut]


def apply(result, parameters):
    if not parameters.get('square_lower_front_wall'):
        return result
    import trimesh
    from internal_rim_cleanup import inward_planes_from_mesh
    raw = result.to_mesh64()
    mesh = trimesh.Trimesh(raw.vert_properties[:, :3], raw.tri_verts, process=True)
    fills, cuts = tools(parameters, inward_planes_from_mesh(mesh))
    for fill in fills:
        result += fill
    for cut in cuts:
        result -= cut
    return result
