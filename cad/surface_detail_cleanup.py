"""Local enclosure surface cleanup, away from the Mini attachment features."""
import numpy as np
import manifold3d as mf


def edge_trench_fills(parameters):
    spec = parameters.get('locator_edge_trench_fill')
    if not spec:
        return []
    z0, z1 = spec['bottom_z_mm'], spec['top_z_mm']
    return [mf.Manifold.extrude(mf.CrossSection([np.asarray(profile)]), z1-z0)
            .translate([0, 0, z0]) for profile in spec['profiles_xy_mm']]


def right_bottom_fill(parameters):
    spec = parameters.get('right_bottom_recess_fill')
    if not spec:
        return None
    y0, y1 = spec['y_bounds_mm']
    profile = np.asarray(spec['profile_xz_mm'], dtype=float)
    following = np.roll(profile, -1, axis=0)
    if np.sum(profile[:,0]*following[:,1]-profile[:,1]*following[:,0]) < 0:
        profile = profile[::-1]
    # Extrude the measured X/Z section along -Y to continue the rear bevel.
    return (mf.Manifold.extrude(mf.CrossSection([profile]), y1-y0)
            .rotate([90, 0, 0]).translate([0, y1, 0]))


def all_fills(parameters):
    fills = edge_trench_fills(parameters)
    bottom = right_bottom_fill(parameters)
    if bottom is not None:
        fills.append(bottom)
    from lower_side_cleanup import exterior_fill
    lower = exterior_fill(parameters)
    if lower is not None:
        fills.append(lower)
    return fills


def apply(result, parameters):
    for fill in all_fills(parameters):
        result += fill
    from lower_side_cleanup import blend_interior
    from front_wall_cleanup import apply as square_front_wall
    return square_front_wall(blend_interior(result, parameters), parameters)
