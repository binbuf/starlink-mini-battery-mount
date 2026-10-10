"""Rebuild visible panels as complete, plane-local hex lattices for ASA.

The supplied shell defines the polygonal rim and inclined planes. The
functional lip is retained verbatim; old interior-plate support patches are optional; screw bosses, round
holes, old ribs and asymmetric pockets do not enter this revision.
"""
import json
import time
import numpy as np
import cadquery as cq
import trimesh
from shapely.geometry import Polygon, box as polygon_box
from build_design import ROOT, OUT, P, box, make_locator, polygon_prism
from mating_profiles import example_outline, supports, prism
from reference_solid import clipped_reference
from prepare_step_reference import prepare
from generate_mount import mesh_shape, assert_mesh


def difference(body, tools):
    return trimesh.boolean.difference([body, *tools], engine='manifold')


def intersection(body, tool):
    return trimesh.boolean.intersection([body, tool], engine='manifold')


def union(meshes):
    return trimesh.boolean.union(meshes, engine='manifold')


def material_window(body, origin, eu, ev, normal, thickness, web=None):
    """Intersect material sections near both sides and centre of this panel.

    This captures the real STEP-clearance outline before laying out cells;
    no hole may be truncated by a mating relief or a neighbouring plane.
    """
    origin,eu,ev,normal=map(lambda p:np.array(p,float),(origin,eu,ev,normal))
    result=None
    for offset in (-thickness/2+.25,0,thickness/2-.25):
        section=body.section(plane_normal=normal,plane_origin=origin+offset*normal)
        region=Polygon()
        if section is not None:
            for loop in section.discrete:
                delta=loop-origin
                poly=Polygon(np.column_stack([delta@eu,delta@ev])).buffer(0)
                if poly.area>1e-4: region=region.symmetric_difference(poly)
        result=region if result is None else result.intersection(region)
    return result.buffer(-(P['hex_web_width_mm'] if web is None else web))


def full_hex_pattern(window, origin, eu, ev, normal, length, label, radius=None,
                     protected=None, web=None):
    """Only whole six-sided cells, with measured plane-local clearances.

    A centred starting phase and translated copies of the regular tiling
    fit narrow panels. Holes cannot cross a plane edge or a protected feature.
    """
    radius = radius or P['hex_hole_radius_mm']
    if P.get('pattern_floor_only') and not label.startswith('floor'):
        return [], {'panel': label, 'whole_hexagons': 0, 'radius_mm': radius,
                    'truncated_hexagons': 0, 'solid_panel': True}
    if window.is_empty:
        return [],{'panel':label,'whole_hexagons':0,'radius_mm':radius,
                   'minimum_hole_separation_mm':None,'truncated_hexagons':0}
    web = P['hex_web_width_mm'] if web is None else web
    pitch = np.sqrt(3)*radius+web
    row_pitch = np.sqrt(3)/2*pitch
    origin, eu, ev, normal = map(lambda p: np.array(p, float), (origin, eu, ev, normal))
    u0,v0,u1,v1 = window.bounds
    roof=P.get('vertical_hex_roof_angle_deg') if abs(normal[2])<.1 else None
    if roof is not None:
        half_width=np.sqrt(3)/2*radius
        shoulder=radius-half_width*np.tan(np.radians(roof))
        assert shoulder>0,'Printable hexagon must retain six distinct sides'
        offsets=np.array([(0,radius),(-half_width,shoulder),(-half_width,-shoulder),
                          (0,-radius),(half_width,-shoulder),(half_width,shoulder)])
    else:
        offsets=np.array([(radius*np.cos(np.pi/2+k*np.pi/3),
                           radius*np.sin(np.pi/2+k*np.pi/3)) for k in range(6)])
    phase_u, phase_v = (u0+u1)/2, (v0+v1)/2
    if abs(u0+u1)<1e-5: phase_u=0
    fixed_phase=P.get('panel_pattern_phase_uv_mm',{}).get(label)
    if fixed_phase is not None:
        phase_u,phase_v=fixed_phase
    def cells(du,dv):
        candidates=[]
        for j in range(-int((v1-v0)/row_pitch)-2, int((v1-v0)/row_pitch)+3):
          for i in range(-int((u1-u0)/pitch)-2, int((u1-u0)/pitch)+3):
            u=phase_u+du+(i+.5*(j%2))*pitch
            v=phase_v+dv+j*row_pitch
            hole=Polygon(offsets+[u,v])
            if not window.covers(hole): continue
            xyz=np.array([origin+uv[0]*eu+uv[1]*ev for uv in list(hole.exterior.coords)[:-1]])
            # Reserve the wide connector aperture on every affected plane.
            if protected is not None and protected(xyz): continue
            candidates.append(hole)
        return candidates
    # Search only translations of the same regular tiling. Narrow irregular
    # plane windows should not lose all cells because of an arbitrary phase.
    shifts=[(0,0)]
    if label=='floor':
        shifts += [(u*pitch/2,v*row_pitch/8) for u in (0,1) for v in range(-4,5)]
    elif label.startswith(('inclined','battery side','front skirt','floor port','floor USB')):
        shifts += [(u*pitch/8,v*row_pitch/8) for u in range(-4,5) for v in range(-4,5)]
    polygons=max((cells(*phase) for phase in shifts),key=len)
    cutters=[mesh_shape(polygon_prism(hole,origin,eu,ev,normal,length)) for hole in polygons]
    separation=min((a.distance(b) for i,a in enumerate(polygons)
                    for b in polygons[i+1:]), default=None)
    assert separation is None or separation>=web-1e-6
    report={'panel':label,'whole_hexagons':len(polygons),'radius_mm':radius,'web_mm':web,
            'minimum_hole_separation_mm':separation,'truncated_hexagons':0}
    if abs(normal[2])<.1 and 'vertical_hex_web_mm' in P:
        report['roof_angle_deg']=roof
        report['cell_centres_uv_mm']=[list(hole.centroid.coords)[0] for hole in polygons]
        report['validation_plane']={'origin':origin.tolist(),'u':eu.tolist(),
                                    'v':ev.tolist(),'normal':normal.tolist()}
    print('Pattern',{key:value for key,value in report.items()
                     if key not in ('cell_centres_uv_mm','validation_plane')},flush=True)
    return cutters,report


