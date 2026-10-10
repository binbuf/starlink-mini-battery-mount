"""Solid end-corner returns, bounded by the reference fin and print slopes."""
import numpy as np
from build_design import P,box
from shapely.geometry import box as polygon_box
from build_design import polygon_prism


def keep_half_space(origin,normal):
    """Large one-sided prism in an orthonormal frame, local +Z kept."""
    n=np.array(normal,float,copy=True);n/=np.linalg.norm(n)
    u=np.cross(n,[0,0,1])
    if np.linalg.norm(u)<1e-8: u=np.array([1.,0,0])
    u/=np.linalg.norm(u)
    v=np.cross(n,u)
    return polygon_prism(polygon_box(-250,-250,250,250),np.asarray(origin)+250*n,u,v,n,500)


def make_returns(planes,zbottom,zcap):
    x0,x1=P['end_corner_return_x_mm']
    ya=P['outer_end_ramp_y_mm'][0]
    yb=P['battery_port_window_y_mm'][0]
    floor_y=P['outer_end_ramp_y_mm'][1]
    result=[]
    for sign,normal,point in planes:
        xa,xb=(x0,x1) if sign>0 else (-x1,-x0)
        shape=box(xa,xb,ya,yb,zbottom,zcap)
        # The roof meets the inner face of the original inclined fin.
        thickness=P.get('attachment_fin_thickness_mm',P['shell_panel_thickness_mm'])
        shape=shape.intersect(keep_half_space(point-thickness*normal,normal))
        # Grow outward from the floor at 45 degrees in X and at the end in Y.
        shape=shape.intersect(keep_half_space((sign*x0,0,zbottom),(-sign,0,1)))
        shape=shape.intersect(keep_half_space((0,floor_y,zbottom),(0,1,1))).clean()
        assert shape.isValid() and len(shape.Solids())==1
        result.append((sign,shape))
    return result
