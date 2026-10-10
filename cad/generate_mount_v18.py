"""Apply PLA prototype feedback: removable OEM nubs, solid fins and access."""
import argparse
from build_design import P
from generate_mount_v3 import run

if __name__ == '__main__':
    assert P['revision'] == 'v18'
    parser = argparse.ArgumentParser()
    parser.add_argument('--mesh-only', action='store_true')
    run(export_step=not parser.parse_args().mesh_only)
