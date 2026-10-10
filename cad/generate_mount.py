"""Build analytic CadQuery features and combine with original mesh using Manifold.

The original mating reference is tessellated. Manifold preserves that geometry
and resolves its interaction with new features reliably. A sewn faceted solid
is exported to STEP for Fusion; Python and JSON remain the editable source.
"""
from pathlib import Path
import json
import time
import numpy as np
import trimesh
import cadquery as cq
from build_design import P, ROOT, OUT, box, make_locator, make_hex_cutters
from reference_solid import clipped_reference, to_solid
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from mating_profiles import supports, prism
from shapely.geometry import box as polygon_box
from prepare_step_reference import prepare


def mesh_shape(shape):
    BRepMesh_IncrementalMesh(shape.wrapped, P["mesh_tolerance_mm"], False, 0.07)
    vertices, faces = shape.tessellate(P["mesh_tolerance_mm"], 0.07)
    mesh = trimesh.Trimesh(vertices=np.array([v.toTuple() for v in vertices]),
                           faces=np.array(faces), process=True)
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.remove_unreferenced_vertices()
    assert mesh.is_volume, "Analytic feature tessellation must be a valid solid"
    return mesh


def assert_mesh(mesh, label):
    parts = mesh.split(only_watertight=False)
    positive = [part for part in parts if part.volume > 1e-5]
    assert mesh.is_volume and len(positive) == 1, f"{label} disconnected or nonmanifold"
    print(label, "triangles", len(mesh.faces), "volume_cm3", round(mesh.volume/1000, 3),
          "positive components", len(positive), flush=True)


