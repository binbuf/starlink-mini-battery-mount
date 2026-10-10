"""Inspect delivered access rectangles, nub sections, withdrawal and lip ramps."""
import json
import numpy as np
import cadquery as cq
import trimesh
from shapely.geometry import Point, Polygon, box as polygon_box
from build_design import ROOT, OUT, P, box
from generate_mount import mesh_shape
from validate_smooth_fins import solid
from prototype_feedback import locator_coordinates


def inspect(mount):
    assert P['revision'] in ('v16', 'v17', 'v18')
    result = {}
    current = solid(mount)
    if P['revision'] in ('v17', 'v18'):
        prior_stem = 'mount_v17' if P['revision'] == 'v18' else 'mount_v16'
        v16 = solid(trimesh.load(OUT/(prior_stem+'.stl'), force='mesh'))
        changes = (current-v16)+(v16-current)
        allowed = None
        for sign in (-1, 1):
            x, y = locator_coordinates(sign)
            region = solid(mesh_shape(box(x-5, x+5, y-3, y+3,
                                          P['locator_root_z_mm']-.1,
                                          P['locator_root_z_mm']+1.2)))
            allowed = region if allowed is None else allowed+region
        if P.get('locator_release_recess_bounds_mm'):
            from prototype_feedback import release_recess_tool
            allowed = allowed+solid(mesh_shape(release_recess_tool()))
        # Later authorized cleanup also moves P10 and removes internal ledges.
        if P.get('remove_internal_rim_lips'):
            from internal_rim_cleanup import cutters, inward_planes_from_mesh, front_wall_tools
            cleanup_tools = cutters(P, inward_planes_from_mesh(mount))
            allowed = allowed + cleanup_tools[0] + cleanup_tools[1]
            front_cut, front_fills = front_wall_tools(P)
            if front_cut is not None:
                allowed = allowed + front_cut
                for fill in front_fills:
                    allowed = allowed + fill
            from surface_detail_cleanup import all_fills
            for fill in all_fills(P):
                allowed = allowed + fill
            from lower_side_cleanup import interior_tools
            fills, cuts = interior_tools(P, inward_planes_from_mesh(mount))
            for tool in fills + cuts:
                allowed = allowed + tool
            from front_wall_cleanup import tools as front_square_tools
            fills, cuts = front_square_tools(P, inward_planes_from_mesh(mount))
            for tool in fills + cuts:
                allowed = allowed + tool
            (a, b), (y0, y1), (z0, z1) = P['display_access_bounds_mm']
            for x0, x1 in ((a, b), (-b, -a)):
                allowed = allowed + solid(mesh_shape(box(x0-.02, x1+.02, y0-.02, y1+.02, z0-.02, z1+.02)))
        outside = abs(float((changes-allowed).volume()))
        assert outside < .01, 'Geometry changed outside the authorized local regions'
        result['reinforcement_change'] = {
            'outside_reinforcement_regions_mm3': outside,
            'joined_short_ends': True, 'sloped_separate_long_sides': True}
    previous = trimesh.load(OUT/'mount_v15.stl', force='mesh')
    old = solid(previous)
    windows = []
    for key in ('power_end_access_bounds_mm', 'display_access_bounds_mm'):
        (x0, x1), (y0, y1), (z0, z1) = P[key]
        probe = solid(mesh_shape(box(x0+.005, x1-.005, y0, y1, z0+.005, z1-.005)))
        overlap = abs(float((current^probe).volume()))
        assert overlap < .01, f'{key} is obstructed'
        section = mount.section(plane_normal=[0, 1, 0], plane_origin=[0, (y0+y1)/2, 0])
        polygons = [Polygon(loop[:, [0, 2]]).buffer(0) for loop in section.discrete]
        desired = polygon_box(x0, z0, x1, z1)
        aperture = min(polygons, key=lambda p: p.hausdorff_distance(desired))
        error = aperture.hausdorff_distance(desired)
        assert error < .005, f'{key} is not a complete rectangle'
        windows.append({'name': key, 'width_mm': x1-x0, 'height_mm': z1-z0,
                        'profile_error_mm': float(error), 'overlap_mm3': overlap})
    result['access_windows'] = windows
    if P.get('locator_release_recess_bounds_mm'):
        from prototype_feedback import release_recess_tool
        obstruction = abs(float((current^solid(mesh_shape(release_recess_tool()))).volume()))
        assert obstruction < .01, 'Finger release recess is obstructed'
        floor = P['locator_release_recess_bounds_mm'][2][0]
        thicknesses = []
        for x in (-6, 0, 6):
            for y in (-35, -34, -32):
                hits, _, _ = mount.ray.intersects_location([[x, y, 2]], [[0, 0, -1]], multiple_hits=True)
                heights = sorted(hits[:, 2], reverse=True)
                assert abs(heights[0]-floor) < .005, 'Incorrect finger recess depth'
                thicknesses.append(float(heights[0]-heights[1]))
        assert min(thicknesses) > 2.38, 'Finger recess backing is too thin'
        assert mount.contains([[-11,-35,-7], [11,-35,-7], [0,-38,-7]]).all(), 'Recess extends beyond its intended edges'
        result['finger_release_recess'] = {
            'width_mm': 20, 'inward_reach_from_edge_mm': 8,
            'depth_from_plate_mm': 2, 'corner_radius_mm': 3,
            'floor_fillet_mm': .8, 'obstruction_mm3': obstruction,
            'minimum_sampled_backing_thickness_mm': min(thicknesses),
            'position': 'X=0, at P19 power-port edge adjoining P11'}
    nubs = []
    fine = trimesh.load(ROOT/'cad/review/dish_step_precise_primary.stl', force='mesh')
    official = max(trimesh.load(ROOT/'docs/official/Starlink_Mini_Dish.stl').split(
        only_watertight=False), key=lambda p: len(p.faces))
    root = P['locator_root_z_mm']
    height = P['locator_height_mm']
    for sign in (-1, 1):
        x, y = locator_coordinates(sign)
        dimensions = []
        for raised in (1.3, 2.2, height-.02):
            section = mount.section(plane_normal=[0, 0, 1], plane_origin=[0, 0, root+raised])
            polygons = [Polygon(loop[:, :2]).buffer(0) for loop in section.discrete]
            candidates = [p for p in polygons if p.contains(Point(x, y))]
            nub = min(candidates, key=lambda p: p.area)
            x0, y0, x1, y1 = nub.bounds
            expected_width = P['locator_base_width_mm'] + raised/height*(
                P['locator_tip_width_mm']-P['locator_base_width_mm'])
            expected_thickness = P['locator_base_thickness_mm'] + raised/height*(
                P['locator_tip_thickness_mm']-P['locator_base_thickness_mm'])
            assert abs(x1-x0-expected_width) < .005
            assert abs(y1-y0-expected_thickness) < .005
            dimensions.append({'height_above_seat_mm': raised,
                               'width_mm': x1-x0, 'thickness_mm': y1-y0})
        points = []
        span = P['locator_root_support_span_mm']
        for sx in (-1, 1):
            for sy in (-1, 1):
                points.append([x+sx*(P['locator_base_width_mm']/2-span/2+.3),
                               y+sy*(P['locator_base_thickness_mm']/2+.65),
                               root+(.3 if P['revision'] in ('v17', 'v18') else .5)])
        assert mount.contains(points).all(), 'One of four corner supports is missing'
        if P['revision'] in ('v17', 'v18'):
            # Joined material outside both short ends, and gradual wedge slopes
            # along the long sides with a clear gap at the centre.
            joined = [[x+sx*(P['locator_base_width_mm']/2+.1), y, root+.2] for sx in (-1, 1)]
            assert mount.contains(joined).all(), 'Short-end supports do not meet'
            wedge = [[x+sx*2.9, y+sy*2.4, root+.15] for sx in (-1, 1) for sy in (-1, 1)]
            above = [[a,b,root+.8] for a,b,_ in wedge]
            assert mount.contains(wedge).all() and not mount.contains(above).any(), 'Long-side supports do not slope gradually'
            gap = [[x, y+sy*2, root+.2] for sy in (-1, 1)]
            assert not mount.contains(gap).any(), 'Long-side end supports have joined across the gap'
        region = mesh_shape(box(x-13, x+13, y-5, y+5, root-.01, root+height+.05))
        material = trimesh.boolean.intersection([mount, region], engine='manifold')
        actual_top = material.bounds[1, 2]
        assert abs(actual_top-(root+height)) < .005
        # Check the extra socket-width plate material is removed, too.
        assert not mount.contains([[x-9, y, -6.5], [x+9, y, -6.5]]).any()
        sweep = []
        for down in (0, .25, .5, 1, 2, 4.5):
            shifted = solid(material.copy().apply_translation([0, 0, -down]))
            overlap = max(abs(float((shifted^solid(target)).volume())) for target in (fine, official))
            assert overlap < .01, 'Locator-only downward withdrawal clips Mini'
            sweep.append({'downward_travel_mm': down, 'maximum_mini_overlap_mm3': overlap})
        nubs.append({'side': sign, 'height_mm': actual_top-root,
                     'section_dimensions': dimensions, 'corner_supports': 4, 'short_end_gussets': 2,
                     'locator_only_withdrawal': sweep})
    result['locators'] = nubs
    # The source lip remains. Ramps add material underneath it, outside the bay.
    if P.get('fin_lip_ramp_depth_mm', 0):
        ramp_region = solid(mesh_shape(box(-105, -75, -148, -62, -14, -9.75)))
        ramp_region += solid(mesh_shape(box(75, 105, -148, -62, -14, -9.75)))
        added = current-old
        ramp_material = added^ramp_region
        assert ramp_material.volume() > 100, 'Lip underside ramps were not delivered'
        change = ramp_material.to_mesh64()
        ramps = trimesh.Trimesh(change.vert_properties[:, :3], change.tri_verts, process=True)
        down = ramps.face_normals[:, 2] < -.4
        area = float(ramps.area_faces[down & (np.abs(ramps.face_normals[:, 2]+np.sqrt(.5)) < .001)].sum())
        assert area > 50, '45-degree lip ramp undersides are missing'
        result['lip_ramps'] = {'added_local_volume_mm3': float(ramp_material.volume()),
                               'measured_45_degree_underside_area_mm2': area,
                               'remaining_supports': 'Broad fin undersides and rectangular-window roofs.'}
    else:
        result['lip_ramps'] = {'enabled': False, 'reason': 'Obsolete internal side ledges removed.'}
    if P.get('remove_internal_rim_lips'):
        from internal_rim_cleanup import cutters, inward_planes_from_mesh
        cleanup_tools = cutters(P, inward_planes_from_mesh(mount))
        planes = inward_planes_from_mesh(mount)
        probes = [tool.trim_by_plane(normal.tolist(), float(np.dot(normal, point))+.0002)
                  for tool, (_, normal, point) in zip(cleanup_tools, planes)]
        obstruction = abs(float((current ^ (probes[0]+probes[1])).volume()))
        assert obstruction < .05, 'Internal side lips remain inside the cleanup envelope'
        result['internal_rim_cleanup'] = {'remaining_internal_material_mm3': obstruction}
        from internal_rim_cleanup import front_wall_tools
        front_cut, _ = front_wall_tools(P)
        if front_cut is not None:
            obstruction = abs(float((current ^ front_cut).volume()))
            assert obstruction < .05, 'Front wall step remains inside the cleanup envelope'
            result['internal_front_wall_cleanup'] = {'remaining_internal_material_mm3': obstruction}
        from surface_detail_cleanup import edge_trench_fills
        missing = sum(abs(float((fill-current).volume())) for fill in edge_trench_fills(P))
        assert missing < .05, 'Locator plate edge trenches remain unfilled'
        result['locator_edge_trench_cleanup'] = {'missing_fill_mm3': missing}
        from surface_detail_cleanup import right_bottom_fill
        bottom_fill = right_bottom_fill(P)
        if bottom_fill is not None:
            missing = abs(float((bottom_fill-current).volume()))
            assert missing < .05, 'Right bottom rectangular setback remains unfilled'
            result['right_bottom_recess_cleanup'] = {'missing_fill_mm3': missing}
        if P.get('lower_interior_blend') and not P.get('square_lower_front_wall'):
            from lower_side_cleanup import exterior_fill, interior_tools
            fills, cuts = interior_tools(P, planes)
            combined_cut = cuts[0]
            for cut in cuts[1:]:
                combined_cut += cut
            obstruction = abs(float((current ^ combined_cut).volume()))
            missing = sum(abs(float(((fill-current)-combined_cut).volume()))
                          for fill in fills + [exterior_fill(P)])
            assert obstruction < .05, 'Lower interior terraces remain'
            assert missing < .05, 'Lower wall blends are incomplete'
            result['lower_wall_cleanup'] = {
                'remaining_terrace_material_mm3': obstruction,
                'missing_blend_material_mm3': missing}
        if P.get('square_lower_front_wall'):
            from front_wall_cleanup import tools as front_square_tools
            fills, cuts = front_square_tools(P, planes)
            obstruction = abs(float((current ^ cuts[0]).volume()))
            missing = sum(abs(float(((fill-current)-cuts[0]).volume()))
                          for fill in fills)
            assert obstruction < .05, 'Lower front wall is not vertical'
            assert missing < .05, 'Square front wall or floor is incomplete'
            result['square_lower_front_wall'] = {
                'remaining_interior_material_mm3': obstruction,
                'missing_wall_or_floor_mm3': missing}
    audit = json.loads((OUT/('mount_'+P['revision']+'_validation.json')).read_text())
    assert all(p['whole_hexagons'] == 0 for p in audit['panel_patterns']
               if not p['panel'].startswith('floor'))
    assert sum(p['whole_hexagons'] for p in audit['panel_patterns']) == 69
    # All previously patterned upright-cell centre locations must now be
    # material, except where explicitly replaced by the access rectangles.
    prior = json.loads((OUT/'mount_v15_validation.json').read_text())
    tested = 0
    for pattern in prior['panel_patterns']:
        if 'validation_plane' not in pattern:
            continue
        plane = pattern['validation_plane']
        for u, v in pattern['cell_centres_uv_mm']:
            point = np.array(plane['origin'])+u*np.array(plane['u'])+v*np.array(plane['v'])
            intentional = any(all(a-.01 <= coordinate <= b+.01
                                 for coordinate, (a, b) in zip(point, P[key]))
                              for key in ('power_end_access_bounds_mm', 'display_access_bounds_mm'))
            if not intentional:
                assert mount.contains([point])[0], 'An old side-wall cell remains open'
                tested += 1
    result['patterns'] = {'floor_hexagons': 69, 'other_pattern_holes': 0,
                          'old_upright_cell_centres_filled': tested}
    return {'delivered_prototype_feedback': result}


if __name__ == '__main__':
    mesh = trimesh.load(OUT/('mount_'+P['revision']+'.stl'), force='mesh')
    result = inspect(mesh)
    path = OUT/('mount_'+P['revision']+'_validation.json')
    audit = json.loads(path.read_text())
    audit.update(result)
    path.write_text(json.dumps(audit, indent=2))
    print(json.dumps(result, indent=2))
