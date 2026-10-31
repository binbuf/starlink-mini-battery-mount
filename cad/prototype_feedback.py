"""Reinforced OEM-style locator: slot-filling tab on a flush seat.

The tab fills most of the Mini's kickstand slot (19.31 x 3.12 x 2.00 mm) and
rises straight out of the surrounding plate.  See docs/locator-tabs.md for the
measurements and rationale.
"""
import math
import cadquery as cq
import numpy as np
from shapely.geometry import Polygon
from build_design import P, box


def locator_coordinates(sign):
    return sign*P['locator_center_x_mm'], P['locator_center_y_mm']


def locator_seat_tools():
    """Cut the seat area back to the level of the surrounding plate.

    The seat is not a pocket: the cut stops at `locator_seat_top_z_mm`, which is
    the top of the surrounding plate, so the tab rises from a flush surface with
    a single step.
    """
    seat_top = P['locator_seat_top_z_mm']
    width, depth = P['locator_recess_size_mm']
    tools = []
    for sign in (-1, 1):
        x, y = locator_coordinates(sign)
        shape = box(x-width/2, x+width/2, y-depth/2, y+depth/2, seat_top, 2)
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


def locator_section(z):
    """Tab cross-section size at height z, measured from the flush seat."""
    seat = P['locator_seat_top_z_mm']
    top = P['locator_root_z_mm'] + P['locator_height_mm']
    u = (z-seat)/(top-seat)
    width = P['locator_base_width_mm']+u*(P['locator_tip_width_mm']-P['locator_base_width_mm'])
    thickness = P['locator_base_thickness_mm']+u*(P['locator_tip_thickness_mm']-P['locator_base_thickness_mm'])
    return width, thickness


def locator_profile(width, thickness, segments=48):
    """Stadium outline matching the rounded ends of the Mini's slot."""
    radius = thickness/2
    centre = width/2-radius
    points = []
    for cx, start in ((centre, -90), (-centre, 90)):
        for index in range(segments):
            angle = math.radians(start+180*index/(segments-1))
            points.append((cx+radius*math.cos(angle), radius*math.sin(angle)))
    return points


def _loft(stations):
    """Ruled loft through (z, x, y, outline) stations."""
    wires = [cq.Wire.makePolygon([cq.Vector(x+px, y+py, z) for px, py in outline],
                                 close=True)
             for z, x, y, outline in stations]
    solid = cq.Solid.makeLoft(wires, True)
    if solid.Volume() < 0:
        solid = cq.Solid.makeLoft(list(reversed(wires)), True)
    assert solid.isValid() and solid.Volume() > 0
    return solid


def tapered_locator(dish, sign):
    """Slot-filling tab grown from just inside the flush seat.

    The root is buried `locator_root_embed_mm` below the seat so the union with
    the plate is volumetric; a purely coplanar union leaves a thin downward
    sliver at the tab base (it shows up as an overhang under the tab ends).
    """
    x, y = locator_coordinates(sign)
    seat = P['locator_seat_top_z_mm']
    base = seat-P['locator_root_embed_mm']
    top = P['locator_root_z_mm']+P['locator_height_mm']
    base_w, base_t = locator_section(base)

    tab = (cq.Workplane('XY', origin=(x, y, base))
           .slot2D(base_w, base_t, 0)
           .workplane(offset=top-base)
           .slot2D(P['locator_tip_width_mm'], P['locator_tip_thickness_mm'], 0)
           .loft(ruled=True).val())

    assert tab.isValid() and len(tab.Solids()) == 1
    assert abs(tab.intersect(dish).Volume()) < 1e-5, 'Locator clips the Mini'
    # Sanity: the engaged section must stay a real slot-filling tab.
    section = Polygon(locator_profile(*locator_section(P['contact_z_mm'])))
    assert section.is_valid and section.area > 35, 'Locator section collapsed'
    return tab


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