def clean_wing_frame(reference, outline, footprint):
    """Match the source fin and rim thickness, keeping their inside faces flush.

    Two large inclined faces in the supplied mesh share exact planar geometry
    with the smaller forward faces. Their equations establish the envelope;
    the old circular perforations and internal bosses are discarded.
    """
    wall=P.get('attachment_fin_thickness_mm',P['shell_panel_thickness_mm'])
    perimeter=P.get('attachment_frame_wall_mm',P['shell_panel_thickness_mm'])
    zcap=P['reference_rim_bottom_z_mm']+.06
    outer=mesh_shape(prism(outline,-29,zcap))
    inner=mesh_shape(prism(outline.buffer(-perimeter,join_style='mitre'),-29+perimeter,zcap+1))
    planes=[]
    for sign in (-1,1):
        candidates=[ids for ids in reference.facets
                    if sign*reference.face_normals[ids[0],0]>.4
                    and reference.face_normals[ids[0],2]<-.9]
        ids=max(candidates,key=lambda ids:reference.area_faces[ids].sum())
        normal=reference.face_normals[ids[0]]
        point=reference.triangles[ids[0],0]
        outer=outer.slice_plane(point,-normal,cap=True)
        inner=inner.slice_plane(point-wall*normal,-normal,cap=True)
        planes.append((sign,normal,point))
    frame=difference(outer,[inner,mesh_shape(prism(footprint.buffer(-.2),-45,15))])
    assert frame.is_volume
    return frame,planes,zcap


