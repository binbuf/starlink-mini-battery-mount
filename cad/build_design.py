"""Parametric battery cradle with original, retained reference mating geometry.

All units are mm. This is the editable source; STEP transfers its solid shape.
"""
from pathlib import Path
import json
import time
import cadquery as cq
import numpy as np
import shapely
from shapely.geometry import Polygon, box as polygon_box
from shapely.ops import unary_union
from reference_solid import clipped_reference, to_solid

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "cad/out"
P = json.loads((ROOT / "cad/design_parameters.json").read_text())


def box(x0, x1, y0, y1, z0, z1):
    return (cq.Workplane("XY").box(x1-x0, y1-y0, z1-z0)
            .translate(((x0+x1)/2, (y0+y1)/2, (z0+z1)/2)).val())


def check(shape, name, one=True):
    print(name, "valid", shape.isValid(), "solids", len(shape.Solids()),
          "faces", len(shape.Faces()), "volume_cm3", round(shape.Volume()/1000, 3), flush=True)
    assert shape.isValid(), name + " is invalid"
    if one:
        assert len(shape.Solids()) == 1, name + " must be one connected solid"
    return shape


def make_locator(dish, sign):
    if P.get('locator_profile') == 'oem_tapered':
        from prototype_feedback import tapered_locator
        return tapered_locator(dish, sign)
    # Capture the real drafted and blended cavity directly from official STEP.
    x0, x1 = ((13, 34) if sign > 0 else (-34, -13))
    cavity = box(x0, x1, -45.5, -40.9, -6.44, -4.4606).cut(dish)
    check(cavity, "locator cavity")
    bb = cavity.BoundingBox()
    c = cq.Vector((bb.xmin+bb.xmax)/2, (bb.ymin+bb.ymax)/2, 0)
    sx = 1-2*P["locator_xy_clearance_mm"]/bb.xlen
    sy = 1-2*P["locator_xy_clearance_mm"]/bb.ylen
    matrix = cq.Matrix([[sx, 0, 0, 0], [0, sy, 0, 0],
                        [0, 0, 1, 0], [0, 0, 0, 1]])
    nub = cavity.translate(-c).transformGeometry(matrix).translate(c)
    nub = nub.translate((0, 0, -P["locator_tip_clearance_mm"]))
    check(nub, "fitted locator")
    assert nub.intersect(dish).Volume() < 1e-5
    return nub


def build_solid():
    OUT.mkdir(exist_ok=True)
    cache = OUT / "reference_retained.brep"
    # Cache is valid for the documented -38 mm cut; regenerate for alternatives.
    if cache.exists() and P["port_cut_y_mm"] == -38:
        reference = cq.Shape.importBrep(str(cache))
    else:
        reference = to_solid(clipped_reference(P["port_cut_y_mm"]))
        reference.exportBrep(str(cache))
    dish = cq.importers.importStep(str(ROOT / "docs/official/Starlink_Mini_Dish.stp")).val()
    ztop = P["contact_z_mm"]
    length, width, height = P["battery_mm"]
    xc, yc = P["battery_center_xy_mm"]
    clearance = P["battery_side_clearance_mm"]
    floor_top = ztop-height-P["depth_allowance_mm"]
    zbottom = floor_top-P["floor_thickness_mm"]
    cage = box(-P["cage_x_half_mm"], P["cage_x_half_mm"],
               P["cage_rear_y_mm"], P["port_cut_y_mm"]-P["cage_seam_inset_mm"],
               zbottom, ztop-P["cage_contact_relief_mm"])
    bay = box(xc-length/2-clearance, xc+length/2+clearance,
              yc-width/2-clearance, yc+width/2+clearance, floor_top, 15)
    joined = reference.fuse(cage)
    assert joined.Volume() >= cage.Volume(), "Union lost enclosure volume"
    body = joined.cut(bay)
    crossbar = box(-64, 64, -48, P["port_cut_y_mm"]-P["cage_seam_inset_mm"],
                   -11, ztop-0.02)
    body = body.fuse(crossbar)
    check(body, "open cradle before dish trim")
    # Raised rails consume the depth allowance, supporting the nominal battery
    # at its contact plane rather than leaving it free to rattle in Z.
    for y in P["support_rail_y_mm"]:
        rail = box(-63, 63, y-P["support_rail_width_mm"]/2,
                   y+P["support_rail_width_mm"]/2, floor_top-0.1, ztop-height)
        body = body.fuse(rail)
    locators = [make_locator(dish, sign) for sign in (-1, 1)]
    print("Attaching locator 1", flush=True)
    body = body.fuse(locators[0])
    print("Attaching locator 2", flush=True)
    body = body.fuse(locators[1])
    check(body, "cradle before dish trim")
    body.exportBrep(str(OUT / "cradle_untrimmed.brep"))
    cq.exporters.export(body, str(OUT / "cradle_untrimmed.stl"), tolerance=0.025, angularTolerance=0.08)
    # Only actual reference intersections are trimmed, without scaling the dish.
    print("Trimming against official dish", flush=True)
    body = body.cut(dish)
    check(body, "trimmed cradle")
    body.exportBrep(str(OUT / "cradle_trimmed.brep"))
    print("Dish trim saved; cleaning", flush=True)
    body = body.clean()
    check(body, "solid cradle")
    battery = box(xc-length/2, xc+length/2, yc-width/2, yc+width/2, ztop-height, ztop)
    assert body.intersect(battery).Volume() < 1e-4, "Cradle intersects nominal battery"
    assert body.intersect(dish).Volume() < 1e-4, "Cradle intersects official dish"
    body.exportBrep(str(OUT / "cradle_solid.brep"))
    battery.exportBrep(str(OUT / "battery_nominal.brep"))
    cq.exporters.export(battery, str(OUT / "battery_nominal.stl"))
    cq.exporters.export(body, str(OUT / "cradle_solid.stl"), tolerance=0.025, angularTolerance=0.08)
    print("Saved solid cradle", flush=True)
    return body, battery, dish


