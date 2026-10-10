"""Independent delivered-mesh, complete-cell and exact STEP fit checks."""
import json
import numpy as np
import trimesh
import cadquery as cq
from shapely.geometry import Polygon
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.TopAbs import TopAbs_IN
from OCP.gp import gp_Pnt
from build_design import ROOT,P,box
from generate_mount import mesh_shape


def section_corners(poly,tolerance=.005):
    """Remove collinear tessellation points, with a checked outline bound."""
    simplified=poly.convex_hull.simplify(tolerance)
    points=list(np.asarray(simplified.exterior.coords)[:-1])
    # Shapely can retain paired midpoint vertices on a near-straight side of
    # a section through float32 STL triangles. Inspect cyclic neighbors too.
    while len(points)>3:
        removed=False
        for i,point in enumerate(points):
            previous=points[i-1];following=points[(i+1)%len(points)]
            segment=following-previous
            length2=np.dot(segment,segment)
            if length2==0:
                continue
            fraction=np.dot(point-previous,segment)/length2
            distance=np.linalg.norm(point-(previous+fraction*segment))
            if 0<fraction<1 and distance<tolerance:
                candidate=Polygon(points[:i]+points[i+1:])
                if poly.hausdorff_distance(candidate)<tolerance:
                    points.pop(i);removed=True;break
        if not removed:
            break
    result=Polygon(points)
    assert poly.hausdorff_distance(result)<tolerance
    return result


