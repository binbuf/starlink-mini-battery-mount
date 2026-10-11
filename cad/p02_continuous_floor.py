"""Continue the main floor lattice through the former straight battery stop."""
import numpy as np
import manifold3d as mf


def hexagon(centre, radius):
    angles = np.pi / 2 + np.arange(6) * np.pi / 3
    return np.column_stack((np.cos(angles), np.sin(angles))) * radius + centre


def prism(points, bottom, top):
    return mf.Manifold.extrude(mf.CrossSection([np.asarray(points)]), top-bottom).translate([0, 0, bottom])


def apply(result, parameters):
    spec = parameters.get('p02_continuous_floor')
    if not spec:
        return result
    bottom, top = spec['floor_z_mm']
    # Replace the old smaller, independently phased holes with the main lattice.
    for centre in spec['old_hole_centres_xy_mm']:
        result += prism(hexagon(centre, spec['old_radius_mm']+.0001), bottom, top)
    lo, hi = np.asarray(spec['old_stop_cut_bounds_mm']).T
    result -= mf.Manifold.cube(hi-lo).translate(lo)
    for centre in spec['new_hole_centres_xy_mm']:
        result -= prism(hexagon(centre, spec['radius_mm']), bottom-.001, top+.0001)
    return result
