# starlink-mini-battery-mount

A premium 3D printed stand mount for your Starlink Mini that cradles a USB-C power bank.

## Features

- Hexagon venting across the visible panels to keep the power bank cool
- Fits snuggly into OEM locators
- Purpose-built bay sized for premium power bank (see below)
- Access windows for the power port, display and USB-C connections.
- Tuned for ASA on a 0.4 mm nozzle, with a PLA prototype variant for fit checks.
- The mount is modeled in [CadQuery](https://cadquery.io/) and mates directly to the official Starlink Mini shell geometry, so the locator nubs, rim profile and clearances line up with the real hardware

## Repository layout

| Path | Contents |
| --- | --- |
| `cad/` | Parametric source, validators and download scripts. |
| `cad/design_parameters.json` | All tunable dimensions for the current revision. |
| `cad/out/` | Generated meshes, STEP files and validation reports (git-ignored). |
| `docs/official/` | Official Starlink Mini dish reference (STL + STEP). |
| `export/` | Published, ready-to-slice outputs (`.stl`, `.3mf`, `.f3d`). |

## Equipment

### Starlink Mini

The dish the mount is designed to carry.

### USB cables

Search for "starlink mini usb c to barrel jack 3ft" or check out the links below:

<img src="docs/images/usb-cable.png" alt="USB-C to Starlink Mini barrel jack cable" width="150">

- https://starlink.com/shop/products/us-usbc-cable-mini
- https://www.amazon.com/dp/B0H491F83B
- https://www.amazon.com/dp/B0F62JD1Z4
- https://www.amazon.com/NEDUL-Starlink-Waterproof-Compatible-Protocol/dp/B0DFH5DSPL

### Power Bank

This 3D model is made specifically for this power bank. It's sized perfectly to
fit behind the Mini and provide ample power to the unit.

[UGREEN Nexode 100W 20000mAh Power Bank](https://www.amazon.com/dp/B0C3GTMX5M)

<img src="docs/images/powerbank.png" alt="UGREEN Nexode 100W 20000mAh Power Bank" width="100">

- Model name: PB720
- Model number: 25188
- Size: 139 x 80.8 x 26.7 mm

## Printing

Recommended settings for the production part (see `cad/design_parameters.json`):

| Setting | Value |
| --- | --- |
| Material | ASA |
| Nozzle | 0.4 mm |
| Layer height | 0.2 mm |
| Line width | 0.45 mm |
| Wall loops | 4 |

Ready-to-print files live in `export/`. If you're developing on the model then I recommend printing the PLA prototype first and test the fit before committing to the ASA part.

## Regenerating the model

The source is Python. From the `cad/` directory:

```sh
python -m venv .venv
.venv/Scripts/activate        # Windows (use source .venv/bin/activate on Unix)
pip install -r requirements.txt
python generate_mount_v18.py  # build revision v18 into cad/out/
python package_mount_v18.py   # publish verified outputs into export/
```

`generate_mount_v18.py --mesh-only` skips the STEP export for faster iteration.
Validation scripts in `cad/` (for example `validate_mount.py`) assert that the
generated solid stays watertight and matches the mated geometry.

## License

MIT