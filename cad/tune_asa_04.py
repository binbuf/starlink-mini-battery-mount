"""Convert the extracted v18 project to ELEGOO ASA / P1S 0.4, then verify a slice."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
import xml.etree.ElementTree as ET

ET.register_namespace('', 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02')
ET.register_namespace('p', 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06')
ET.register_namespace('BambuStudio', 'http://schemas.bambulab.com/package/2021')

ROOT = Path(__file__).resolve().parents[1]
EXTRACTED = ROOT/'export/prototype'
CONFIG = EXTRACTED/'Metadata/project_settings.config'
DESTINATION = ROOT/'export/mount_v18_elegoo_asa_04.3mf'
REVIEW = ROOT/'cad/review/asa_04'


def system_profile(name, category):
    folder = Path('C:/Program Files/Bambu Studio/resources/profiles/BBL')/category
    matches = list(folder.rglob(name+'.json'))
    assert len(matches) == 1, f'Installed profile not uniquely found: {name}'
    value = json.loads(matches[0].read_text(encoding='utf-8'))
    result = system_profile(value['inherits'], category) if value.get('inherits') else {}
    result.update(value)
    return result


def run(slice_model=False):
    REVIEW.mkdir(parents=True, exist_ok=True)
    backup = CONFIG.with_name('project_settings.before_asa_04.config')
    if not backup.exists():
        shutil.copy2(CONFIG, backup)
    original = json.loads(backup.read_text())
    settings = original.copy()
    names = ('Bambu Lab P1S 0.4 nozzle', '0.20mm Standard @BBL X1C', 'Generic ASA')
    baselines = {name: system_profile(name, category)
                 for name, category in zip(names, ('machine', 'process', 'filament'))}
    (REVIEW/'system_baselines.json').write_text(json.dumps(baselines, indent=2))
    # Resolve all categories from the installed release, preserving project
    # bookkeeping and avoiding stale PLA thermal values or 0.6 mm machine code.
    for name in names:
        settings.update({key: value for key, value in baselines[name].items()
                         if key in original})
    process = {
        'layer_height': '0.2', 'initial_layer_print_height': '0.2',
        'line_width': '0.45', 'initial_layer_line_width': '0.5',
        'outer_wall_line_width': '0.42', 'inner_wall_line_width': '0.45',
        'internal_solid_infill_line_width': '0.45', 'sparse_infill_line_width': '0.45',
        'top_surface_line_width': '0.42', 'support_line_width': '0.42',
        'skin_infill_line_width': '0.45', 'skeleton_infill_line_width': '0.45',
        'wall_loops': '5', 'wall_generator': 'arachne', 'precise_outer_wall': '1',
        'wall_sequence': 'inner wall/outer wall', 'top_one_wall_type': 'not apply',
        'top_shell_layers': '6', 'top_shell_thickness': '1.2',
        'bottom_shell_layers': '6', 'bottom_shell_thickness': '1.2',
        'top_surface_pattern': 'monotonicline', 'bottom_surface_pattern': 'monotonic',
        'sparse_infill_density': '25%', 'sparse_infill_pattern': 'gyroid',
        'infill_wall_overlap': '15%', 'infill_combination': '0',
        'initial_layer_speed': ['20', '20'], 'initial_layer_infill_speed': ['30', '30'],
        'outer_wall_speed': ['40', '40'], 'inner_wall_speed': ['80', '80'],
        'small_perimeter_speed': ['50%', '50%'], 'small_perimeter_threshold': ['6', '6'],
        'sparse_infill_speed': ['90', '90'], 'internal_solid_infill_speed': ['80', '80'],
        'top_surface_speed': ['30', '30'], 'gap_infill_speed': ['35', '35'],
        'bridge_speed': ['25', '25'], 'bridge_flow': '1',
        'overhang_1_4_speed': ['0', '0'], 'overhang_2_4_speed': ['35', '35'],
        'overhang_3_4_speed': ['20', '20'], 'overhang_4_4_speed': ['12', '12'],
        'overhang_totally_speed': ['12', '12'], 'enable_overhang_speed': ['1', '1'],
        'default_acceleration': ['3000', '3000'], 'outer_wall_acceleration': ['1200', '1200'],
        'inner_wall_acceleration': ['2500', '2500'], 'top_surface_acceleration': ['1200', '1200'],
        'initial_layer_acceleration': ['500', '500'],
        'initial_layer_travel_acceleration': ['3000', '3000'],
        'travel_speed': ['350', '350'], 'travel_acceleration': ['5000', '5000'],
        'reduce_crossing_wall': '1', 'avoid_crossing_wall_includes_support': '1',
        'brim_type': 'outer_only', 'brim_width': '10', 'brim_object_gap': '0.1',
        'skirt_loops': '0', 'raft_layers': '0', 'enable_prime_tower': '0',
        'elefant_foot_compensation': '0.15', 'xy_contour_compensation': '0',
        'xy_hole_compensation': '0', 'seam_position': 'aligned', 'seam_slope_type': 'none',
        'enable_support': '1', 'support_type': 'tree(auto)', 'support_style': 'tree_organic',
        'support_threshold_angle': '30', 'support_on_build_plate_only': '0',
        'support_critical_regions_only': '0', 'support_remove_small_overhang': '1',
        'support_top_z_distance': '0.28', 'support_bottom_z_distance': '0.24',
        'support_object_xy_distance': '0.45', 'support_object_first_layer_gap': '0.2',
        'independent_support_layer_height': '1', 'support_base_pattern': 'default',
        'support_base_pattern_spacing': '3', 'support_interface_pattern': 'rectilinear',
        'support_interface_top_layers': '3', 'support_interface_bottom_layers': '2',
        'support_interface_spacing': '0.35', 'support_bottom_interface_spacing': '0.4',
        'support_interface_loop_pattern': '0', 'support_speed': ['50', '50'],
        'support_interface_speed': ['30', '30'], 'support_filament': '0',
        'support_interface_filament': '0', 'support_expansion': '0',
        'tree_support_branch_diameter': '2.4', 'tree_support_branch_distance': '5',
        'tree_support_branch_angle': '45', 'tree_support_wall_count': '2',
        'tree_support_branch_diameter_angle': '5', 'top_z_overrides_xy_distance': '0',
        'bridge_no_support': '0', 'fuzzy_skin': 'none',
    }
    filament = {
        'filament_type': ['ASA'], 'filament_vendor': ['ELEGOO'],
        'filament_colour': ['#101010'], 'filament_multi_colour': ['#101010'],
        'nozzle_temperature': ['260'], 'nozzle_temperature_initial_layer': ['260'],
        'nozzle_temperature_range_low': ['240'], 'nozzle_temperature_range_high': ['270'],
        'textured_plate_temp': ['100'], 'textured_plate_temp_initial_layer': ['100'],
        'hot_plate_temp': ['100'], 'hot_plate_temp_initial_layer': ['100'],
        'eng_plate_temp': ['100'], 'eng_plate_temp_initial_layer': ['100'],
        'filament_max_volumetric_speed': ['8'], 'filament_flow_ratio': ['0.95'],
        'additional_cooling_fan_speed': ['0'], 'fan_min_speed': ['10'], 'fan_max_speed': ['30'],
        'overhang_fan_speed': ['60'], 'overhang_fan_threshold': ['25%'],
        'overhang_threshold_participating_cooling': ['95%'],
        'close_fan_the_first_x_layers': ['3'], 'fan_cooling_layer_time': ['35'],
        'slow_down_layer_time': ['6'], 'slow_down_min_speed': ['10'],
        'slow_down_for_layer_cooling': ['1'], 'enable_overhang_bridge_fan': ['1'],
        'activate_air_filtration': ['0'], 'during_print_exhaust_fan_speed': ['0'],
        'complete_print_exhaust_fan_speed': ['70'], 'chamber_temperatures': ['0'],
        'filament_shrink': ['100%'], 'enable_pressure_advance': ['0'],
    }
    settings.update(process)
    settings.update(filament)
    settings.update({
        'printer_settings_id': names[0], 'printer_variant': '0.4', 'nozzle_diameter': ['0.4'],
        'default_print_profile': names[1], 'default_filament_profile': ['Generic ASA'],
        'print_settings_id': 'Starlink Mini ASA 0.20mm - P1S 0.4 nozzle',
        'filament_settings_id': ['ELEGOO ASA Deep Black - P1S 0.4 mount'],
        'filament_ids': ['GFB98'], 'print_compatible_printers': [names[0]],
        'inherits': [names[1], 'Generic ASA', names[0]],
        'process_notes': 'V18, outside floor down. 5 walls, 25% gyroid, ASA organic supports. Physical ASA mating coupon recommended before full print.',
        'filament_notes': 'ELEGOO ASA Deep Black, 1.75 mm. 260C nozzle / 100C Textured PEI. Generic ASA flow 0.95 is an uncalibrated baseline; calibrate spool flow and dynamic flow. Closed P1S, allow bed/chamber to warm before starting. No active chamber heater.',
        'from': 'project', 'name': 'project_settings',
    })
    settings['different_settings_to_system'] = [
        ';'.join(sorted(k for k in process if settings[k] != baselines[names[1]].get(k))),
        ';'.join(sorted(k for k in filament if settings[k] != baselines[names[2]].get(k))), '']
    CONFIG.write_text(json.dumps(settings, indent=4)+'\n')
    changed = {k: {'before': original.get(k), 'after': v} for k, v in settings.items()
               if original.get(k) != v}
    (REVIEW/'settings_changes.json').write_text(json.dumps(changed, indent=2))
    entries = {}
    for path in EXTRACTED.rglob('*'):
        if path.is_file() and path != backup:
            name = path.relative_to(EXTRACTED).as_posix()
            if name.endswith('.gcode') or name in ('Metadata/slice_info.config',):
                continue
            entries[name] = path.read_bytes()
    main = ET.fromstring(entries['3D/3dmodel.model'])
    for element in main:
        if element.get('name') in ('Title', 'ProfileTitle', 'Description'):
            element.text = 'Starlink Mini battery mount v18 - ELEGOO ASA P1S 0.4 mm'
    entries['3D/3dmodel.model'] = ET.tostring(main, encoding='utf-8', xml_declaration=True)
    def package():
        with zipfile.ZipFile(DESTINATION, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
    package()
    report = {'config': str(CONFIG), 'backup': str(backup), 'project': str(DESTINATION),
              'changed_settings': len(changed), 'source_profiles': list(names),
              'model_sha256': hashlib.sha256(entries['3D/Objects/object_1.model']).hexdigest()}
    if slice_model:
        sliced = REVIEW/'sliced_asa_04.3mf'
        command = ['C:/Program Files/Bambu Studio/bambu-studio.exe', '--debug', '2',
                   '--slice', '1', '--export-3mf', sliced.name, '--outputdir', str(REVIEW), str(DESTINATION)]
        completed = subprocess.run(command, capture_output=True)
        (REVIEW/'slice.log').write_bytes(completed.stdout+completed.stderr)
        report['slice_exit_code'] = completed.returncode
        assert completed.returncode == 0, completed.stderr.decode(errors='replace')
        with zipfile.ZipFile(sliced) as archive:
            effective = json.loads(archive.read('Metadata/project_settings.config'))
            for key in list(process)+list(filament)+['nozzle_diameter', 'printer_settings_id']:
                assert effective[key] == settings[key], f'Slicer changed {key}: {effective[key]}'
            for name in archive.namelist():
                if name.startswith('Metadata/') and name.endswith('.png'):
                    entries[name] = archive.read(name)
                    (EXTRACTED/name).write_bytes(entries[name])
            for name in ('Metadata/slice_info.config', 'Metadata/plate_1.json'):
                if name in archive.namelist():
                    (REVIEW/Path(name).name).write_bytes(archive.read(name))
            info_root = ET.fromstring(archive.read('Metadata/slice_info.config'))
            info = {element.get('key'): element.get('value')
                    for element in info_root.findall('.//plate/metadata')}
            report.update(estimated_seconds=int(info['prediction']),
                          filament_grams=float(info['weight']),
                          support_used=info['support_used'] == 'true',
                          outside_build_plate=info['outside'] != 'false',
                          slicer_warnings=[e.attrib for e in info_root.findall('.//warning')])
            assert report['support_used'] and not report['outside_build_plate']
            report['effective_settings_verified'] = True
        package()
    (REVIEW/'validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--slice', action='store_true')
    run(parser.parse_args().slice)
