"""Use the two example outlines and exact STEP to shape new upper supports."""
import cadquery as cq
import trimesh
from shapely.geometry import Polygon, box as polygon_box
from build_design import ROOT, P, polygon_prism


def example_outline(name):
    mesh = trimesh.load(ROOT/'docs/example-mount'/f'{name}.stl', force='mesh')
    section = mesh.section(plane_normal=[0,0,1], plane_origin=[0,0,-7])
    # The largest loop is the outer boundary; the other loops are holes.
    outlines = [Polygon(line[:,:2]).buffer(0) for line in section.discrete]
    outline = max(outlines, key=lambda poly:poly.area)
    assert outline.is_valid and outline.geom_type == 'Polygon'
    return outline


def prism(poly, z0, z1):
    return polygon_prism(poly, (0,0,(z0+z1)/2), (1,0,0), (0,1,0), (0,0,1), z1-z0)


def supports(dish, zbottom, ztop):
    cut = P['port_cut_y_mm']-P['cage_seam_inset_mm']
    limits = polygon_box(-P['cage_x_half_mm'],P['cage_rear_y_mm'],P['cage_x_half_mm'],cut)
    footprint = example_outline('exterior').intersection(limits)
    cage = prism(footprint,zbottom,ztop-P['cage_contact_relief_mm'])
    interior = example_outline('interior').intersection(polygon_box(-100,-48,100,cut))
    bar = prism(interior,-11,ztop-.02)
    # Keep the reference engagement band unchanged. Only newly added supports
    # receive vertical relief against the exact official STEP surfaces.
    relief = dish.translate((0,0,-P['new_support_step_clearance_z_mm']))
    cage = cage.cut(dish).cut(relief).clean()
    bar = bar.cut(dish).cut(relief).clean()
    for name, shape in [('cage',cage),('locator bar',bar)]:
        assert shape.isValid() and len(shape.Solids()) == 1, name
        assert shape.intersect(dish).Volume() < 1e-5, name+' STEP interference'
    return cage, bar, footprint
