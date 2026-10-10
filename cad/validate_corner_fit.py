"""Delivered corner closure, exact new-material fit and reference retention."""
import numpy as np
import trimesh
import cadquery as cq
from shapely.geometry import Polygon,box as polygon_box
from build_design import ROOT,P,box,make_locator
from generate_mount import mesh_shape
from mating_profiles import example_outline,prism
from reference_solid import clipped_reference
from corner_returns import make_returns


def volume(mesh):
    return float(abs(mesh.volume)) if len(mesh.faces) else 0.


def difference(first,second):
    return trimesh.boolean.difference([first,second],engine='manifold')


def inspect(mount,fine,official,section_corners):
    reference=clipped_reference(P['port_cut_y_mm'])
    planes=[]
    for sign in (-1,1):
        candidates=[ids for ids in reference.facets if sign*reference.face_normals[ids[0],0]>.4
                    and reference.face_normals[ids[0],2]<-.9]
        ids=max(candidates,key=lambda ids:reference.area_faces[ids].sum())
        planes.append((sign,reference.face_normals[ids[0]],reference.triangles[ids[0],0]))
    floor_top=P['contact_z_mm']-P['battery_mm'][2]
    bottom=floor_top-P['floor_thickness_mm']
    cap=P['reference_rim_bottom_z_mm']+.06
    dish=cq.importers.importStep(str(ROOT/'docs/official/Starlink_Mini_Dish.stp')).val()
    details=[]
    for sign,shape in make_returns(planes,bottom,cap):
        exact=shape.intersect(dish)
        assert exact.isValid() and abs(exact.Volume())<1e-5,'New corner clips the exact STEP'
        expected=mesh_shape(shape)
        absent=volume(difference(expected,mount))
        assert absent<.01,'Rectangular or triangular gap remains in the solid corner return'
        xa,xb=(-75,-72.8) if sign<0 else (72.8,75)
        gap_probe=mesh_shape(box(xa,xb,-140.7,-124.001,-30.35,-29.01))
        missing=volume(difference(gap_probe,mount))
        assert missing<.01,'Former corner slit is not filled solid'
        details.append({'side':sign,'exact_step_overlap_mm3':float(abs(exact.Volume())),
                        'missing_return_material_mm3':absent,'former_slit_missing_material_mm3':missing,
                        'return_width_mm':P['end_corner_return_x_mm'][1]-P['end_corner_return_x_mm'][0]})
    # Retained source rail/catches must still be present after all panel cuts.
    # Fit the expected reference feature volume to the same documented Mini
    # clearance; this intentionally excludes source material inside the Mini.
    outline=example_outline('exterior').intersection(polygon_box(-110,-160,110,P['port_cut_y_mm']))
    rail_outline=outline.difference(outline.buffer(-P['rim_rail_width_mm'],join_style='mitre'))
    band=mesh_shape(prism(rail_outline,P['reference_rim_bottom_z_mm'],5))
    rail=trimesh.boolean.intersection([reference,band],engine='manifold')
    xc,yc=P['battery_center_xy_mm'];length,width=P['bay_xy_mm']
    front=yc+width/2
    footprint=outline.intersection(polygon_box(-P['cage_x_half_mm'],P['cage_rear_y_mm'],
                                              P['cage_x_half_mm'],P['port_cut_y_mm']-.1))
    cavity=polygon_box(xc-length/2,yc-width/2,xc+length/2,front)
    cavity=cavity.union(footprint.buffer(-P['shell_panel_thickness_mm'],join_style='mitre').intersection(
        polygon_box(-110,front-.01,110,0)))
    rail=difference(rail,mesh_shape(prism(cavity,floor_top,15)))
    catches=[]
    for sign in (-1,1):
        xa,xb=(-94,-82.2) if sign<0 else (82.2,94)
        catches.append(trimesh.boolean.intersection([reference,mesh_shape(box(xa,xb,-128.4,-84,-16,-8.4))],engine='manifold'))
    retain_supports=P.get('retain_legacy_plate_supports',True)
    expected=trimesh.boolean.union([rail,*(catches if retain_supports else [])],engine='manifold')
    expected=difference(expected,fine)
    for axis in range(3):
        for sign in (-1,1):
            relief=fine.copy();offset=np.zeros(3);offset[axis]=sign*P['mating_clearance_axes_mm']
            relief.apply_translation(offset);expected=difference(expected,relief)
    expected=difference(expected,official)
    absent=volume(difference(expected,mount))
    assert absent<.01,'Retained original mating features lost material'
    nubs=[]
    for sign in (-1,1):
        nub=make_locator(dish,sign)
        missing=volume(difference(mesh_shape(nub),mount))
        assert missing<.01,'Fitted inner nub has lost material'
        nubs.append({'side':sign,'missing_material_mm3':missing,'exact_step_overlap_mm3':float(abs(nub.intersect(dish).Volume()))})
    # Compare the locator plane with the original interior plate outline.
    # Fill only actual regular hexagon loops; a large missing plate cannot
    # be mistaken for an intended perforation or filled by a rim silhouette.
    z=-8.8053
    interior=example_outline('interior').intersection(polygon_box(-100,-48,100,P['port_cut_y_mm']-.1))
    plate=prism(interior,-11,P['contact_z_mm']-.02)
    plate=plate.cut(dish).cut(dish.translate((0,0,-P['new_support_step_clearance_z_mm']))).clean()
    if P.get('locator_profile') == 'oem_tapered':
        from prototype_feedback import locator_seat_tools
        plate = plate.cut(*locator_seat_tools()).clean()
    expected_section=mesh_shape(plate).section(plane_normal=[0,0,1],plane_origin=[0,0,z])
    expected_region=Polygon()
    for loop in expected_section.discrete:
        expected_region=expected_region.symmetric_difference(Polygon(loop[:,:2]).buffer(0))
    actual_section=mount.section(plane_normal=[0,0,1],plane_origin=[0,0,z])
    actual_region=Polygon();cells=[]
    for loop in actual_section.discrete:
        poly=Polygon(loop[:,:2]).buffer(0)
        actual_region=actual_region.symmetric_difference(poly)
        if poly.area>10 and poly.area<70 and expected_region.covers(poly):
            corners=section_corners(poly)
            points=np.asarray(corners.exterior.coords)[:-1]
            assert len(points)==6,'Locator plane contains a non-hexagonal gap'
            edges=np.roll(points,-1,axis=0)-points
            assert np.max(np.abs(np.linalg.norm(edges,axis=1)-P['hex_locator_radius_mm']))<.01
            cells.append(poly)
    expected_cells = 0 if P.get('pattern_floor_only') else 5
    assert len(cells)==expected_cells,'Unexpected locator-plane perforations'
    for cell in cells: actual_region=actual_region.union(cell)
    missing_outline=expected_region.buffer(-.15).difference(actual_region).area
    assert missing_outline<.01,'Locator plane no longer follows the example interior outline'
    # The original corner fix must leave all upper geometry unchanged.
    # Matching the reference fin thickness intentionally changes the backing
    # and whole-cell layout; rail, catch, nub and plate checks above still apply.
    previous_path=ROOT/'cad/out/mount_v10.stl'
    changed=None
    if previous_path.exists():
        previous=trimesh.load(previous_path,force='mesh')
        upper=mesh_shape(box(-110,110,-150,-28,-17.5,10))
        old=trimesh.boolean.intersection([previous,upper],engine='manifold')
        new=trimesh.boolean.intersection([mount,upper],engine='manifold')
        changed=volume(difference(old,new))+volume(difference(new,old))
        if 'attachment_fin_thickness_mm' not in P:
            assert changed<.01,'Established upper mating geometry changed'
    print('Both corner closures, exact STEP corner fit and original mating features passed',flush=True)
    missing_key='missing_fitted_exterior_rail_and_catches_mm3' if retain_supports else 'missing_fitted_exterior_rail_mm3'
    return {'delivered_end_corners':details,'delivered_reference_mating_retention':{
        missing_key:absent,'fitted_retained_reference_volume_mm3':volume(expected),
        'legacy_interior_plate_supports_retained':retain_supports,
        'inner_nubs':nubs,'upper_geometry_difference_from_v10_mm3':changed,
        'locator_plane_missing_interior_outline_mm2':float(missing_outline),
        'locator_plane_outline_clearance_allowance_mm':.15,'locator_plane_complete_hexagons':len(cells)}}
