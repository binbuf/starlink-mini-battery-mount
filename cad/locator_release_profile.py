"""Dropped release web between the P19 locating nubs (mm)."""
import cadquery as cq
import manifold3d as mf
import numpy as np
import trimesh
from internal_rim_cleanup import as_solid


def cuboid(bounds):
    lo,hi=np.asarray(bounds,dtype=float).T
    return mf.Manifold.cube(hi-lo).translate(lo)


def mesh_solid(shape, tolerance=.015):
    vertices,faces=shape.tessellate(tolerance,.07)
    mesh=trimesh.Trimesh([v.toTuple() for v in vertices],faces,process=True)
    assert mesh.is_volume
    return as_solid(mesh)


def rear_wall_tools(parameters):
    spec=parameters.get('locator_rear_wall_removal')
    if not spec:
        return []
    width,depth=parameters['locator_recess_size_mm']
    end_y=parameters['locator_center_y_mm']-depth/2+spec['corner_reach_mm']
    return [cuboid([[sign*parameters['locator_center_x_mm']-width/2,
                    sign*parameters['locator_center_x_mm']+width/2],
                   [spec['back_edge_y_mm']-.02,end_y],
                   [parameters['locator_root_z_mm']-spec.get('floor_trim_mm',0),2]]) for sign in (-1,1)]


def p11_upper_wall_tools(parameters):
    spec=parameters.get('p11_upper_wall_relief')
    if not spec:
        return []
    result=[]
    y0,y1=spec['y_bounds_mm'];z0,z1=spec['z_bounds_mm']
    for sign in (-1,1):
        x0,x1=sorted([sign*spec['inner_x_mm'],sign*spec['outer_x_mm']])
        cutter=(cq.Workplane('XZ',origin=(0,y1,0))
                .polyline([(x0,z0),(x1,z0),(x1,z1),(x0,z1)])
                .close().extrude(y1-y0).val())
        # Round the corner end only; rounding the inner lower corner would
        # leave an unsupported scrap above the existing access window.
        outer_edges=[edge for edge in cutter.Edges()
                     if abs(edge.Center().x-sign*spec['outer_x_mm'])<1e-6
                     and abs(edge.Length()-(y1-y0))<1e-6]
        assert len(outer_edges)==2
        if spec['end_radius_mm']>0:
            cutter=cutter.fillet(spec['end_radius_mm'],outer_edges)
        result.append(mesh_solid(cutter,parameters['mesh_tolerance_mm']))
    return result


def tools(parameters):
    spec=parameters['locator_release_profile']
    top=spec['top_z_mm'];bottom=top-spec['drop_mm']
    radius=spec['lower_corner_radius_mm'];angle=np.deg2rad(spec['draft_from_vertical_deg'])
    # Offset the sharp intersections so the flat span after filleting is 18 mm.
    half=spec['flat_span_mm']/2+radius*np.tan((np.pi/2-angle)/2)
    high=half+(2-bottom)*np.tan(angle)
    y0,y1=spec['y_bounds_mm']
    channel=(cq.Workplane('XZ',origin=(0,y1+.001,0))
             .polyline([(-half,bottom),(half,bottom),(high,2),(-high,2)])
             .close().extrude(y1-y0+.002).edges('|Y').fillet(radius).val())
    restore_bounds=spec['restore_old_recess_bounds_mm']
    restore=[list(bounds) for bounds in restore_bounds]
    restore[0]=[restore[0][0]-.01,restore[0][1]+.01]
    restore[1]=[restore[1][0]-.01,y1]
    restore[2]=[restore[2][0]-.01,top]
    if spec['style'] == 'thin_contoured_release_web':
        thickness=spec['backing_thickness_mm']
        # Parallel offset of the sloping wall gives constant normal thickness.
        outer_half=half+thickness*(1/np.cos(angle)-np.tan(angle))
        outer_top=outer_half+spec['drop_mm']*np.tan(angle)
        extent=spec['solid_half_width_mm']
        backing=(cq.Workplane('XZ',origin=(0,y1,0))
                 .polyline([(-extent,top),(extent,top),(extent,top-thickness),
                            (outer_top,top-thickness),(outer_half,bottom-thickness),
                            (-outer_half,bottom-thickness),(-outer_top,top-thickness),
                            (-extent,top-thickness)])
                 .close().extrude(y1-y0).val())
        lower_edges=[edge for edge in backing.Edges()
                     if abs(edge.Center().z-(bottom-thickness))<1e-6
                     and abs(edge.Length()-(y1-y0))<1e-6]
        assert len(lower_edges)==2
        backing=mesh_solid(backing.fillet(radius+thickness,lower_edges),parameters['mesh_tolerance_mm'])
    else:
        backing=cuboid([[-spec['solid_half_width_mm'],spec['solid_half_width_mm']],
                        [y0,y1],[bottom-spec['backing_thickness_mm'],top]])
    return cuboid(restore),backing,mesh_solid(channel,parameters['mesh_tolerance_mm'])


def apply(shape,parameters):
    original=shape
    restore,backing,channel=tools(parameters)
    if parameters['locator_release_profile'].get('replace_bounds_mm'):
        shape-=cuboid(parameters['locator_release_profile']['replace_bounds_mm'])
    shape=(shape+restore+backing)-channel
    # New solid backing must not fill the existing relieved nub seats.
    width,depth=parameters['locator_recess_size_mm']
    for sign in (-1,1):
        x=sign*parameters['locator_center_x_mm'];y=parameters['locator_center_y_mm']
        z=parameters['locator_root_z_mm']
        seat=(cq.Workplane('XY').box(width,depth,2-z)
              .translate((x,y,(z+2)/2)).edges('|Z').fillet(1).val())
        shape -= mesh_solid(seat,parameters['mesh_tolerance_mm'])-original
    for wall in rear_wall_tools(parameters):
        shape-=wall
    for wall in p11_upper_wall_tools(parameters):
        shape-=wall
    assert shape.status()==mf.Error.NoError
    return shape