def polygon_prism(poly, origin, eu, ev, normal, length):
    """Extrude a clipped planar polygon symmetrically along the panel normal."""
    origin, eu, ev, normal = [np.array(v, dtype=float) for v in (origin, eu, ev, normal)]
    def wire(coords):
        pts = [cq.Vector(*(origin+u*eu+v*ev-length/2*normal)) for u, v in list(coords)[:-1]]
        return cq.Wire.makePolygon(pts, close=True)
    outer = wire(poly.exterior.coords)
    inner = [wire(ring.coords) for ring in poly.interiors]
    return cq.Solid.extrudeLinear(outer, inner, cq.Vector(*(length*normal)))


def panel_hex_cutters(window, origin, eu, ev, normal, length, label):
    if window.is_empty:
        return [], {"panel": label, "holes": 0}
    radius = P["hex_hole_radius_mm"]
    pitch = np.sqrt(3)*radius+P["hex_web_width_mm"]
    row_pitch = np.sqrt(3)/2*pitch
    u0, v0, u1, v1 = window.bounds
    cutters, polygons = [], []
    for j in range(int(np.floor((v0-radius)/row_pitch)), int(np.ceil((v1+radius)/row_pitch))+1):
        v = j*row_pitch
        for i in range(int(np.floor((u0-radius)/pitch))-1, int(np.ceil((u1+radius)/pitch))+2):
            u = (i+0.5*(j % 2))*pitch
            hole = Polygon([(u+radius*np.cos(np.pi/2+k*np.pi/3),
                             v+radius*np.sin(np.pi/2+k*np.pi/3)) for k in range(6)])
            clipped = hole.intersection(window)
            parts = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
            for part in parts:
                if part.geom_type != "Polygon" or part.area < 12:
                    continue
                b = part.bounds
                if min(b[2]-b[0], b[3]-b[1]) < 2:
                    continue
                cutters.append(polygon_prism(part, origin, eu, ev, normal, length))
                polygons.append(part)
    # The regular tiling guarantees the defined distance between full holes.
    minimum = min((a.distance(b) for i, a in enumerate(polygons)
                   for b in polygons[i+1:]), default=float("inf"))
    assert minimum >= P["hex_web_width_mm"]-1e-6
    return cutters, {"panel": label, "holes": len(cutters),
                     "minimum_hole_separation_mm": minimum if np.isfinite(minimum) else None}


