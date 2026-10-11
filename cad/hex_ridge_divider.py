"""A raised wall following the measured upper outline of a floor hexagon row."""
import numpy as np
import manifold3d as mf
from shapely.geometry import LineString, box
from shapely.geometry.polygon import orient


def footprint(parameters):
    spec = parameters.get('hex_ridge_divider')
    if not spec:
        return None
    path = LineString(spec['edge_polyline_xy_mm'])
    # Positive side of an X-increasing path is the solid land above the holes.
    polygon = path.buffer(spec['thickness_mm'], single_sided=True,
                          cap_style='flat', join_style='mitre')
    start, end = path.coords[0][0], path.coords[-1][0]
    polygon = polygon.intersection(box(start, -200, end, 0))
    assert polygon.geom_type == 'Polygon' and polygon.is_valid
    return orient(polygon, sign=1)


def solid(parameters):
    spec = parameters.get('hex_ridge_divider')
    if not spec:
        return None
    polygon = footprint(parameters)
    overlap = spec.get('root_overlap_mm', .05)
    return (mf.Manifold.extrude(mf.CrossSection([np.asarray(polygon.exterior.coords[:-1])]),
                                spec['height_mm'] + overlap)
            .translate([0, 0, spec['base_z_mm'] - overlap]))
