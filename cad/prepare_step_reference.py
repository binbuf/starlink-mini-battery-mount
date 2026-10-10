"""Cache an absolute-deflection STEP mesh for the independent whole-mount check."""
import hashlib
import json
import cadquery as cq
import trimesh
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from reference_solid import ROOT


def prepare():
    step=ROOT/'docs/official/Starlink_Mini_Dish.stp'
    cache=ROOT/'cad/review/dish_step_precise_primary.stl'
    cache.parent.mkdir(parents=True,exist_ok=True)
    audit=cache.with_suffix('.json')
    digest=hashlib.sha256(step.read_bytes()).hexdigest()
    if cache.exists() and audit.exists() and json.loads(audit.read_text())['source_sha256']==digest:
        return trimesh.load(cache,force='mesh')
    dish=cq.importers.importStep(str(step)).val()
    BRepMesh_IncrementalMesh(dish.wrapped,.01,False,.08)
    vertices,faces=dish.tessellate(.011,.08)
    mesh=trimesh.Trimesh([p.toTuple() for p in vertices],faces)
    components=sorted(mesh.split(only_watertight=False),key=lambda p:len(p.faces),reverse=True)
    assert components[0].is_volume
    assert all(abs(p.volume)<1e-6 for p in components[1:])
    primary=components[0]
    primary.export(cache)
    audit.write_text(json.dumps({'source_sha256':digest,'absolute_deflection_mm':.01,
                                'angular_tolerance_radians':.08,'triangles':len(primary.faces),
                                'zero_volume_triangles_excluded':sum(len(p.faces) for p in components[1:])},indent=2))
    return primary


if __name__=='__main__':
    m=prepare()
    print('STEP reference',len(m.faces),'triangles; volume',m.volume)
