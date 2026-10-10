"""Symmetric exterior fairing and continuous interior wall transitions."""
import numpy as np
import manifold3d as mf
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


def prism(profile, depth):
    contour = np.asarray(orient(Polygon(profile)).exterior.coords[:-1])
    return mf.Manifold.extrude(mf.CrossSection([contour]), depth)


def exterior_fill(parameters):
    spec = parameters.get('lower_side_fairing')
    if not spec:
        return None
    base = prism(spec['preserved_baseline_xy_mm'], 43).translate([0, 0, -40])
    stations = spec['upper_yz_mm']
    profile = [[stations[0][0], -40], [stations[-1][0], -40]] + stations[::-1]
    cap = prism(profile, 220).rotate([90, 0, 90]).translate([-110, 0, 0])
    fill = prism(spec['outer_xy_mm'], 38.4606).translate([0, 0, -36.4606])
    fill = (fill - base) ^ cap
    for normal, distance in spec['bevel_planes']:
        fill = fill.trim_by_plane((-np.asarray(normal)).tolist(), -distance)
    # Restrict fairing to the sidewalls; the front edge crosses the power window.
    min_x = spec['min_abs_x_mm']
    central = mf.Manifold.cube([2*min_x, 200, 80]).translate([-min_x, -180, -50])
    fill -= central
    # Retain the complete existing connector gap on the left side.
    window = mf.Manifold.cube([48, 62, 12.4606]).translate([-115, -124, -30.4606])
    return fill - window


def interior_tools(parameters, inward_planes):
    spec = parameters.get('lower_interior_blend')
    if not spec:
        return [], []
    def yz(profile):
        return prism(profile, 220).rotate([90, 0, 90]).translate([-110, 0, 0])
    wall_cut = yz(spec['end_cut_yz_mm'])
    wall_fill = yz(spec['end_fill_yz_mm'])
    # The battery bay lies below the fin planes at the end corners. Continue
    # the blend through that central bay instead of leaving triangular steps.
    half = spec['central_return_half_width_mm']
    central = mf.Manifold.cube([2*half, 200, 80]).translate([-half, -180, -50])
    central_cut, central_fill = wall_cut ^ central, wall_fill ^ central
    for _, normal, point in inward_planes:
        distance = float(np.dot(normal, point)) - .0001
        wall_cut = wall_cut.trim_by_plane(normal.tolist(), distance)
        wall_fill = wall_fill.trim_by_plane(normal.tolist(), distance)
    wall_cut += central_cut
    wall_fill += central_fill
    lo, hi = np.asarray(parameters['display_access_bounds_mm']).T.copy()
    hi[1] = spec['display_clearance_end_y_mm']
    wall_fill -= mf.Manifold.cube(hi-lo).translate(lo)
    cuts = [wall_cut]
    y0, y1 = spec['side_y_mm']
    for sign in (-1, 1):
        profile = np.asarray(spec['side_bevel_xz_mm']).copy()
        profile[:, 0] *= sign
        cuts.append(prism(profile, y1-y0).rotate([90, 0, 0]).translate([0, y1, 0]))
    return [wall_fill], cuts


def blend_interior(result, parameters):
    if not parameters.get('lower_interior_blend'):
        return result
    import trimesh
    from internal_rim_cleanup import inward_planes_from_mesh
    raw = result.to_mesh64()
    mesh = trimesh.Trimesh(raw.vert_properties[:, :3], raw.tri_verts, process=True)
    fills, cuts = interior_tools(parameters, inward_planes_from_mesh(mesh))
    for fill in fills:
        result += fill
    for cut in cuts:
        result -= cut
    return result
