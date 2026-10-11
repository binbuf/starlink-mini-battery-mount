"""Restore printable backing under the inward sides of the P19 nub seats."""
import manifold3d as mf
import numpy as np


def fills(parameters):
    spec = parameters.get('locator_bridge_backing')
    if not spec:
        return []
    result = []
    for sign in (-1, 1):
        x_bounds = sorted(sign * x for x in spec['abs_x_bounds_mm'])
        lo, hi = np.array([x_bounds, spec['y_bounds_mm'],
                           spec['z_bounds_mm']], dtype=float).T
        result.append(mf.Manifold.cube(hi - lo).translate(lo))
    return result


def apply(shape, parameters):
    for fill in fills(parameters):
        shape += fill
    assert shape.status() == mf.Error.NoError
    return shape
