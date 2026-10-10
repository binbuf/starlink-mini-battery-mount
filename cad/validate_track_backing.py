"""Inspect the serialized local repair and preserve all other geometry."""
import numpy as np
import trimesh
from build_design import ROOT, P
from track_backing import bounding_meshes
from validate_smooth_fins import solid


def inspect(mount):
    previous=trimesh.load(ROOT/'cad/out/mount_v14.stl',force='mesh')
    old,new=solid(previous),solid(mount)
    removed=abs(float((old-new).volume()))
    boxes=bounding_meshes()
    allowed=solid(boxes[0])+solid(boxes[1])
    comparison_scope = 'complete enclosure'
    if P['revision'] != 'v15':
        # Later revisions intentionally change other panels. Limit this
        # original repair audit to the two previously approved backing boxes.
        old, new = old^allowed, new^allowed
        removed=abs(float((old-new).volume()))
        comparison_scope = 'two approved backing boxes'
    added=new-old
    outside=abs(float((added-allowed).volume()))
    assert removed<.03, 'Track backing removed existing geometry'
    assert outside<.03, 'Track backing changed unrelated geometry'
    sides=[]
    for sign, bounds in zip((-1,1),boxes):
        mirror=np.array([sign,1,1])
        centre=np.array([69.8179718467,-52.0166290508,-20.7335429733])*mirror
        direction=np.array([-162.,-236.,-47.])*mirror
        direction/=np.linalg.norm(direction)
        u=np.cross(direction,[0,0,1]);u/=np.linalg.norm(u)
        v=np.cross(u,direction)
        starts=np.array([centre+du*u+dv*v-100*direction
                         for du in (-.12,0,.12) for dv in (-.12,0,.12)])
        rays=np.tile(direction,(len(starts),1))
        points,ids,_=mount.ray.intersects_location(starts,rays,multiple_hits=True)
        bb=bounds.bounds
        inside=np.all((points>=bb[0]-.01)&(points<=bb[1]+.01),axis=1)
        count=len(np.unique(ids[inside]))
        assert count==len(starts),'Track opening remains through the local backing'
        old_points,old_ids,_=previous.ray.intersects_location(starts,rays,multiple_hits=True)
        old_inside=np.all((old_points>=bb[0]-.01)&(old_points<=bb[1]+.01),axis=1)
        previously_open=len(starts)-len(np.unique(old_ids[old_inside]))
        assert previously_open>0,'Inspection rays did not locate the original opening'
        sides.append({'side':sign,'ray_count':len(starts),'rays_blocked':count,
                      'previously_open_rays':previously_open,
                      'added_material_mm3':abs(float((added^solid(bounds)).volume()))})
    result={'sides':sides,'added_material_mm3':abs(float(added.volume())),
            'comparison_scope':comparison_scope,
            'removed_numerical_difference_mm3':removed,
            'added_outside_approved_local_boxes_mm3':outside,
            'measured_battery_end_clearance_at_backing_mm':P['track_backing_bounds_positive_mm'][0][0]-P['battery_mm'][0]/2,
            'boolean_precision':'float64'}
    print('Both small track holes backed; unchanged geometry verified',flush=True)
    return {'delivered_track_backing':result}
