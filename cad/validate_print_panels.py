"""Measure the delivered end closure and upright hexagon print slopes."""
import numpy as np
import trimesh
from shapely.geometry import Polygon
from build_design import box
from generate_mount import mesh_shape


def inspect(mount,audit,parameters,section_corners):
    # The old full-width slit lies between the raised outer frame and the
    # seating lip. Its interior must now contain solid material throughout.
    probe=mesh_shape(box(-72.6,72.6,-140.65,-140.51,-30.45,-29.01))
    missing=trimesh.boolean.difference([probe,mount],engine='manifold')
    volume=abs(missing.volume) if len(missing.faces) else 0.
    assert volume<.01,'Horizontal end slit is not filled solid'
    ya,yb=parameters['outer_end_ramp_y_mm']
    floor_bottom=parameters['contact_z_mm']-parameters['battery_mm'][2]-parameters['floor_thickness_mm']
    ys=np.linspace(ya+.1,yb-.4,17)
    rays=np.array([[0,y,floor_bottom-1] for y in ys])
    points,ids,_=mount.ray.intersects_location(rays,np.tile([0,0,1],(len(rays),1)),multiple_hits=True)
    underside=[]
    for index in range(len(rays)):
        heights=points[ids==index,2]
        assert len(heights),'Missing solid end ramp'
        underside.append(heights.min())
    underside=np.array(underside)
    expected=floor_bottom+yb-ys
    assert np.max(np.abs(underside-expected))<.005,'End ramp underside is not continuous at 45 degrees'
    angles=np.degrees(np.arctan(np.abs(np.diff(underside)/np.diff(ys))))
    assert np.min(angles)>44.95
    result={'delivered_solid_end_transition':{
        'former_slit_missing_material_mm3':float(volume),'underside_samples':len(ys),
        'minimum_underside_angle_from_horizontal_deg':float(angles.min()),
        'minimum_normal_thickness_mm':float((parameters['outer_end_solid_band_top_z_mm']-
                                               (floor_bottom+yb-ya))/np.sqrt(2))}}
    panels=[]
    for pattern in audit['panel_patterns']:
        if 'validation_plane' not in pattern:
            continue
        plane=pattern['validation_plane']
        origin,eu,ev,normal=[np.array(plane[key]) for key in ('origin','u','v','normal')]
        section=mount.section(plane_origin=origin,plane_normal=normal)
        assert section is not None
        polygons=[]
        for loop in section.discrete:
            delta=loop-origin
            poly=Polygon(np.column_stack([delta@eu,delta@ev])).buffer(0)
            if poly.geom_type=='Polygon' and not poly.is_empty:
                polygons.append(poly)
        holes=[];slopes=[]
        for centre in pattern['cell_centres_uv_mm']:
            # Locate each actual closed section loop, then inspect its shape.
            # Cutter centres locate the panel cells; they do not supply their
            # dimensions, web clearance, vertices or roof angles.
            poly=min(polygons,key=lambda p:np.linalg.norm(np.array(p.centroid.coords[0])-centre))
            assert np.linalg.norm(np.array(poly.centroid.coords[0])-centre)<.01
            assert any(other is not poly and other.contains(poly) for other in polygons), 'Cell opens into panel edge'
            cleaned=section_corners(poly)
            points=np.asarray(cleaned.exterior.coords)[:-1]
            assert len(points)==6,'Upright cell is not a complete hexagon'
            edges=np.roll(points,-1,axis=0)-points
            lengths=np.linalg.norm(edges,axis=1)
            width=np.ptp(points[:,0]);height=np.ptp(points[:,1])
            assert abs(width-np.sqrt(3)*pattern['radius_mm'])<.01
            assert abs(height-2*pattern['radius_mm'])<.01
            half_width=width/2
            shoulder=height/2-half_width*np.tan(np.radians(pattern['roof_angle_deg']))
            desired=np.sort([2*shoulder]*2+[half_width/np.cos(np.radians(pattern['roof_angle_deg']))]*4)
            assert np.max(np.abs(np.sort(lengths)-desired))<.01,'Upright hexagon shoulder dimensions differ'
            xyz_edges=edges[:,0,None]*eu+edges[:,1,None]*ev
            angle=np.degrees(np.arctan2(np.abs(xyz_edges[:,2]),np.linalg.norm(xyz_edges[:,:2],axis=1)))
            assert angle.min()>44.95,'Upright hexagon has a shallow or flat roof edge'
            slopes.extend(angle.tolist());holes.append(poly)
        assert len(holes)==pattern['whole_hexagons'] and holes
        gap=min((a.distance(b) for index,a in enumerate(holes) for b in holes[index+1:]),default=None)
        assert gap is None or gap>=parameters['vertical_hex_web_mm']-.005
        minimum=min(slopes)
        panels.append({'panel':pattern['panel'],'whole_hexagons':len(holes),
                       'radius_mm':pattern['radius_mm'],'minimum_web_mm':gap,
                       'minimum_edge_angle_from_horizontal_deg':minimum,
                       'maximum_horizontal_growth_per_layer_mm':float(parameters['print_layer_height_mm']/np.tan(np.radians(minimum))),
                       'all_complete_six_sided_hexagons':True,'roof_angle_deg':pattern['roof_angle_deg']})
    expected_panels = 0 if parameters.get('pattern_floor_only') else 5
    assert len(panels)==expected_panels,'Unexpected upright perforated panels'
    result['delivered_upright_print_panels']=panels
    print('Solid end transition and all upright print panels passed',flush=True)
    return result
