"""Replace the tested PLA package's model with v18; retain its known settings."""
import json
import subprocess
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import trimesh
from build_design import ROOT, OUT

CORE = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
PRODUCTION = 'http://schemas.microsoft.com/3dmanufacturing/production/2015/06'
ET.register_namespace('', CORE)
ET.register_namespace('p', PRODUCTION)
ET.register_namespace('BambuStudio', 'http://schemas.bambulab.com/package/2021')


def run(slice_model=False):
    mesh = trimesh.load(OUT/'mount_v18.stl', force='mesh')
    assert mesh.is_volume and mesh.is_watertight
    centre = mesh.bounds.mean(axis=0)
    vertices = mesh.vertices-centre
    source = OUT/'prototype_pla_06_tuned.3mf'
    destination = OUT/'prototype_v18_pla_06.3mf'
    with zipfile.ZipFile(source) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    object_xml = ET.fromstring(entries['3D/Objects/object_1.model'])
    mesh_xml = object_xml.find(f'.//{{{CORE}}}mesh')
    for child in list(mesh_xml):
        mesh_xml.remove(child)
    vertex_xml = ET.SubElement(mesh_xml, f'{{{CORE}}}vertices')
    for x, y, z in vertices:
        ET.SubElement(vertex_xml, f'{{{CORE}}}vertex', x=f'{x:.9f}', y=f'{y:.9f}', z=f'{z:.9f}')
    triangle_xml = ET.SubElement(mesh_xml, f'{{{CORE}}}triangles')
    for a, b, c in mesh.faces:
        ET.SubElement(triangle_xml, f'{{{CORE}}}triangle', v1=str(a), v2=str(b), v3=str(c))
    entries['3D/Objects/object_1.model'] = ET.tostring(object_xml, encoding='utf-8', xml_declaration=True)
    main = ET.fromstring(entries['3D/3dmodel.model'])
    item = main.find(f'{{{CORE}}}build/{{{CORE}}}item')
    item.set('transform', f'1 0 0 0 1 0 0 0 1 128 128 {np.ptp(mesh.bounds[:, 2])/2:.9f}')
    for metadata in main.findall(f'{{{CORE}}}metadata'):
        if metadata.get('name') in ('Title', 'ProfileTitle', 'Description'):
            metadata.text = 'Starlink Mini battery mount v18 - PLA 0.6 mm prototype'
    entries['3D/3dmodel.model'] = ET.tostring(main, encoding='utf-8', xml_declaration=True)
    settings = ET.fromstring(entries['Metadata/model_settings.config'])
    for element in settings.iter():
        if element.get('key') in ('name', 'source_file'):
            element.set('value', 'mount_v18.stl')
        if element.get('key', '').startswith('source_offset_'):
            axis = 'xyz'.index(element.get('key')[-1])
            element.set('value', str(centre[axis]))
        if 'face_count' in element.attrib:
            element.set('face_count', str(len(mesh.faces)))
        if element.tag == 'assemble_item':
            element.set('transform', item.get('transform'))
    entries['Metadata/model_settings.config'] = ET.tostring(settings, encoding='utf-8', xml_declaration=True)
    # Remove stale model thumbnails and prior slice metadata. Bambu creates
    # new previews and toolpaths when this new model is sliced.
    entries = {name: data for name, data in entries.items()
               if not (name.startswith('Metadata/') and
                       (name.endswith('.png') or name == 'Metadata/slice_info.config'))}
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(destination) as archive:
        assert archive.read('Metadata/project_settings.config') == entries['Metadata/project_settings.config']
        model = ET.fromstring(archive.read('3D/Objects/object_1.model'))
        actual = np.array([[float(v.get(k)) for k in 'xyz']
                           for v in model.findall(f'.//{{{CORE}}}vertex')])
        assert np.max(np.abs(actual+centre-mesh.vertices)) < 1e-6
        assert len(model.findall(f'.//{{{CORE}}}triangle')) == len(mesh.faces)
    print(json.dumps({'archive': str(destination), 'triangles': len(mesh.faces),
                      'profile': 'Existing tuned PLA, P1S 0.6 mm nozzle, 0.24 mm layers.',
                      'model_unchanged_by_packaging': True}), flush=True)
    if slice_model:
        output = OUT/'v18_pla_slice'
        output.mkdir(exist_ok=True)
        command = ['C:/Program Files/Bambu Studio/bambu-studio.exe', '--debug', '2',
                   '--slice', '1', '--export-3mf', 'sliced_v18.3mf',
                   '--outputdir', str(output), str(destination)]
        completed = subprocess.run(command, capture_output=True)
        (output/'slice.log').write_bytes(completed.stdout+completed.stderr)
        print('Slice exit code', completed.returncode, flush=True)
        assert completed.returncode == 0, completed.stderr.decode(errors='replace')
        # Bring the slicer's fresh thumbnails back into the unsliced package.
        # Leave G-code and slice metadata in the verification archive only.
        with zipfile.ZipFile(output/'sliced_v18.3mf') as sliced:
            thumbnails = {name: sliced.read(name) for name in sliced.namelist()
                          if name.startswith('Metadata/') and name.endswith('.png')}
        with zipfile.ZipFile(destination) as package:
            refreshed = {name: package.read(name) for name in package.namelist()
                         if name not in thumbnails}
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as package:
            for name, data in {**refreshed, **thumbnails}.items():
                package.writestr(name, data)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--slice', action='store_true')
    run(parser.parse_args().slice)
