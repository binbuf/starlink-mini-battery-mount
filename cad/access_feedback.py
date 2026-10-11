"""Final local access/removal cuts for the current enclosure, in millimetres.

Can also regenerate this edit from a preserved closed STL, independently of
the unavailable original example-mount meshes:
python cad/access_feedback.py --input PATH --output PATH
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import cadquery as cq
import manifold3d as mf
import numpy as np
import trimesh
from internal_rim_cleanup import as_solid


def cuboid(bounds):
    lo, hi = np.asarray(bounds, dtype=float).T
    return mf.Manifold.cube(hi-lo).translate(lo)


def cutters(parameters):
    result = {'display_access_bounds_mm': cuboid(parameters['display_access_bounds_mm']),
              'power_end_access_bounds_mm': cuboid(parameters['power_end_access_bounds_mm'])}
    y0, y1 = parameters['battery_port_window_y_mm']
    z0, z1 = parameters['battery_port_window_z_mm']
    result['usb_access'] = cuboid([
        [parameters.get('usb_cut_outer_x_mm', -115), -67], [y0, y1], [z0, z1]])
    if parameters.get('locator_release_recess_bounds_mm'):
        (x0,x1),(y0,y1),(z0,z1) = parameters['locator_release_recess_bounds_mm']
        recess = (cq.Workplane('XY').box(x1-x0,y1-y0,z1-z0)
                  .translate(((x0+x1)/2,(y0+y1)/2,(z0+z1)/2))
                  .edges('|Z').fillet(3).edges('<Z').fillet(.8).val())
        vertices, faces = recess.tessellate(parameters['mesh_tolerance_mm'], .07)
        recess_mesh=trimesh.Trimesh([v.toTuple() for v in vertices],faces,process=True)
        assert recess_mesh.is_volume
        result['release_recess'] = as_solid(recess_mesh)
    top = parameters['locator_root_z_mm'] + parameters['locator_height_mm']
    for sign in (-1,1):
        x = sign*parameters['locator_center_x_mm']
        y = parameters['locator_center_y_mm']
        result[f'nub_cap_{sign}'] = cuboid([[x-5,x+5],[y-3,y+3],[top,2]])
    return result


def clean_numeric_sheets(result):
    """Drop only isolated zero-area sheets; never fill holes or repair geometry."""
    components = result.split(only_watertight=False,repair=False)
    positive = [part for part in components if part.volume > 1e-7]
    scraps = [part for part in components if part.volume <= 1e-7]
    assert len(positive) == 1, [(len(part.faces),part.volume,part.bounds.tolist()) for part in components]
    assert all(abs(part.volume)<1e-8 and part.area<1e-8 and len(part.faces)<=2 for part in scraps), [(len(part.faces),part.volume,part.area) for part in scraps]
    result = positive[0]
    assert result.is_volume and result.is_watertight and len(result.split()) == 1
    return result


def apply(mesh, parameters, tool_shapes=None):
    shape = as_solid(mesh)
    for cutter in (cutters(parameters) if tool_shapes is None else tool_shapes).values():
        shape -= cutter
    if parameters.get('locator_release_profile'):
        from locator_release_profile import apply as apply_release_profile
        shape = apply_release_profile(shape,parameters)
    assert shape.status() == mf.Error.NoError
    raw = shape.to_mesh64()
    result=clean_numeric_sheets(trimesh.Trimesh(raw.vert_properties[:,:3],raw.tri_verts,process=False))
    # Weld serialized vertices and discard only zero-area numeric sheets.
    result.merge_vertices()
    result=clean_numeric_sheets(result)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--parameters',type=Path,default=Path(__file__).with_name('design_parameters.json'))
    args=parser.parse_args()
    parameters=json.loads(args.parameters.read_text())
    result=apply(trimesh.load(args.input,force='mesh'),parameters)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result.export(args.output,file_type='stl_ascii')
    # A nonempty STL solid name prevents Fusion's spurious mesh warning.
    data=args.output.read_bytes()
    if data.startswith(b'solid \n'):
        args.output.write_bytes(b'solid enclosure\n'+data[7:])
    reloaded=clean_numeric_sheets(trimesh.load(args.output,force='mesh'))
    reloaded.export(args.output,file_type='stl_ascii')
    data=args.output.read_bytes()
    if data.startswith(b'solid \n'):
        args.output.write_bytes(b'solid enclosure\n'+data[7:])
    reloaded=trimesh.load(args.output,force='mesh')
    assert reloaded.is_volume and reloaded.is_watertight and len(reloaded.split())==1
    print(json.dumps({'triangles':len(reloaded.faces),'volume_mm3':reloaded.volume}))
