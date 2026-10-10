"""OEM-sized tapered nubs, root reliefs, access windows and printable lip ramps."""
import cadquery as cq
import numpy as np
from shapely.geometry import Polygon
from build_design import P, box


def locator_coordinates(sign):
    return sign*P['locator_center_x_mm'], P['locator_center_y_mm']


def locator_seat_tools():
    root = P['locator_root_z_mm']
    width, depth = P['locator_recess_size_mm']
    tools = []
    for sign in (-1, 1):
        x, y = locator_coordinates(sign)
        shape = box(x-width/2, x+width/2, y-depth/2, y+depth/2, root, 2)
        tools.append(cq.Workplane('XY').newObject([shape]).edges('|Z').fillet(1).val())
    if P.get('locator_release_recess_bounds_mm'):
        tools.append(release_recess_tool())
    return tools


def release_recess_tool():
    """Rounded shallow purchase at the centre of the power-port plate edge."""
    (x0, x1), (y0, y1), (z0, z1) = P['locator_release_recess_bounds_mm']
    cutter = box(x0, x1, y0, y1, z0, z1)
    return (cq.Workplane('XY').newObject([cutter]).edges('|Z').fillet(3)
            .edges('<Z').fillet(.8).val())


def tapered_locator(dish, sign):
    x, y = locator_coordinates(sign)
    root = P['locator_root_z_mm']
    height = P['locator_height_mm']
    width = P['locator_base_width_mm']
    thickness = P['locator_base_thickness_mm']
    # A small root overlap joins the remaining locator-plate backing.
    nub = (cq.Workplane('XY', origin=(x, y, root-.05))
           .rect(width, thickness).workplane(offset=.05).rect(width, thickness)
           .workplane(offset=height)
           .rect(P['locator_tip_width_mm'], P['locator_tip_thickness_mm'])
           .loft(ruled=True).val())
    span = P['locator_root_support_span_mm']
    support_height = P['locator_root_support_height_mm']
    # Each short end joins its two corner supports into one tapered gusset.
    # The outer edges of the long sides rise gradually into the nub; the
    # central gap between the two end gussets remains open on both long sides.
    for sx in (-1, 1):
        cx = x+sx*(width/2-span/2+.3)
        local_width = width+support_height/height*(P['locator_tip_width_mm']-width)
        local_thickness = thickness+support_height/height*(P['locator_tip_thickness_mm']-thickness)
        inner = x+sx*(width/2-span+.3)
        outer = x+sx*local_width/2
        upper_centre = (inner+outer)/2
        pad = (cq.Workplane('XY', origin=(cx, y, root-.05))
               .rect(span, thickness+span)
               .workplane(offset=.05).rect(span, thickness+span)
               .workplane(offset=support_height)
               .center(upper_centre-cx, 0)
               .rect(abs(outer-inner), local_thickness)
               .loft(ruled=True).val())
        nub = nub.fuse(pad)
    nub = nub.clean()
    assert nub.isValid() and len(nub.Solids()) == 1
    assert abs(nub.intersect(dish).Volume()) < 1e-5, 'OEM-style locator clips Mini'
    return nub


def access_window_tools():
    result = []
    for key in ('power_end_access_bounds_mm', 'display_access_bounds_mm'):
        (x0, x1), (y0, y1), (z0, z1) = P[key]
        result.append(box(x0, x1, y0, y1, z0, z1))
    return result


def lip_ramps(reference):
    """Grow each short ledge downward/outward at 45 degrees to meet its fin.

    Only existing horizontal ledge undersides are used. The top wire is the
    actual ledge footprint; the bottom wire moves outward as far as it moves
    downward. Subsequent official-Mini clearance trimming limits new material.
    """
    depth = P['fin_lip_ramp_depth_mm']
    ramps = []
    for facet in reference.facets:
        normal = reference.face_normals[facet[0]]
        points = reference.vertices[np.unique(reference.faces[facet])]
        centre = reference.triangles_center[facet].mean(0)
        if (normal[2] > -.99999 or abs(centre[0]) < 75 or
                not -9.9 < centre[2] < -7.9 or
                reference.area_faces[facet].sum() < .2):
            continue
        footprint = Polygon()
        for tri in reference.triangles[facet]:
            footprint = footprint.union(Polygon(tri[:, :2]))
        polygons = list(footprint.geoms) if hasattr(footprint, 'geoms') else [footprint]
        for polygon in polygons:
            if polygon.area < .2:
                continue
            assert not polygon.interiors
            xy = np.asarray(polygon.exterior.coords[:-1])
            sign = np.sign(centre[0])
            top = np.column_stack([xy, np.full(len(xy), centre[2]+.005)])
            bottom = top + [sign*depth, 0, -depth]
            a = cq.Wire.makePolygon([cq.Vector(*v) for v in bottom], close=True)
            b = cq.Wire.makePolygon([cq.Vector(*v) for v in top], close=True)
            ramp = cq.Solid.makeLoft([a, b], ruled=True)
            assert ramp.isValid()
            ramps.append(ramp)
    assert len(ramps) >= 2, 'No trench ledge undersides found'
    return ramps
