"""Measure delivered fin planes and the complete requested battery envelope."""
import numpy as np
import manifold3d as md
import trimesh
from build_design import P,box
from generate_mount import mesh_shape
from reference_solid import clipped_reference


def solid(mesh):
    return md.Manifold(md.Mesh64(np.asarray(mesh.vertices,dtype=np.float64),
                                np.asarray(mesh.faces,dtype=np.uint64)))


def inspect(mount):
    reference=clipped_reference(P['port_cut_y_mm'])
    centres=mount.triangles_center
    results=[]
    for sign in (-1,1):
        outer=max((f for f in reference.facets
                   if sign*reference.face_normals[f[0],0]>.4
                   and reference.face_normals[f[0],2]<-.9),
                  key=lambda f:reference.area_faces[f].sum())
        normal=reference.face_normals[outer[0]]
        point=reference.triangles[outer[0],0]
        # The broad original inside faces, including the catch backing, are
        # parallel to the outside fin. Their physical offset must match.
        original_centres=reference.triangles_center
        selected=(reference.face_normals@(-normal)>.99999)&(sign*original_centres[:,0]>78)
        selected&=(sign*original_centres[:,0]<96)&(original_centres[:,1]>-135)
        selected&=(original_centres[:,1]<-70)&(original_centres[:,2]<-9.9)
        # Use the largest source face for nominal thickness. Smaller parallel
        # source faces belong to the original clip and relief features.
        source_face=max((f for f in reference.facets if selected[f].any()),
                        key=lambda f:reference.area_faces[f].sum())
        original_offsets=-(original_centres[source_face]-point)@normal
        assert len(original_offsets) and np.max(np.abs(original_offsets-4))<.002
        selected=(mount.face_normals@(-normal)>.99999)&(sign*centres[:,0]>78)
        selected&=(sign*centres[:,0]<96)&(centres[:,1]>-135)
        selected&=(centres[:,1]<-70)&(centres[:,2]<-9.9)
        offsets=-(centres[selected]-point)@normal
        assert len(offsets) and np.max(np.abs(offsets-4))<.002,'Stepped inner fin faces remain'
        results.append({'side':sign,'inspected_inside_area_mm2':float(mount.area_faces[selected].sum()),
                        'source_thickness_range_mm':[float(original_offsets.min()),float(original_offsets.max())],
                        'delivered_thickness_range_mm':[float(offsets.min()),float(offsets.max())],
                        'maximum_plane_error_mm':float(np.max(np.abs(offsets-4)))})
    length,width=P['bay_xy_mm'];xc,yc=P['battery_center_xy_mm']
    top=P['contact_z_mm'];floor=top-P['battery_mm'][2]
    envelope=mesh_shape(box(xc-length/2,xc+length/2,yc-width/2,yc+width/2,floor,top))
    overlap=float((solid(mount)^solid(envelope)).volume())
    outside=abs(overlap)
    if P.get('track_backing_bounds_positive_mm'):
        from track_backing import bounding_meshes
        allowed=solid(bounding_meshes()[0])+solid(bounding_meshes()[1])
        outside=abs(float(((solid(mount)^solid(envelope))-allowed).volume()))
    assert outside<.01,'Battery clearance envelope is obstructed outside approved corner backing'
    return {'delivered_smooth_inner_fins':results,
            'delivered_full_battery_envelope':{'size_mm':[length,width,top-floor],
                'overlap_mm3':abs(overlap),'overlap_outside_approved_backing_mm3':outside,
                'boolean_precision':'float64'}}