def run(export_step=True):
    OUT.mkdir(exist_ok=True)
    t=time.monotonic()
    revision=P.get('revision','v3')
    stem='mount_'+revision
    ztop=P['contact_z_mm']
    height=P['battery_mm'][2]
    floor_top=ztop-height
    zbottom=floor_top-P['floor_thickness_mm']
    wall=P['shell_panel_thickness_mm']
    fin_wall=P.get('attachment_fin_thickness_mm',wall)
    frame_wall=P.get('attachment_frame_wall_mm',wall)
    edge=P['panel_edge_rib_mm']
    dish=cq.importers.importStep(str(ROOT/'docs/official/Starlink_Mini_Dish.stp')).val()
    cage,crossbar,footprint=supports(dish,zbottom,ztop)
    reference=clipped_reference(P['port_cut_y_mm'])
    outline=example_outline('exterior').intersection(polygon_box(-110,-160,110,P['port_cut_y_mm']))
    frame,planes,zcap=clean_wing_frame(reference,outline,footprint)
    # The upper mating rail is retained. Legacy interior-plate supports are
    # reconstructed only to preserve historical revisions and cell layout.
    rail_outline=outline.difference(outline.buffer(-P['rim_rail_width_mm'],join_style='mitre'))
    rim=intersection(reference,mesh_shape(prism(rail_outline,P['reference_rim_bottom_z_mm'],5)))
    plate_supports=[]
    for sign in (-1,1):
        xa,xb=(82.2,94) if sign>0 else (-94,-82.2)
        patch=intersection(reference,mesh_shape(box(xa,xb,-128.4,-84,-16,-8.4)))
        plate_supports.append(patch)
    bay_l,bay_w=P['bay_xy_mm']
    xc,yc=P['battery_center_xy_mm']
    bay_back=yc-bay_w/2
    bay_front=yc+bay_w/2
    cavity=polygon_box(xc-bay_l/2,bay_back,xc+bay_l/2,bay_front)
    # Continue the hollow space through the extension: no full-height divider.
    cavity=cavity.union(footprint.buffer(-wall,join_style='mitre').intersection(
        polygon_box(-110,bay_front-.01,110,0)))
    void=mesh_shape(prism(cavity,floor_top,15))
    cage_mesh=difference(mesh_shape(cage),[void])
    rim=difference(rim,[void])
    low_walls=P.get('low_battery_walls',[])
    low_top=floor_top+P.get('low_battery_wall_height_mm',3.0)
    if '-Y' in low_walls:
        cage_mesh=difference(cage_mesh,[mesh_shape(box(-bay_l/2,bay_l/2,P['cage_rear_y_mm']-.1,
                                                      bay_back+.001,low_top,15))])
    if '+X' in low_walls:
        cage_mesh=difference(cage_mesh,[mesh_shape(box(bay_l/2-.001,110,P['cage_rear_y_mm']-.1,
                                                      bay_front+.001,low_top,15))])
    if '-X' in low_walls:
        # Match the other seating lips: the former USB-slot bottom is 3 mm
        # above the floor. Remove the cage wall above it, leaving the separate
        # Mini attachment fin, rail and front skirt in place.
        corners=[]
        corner_height=P.get('port_side_corner_height_mm',0)
        if corner_height>P['low_battery_wall_height_mm']:
            usb_y0,usb_y1=P['battery_port_window_y_mm']
            for ya,yb in ((bay_back,usb_y0),(usb_y1,bay_front)):
                corners.append(intersection(cage_mesh,mesh_shape(box(-110,-bay_l/2+.001,
                    ya,yb,floor_top-.1,floor_top+corner_height))))
        cage_mesh=difference(cage_mesh,[mesh_shape(box(-110,-bay_l/2+.001,P['cage_rear_y_mm']-.1,
                                                      bay_front+.001,low_top,15))])
        if corners:
            cage_mesh=union([cage_mesh,*corners])
    stop=intersection(mesh_shape(box(-bay_l/2,bay_l/2,bay_front,bay_front+P['battery_stop_thickness_mm'],
                                    floor_top-.1,floor_top+P['battery_stop_height_mm'])),
                      mesh_shape(prism(footprint,zbottom,ztop)))
    locators=[make_locator(dish,sign) for sign in (-1,1)]
    skirt_panels=[]
    if revision in ('v4','v5','v6','v7','v8','v9','v10','v11','v12','v13','v14','v15','v16','v17','v18'):
        # The gap is on the cavity side of the Mini's angled shoulder. Thicken
        # the skirt inward into the empty recess, then trim its outer surface
        # against the Mini. Moving it outward would enter the Mini's housing.
        from shapely.geometry import MultiPoint
        candidates=[ids for ids in reference.facets if reference.area_faces[ids].sum()>100
                    and reference.triangles_center[ids].mean(0)[1]>-62
                    and reference.face_normals[ids[0],0]>.8
                    and reference.face_normals[ids[0],1]>.4
                    and abs(reference.face_normals[ids[0],2])<.1]
        ids=max(candidates,key=lambda ids:reference.area_faces[ids].sum())
        source_points=reference.vertices[np.unique(reference.faces[ids])]
        source_normal=reference.face_normals[ids[0]]
        source_origin=reference.triangles[ids[0],0]
        for sign in P['front_skirt_sides']:
            mirror=np.array([sign,1,1])
            n=source_normal*mirror;origin=source_origin*mirror
            eu=np.cross([0,0,1],n);eu/=np.linalg.norm(eu)
            ev=np.cross(n,eu)
            delta=source_points*mirror-origin
            projected=np.column_stack([delta@eu,delta@ev])
            u0,v0,u1,v1=MultiPoint(projected).bounds
            v_floor=(low_top-origin[2])/ev[2]
            panel=MultiPoint(np.vstack([projected,[u0,v_floor],[u1,v_floor]])).convex_hull
            depth=P['front_skirt_inward_depth_mm']
            skirt=mesh_shape(polygon_prism(panel,origin-depth/2*n,eu,ev,n,depth))
            skirt_panels.append((sign,panel,origin,eu,ev,n,skirt))
    returns=[]
    if revision in ('v5','v6','v7','v8','v9','v10','v11','v12','v13','v14','v15','v16','v17','v18'):
        # Join the raised outer fin to the low seating lip with an outboard
        # return. The inner bay wall stays low; this panel lies outside it.
        x0,x1=P['right_fin_return_x_mm']
        normal,point=next((normal,point) for sign,normal,point in planes if sign>0)
        panel=mesh_shape(box(x0,x1,P['cage_rear_y_mm'],bay_front,
                             floor_top-.1,zcap))
        panel=panel.slice_plane(point-fin_wall*normal,normal,cap=True)
        assert_mesh(panel,'right fin return')
        returns.append(panel)
    fin_bridge=None
    end_corners=[]
    if P.get('end_corner_return_x_mm'):
        from corner_returns import make_returns
        for sign,shape in make_returns(planes,zbottom,zcap):
            assert shape.intersect(dish).Volume()<1e-5,'End corner clips exact Mini STEP'
            end_corners.append(mesh_shape(shape))
    end_band=None
    if P.get('outer_end_ramp_y_mm'):
        # Close the long slit below the outer end wall. The underside grows
        # outward at 45 degrees from the existing floor, rather than starting
        # a full-width horizontal shelf in mid-air. Stay outside the low bay
        # lip and overlap both the floor and the existing frame.
        ya,yb=P['outer_end_ramp_y_mm']
        top=P['outer_end_solid_band_top_z_mm']
        profile=Polygon([(yb,zbottom),(ya,zbottom+yb-ya),(ya,top),(yb,top)])
        end_band=mesh_shape(polygon_prism(profile,(0,0,0),(0,1,0),(0,0,1),
                                         (1,0,0),2*P['cage_x_half_mm']))
    bridge_outline=None
    bridge_window=None
    if revision=='v5':
        # Cover the unwanted top-view fin gap below the connector route.
        # The USB slot stays open across the whole outward approach volume.
        y0,y1=P['battery_port_window_y_mm']
        z0,z1=P['battery_port_window_z_mm']
        lost=intersection(frame,mesh_shape(box(-115,-67,y0,y1,z0,z1)))
        from shapely.geometry import MultiPoint
        bridge_outline=MultiPoint(lost.vertices[:,:2]).convex_hull
        # Overlap the cradle floor edge and the port-floor lip by 0.25 mm.
        bridge_outline=bridge_outline.union(polygon_box(-73,bay_back,-72.45,y1)).convex_hull
        fin_bridge=mesh_shape(prism(bridge_outline,
                                   z0-P['usb_fin_bridge_thickness_mm']-.1,z0))
        # A complete cell in the lower panel must also remain complete when
        # viewed from above. Reserve the projection of the retained upper fin
        # and old plate supports instead of hiding half a cell beneath their edges.
        from shapely.ops import unary_union
        connector_shadow=mesh_shape(cq.Workplane('XY').newObject([
            box(-115,-67,y0,y1,z0,z1)]).edges('|X').fillet(2).val())
        upper=difference(union([frame,rim,*plate_supports]),[connector_shadow])
        projected=[Polygon(triangle[:,:2]) for triangle in upper.triangles]
        shadow=unary_union([poly for poly in projected if poly.area>1e-8])
        bridge_window=bridge_outline.buffer(-wall).difference(
            shadow.buffer(P['print_line_width_mm']))
    retained_patches=plate_supports if P.get('retain_legacy_plate_supports',True) else []
    elements=[frame,rim,cage_mesh,mesh_shape(crossbar),stop,*retained_patches,
              *[panel[-1] for panel in skirt_panels],
              *returns,
              *end_corners,
              *([] if fin_bridge is None else [fin_bridge]),
              *([] if end_band is None else [end_band]),
              *[mesh_shape(nub) for nub in locators]]
    if frame_wall>wall:
        # Keep the open-end panel uniform through its height as well. The
        # rebuilt frame is thicker than the low cage, so extend its backing
        # down to the floor rather than leave a thickness step through cells.
        front=P['port_cut_y_mm']-.1
        end_outline=footprint.intersection(polygon_box(-110,front-frame_wall,110,front+.1))
        elements.append(mesh_shape(prism(end_outline,floor_top-.1,zcap)))
    body=union(elements)
    if P.get('locator_profile') == 'oem_tapered':
        # Recess the existing plate before rejoining the new 4.35 mm nubs.
        # Cutting only the plate keeps the nub roots and corner pads intact.
        from prototype_feedback import locator_seat_tools
        body = difference(body, [mesh_shape(tool) for tool in locator_seat_tools()])
        body = union([body, *[mesh_shape(nub) for nub in locators]])
    if P.get('fin_lip_ramp_depth_mm'):
        from prototype_feedback import lip_ramps
        ramps = [mesh_shape(shape) for shape in lip_ramps(reference)]
        body = union([body, *ramps])
    if P.get('clear_full_battery_envelope',False):
        # The example-derived front skirts previously entered the nominal bay
        # near its upper/front corners. Clear the complete requested envelope
        # after joining every panel, before placing whole hexagonal cells.
        body=difference(body,[mesh_shape(box(xc-bay_l/2,xc+bay_l/2,
            bay_back,bay_front,floor_top,ztop))])
    # Retain the measured battery as an independent assembly reference.
    # No old support bars are added: the uniform honeycomb floor seats the pack.
    battery=box(xc-P['battery_mm'][0]/2,xc+P['battery_mm'][0]/2,
                yc-P['battery_mm'][1]/2,yc+P['battery_mm'][1]/2,floor_top,ztop)
    mesh_shape(battery).export(OUT/'battery_nominal.stl')
    cq.exporters.export(battery,str(OUT/'battery_nominal.step'))
    precise=prepare()
    official=max(trimesh.load(ROOT/'docs/official/Starlink_Mini_Dish.stl',force='mesh').split(
        only_watertight=False),key=lambda m:len(m.faces))
    # Fit first, pattern second. Otherwise the STEP relief can clip a cell.
    body=difference(body,[precise])
    for axis in range(3):
        for sign in (-1,1):
            relief=precise.copy();delta=np.zeros(3);delta[axis]=sign*P['mating_clearance_axes_mm']
            relief.apply_translation(delta)
            body=difference(body,[relief])
    body=difference(body,[official])
    body.export(OUT/(stem+'_solid.stl'))
    assert_mesh(body,'rebuilt fitted unperforated shell')
    tools=[]
    stats=[]
    y0,y1=P['battery_port_window_y_mm']
    z0,z1=P['battery_port_window_z_mm']
    def aperture_guard(xyz):
        lo,hi=xyz.min(0),xyz.max(0)
        return (lo[0]<-67 and hi[0]>P.get('usb_cut_outer_x_mm',-115)-edge
                and hi[1]>y0-edge and lo[1]<y1+edge
                and hi[2]>z0-edge and lo[2]<z1+edge)
    def add(window,origin,eu,ev,normal,length,label,protect=False,radius=None):
        upright=abs(normal[2])<.1 and 'vertical_hex_web_mm' in P
        web=P['vertical_hex_web_mm'] if upright else P['hex_web_width_mm']
        if upright and radius is None:
            radius=P['vertical_hex_radius_mm']
        actual=material_window(body,origin,eu,ev,normal,length,web)
        window=window.intersection(actual)
        cs,report=full_hex_pattern(window,origin,eu,ev,normal,length,label,radius,
                                  aperture_guard if protect else None,web)
        tools.extend(cs);stats.append(report)
    # Floor holes stop clear of the low divider; there are no straight floor rails.
    floor_window=cavity.buffer(-edge,join_style='mitre')
    floor_window=floor_window.difference(polygon_box(-100,bay_front-edge,100,
                                                   bay_front+P['battery_stop_thickness_mm']+edge))
    add(floor_window,(0,0,floor_top-1.5),(1,0,0),(0,1,0),(0,0,1),3.2,'floor')
    if revision in ('v4','v5','v6','v7','v8','v9','v10','v11','v12','v13','v14','v15','v16','v17','v18'):
        extension=cavity.buffer(-P['hex_web_width_mm'],join_style='mitre').intersection(
            polygon_box(-110,bay_front+P['battery_stop_thickness_mm']+P['hex_web_width_mm'],110,0))
        add(extension,(0,0,floor_top-1.5),(1,0,0),(0,1,0),(0,0,1),3.2,'floor port extension',
            radius=P['front_floor_hex_radius_mm'])
    if fin_bridge is not None:
        add(bridge_window,
            (0,0,z0-P['usb_fin_bridge_thickness_mm']/2),(1,0,0),(0,1,0),(0,0,1),
            P['usb_fin_bridge_thickness_mm']+.3,'floor USB fin bridge',
            radius=P['usb_fin_bridge_hex_radius_mm'])
    side_window=polygon_box(bay_back+edge,floor_top+edge,bay_front-edge,
                            ztop-edge)
    for sign,normal,point in planes:
        if ('+X' if sign>0 else '-X') in low_walls:
            stats.append({'panel':f'battery side {sign}','whole_hexagons':0,'truncated_hexagons':0,
                          'wall_height_mm':P['low_battery_wall_height_mm']})
            continue
        # The wing joins the cage along a slanted plane edge. Keep cells clear
        # of this whole junction, including the panel thickness.
        d=float(normal@point)
        ys=[side_window.bounds[0]-1,side_window.bounds[2]+1]
        seam=[]
        for y in ys:
            z=(d-normal[0]*sign*P['cage_x_half_mm']-normal[1]*y)/normal[2]
            seam.append((y,z))
        strip=Polygon([(ys[0],seam[0][1]-edge),(ys[1],seam[1][1]-edge),
                       (ys[1],seam[1][1]+wall/abs(normal[2])+edge),
                       (ys[0],seam[0][1]+wall/abs(normal[2])+edge)])
        add(side_window.difference(strip),(sign*(70+wall/2),0,0),(0,1,0),(0,0,1),
            (sign,0,0),wall+.2,f'battery side {sign}',protect=sign<0,radius=P['hex_narrow_radius_mm'])
    # Cage end panels receive local tools, never a cutter spanning both end walls.
    back_window=polygon_box(-70+edge,floor_top+edge,70-edge,
                            ztop-P['protected_contact_depth_mm'])
    if '-Y' not in low_walls:
        add(back_window,(0,(P['cage_rear_y_mm']+bay_back)/2,0),(1,0,0),(0,0,1),(0,1,0),
            bay_back-P['cage_rear_y_mm']+.2,'battery rear')
    else:
        stats.append({'panel':'battery rear','whole_hexagons':0,'truncated_hexagons':0,
                      'wall_height_mm':P['low_battery_wall_height_mm']})
    from shapely.geometry import LineString
    front_y=P['port_cut_y_mm']-.1
    front_segment=footprint.intersection(LineString([(-150,front_y-.01),(150,front_y-.01)]))
    lo,_,hi,_=front_segment.bounds
    front_window=polygon_box(lo+edge,floor_top+edge,hi-edge,-11-edge)
    add(front_window,(0,front_y-frame_wall/2,0),(1,0,0),(0,0,1),(0,1,0),frame_wall+.3,'extended front')
    # A whole-cell row in the upper locator plane, clear of the drafted nubs.
    bar_window=example_outline('interior').intersection(polygon_box(-100,-48,100,front_y)).buffer(-wall)
    for sign in (-1,1):
        bar_window=bar_window.difference(polygon_box(sign*23.58-13,-46.8,sign*23.58+13,-39.2))
    add(bar_window,(0,0,-8.8053),(1,0,0),(0,1,0),(0,0,1),4.5,'locator plane',radius=P['hex_locator_radius_mm'])
    # Perforate the new inner face of the skirt. Sample the guaranteed free
    # inner panel thickness while the cutter passes through the entire skirt.
    for sign,panel,origin,eu,ev,n,skirt in skirt_panels:
        depth=P['front_skirt_inward_depth_mm']
        inner_origin=origin-(depth-wall/2)*n
        skirt_web=P.get('vertical_hex_web_mm',P['hex_web_width_mm'])
        window=panel.buffer(-skirt_web).intersection(material_window(body,inner_origin,eu,ev,n,wall,skirt_web))
        cs,report=full_hex_pattern(window,origin-depth/2*n,eu,ev,n,depth+.2,
                                  f'front skirt {sign}',P['hex_narrow_radius_mm'],
                                  aperture_guard if sign<0 else None,skirt_web)
        if 'validation_plane' in report:
            report['validation_plane']['origin']=inner_origin.tolist()
        tools.extend(cs);stats.append(report)
    # True inclined wing panels: use their own local metric and normal.
    for sign,normal,point in planes:
        # Project the entire continuous lower face, then fill its inherited round holes.
        frame_section=frame.section(plane_normal=normal,plane_origin=point-.1*normal)
        eu=np.cross(normal,[0,0,1]);eu/=np.linalg.norm(eu)
        ev=np.cross(normal,eu)
        areas=[]
        for loop in frame_section.discrete:
            delta=loop-point
            poly=Polygon(np.column_stack([delta@eu,delta@ev])).buffer(0)
            if poly.area>50: areas.append(poly)
        wing=max(areas,key=lambda poly:poly.area)
        wing=Polygon(wing.exterior.coords).buffer(-edge)
        # Keep the existing reserved support footprint so removing the old
        # plate ledges does not move the established whole-cell layout.
        # Use the actual source patch footprint rather than its bounding box.
        support=plate_supports[0 if sign<0 else 1]
        delta=support.vertices-point
        from shapely.geometry import MultiPoint
        pad=MultiPoint(np.column_stack([delta@eu,delta@ev])).convex_hull.buffer(wall)
        wing=wing.difference(pad)
        add(wing,point-fin_wall/2*normal,eu,ev,normal,fin_wall+.2,f'inclined wing {sign}',
            protect=sign<0 and revision!='v6',
            radius=P['hex_narrow_radius_mm'])
    if returns:
        x0,x1=P['right_fin_return_x_mm']
        window=polygon_box(P['cage_rear_y_mm']+wall,floor_top+wall,
                           bay_front-wall,zcap)
        # The front skirt overlaps the return at its forward end. Keep holes
        # out of that seam so a second panel cannot mask half a hexagon.
        from shapely.geometry import MultiPoint
        for sign,_,_,_,_,_,skirt in skirt_panels:
            if sign>0:
                reserved=MultiPoint(skirt.vertices[:,1:]).convex_hull.buffer(wall)
                window=window.difference(reserved)
        add(window,((x0+x1)/2,0,0),(0,1,0),(0,0,1),(1,0,0),x1-x0+.2,
            'battery side right fin return',radius=P['right_fin_return_hex_radius_mm'])
    # Rear outer plane; conservative local tools keep the inner bay wall intact.
    rear_x=73.0
    rear_window=polygon_box(-rear_x+edge,-29+edge,rear_x-edge,zcap-edge)
    add(rear_window,(0,-147.4+frame_wall/2,0),(1,0,0),(0,0,1),(0,1,0),frame_wall+.2,'outer rear')
    # Extend the rectangle through any fin material that would otherwise
    # mask its visible outline. Leave the fin outside this aperture intact.
    connector=box(P.get('usb_cut_outer_x_mm',-115),-67,y0,y1,z0,z1)
    corner_radius=P.get('usb_corner_radius_mm',2.0)
    if corner_radius>0:
        connector=cq.Workplane('XY').newObject([connector]).edges('|X').fillet(corner_radius).val()
    tools.append(mesh_shape(connector))
    if P.get('power_end_access_bounds_mm'):
        from prototype_feedback import access_window_tools
        tools.extend(mesh_shape(tool) for tool in access_window_tools())
    perforated=difference(body,[union(tools)])
    final=perforated
    if P.get('track_backing_bounds_positive_mm'):
        from track_backing import make as make_track_backing, join as join_track_backing
        final=join_track_backing(final,make_track_backing(precise,official))
    final.export(OUT/(stem+'_debug_raw.stl'))
    print('Components',[(len(p.faces),round(p.volume,5),p.bounds.tolist()) for p in final.split(
        only_watertight=False)],flush=True)
    assert_mesh(final,'complete-cell hexagonal shell')
    final.export(OUT/(stem+'.stl'))
    validation={}
    for name,target in [('battery',mesh_shape(battery)),('official_stl',official),('step_precise_mesh',precise)]:
        common=intersection(final,target)
        vol=abs(common.volume) if len(common.faces) else 0.
        assert vol<.01,f'{name} overlap {vol}'
        validation[name+'_overlap_mm3']=vol
    validation.update(mesh_watertight=final.is_watertight,mesh_winding_consistent=final.is_winding_consistent,
                      mesh_volume_cm3=final.volume/1000,bounds_mm=final.bounds.tolist(),parameters=P,
                      panel_patterns=stats,whole_hexagon_count=sum(p['whole_hexagons'] for p in stats),
                      divider_height_mm=P['battery_stop_height_mm'],floor_rails=0,
                      low_battery_walls=low_walls,low_battery_wall_height_mm=P.get('low_battery_wall_height_mm'),
                      retained_features=['polygonal lip above Z=-9.8086','two drafted inner nubs']+
                          (['two original interior-plate support patches'] if retained_patches else []),
                      notes=['Complete hexagons only; no clipped cells in the panel patterns.',
                             'No legacy screw holes, bosses, random pockets or support strips.',
                             'Independent numerical fit checks; physical ASA coupon testing remains necessary.'])
    if 'vertical_hex_roof_angle_deg' in P and not P.get('pattern_floor_only'):
        validation['notes'].append('Upright cells have shortened vertical shoulders and 45-degree roofs; floor and inclined-fin cells remain regular.')
    if P.get('pattern_floor_only'):
        validation['notes'].append('Only the main and extension floor planes retain hexagons; fins, skirts, walls and locator plate are solid apart from functional access.')
        validation['notes'].append('OEM-sized tapered nubs have joined short-end gussets with sloped long-side supports and recessed plate seats; lip underside ramps target trapped trench supports.')
    if not retained_patches:
        validation['notes'].append('Legacy interior-plate support patches removed; original polygonal mating rim retained.')
    if bridge_outline is not None:
        validation['usb_fin_bridge']={
            'outline_xy_mm':list(bridge_outline.exterior.coords),
            'bottom_z_mm':z0-P['usb_fin_bridge_thickness_mm']-.1,
            'top_z_mm':z0,
            'full_usb_approach_preserved':True}
    validation['usb_aperture']={
        'y_mm':[y0,y1],'z_mm':[z0,z1],
        'corner_radius_mm':corner_radius,
        'cut_outer_x_mm':P.get('usb_cut_outer_x_mm',-115),
        'bay_wall_open_top':'-X' in low_walls}
    if end_band is not None:
        validation['outer_end_solid_band']={
            'y_mm':P['outer_end_ramp_y_mm'],'top_z_mm':P['outer_end_solid_band_top_z_mm'],
            'underside_angle_from_horizontal_deg':45.0,
            'minimum_normal_thickness_mm':(top-(zbottom+yb-ya))/np.sqrt(2),
            'continuous_solid':True}
    if P.get('port_side_corner_height_mm',0)>0:
        validation['port_side_corner_retention']={
            'height_above_floor_mm':P['port_side_corner_height_mm'],
            'rear_y_mm':[bay_back,y0],'front_y_mm':[y1,bay_front],
            'reported_port_count':P['battery_port_count'],
            'reported_edge_inset_mm':P['battery_port_edge_inset_mm'],
            'port_end_clearance_mm':P['battery_port_end_clearance_mm']}
    (OUT/(stem+'_validation.json')).write_text(json.dumps(validation,indent=2))
    if export_step:
        from export_mount_step import run as convert
        convert(revision)
    print(revision,'build seconds',round(time.monotonic()-t,2),flush=True)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--mesh-only',action='store_true')
    run(export_step=not parser.parse_args().mesh_only)
