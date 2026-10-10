"""Publish the verified local revision to the project export directory."""
import json
import shutil
from pathlib import Path
from build_design import ROOT, OUT


def run():
    audit = json.loads((OUT/'mount_v18_validation.json').read_text())
    fusion = json.loads((ROOT/'cad/review/fusion_v18_import.json').read_text())
    assert audit['step_solid_valid'] and audit['stl_reloaded_watertight']
    assert audit['delivered_exact_step_continuous_intersection']['overlap_mm3'] == 0
    assert audit['delivered_prototype_feedback']['patterns']['other_pattern_holes'] == 0
    assert fusion['closed'] and fusion['oriented'] and fusion['surface_map_visible']
    shutil.copy2(OUT/'mount_v18_validation.json', ROOT/'docs/validation-v18.json')
    export = ROOT/'export'
    old = export/'starlink-mini-battery-mount.f3d'
    backup = export/'starlink-mini-battery-mount.before-v18.f3d'
    if old.exists() and not backup.exists():
        shutil.copy2(old, backup)
    targets = {
        'mount_v18_assembly.f3d': 'starlink-mini-battery-mount.f3d',
        'mount_v18_surface_map.f3d': 'starlink-mini-battery-mount_v18_surface_map.f3d',
        'mount_v18_print.stl': 'starlink-mini-battery-mount_v18_print.stl',
        'prototype_v18_pla_06.3mf': 'prototype_v18_pla_06.3mf',
        'mount_v18_mating_coupon_print.stl': 'mount_v18_mating_coupon_print.stl'}
    for source, destination in targets.items():
        shutil.copy2(OUT/source, export/destination)
    manifest = json.loads((OUT/'surface_reference/v18/manifest.json').read_text())
    fins = json.loads((OUT/'surface_reference/v18/refined_fins.json').read_text())
    lines = ['# Enclosure surface map v18', '',
             'V18 is loaded in the current Fusion tab. Surface-map meshes are review',
             'regions; use the closed print mesh or assembly archive for fabrication.', '',
             'In Top view: -X left, +X right, +Y power-port end, -Y outer end.', '',
             'All pattern holes are in P01/P02. P03/P04 fins and the other walls are',
             'solid apart from functional access; P19 includes the tapered OEM-sized',
             'nubs, joined end gussets with sloped sides, recessed seats and a',
             'central finger/tool purchase at the P11 edge.', '',
             '| ID | Region |', '| --- | --- |']
    lines += [f"| {r['id']} | {r['name']} |" for r in manifest['regions']]
    for parent in fins['parents']:
        lines += ['', f"## {parent['id']} fin details", '', '| ID | Surface |', '| --- | --- |']
        lines += [f"| {child['id']} | {child['name']} |" for child in parent['children']]
    lines += ['', 'Saved review: `cad/out/mount_v18_surface_map.f3d`.',
              'Design and validation: `design-v18.md` and `validation-v18.json`.', '']
    (ROOT/'docs/surface-map-v18.md').write_text('\n'.join(lines))
    print(json.dumps({'files': [str(export/p) for p in targets.values()],
                      'main_export_backup': str(backup), 'validation': 'docs/validation-v18.json'}, indent=2))


if __name__ == '__main__':
    run()