def make_hex_cutters(reference, footprint=None):
    ztop = P["contact_z_mm"]
    floor_top = ztop-P["battery_mm"][2]-P["depth_allowance_mm"]
    protected_z = ztop-P["protected_contact_depth_mm"]
    edge = P["panel_edge_rib_mm"]
    cutters, stats = [], []
    def add(*args):
        cs, report = panel_hex_cutters(*args)
        cutters.extend(cs)
        stats.append(report)
        print("Panel", report, flush=True)
    window = polygon_box(-P["cage_x_half_mm"]+edge, P["cage_rear_y_mm"]+edge,
                         P["cage_x_half_mm"]-edge, -51.5)
    if footprint is not None:
        window = footprint.buffer(-edge)
    for y in P["support_rail_y_mm"]:
        width = P["support_rail_width_mm"]/2+0.8
        window = window.difference(polygon_box(-65, y-width, 65, y+width))
    add(window, (0, 0, floor_top-1), (1, 0, 0), (0, 1, 0), (0, 0, 1), 7, "floor")
    side_window = polygon_box(P["cage_rear_y_mm"]+edge, floor_top+edge,
                              -51.5-edge, protected_z)
    for sign in (-1, 1):
        add(side_window, (sign*P["cage_x_half_mm"], 0, 0),
            (0, 1, 0), (0, 0, 1), (sign, 0, 0), 13, f"cage side {sign}")
    end_window = polygon_box(-P["cage_x_half_mm"]+edge, floor_top+edge,
                            P["cage_x_half_mm"]-edge, protected_z)
    for label, y, length in (("rear end", P["cage_rear_y_mm"], 15),
                             ("port end below locator bar", P["port_cut_y_mm"]-0.1, 30)):
        panel_window = end_window
        if footprint is not None and label.startswith('port'):
            from shapely.geometry import LineString
            segment=footprint.intersection(LineString([(-200,y-.001),(200,y-.001)]))
            lo,_,hi,_=segment.bounds
            panel_window=polygon_box(lo+edge,floor_top+edge,hi-edge,protected_z)
        add(panel_window, (0, y, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), length, label)

    # Follow the retained reference's inclined exterior planes, with protected
    # edge ribs. Tessellated fillets and snap details are deliberately excluded.
    for index, face in enumerate(reference.Faces()):
        n = np.array(face.normalAt().toTuple())
        if face.Area() < 600 or n[2] > -0.3 or abs(n[0]) < 0.3:
            continue
        origin = np.array(face.Center().toTuple())
        eu = np.cross(n, [0, 0, 1.0])
        eu /= np.linalg.norm(eu)
        ev = np.cross(n, eu)
        vertices, triangles = face.tessellate(0.01)
        vertices = np.array([v.toTuple() for v in vertices])
        planar = np.column_stack(((vertices-origin)@eu, (vertices-origin)@ev))
        window = unary_union([Polygon(planar[list(t)]) for t in triangles]).buffer(-edge)
        # Convert the protected horizontal contact band into local panel space.
        for part in list(window.geoms) if hasattr(window, "geoms") else [window]:
            if part.is_empty:
                continue
            # ev has nonzero Z for these inclined planes.
            vmax = (protected_z-origin[2])/ev[2]
            bounds = part.bounds
            z_window = (polygon_box(bounds[0]-1, -10000, bounds[2]+1, vmax)
                        if ev[2] > 0 else
                        polygon_box(bounds[0]-1, vmax, bounds[2]+1, 10000))
            add(part.intersection(z_window), origin, eu, ev, n, 8,
                f"inclined reference panel {index}")
    assert cutters
    return cutters, stats


def perforate(body):
    reference = cq.Shape.importBrep(str(OUT / "reference_retained.brep"))
    cutters, stats = make_hex_cutters(reference)
    print("Cutting", len(cutters), "hexagonal openings", flush=True)
    perforated = body.cut(*cutters).clean()
    check(perforated, "hex cradle")
    assert perforated.Volume() < body.Volume()
    perforated.exportBrep(str(OUT / "mount_v1.brep"))
    cq.exporters.export(perforated, str(OUT / "mount_v1.stl"), tolerance=0.025, angularTolerance=0.08)
    cq.exporters.export(perforated, str(OUT / "mount_v1.step"))
    (OUT / "hex_panels.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return perforated


if __name__ == "__main__":
    # The analytic-only boolean route above remains an investigation helper.
    # Use the validated mesh composition pipeline for the actual model.
    from generate_mount import run
    run()