def run():
    stem='mount_'+P['revision']
    out=ROOT/'cad/out'
    mount=trimesh.load(out/(stem+'.stl'),force='mesh')
    assert mount.is_volume and mount.is_watertight and mount.is_winding_consistent
    positive=[part for part in mount.split(only_watertight=False) if part.volume>1e-5]
    assert len(positive)==1
    fine=trimesh.load(ROOT/'cad/review/dish_step_precise_primary.stl',force='mesh')
    official=max(trimesh.load(ROOT/'docs/official/Starlink_Mini_Dish.stl').split(
        only_watertight=False),key=lambda part:len(part.faces))
    targets=[('official_stl',official),('step_mesh_001mm',fine),
             ('measured_battery',trimesh.load(out/'battery_nominal.stl',force='mesh'))]
    floor_top=P['contact_z_mm']-P['battery_mm'][2]
    front=P['battery_center_xy_mm'][1]+P['bay_xy_mm'][1]/2
    usb_y0,usb_y1=P['battery_port_window_y_mm']
    usb_probe_x=-72.71 if P['revision']=='v6' else -114
    targets += [('clear_space_above_3mm_stop',mesh_shape(box(-65,65,front+.2,
                    front+P['battery_stop_thickness_mm']-.2,floor_top+3.05,-7))),
                ('usb_slot_inner_access',mesh_shape(box(usb_probe_x,-67.1,usb_y0+2,usb_y1-2,-29.4,-19.1)))]
    if P.get('revision') in ('v4','v5','v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        back=P['battery_center_xy_mm'][1]-P['bay_xy_mm'][1]/2
        targets += [('clear_space_above_low_rear_wall',mesh_shape(box(-65,65,
                    P['cage_rear_y_mm']+.3,back-.2,floor_top+3.05,-7))),
                    ('clear_space_above_low_positive_x_wall',mesh_shape(box(70.1,72.44,
                    back+.2,(-65 if P['revision'] in ('v5','v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18') else front-.2),floor_top+3.05,-7)))]
    if P['revision'] in ('v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        ya,yb=(usb_y0+.2,usb_y1-.2) if P['revision'] in ('v9','v10','v11','v13','v14','v15','v16','v17','v18') else (back+.2,-65)
        targets += [('clear_space_above_low_negative_x_wall',mesh_shape(box(-72.44,-70.1,
                    ya,yb,floor_top+3.05,-7)))]
    if P['revision'] in ('v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        # Exclude the reference-derived front skirts; this volume covers the
        # unwanted v5 shelf outside the rear/left seating corner.
        shelf_probe=mesh_shape(box(-110,-72.71,P['cage_rear_y_mm'],-65,floor_top-3,-29.05))
        if P.get('end_corner_return_x_mm'):
            # A narrow vertical corner wall is now intentional. Continue
            # rejecting the old horizontal shelf everywhere outside it,
            # including the entire USB approach and the outboard fin area.
            x0,x1=P['end_corner_return_x_mm']
            permitted=mesh_shape(box(-x1,-x0,P['outer_end_ramp_y_mm'][0],
                                      P['battery_port_window_y_mm'][0],floor_top-3,-7))
            shelf_probe=trimesh.boolean.difference([shelf_probe,permitted],engine='manifold')
        targets += [('removed_lower_left_shelf',shelf_probe)]
    if P['revision'] in ('v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        y0,y1=P['battery_port_window_y_mm'];z0,z1=P['battery_port_window_z_mm']
        targets += [('usb_full_rectangle_access',mesh_shape(box(-114,-67.1,
                    y0+.001,y1-.001,z0+.001,z1-.001)))]
    data={}
    if 'attachment_fin_thickness_mm' in P:
        from validate_smooth_fins import inspect as inspect_smooth_fins
        data.update(inspect_smooth_fins(mount))
    if not P.get('retain_legacy_plate_supports',True):
        from validate_legacy_support_removal import inspect as inspect_support_removal
        data.update(inspect_support_removal(mount))
    for name,geometry in targets:
        common=trimesh.boolean.intersection([mount,geometry],engine='manifold')
        if name=='clear_space_above_low_positive_x_wall' and P['revision']=='v4':
            # The original Mini attachment lip turns inward at the bay's front
            # corner. Preserve that rail, but permit no raised battery wall.
            # Exempt only its upper 3.35 mm within the 3.6 mm front edge rib.
            lip_zone=mesh_shape(box(70.1,72.45,front-P['panel_edge_rib_mm'],front-.2,
                                   P['reference_rim_bottom_z_mm']-.0001,-7))
            lip=trimesh.boolean.intersection([common,lip_zone],engine='manifold')
            data['retained_positive_x_front_mating_lip']={
                'volume_mm3':abs(lip.volume),'bounds_mm':lip.bounds.tolist()}
            common=trimesh.boolean.difference([common,lip_zone],engine='manifold')
        volume=abs(common.volume) if len(common.faces) else 0.
        print(name,'overlap mm3',volume,flush=True)
        assert volume<.01
        data['delivered_'+name+'_overlap_mm3']=volume
    # Check actual serialized floor openings, rather than trusting cutter counts.
    section=mount.section(plane_normal=[0,0,1],plane_origin=[0,0,floor_top-.05])
    loops=[Polygon(loop[:,:2]).buffer(0) for loop in section.discrete]
    outline=max(loops,key=lambda p:p.area)
    originals=[poly for poly in loops if poly is not outline and outline.contains(poly)]
    holes=[poly.convex_hull.simplify(.005) for poly in originals]
    audit=json.loads((out/(stem+'_validation.json')).read_text())
    if P.get('track_backing_bounds_positive_mm'):
        from validate_track_backing import inspect as inspect_track
        data.update(inspect_track(mount))
    if P.get('outer_end_ramp_y_mm'):
        from validate_print_panels import inspect
        data.update(inspect(mount,audit,P,section_corners))
    if P.get('end_corner_return_x_mm'):
        from validate_corner_fit import inspect as inspect_corners
        data.update(inspect_corners(mount,fine,official,section_corners))
    floor_patterns=[p for p in audit['panel_patterns'] if p['panel'].startswith('floor')]
    expected=sum(p['whole_hexagons'] for p in floor_patterns)
    radii=sorted({p['radius_mm'] for p in floor_patterns})
    counts={radius:0 for radius in radii}
    assert len(holes)==expected,(len(holes),expected)
    for original,poly in zip(originals,holes):
        assert original.hausdorff_distance(poly)<.005
        points=np.array(poly.exterior.coords)[:-1]
        assert len(points)==6,'Non-hexagonal delivered floor opening'
        edges=np.roll(points,-1,axis=0)-points
        sizes=np.linalg.norm(edges,axis=1)
        radius=min(radii,key=lambda value:np.max(np.abs(sizes-value)))
        assert np.max(np.abs(sizes-radius))<.01
        counts[radius]+=1
        turns=np.sum(edges*np.roll(edges,-1,axis=0),axis=1)/np.linalg.norm(edges,axis=1)**2
        assert np.max(np.abs(turns-.5))<.005
    gap=min(a.distance(b) for i,a in enumerate(holes) for b in holes[i+1:])
    assert gap>=P['hex_web_width_mm']-.005
    data['delivered_floor_cells']={'count':len(holes),'all_regular_hexagons':True,
                                  'minimum_web_mm':gap,'counts_by_radius_mm':counts}
    for radius,count in counts.items():
        assert count==sum(p['whole_hexagons'] for p in floor_patterns if p['radius_mm']==radius)
    if P.get('revision') in ('v4','v5','v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        # The former slit lies at the power-port end, outside the USB aperture.
        # Horizontal rays through its lower band must meet the new skirt.
        rays=np.array([[-110,y,z] for y in np.linspace(-51,-33,19)
                       for z in np.linspace(-26,-20,13)])
        directions=np.tile([1,0,0],(len(rays),1))
        points_hit,ray_ids,_=mount.ray.intersects_location(rays,directions,multiple_hits=True)
        hits=set(ray_ids[points_hit[:,0]<-40])
        assert len(hits)==len(rays),'Extra slit remains on the negative X side'
        assert mount.contains([[71.35,-93,floor_top+1.5],[0,-137.5,floor_top+1.5]]).all()
        data['negative_x_skirt_closed_band']={'ray_samples':len(rays),'material_hits':len(hits)}
    if P.get('revision') in ('v5','v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        rays[:,0]=110
        directions=np.tile([-1,0,0],(len(rays),1))
        points_hit,ray_ids,_=mount.ray.intersects_location(rays,directions,multiple_hits=True)
        hits=set(ray_ids[points_hit[:,0]>40])
        assert len(hits)==len(rays),'Front/right corner remains open'
        data['positive_x_skirt_closed_band']={'ray_samples':len(rays),'material_hits':len(hits)}
        # Check the actual return-panel openings in its own YZ plane.
        x0,x1=P['right_fin_return_x_mm']
        section=mount.section(plane_normal=[1,0,0],plane_origin=[(x0+x1)/2,0,0])
        return_holes=[]
        for loop in section.discrete:
            poly=Polygon(loop[:,1:]).buffer(0)
            y0,z0,y1,z1=poly.bounds
            if y0>back and y1<-62 and z0>floor_top+.5 and z1<-10:
                return_holes.append(poly)
        expected=next(p['whole_hexagons'] for p in audit['panel_patterns']
                      if p['panel']=='battery side right fin return')
        assert len(return_holes)==expected,(len(return_holes),expected)
        for poly in return_holes:
            cleaned=section_corners(poly)
            assert poly.hausdorff_distance(cleaned)<.005
            points=np.array(cleaned.exterior.coords)[:-1]
            assert len(points)==6,'Truncated right-return hexagon'
            edges=np.roll(points,-1,axis=0)-points
            if 'vertical_hex_roof_angle_deg' not in P:
                assert np.max(np.abs(np.linalg.norm(edges,axis=1)-P['right_fin_return_hex_radius_mm']))<.01
        data['delivered_right_return_cells']={'count':len(return_holes),'all_complete_hexagons':True,
                                            'regular': 'vertical_hex_roof_angle_deg' not in P}
    if P.get('revision')=='v5':
        # Inspect the repaired fin from the user's +Z direction. Every remaining
        # opening inside the intended panel must be a complete small hexagon;
        # a large triangular slit would fail this independently of wall checks.
        from shapely.ops import unary_union
        projected=[Polygon(triangle[:,:2]) for triangle in mount.triangles]
        shadow=unary_union([poly for poly in projected if poly.area>1e-8])
        panel=Polygon(audit['usb_fin_bridge']['outline_xy_mm']).buffer(-.05)
        openings=panel.difference(shadow)
        pieces=[] if openings.is_empty else ([openings] if openings.geom_type=='Polygon' else list(openings.geoms))
        pieces=[poly for poly in pieces if poly.area>.01]
        expected=next(p['whole_hexagons'] for p in audit['panel_patterns'] if p['panel']=='floor USB fin bridge')
        assert len(pieces)==expected,(len(pieces),expected)
        for poly in pieces:
            cleaned=poly.convex_hull.simplify(.005)
            assert poly.hausdorff_distance(cleaned)<.005
            points=np.array(cleaned.exterior.coords)[:-1]
            assert len(points)==6,'Non-hexagonal gap remains in the left fin top view'
            edges=np.roll(points,-1,axis=0)-points
            assert np.max(np.abs(np.linalg.norm(edges,axis=1)-P['usb_fin_bridge_hex_radius_mm']))<.01
        data['delivered_left_fin_top_view']={'whole_visible_hexagons':len(pieces),
                                            'additional_non_hexagonal_gaps':0}
    if P.get('revision') in ('v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        # Check the fin itself in its original inclined plane. A horizontal
        # shelf can cover a gap in projection, so a top-view shadow alone is
        # insufficient. Compare both actual fin silhouettes in the same plane.
        from reference_solid import clipped_reference
        from shapely.ops import unary_union
        reference=clipped_reference(P['port_cut_y_mm'])
        candidates=[ids for ids in reference.facets
                    if reference.face_normals[ids[0],0]<-.4 and
                       reference.face_normals[ids[0],2]<-.9]
        facet=max(candidates,key=lambda ids:reference.area_faces[ids].sum())
        normal=reference.face_normals[facet[0]]
        thickness=P.get('attachment_fin_thickness_mm',P['shell_panel_thickness_mm'])
        origin=reference.triangles[facet[0],0]-thickness/2*normal
        eu=np.cross(normal,[0,0,1]);eu/=np.linalg.norm(eu)
        ev=np.cross(normal,eu)
        roi=mesh_shape(box(-101,-73,-147.5,-65,-29.1,-9.7))
        mirrored=mount.copy();mirrored.apply_transform(np.diag([-1.,1.,1.,1.]))
        silhouettes={}
        fin_data={}
        for label,geometry,sign in (('left',mount,-1),('right_mirrored',mirrored,1)):
            material=trimesh.boolean.intersection([geometry,roi],engine='manifold')
            section=material.section(plane_normal=normal,plane_origin=origin)
            assert section is not None,'Missing inclined fin material'
            polygons=[]
            for loop in section.discrete:
                offset=loop-origin
                polygons.append(Polygon(np.column_stack([offset@eu,offset@ev])).buffer(0))
            holes=[poly for poly in polygons if any(other is not poly and other.contains(poly)
                                                    for other in polygons)]
            expected=next(pattern['whole_hexagons'] for pattern in audit['panel_patterns']
                          if pattern['panel']==f'inclined wing {sign}')
            assert len(holes)==expected,(label,len(holes),expected)
            for hole in holes:
                cleaned=section_corners(hole)
                points=np.array(cleaned.exterior.coords)[:-1]
                assert len(points)==6,(label,'Non-hexagonal inclined fin opening',len(points))
                edges=np.roll(points,-1,axis=0)-points
                lengths=np.linalg.norm(edges,axis=1)
                assert np.max(np.abs(lengths-P['hex_narrow_radius_mm']))<.01
                turns=np.sum(edges*np.roll(edges,-1,axis=0),axis=1)/(lengths*np.roll(lengths,-1))
                assert np.max(np.abs(turns-.5))<.005
            silhouettes[label]=unary_union(polygons)
            fin_data[label]={'whole_hexagons':len(holes),'all_regular_hexagons':True,
                             'outline_area_mm2':silhouettes[label].area}
        expected=silhouettes['right_mirrored']
        if P['revision'] in ('v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
            # The only permitted fin-outline difference is the intentional
            # rectangular USB aperture. Compare its actual plane section.
            y0,y1=P['battery_port_window_y_mm'];z0,z1=P['battery_port_window_z_mm']
            cutter=mesh_shape(box(P['usb_cut_outer_x_mm'],-67,y0,y1,z0,z1))
            cut_section=cutter.section(plane_normal=normal,plane_origin=origin)
            cuts=[]
            for loop in cut_section.discrete:
                offset=loop-origin
                cuts.append(Polygon(np.column_stack([offset@eu,offset@ev])).buffer(0))
            expected=expected.difference(unary_union(cuts))
        difference=silhouettes['left'].symmetric_difference(expected).area
        assert difference<.01,'Unexpected gap in the left fin outside the USB aperture'
        fin_data['outline_difference_excluding_usb_mm2']=difference
        if P['revision']=='v6':
            fin_data['mirrored_outline_difference_mm2']=difference
        data['delivered_inclined_fin_sections']=fin_data
        data['usb_access']={'wall_slot_clear':True,'opening_width_mm':usb_y1-usb_y0,
                            'full_outward_approach_clear':P['revision'] in ('v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18')}
        if P['revision'] in ('v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
            data['usb_access'].pop('wall_slot_clear')
            data['usb_access']['bay_wall_open_above_retaining_lip']=True
        if P['revision']=='v6':
            data['usb_access']['note']='Restored inclined fin partly screens the outward cable approach; check the actual plug.'
    if P['revision']=='v7':
        # Verify the delivered bay-wall opening has exactly four straight
        # sides and square corners, rather than trusting the box cutter.
        from shapely.geometry import box as polygon_box
        y0,y1=P['battery_port_window_y_mm'];z0,z1=P['battery_port_window_z_mm']
        desired=polygon_box(y0,z0,y1,z1)
        section=mount.section(plane_normal=[1,0,0],plane_origin=[-71.35,0,0])
        candidates=[Polygon(loop[:,1:]).buffer(0) for loop in section.discrete]
        aperture=min(candidates,key=lambda poly:poly.hausdorff_distance(desired))
        assert aperture.hausdorff_distance(desired)<.005,'Bay-wall USB aperture is not rectangular'
        cleaned=section_corners(aperture)
        points=np.asarray(cleaned.exterior.coords)[:-1]
        assert len(points)==4,'USB rectangle has extra corners'
        edges=np.roll(points,-1,axis=0)-points
        lengths=np.linalg.norm(edges,axis=1)
        turns=np.sum(edges*np.roll(edges,-1,axis=0),axis=1)/(lengths*np.roll(lengths,-1))
        assert np.max(np.abs(turns))<.005,'USB corners are not square'
        # Rays just outside each edge must encounter the frame. This ensures
        # the clear rectangle remains visually bounded when viewed from -X.
        border=[(y,z0-.2) for y in np.linspace(y0+.2,y1-.2,41)]
        border += [(y,z1+.2) for y in np.linspace(y0+.2,y1-.2,41)]
        border += [(y0-.2,z) for z in np.linspace(z0+.2,z1-.2,17)]
        border += [(y1+.2,z) for z in np.linspace(z0+.2,z1-.2,17)]
        rays=np.array([[-114,y,z] for y,z in border])
        directions=np.tile([1,0,0],(len(rays),1))
        hit_points,ray_ids,_=mount.ray.intersects_location(rays,directions,multiple_hits=True)
        hits=set(ray_ids[hit_points[:,0]<-67.1])
        assert len(hits)==len(rays),'Visible USB rectangle has an open frame edge'
        data['delivered_usb_rectangle']={'width_mm':y1-y0,'height_mm':z1-z0,
                                        'square_corners':True,'straight_edges':4,
                                        'frame_ray_samples':len(rays),'material_hits':len(hits)}
    if P['revision'] in ('v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        # The bay-side wall is now an open-top lip, not a closed slot. Check
        # its actual upper surface independently of the builder parameters.
        ya,yb=(usb_y0+.5,usb_y1-.5) if P['revision'] in ('v9','v10','v11','v13','v14','v15','v16','v17','v18') else (back+.5,-65.5)
        ys=np.linspace(ya,yb,35)
        rays=np.array([[-71.35,y,floor_top-1] for y in ys])
        directions=np.tile([0,0,1],(len(rays),1))
        hit_points,ray_ids,_=mount.ray.intersects_location(rays,directions,multiple_hits=True)
        tops=[]
        for ray_id in range(len(rays)):
            heights=hit_points[ray_ids==ray_id,2]
            assert len(heights),'Missing left retaining lip'
            tops.append(float(heights.max()))
        actual=np.array(tops)
        target_top=P['battery_port_window_z_mm'][0]
        assert np.max(np.abs(actual-target_top))<.005,'Left retaining lip is not at the former slot bottom'
        assert mount.contains([[-71.35,y,floor_top+1.5] for y in ys]).all()
        data['delivered_left_retaining_lip']={
            'samples':len(ys),'top_z_mm':float(actual.mean()),
            'height_above_floor_mm':float(actual.mean()-floor_top),
            'max_height_error_mm':float(np.max(np.abs(actual-target_top))),
            'upper_wall_removed':True}
        audit['usb_aperture']['bay_wall_open_top']=True
    if P['revision'] in ('v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        yc=P['battery_center_xy_mm'][1]
        half=P['battery_mm'][1]/2
        inset=P['battery_port_edge_inset_mm']
        port_y0,port_y1=yc-half+inset,yc+half-inset
        clearances=[port_y0-usb_y0,usb_y1-port_y1]
        assert min(clearances)>=P['battery_port_end_clearance_mm']-1e-6
        expected_top=floor_top+P['port_side_corner_height_mm']
        corner_data={}
        # The front return merges into the original Mini skirt farther
        # forward. Sample its straight bay-side tab before that junction.
        for label,ys in (('rear',np.linspace(back+.4,usb_y0-.4,5)),
                         ('front',np.linspace(usb_y1+.4,usb_y1+3.4,5))):
            rays=np.array([[-71.35,y,floor_top-1] for y in ys])
            directions=np.tile([0,0,1],(len(rays),1))
            hits,ids,_=mount.ray.intersects_location(rays,directions,multiple_hits=True)
            tops=[]
            for ray_id in range(len(rays)):
                heights=hits[ids==ray_id,2]
                assert len(heights),'Missing corner retainer'
                tops.append(float(heights.max()))
            assert np.max(np.abs(np.array(tops)-expected_top))<.005,'Corner retainer height is wrong'
            assert mount.contains([[-71.35,y,floor_top+4.5] for y in ys]).all()
            corner_data[label]={'samples':len(ys),'height_above_floor_mm':float(np.mean(tops)-floor_top)}
        data['delivered_port_corner_retention']={
            'reported_port_count':P['battery_port_count'],'port_span_y_mm':[port_y0,port_y1],
            'opening_width_mm':usb_y1-usb_y0,'end_clearance_mm':clearances,
            'corners':corner_data}
    dish=cq.importers.importStep(str(ROOT/'docs/official/Starlink_Mini_Dish.stp')).val()
    classifier=BRepClass3d_SolidClassifier(dish.wrapped)
    regions={'lip and latches':lambda p:(np.abs(p[:,0])>75)&(p[:,1]>-135)&(p[:,2]>-25),
             'extended front':lambda p:(p[:,1]>-55)&(p[:,2]>-30)}
    points=np.vstack([mount.vertices,mount.triangles_center])
    checks={}
    for name,selector in regions.items():
        selected=points[selector(points)]
        ids=np.linspace(0,len(selected)-1,min(len(selected),1500),dtype=int)
        inside=[]
        for p in selected[ids]:
            classifier.Perform(gp_Pnt(*p),1e-5)
            if classifier.State()==TopAbs_IN: inside.append(p.tolist())
        confirmed=[]
        discrepancies=[]
        for point in inside:
            # A reference NURBS seam can give an isolated IN classification
            # even though nearby points and both mesh checks are outside.
            # Confirm by an exact local volume test and surface clearance;
            # never discard a positive overlap or a point close to a surface.
            x,y,z=point
            half=.05
            probe=box(x-half,x+half,y-half,y+half,z-half,z+half)
            common=dish.intersect(probe)
            assert common.isValid()
            overlap=abs(common.Volume())
            vertex=BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
            distances=[]
            for face in dish.Faces():
                distance=BRepExtrema_DistShapeShape(vertex,face.wrapped)
                distance.Perform()
                assert distance.IsDone()
                distances.append(distance.Value())
            clearance=min(distances)
            adjacent=[]
            for dx in (-.001,.001):
                classifier.Perform(gp_Pnt(x+dx,y,z),1e-5)
                adjacent.append(classifier.State()!=TopAbs_IN)
            if overlap>1e-9 or clearance<=np.sqrt(3)*half or not all(adjacent):
                confirmed.append(point)
            else:
                discrepancies.append({'point_mm':point,'probe_side_mm':2*half,
                                      'exact_probe_overlap_mm3':overlap,
                                      'minimum_exact_face_distance_mm':clearance,
                                      'both_x_offsets_001mm_outside':True})
        checks[name]={'samples':len(ids),'strictly_inside_step':len(inside),'inside_points':inside[:10],
                      'confirmed_inside_step':len(confirmed),
                      'point_classifier_discrepancies':discrepancies}
        print(name,checks[name],flush=True)
        assert not confirmed,'Sampled surface clips exact STEP'
    data['exact_step_point_checks']=checks
    audit.update(data)
    audit['parameters']=P
    (out/(stem+'_validation.json')).write_text(json.dumps(audit,indent=2))
    print('Delivered STL passed geometry and fit checks',flush=True)


if __name__=='__main__':
    run()
