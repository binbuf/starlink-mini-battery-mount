"""Exclude numerical zero-volume shells and export an unchanged faceted solid."""
import json
from pathlib import Path
import numpy as np
import trimesh
import cadquery as cq
from reference_solid import ROOT, to_solid

OUT = ROOT / "cad/out"


def run(revision='v1'):
    stem='mount_'+revision
    raw = trimesh.load(OUT / (stem+".stl"), force="mesh")
    parts = raw.split(only_watertight=False)
    # Float32 boolean/STL arithmetic leaves shells below 1e-6 mm3. Exclude
    # those explicitly; retain the enclosed 2.225 mm3 reference cavity.
    retained = [p for p in parts if p.is_watertight and abs(p.volume)>=1e-6]
    zero = [p for p in parts if p not in retained]
    assert all((p.is_watertight and abs(p.volume)<1e-6) or
               (len(p.faces)<=2 and p.area<.001) for p in zero), 'Substantial boundary fragment'
    primary=max(retained,key=lambda p:p.volume)
    near_surface_slivers=[]
    for part in list(retained):
        if part is primary or part.volume<=0:
            continue
        assert part.volume<.01, 'Disconnected material body'
        _,distance,_=trimesh.proximity.closest_point(primary,np.vstack([part.vertices,part.triangles_center]))
        assert distance.max()<.005, 'Detached fragment is away from the main surface'
        retained.remove(part)
        near_surface_slivers.append({'volume_mm3':float(part.volume),'faces':len(part.faces),
                                     'max_distance_to_primary_mm':float(distance.max())})
    mesh = trimesh.util.concatenate(retained)
    prepared = mesh.copy()
    simplification_tolerance=0.0
    if revision in ('v3','v4','v5','v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        # Mesh booleans can leave extremely narrow, nearly collinear facets at
        # the reference rim seam. Use Manifold's topology-preserving simplify
        # with a 0.00002 mm surface bound, then independently check deviation.
        import manifold3d as md
        simplification_tolerance=.00002
        manifold=md.Manifold(md.Mesh64(np.asarray(prepared.vertices,dtype=np.float64),
                                     np.asarray(prepared.faces,dtype=np.uint64)))
        result=manifold.simplify(simplification_tolerance).to_mesh64()
        prepared=trimesh.Trimesh(vertices=result.vert_properties[:,:3],faces=result.tri_verts,process=True)
        assert prepared.is_volume and prepared.is_watertight
    collapsed=[]
    # STL serialization can turn microscopic triangles into straight lines or
    # nearly collinear wires that OpenCascade cannot orient as planar faces.
    # Collapse only their shortest edges, bounded to 0.00005 mm. Verify
    # connectivity after each collapse and surface deviation afterwards.
    for iteration in range(100):
        degenerate=np.flatnonzero(prepared.area_faces<=1e-9)
        if not len(degenerate):
            break
        ids=prepared.faces[degenerate[0]]
        pairs=[(ids[i],ids[(i+1)%3]) for i in range(3)]
        a,b=min(pairs,key=lambda p:np.linalg.norm(prepared.vertices[p[0]]-prepared.vertices[p[1]]))
        length=float(np.linalg.norm(prepared.vertices[a]-prepared.vertices[b]))
        assert length<.00005, 'Degenerate face requires excessive movement'
        faces=prepared.faces.copy()
        faces[faces==b]=a
        keep=(faces[:,0]!=faces[:,1])&(faces[:,1]!=faces[:,2])&(faces[:,0]!=faces[:,2])
        candidate=trimesh.Trimesh(prepared.vertices.copy(),faces[keep],process=False)
        candidate.remove_unreferenced_vertices()
        assert candidate.is_watertight and candidate.is_winding_consistent
        prepared=candidate
        collapsed.append(length)
    assert not np.any(prepared.area_faces<=1e-9)
    assert prepared.is_volume
    # Check deviations against the actual surfaces, not nearest vertices.
    max_distance = 0.0
    for source, target in ((prepared, raw), (raw, prepared)):
        points = np.vstack((source.vertices, source.triangles_center[::7]))
        for start in range(0, len(points), 400):
            _, distance, _ = trimesh.proximity.closest_point(target, points[start:start+400])
            max_distance = max(max_distance, float(distance.max()))
    assert max_distance < 0.005, f"CAD preparation moved surfaces {max_distance} mm"
    print("CAD prep triangles", len(prepared.faces), "maximum checked deviation", max_distance, flush=True)
    from faceted_solid import convert
    solid = convert(prepared)
    assert solid.isValid() and len(solid.Solids()) == 1
    cq.exporters.export(solid, str(OUT / (stem+".step")))
    solid.exportBrep(str(OUT / (stem+".brep")))
    # Deliver the same prepared geometry to printing and Fusion.
    mesh.export(OUT / (stem+"_before_cad_prep.stl"))
    prepared.export(OUT / (stem+".stl"))
    reloaded=trimesh.load(OUT/(stem+'.stl'),force='mesh')
    assert reloaded.is_volume and reloaded.is_watertight
    data = json.loads((OUT / (stem+"_validation.json")).read_text())
    data.update({"step_solid_valid": solid.isValid(), "step_solid_count": len(solid.Solids()),
                 "step_volume_cm3": solid.Volume()/1000, "step_faces": len(solid.Faces()),
                 "cad_preparation_tolerance_mm": .00005 if collapsed else 0.0,
                 "cad_preparation_max_checked_deviation_mm": max_distance,
                 "manifold_simplification_tolerance_mm":simplification_tolerance,
                 "zero_volume_stl_components_excluded": len(zero),
                 "zero_volume_stl_triangles_excluded": sum(len(p.faces) for p in zero),
                 "numerical_fragment_max_area_mm2":max((p.area for p in zero),default=0),
                 "prepared_volume_change_mm3":prepared.volume-raw.volume,
                 "near_surface_slivers_excluded":near_surface_slivers,
                 "collapsed_degenerate_edges":len(collapsed),
                 "collapsed_face_area_threshold_mm2":1e-9,
                 "max_collapsed_edge_mm":max(collapsed,default=0),
                 "stl_reloaded_watertight":reloaded.is_watertight,
                 "cad_prepared_mesh_volume_cm3": prepared.volume/1000})
    # Repeat overlap checks on the deliverable after CAD preparation.
    for name, target in (("battery", trimesh.load(OUT / "battery_nominal.stl")),
                         ("dish", max(trimesh.load(ROOT / "docs/official/Starlink_Mini_Dish.stl").split(
                             only_watertight=False), key=lambda p: len(p.faces)))):
        common = trimesh.boolean.intersection([prepared, target], engine="manifold")
        volume = abs(common.volume) if len(common.faces) else 0.0
        assert volume < 0.05
        data["cad_prepared_"+name+"_overlap_mm3"] = volume
    (OUT / (stem+"_validation.json")).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("STEP export finished", flush=True)


if __name__ == "__main__":
    run()