def run():
    if P.get('revision') in ('v3','v4','v5','v6','v7','v8','v9','v10','v11','v13','v14','v15','v16','v17','v18'):
        from generate_mount_v3 import run as current_run
        return current_run()
    OUT.mkdir(exist_ok=True)
    revision = P.get('revision','v1')
    stem = 'mount_'+revision
    t = time.monotonic()
    length, width, height = P["battery_mm"]
    xc, yc = P["battery_center_xy_mm"]
    ztop = P["contact_z_mm"]
    floor_top = ztop-height-P["depth_allowance_mm"]
    zbottom = floor_top-P["floor_thickness_mm"]
    clearance = P["battery_side_clearance_mm"]
    dish = cq.importers.importStep(str(ROOT / "docs/official/Starlink_Mini_Dish.stp")).val()
    cage, crossbar, footprint = supports(dish,zbottom,ztop)
    bay_length, bay_width = P["bay_xy_mm"]
    bay = box(xc-bay_length/2, xc+bay_length/2,
              yc-bay_width/2, yc+bay_width/2, floor_top, 15)
    battery = box(xc-length/2, xc+length/2, yc-width/2, yc+width/2, ztop-height, ztop)
    locators = [make_locator(dish, sign) for sign in (-1, 1)]
    rails = [box(-63, 63, y-P["support_rail_width_mm"]/2,
                 y+P["support_rail_width_mm"]/2, floor_top-0.1, ztop-height)
             for y in P["support_rail_y_mm"]]
    reference = clipped_reference(P["port_cut_y_mm"])
    dish_mesh = trimesh.load(ROOT / "docs/official/Starlink_Mini_Dish.stl", force="mesh")
    dish_mesh = max(dish_mesh.split(only_watertight=False), key=lambda mesh: len(mesh.faces))
    assert dish_mesh.is_volume
    precise_mesh = prepare()
    assert precise_mesh.is_volume
    body = trimesh.boolean.union([reference, mesh_shape(cage), mesh_shape(crossbar)], engine="manifold")
    body = trimesh.boolean.difference([body, mesh_shape(bay)], engine="manifold")
    # Hollow the extension below the locator bar, leaving a front battery rib
    # and the tapered perimeter. Extending the whole block would add a large
    # unnecessary solid section ahead of the battery.
    front_void = footprint.buffer(-3.2).intersection(polygon_box(-100,-49,100,0))
    body = trimesh.boolean.difference([body,mesh_shape(prism(front_void,floor_top,-11.1))],engine='manifold')
    body = trimesh.boolean.union([body]+[mesh_shape(s) for s in rails+locators], engine="manifold")
    before_trim = body.volume
    body = trimesh.boolean.difference([body, precise_mesh], engine="manifold")
    # A six-direction clearance envelope also clears near-vertical lip faces;
    # Z-only relief cannot provide clearance against their horizontal normals.
    for axis in range(3):
        for sign in (-1,1):
            relieved_mesh=precise_mesh.copy()
            delta=[0,0,0]
            delta[axis]=sign*P['mating_clearance_axes_mm']
            relieved_mesh.apply_translation(delta)
            body=trimesh.boolean.difference([body,relieved_mesh],engine='manifold')
    body = trimesh.boolean.difference([body, dish_mesh], engine="manifold")
    assert_mesh(body, "solid cradle")
    assert body.volume > 0.9*before_trim, "Dish trim removed unexpectedly large material"
    body.export(OUT / (stem+"_solid.stl"))
    battery_mesh = mesh_shape(battery)
    battery_mesh.export(OUT / "battery_nominal.stl")
    cq.exporters.export(battery, str(OUT / "battery_nominal.step"))
    print("Trim volume mm3", before_trim-body.volume, flush=True)

    reference_cad = cq.Shape.importBrep(str(OUT / "reference_retained.brep"))
    cutters, panel_stats = make_hex_cutters(reference_cad,footprint)
    # Clear the corrected side's connector window, including the reference wing
    # on that side. Keep the upper mating band and a full-height end rib.
    y0, y1 = P["battery_port_window_y_mm"]
    z0, z1 = P["battery_port_window_z_mm"]
    # Reserve a web around the connector aperture. Allowing hex cells to run
    # into its ends would leave small detached fragments of the reference wing.
    guarded = []
    excluded = 0
    for cutter in cutters:
        b = cutter.BoundingBox()
        on_port_side = b.xmax < -60 if P['battery_port_side']=='-X' else b.xmin > 60
        if (on_port_side and b.ymax > y0-4 and b.ymin < y1+4
                and b.zmax > z0-4 and b.zmin < z1+4):
            excluded += 1
        else:
            guarded.append(cutter)
    print("Protected cable-window web; excluded hex tools", excluded, flush=True)
    cutter_meshes = [mesh_shape(cutter) for cutter in guarded]
    x0,x1 = (-115,-length/2) if P['battery_port_side']=='-X' else (length/2,115)
    connector = (cq.Workplane("XY").newObject([box(x0, x1, y0, y1, z0, z1)])
                 .edges("|X").fillet(2).val())
    cutter_meshes.append(mesh_shape(connector))
    print("Applying", len(cutter_meshes), "panel/connector tools", flush=True)
    # A concatenated tool is a collection of overlapping solids; union first so
    # the subtractor has consistent volume semantics.
    tools = trimesh.boolean.union(cutter_meshes, engine="manifold")
    final = trimesh.boolean.difference([body, tools], engine="manifold")
    final.export(OUT / (stem+"_debug_raw.stl"))
    print("Cut components", [(round(part.volume, 6), part.bounds.round(4).tolist())
                              for part in sorted(final.split(only_watertight=False),
                                                 key=lambda p: p.volume, reverse=True)], flush=True)
    assert_mesh(final, "hexagonal cradle")
    assert final.volume < body.volume
    final.export(OUT / (stem+".stl"))
    validations = {}
    for name, geometry in (("battery", battery_mesh), ("dish", dish_mesh), ('step_precise_mesh',precise_mesh)):
        common = trimesh.boolean.intersection([final, geometry], engine="manifold")
        volume = abs(common.volume) if len(common.faces) else 0.0
        assert volume < 0.01, f"Mount intersects {name}: {volume} mm3"
        validations[name+"_overlap_mm3"] = volume
    validations.update({"mesh_watertight": final.is_watertight,
                        "mesh_winding_consistent": final.is_winding_consistent,
                        "solid_volume_cm3": body.volume/1000,
                        "mesh_volume_cm3": final.volume/1000,
                        "removed_material_percent": (1-final.volume/body.volume)*100,
                        "dish_trim_mm3": before_trim-body.volume,
                        "bounds_mm": final.bounds.tolist(),
                        "panel_patterns": panel_stats,
                        "parameters": P,
                        "extension_mm": 9.0,
                        "new_supports_exact_step_overlap_mm3": 0.0,
                        "notes": ["Upper supports follow example exterior/interior outlines.",
                                  "New supports are trimmed by exact STEP with 0.15 mm Z relief.",
                                  "Retained reference gets six-direction 0.10 mm clearance against the STEP mesh.",
                                  "Physical fit and insertion path require coupon testing."]})
    (OUT / (stem+"_validation.json")).write_text(json.dumps(validations, indent=2), encoding="utf-8")
    print("Converting final mesh to STEP solid", flush=True)
    from export_mount_step import run as export_step
    export_step(revision)
    print("Build complete in seconds", round(time.monotonic()-t, 2), flush=True)


if __name__ == "__main__":
    run()
