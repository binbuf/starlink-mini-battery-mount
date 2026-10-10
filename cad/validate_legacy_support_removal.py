"""Check that old plate ledges are absent and removal stays in their patches."""
import trimesh
from build_design import P,ROOT,box
from generate_mount import mesh_shape
from validate_smooth_fins import solid


def inspect(mount):
    new=solid(mount);clear=[]
    for sign in (-1,1):
        x0,x1=(93.05,93.95) if sign>0 else (-93.95,-93.05)
        probe=solid(mesh_shape(box(x0,x1,-127,-104,-9.78,-8.48)))
        overlap=abs(float((new^probe).volume()))
        assert overlap<.01,'Legacy interior-plate seating ledge remains'
        clear.append({'side':sign,'former_plate_seat_probe_overlap_mm3':overlap})
    result={'legacy_plate_seats':clear,'comparison_to_v13':None}
    previous=ROOT/'cad/out/mount_v13.stl'
    if previous.exists() and P['revision']=='v14':
        old=solid(trimesh.load(previous,force='mesh'))
        allowed=solid(mesh_shape(box(-94.01,-82.19,-128.41,-83.99,-16.01,-8.39)))
        allowed+=solid(mesh_shape(box(82.19,94.01,-128.41,-83.99,-16.01,-8.39)))
        removed=old-new;added=new-old
        outside=abs(float((removed-allowed).volume()))
        extra=abs(float(added.volume()))
        assert outside<.03,'Material removed outside the selected legacy support patches'
        assert extra<.03,'Unrelated material added during support removal'
        result['comparison_to_v13']={'removed_mm3':abs(float(removed.volume())),
            'added_numerical_difference_mm3':extra,'removed_outside_support_patches_mm3':outside,
            'boolean_precision':'float64'}
    return {'delivered_legacy_support_removal':result}
