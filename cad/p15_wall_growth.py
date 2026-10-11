"""Grow the right interior lip toward the battery and upward."""
import numpy as np
import manifold3d as mf
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


def solid(parameters):
    spec = parameters.get('p15_wall_growth')
    if not spec:
        return None
    result = mf.Manifold()
    for section in spec['sections']:
        profile = np.asarray(orient(Polygon(section['profile_xz_mm'])).exterior.coords[:-1])
        y0, y1 = section['y_bounds_mm']
        result += (mf.Manifold.extrude(mf.CrossSection([profile]), y1-y0)
                   .rotate([90, 0, 0]).translate([0, y1, 0]))
    return result
