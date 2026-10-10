"""Regenerate docs/images/render-01.png through render-07.png via Fusion MCP.

Open the updated design in Fusion, then run from the project root:
    python cad/render_readme.py

Requires Pillow (pip install Pillow), Fusion running, and its MCP add-in enabled.
The default source is the active, potentially unsaved Fusion design. Alternatively:
    python cad/render_readme.py --model export/starlink-mini-battery-mount.f3d
    python cad/render_readme.py --document "starlink-mini-battery-mount v21"
    python cad/render_readme.py --list-documents

Rendering happens in an unsaved temporary document; the source is never saved or
edited. Existing README images are replaced only after all seven renders and PNG
encodes succeed. Raw captures are retained in cad/out/readme-renders/<run-id>.
Use --output-dir to preview without replacing the README images.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
from pathlib import Path
import shutil
import textwrap
import time
import urllib.error
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 1083, 812
# These are the dimensions, byte sizes, subjects, and cameras of the original
# README assets. Keep the targets stable across repeated regeneration.
VIEWS = (
    ("render-01.png", False, False, (35, -45, -40), (0, 0, -1), 49647),
    ("render-02.png", False, False, (-40, -30, -22), (0, 0, -1), 39573),
    ("render-03.png", False, False, (32, 35, 35), (0, 0, 1), 64917),
    ("render-04.png", False, True, (-40, -30, -22), (0, 0, -1), 49528),
    ("render-05.png", False, True, (32, 35, 35), (0, 0, 1), 39867),
    ("render-06.png", True, True, (35, -45, -40), (0, 0, -1), 41937),
    ("render-07.png", True, True, (-40, -30, -22), (0, 0, -1), 34776),
)


class FusionMCP:
    """Small standard-library client for the local streamable HTTP MCP server."""

    def __init__(self, url: str, timeout: float):
        self.url, self.timeout = url, timeout
        self.session = None
        self.sequence = 0
        result = self.request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "readme-render", "version": "1.0"},
        })
        self.protocol = result.get("protocolVersion", "2024-11-05")
        self.request("notifications/initialized", notification=True)

    def request(self, method, params=None, notification=False):
        self.sequence += 1
        message = {"jsonrpc": "2.0", "method": method}
        if not notification:
            message["id"] = self.sequence
        if params is not None:
            message["params"] = params
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        if hasattr(self, "protocol"):
            headers["MCP-Protocol-Version"] = self.protocol
        req = urllib.request.Request(self.url, json.dumps(message).encode(), headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                self.session = response.headers.get("Mcp-Session-Id", self.session)
                payload = response.read().decode("utf-8")
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Fusion MCP HTTP {exc.code}: {exc.read().decode()}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(
                f"Cannot complete Fusion MCP request at {self.url}: {exc}. "
                "Check Fusion and its MCP add-in. A timed-out render may still be "
                "running: wait for it to finish before retrying."
            ) from exc
        if notification or not payload.strip():
            return {}
        if "text/event-stream" in content_type:
            replies = []
            for event in payload.replace("\r\n", "\n").split("\n\n"):
                data = "\n".join(line[5:].lstrip() for line in event.splitlines()
                                 if line.startswith("data:"))
                if data:
                    replies.append(json.loads(data))
            matches = [reply for reply in replies if reply.get("id") == message["id"]]
            if not matches:
                raise RuntimeError("Fusion MCP stream did not return the requested response")
            reply = matches[-1]
        else:
            reply = json.loads(payload)
        if "error" in reply:
            raise RuntimeError(str(reply["error"]))
        return reply["result"]

    def script(self, source, read_only=False):
        result = self.request("tools/call", {
            "name": "fusion_mcp_execute",
            "arguments": {"featureType": "script", "object": {
                "script": source, "readOnly": read_only}},
        })
        if result.get("isError"):
            raise RuntimeError(str(result))
        for item in result.get("content", []):
            if item.get("type") != "text":
                continue
            text = item["text"]
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                raise RuntimeError(f"Unexpected Fusion script response: {text}")
            if data.get("success") is False or data.get("error"):
                raise RuntimeError(data.get("error", text))
            if data.get("message"):
                print(data["message"].strip(), flush=True)


def setup_script(key: str, archive: Path, model: Path | None, document: str | None):
    return textwrap.dedent('''\
        import adsk.core, adsk.fusion, builtins
        def run(_context: str):
            app = adsk.core.Application.get()
            original = app.activeDocument
            if original is None:
                raise RuntimeError('Open the updated design in Fusion first')
            state = dict(original=original, workspace=app.userInterface.activeWorkspace.id,
                         camera=app.activeViewport.camera, copy=None)
            setattr(builtins, KEY, state)
            model = MODEL
            document = DOCUMENT
            if document is not None:
                matches = [doc for doc in app.documents if doc.name == document]
                if len(matches) != 1:
                    raise RuntimeError('Expected one open document named %r, found %s. '
                                       'Use --list-documents for exact tab names.' %
                                       (document, len(matches)))
                matches[0].activate()
            source_name = app.activeDocument.name
            if model is None:
                design = adsk.fusion.Design.cast(app.activeProduct)
                if design is None:
                    raise RuntimeError('The active Fusion document must be a Design')
                options = design.exportManager.createFusionArchiveExportOptions(ARCHIVE)
                if not design.exportManager.execute(options):
                    raise RuntimeError('Could not snapshot the current design')
                source = ARCHIVE
            else:
                source = model
                source_name = model
            copy = app.importManager.importToNewDocument(
                app.importManager.createFusionArchiveImportOptions(source))
            state['copy'] = copy
            if copy is None:
                raise RuntimeError('Could not open the render copy')
            design = adsk.fusion.Design.cast(app.activeProduct)
            state['design'] = design
            root = design.rootComponent
            components = [root] + [occ.component for occ in root.allOccurrences]
            subjects = dict(mini=[], battery=[], enclosure=[])
            seen = set()
            for component in components:
                if component.entityToken in seen:
                    continue
                seen.add(component.entityToken)
                for body in list(component.bRepBodies) + list(component.meshBodies):
                    if body.name == 'Official Starlink Mini':
                        subjects['mini'].append(body)
                    elif body.name.startswith('GRAY -'):
                        subjects['battery'].append(body)
                    elif body.name == 'Enclosure - closed print mesh':
                        subjects['enclosure'].append(body)
            for subject, bodies in subjects.items():
                if len(bodies) != 1:
                    raise RuntimeError('Expected one %s body, found %s. Update the body '
                                       'selectors in render_readme.py for this design.' %
                                       (subject, len(bodies)))
            library = app.materialLibraries.itemByName('Fusion Appearance Library')
            colors = {}
            for subject, rgb in [('mini', (245,245,245)), ('battery', (35,38,42)),
                                 ('enclosure', (255,92,0))]:
                appearance = design.appearances.addByCopy(
                    library.appearances.itemByName('Plastic - Matte (White)'),
                    'README ' + subject)
                appearance.color = adsk.core.Color.create(*rgb, 255)
                for prop_id in ['opaque_albedo', 'surface_albedo']:
                    prop = adsk.core.ColorProperty.cast(
                        appearance.appearanceProperties.itemById(prop_id))
                    if prop:
                        prop.value = adsk.core.Color.create(*rgb, 255)
                colors[subject] = appearance
            for occurrence in root.allOccurrences:
                occurrence.isLightBulbOn = True
                if hasattr(occurrence, 'opacity'):
                    occurrence.opacity = 1.0
                occurrence.appearance = None
            seen.clear()
            for component in components:
                if component.entityToken in seen:
                    continue
                seen.add(component.entityToken)
                for sketch in component.sketches:
                    sketch.isLightBulbOn = False
                for body in list(component.bRepBodies) + list(component.meshBodies):
                    body.isLightBulbOn = False
                    if hasattr(body, 'opacity'):
                        body.opacity = 1.0
            for subject, bodies in subjects.items():
                for body in bodies:
                    body.appearance = colors[subject]
                    if adsk.fusion.BRepBody.cast(body):
                        for face in body.faces:
                            face.appearance = None
            subjects['enclosure'][0].isLightBulbOn = True
            state['subjects'] = subjects
            manager = design.renderManager
            manager.activateRenderWorkspace()
            scene = manager.sceneSettings
            scene.backgroundEnvironment = manager.renderEnvironments.itemById('Studio6')
            scene.backgroundSolidColor = adsk.core.Color.create(255,255,255,255)
            scene.brightness = 5000
            scene.cameraExposure = 10
            scene.isGroundDisplayed = False
            scene.isDepthOfFieldEnabled = False
            scene.cameraType = adsk.core.CameraTypes.OrthographicCameraType
            scene.aspectRatio = adsk.fusion.RenderAspectRatios.Presentation4to3RenderAspectRatio
            print('Rendering a temporary copy of: ' + source_name)
    ''').replace('KEY', repr(key)).replace('ARCHIVE', repr(str(archive))).replace(
        'MODEL', repr(str(model)) if model else 'None').replace('DOCUMENT', repr(document))


def render_script(key, view, path, seconds):
    filename, mini, battery, eye, up, _ = view
    return textwrap.dedent(f'''\
        import adsk.core, adsk.fusion, builtins, time
        def run(_context: str):
            app = adsk.core.Application.get()
            state = getattr(builtins, {key!r})
            if app.activeDocument != state['copy']:
                raise RuntimeError('The render copy is no longer active; rendering stopped')
            manager = state['design'].renderManager
            if not manager.isRenderWorkspaceActive:
                raise RuntimeError('Keep Fusion in the Render workspace while rendering')
            for body in state['subjects']['mini']:
                body.isLightBulbOn = {mini!r}
            for body in state['subjects']['battery']:
                body.isLightBulbOn = {battery!r}
            viewport = app.activeViewport
            camera = viewport.camera
            camera.cameraType = adsk.core.CameraTypes.OrthographicCameraType
            camera.eye = adsk.core.Point3D.create(*{eye!r})
            camera.target = adsk.core.Point3D.create(0, -8, -2)
            camera.upVector = adsk.core.Vector3D.create(*{up!r})
            camera.isSmoothTransition = False
            camera.isFitView = True
            viewport.camera = camera
            camera = viewport.camera
            camera.isFitView = False
            camera.viewExtents *= 0.75
            viewport.camera = camera
            viewport.refresh()
            adsk.doEvents()
            renderer = manager.inCanvasRendering
            renderer.isAdvanced = False
            renderer.limitResolution = 100
            if not renderer.start(0.5):
                raise RuntimeError('Could not start the in-canvas renderer')
            deadline = time.monotonic() + {seconds!r}
            while time.monotonic() < deadline:
                adsk.doEvents()
                time.sleep(0.1)
                if app.activeDocument != state['copy']:
                    raise RuntimeError('Document changed during rendering; output not saved')
            if not renderer.saveImage({str(path)!r}):
                raise RuntimeError('Could not save {filename}')
            renderer.stop()
            print('Captured {filename}')
    ''')


def cleanup_script(key):
    return textwrap.dedent(f'''\
        import adsk.core, builtins
        def run(_context: str):
            app = adsk.core.Application.get()
            state = getattr(builtins, {key!r}, None)
            if state is None:
                return
            copy = state['copy']
            if copy is not None and copy.isValid:
                copy.activate()
                if state.get('design') and state['design'].renderManager.isRenderWorkspaceActive:
                    state['design'].renderManager.inCanvasRendering.stop()
                copy.close(False)
            if state['original'].isValid:
                state['original'].activate()
                app.userInterface.workspaces.itemById(state['workspace']).activate()
                app.activeViewport.camera = state['camera']
            delattr(builtins, {key!r})
            print('Restored the original Fusion document')
    ''')


def encode_png(source: Path, destination: Path, target_bytes: int):
    """Preserve dimensions and white background; choose a similar-size palette PNG."""
    from PIL import Image

    with Image.open(source) as raw:
        if raw.width < WIDTH or raw.height < HEIGHT:
            raise RuntimeError(f"{source.name}: capture {raw.size} is smaller than "
                               f"{WIDTH}x{HEIGHT}; enlarge Fusion's viewport and retry")
        rgba = raw.convert("RGBA")
        image = Image.new("RGBA", rgba.size, "white")
        image.alpha_composite(rgba)
        image = image.convert("RGB").resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    candidates = []
    for colors in (256, 224, 192, 160, 128, 96, 64, 48, 32):
        palette = image.quantize(colors=colors, method=Image.Quantize.MEDIANCUT,
                                 dither=Image.Dither.NONE)
        data = io.BytesIO()
        palette.save(data, format="PNG", optimize=True, compress_level=9)
        candidates.append((colors, data.getvalue()))
    near = [candidate for candidate in candidates
            if abs(len(candidate[1]) / target_bytes - 1) <= 0.20]
    # Favor more colors within the size band; otherwise use the closest size.
    colors, data = max(near, key=lambda c: c[0]) if near else min(
        candidates, key=lambda c: abs(math.log(len(c[1]) / target_bytes)))
    destination.write_bytes(data)
    with Image.open(destination) as check:
        check.load()
        if check.size != (WIDTH, HEIGHT) or check.mode != "P":
            raise RuntimeError(f"Output verification failed: {destination}")
    delta = (len(data) / target_bytes - 1) * 100
    print(f"{destination.name}: {WIDTH}x{HEIGHT}, {len(data):,} bytes "
          f"(target {target_bytes:,}, {delta:+.1f}%, {colors} colors)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:27182/mcp")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--model", type=Path, help="Use an .f3d archive instead of the active design")
    sources.add_argument("--document", help="Exact name of an already open Fusion tab")
    parser.add_argument("--list-documents", action="store_true", help="List open Fusion tab names")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "images")
    parser.add_argument("--seconds", type=float, default=12,
                        help="Render time per view (default: 12; increase for cleaner images)")
    parser.add_argument("--postprocess-only", type=Path,
                        help="Encode seven existing raw render-01..07 PNGs; no Fusion connection")
    parser.add_argument("--dry-run", action="store_true", help="Show output plan without changes")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 90:
        parser.error("--seconds must be between 1 and 90")
    if args.model and (not args.model.is_file() or args.model.suffix.lower() != ".f3d"):
        parser.error("--model must be an existing .f3d archive")
    if args.dry_run:
        print(f"Source: {args.model or args.document or 'active Fusion design'}\n"
              f"Output: {args.output_dir.resolve()}")
        for name, mini, battery, _, _, size in VIEWS:
            print(f"{name}: Mini={mini}, battery={battery}, enclosure=True; "
                  f"{WIDTH}x{HEIGHT}; target {size:,} bytes")
        return
    if args.list_documents:
        client = FusionMCP(args.url, timeout=180)
        client.script(textwrap.dedent('''\
            import adsk.core
            def run(_context: str):
                app = adsk.core.Application.get()
                for document in app.documents:
                    marker = ' (active)' if document == app.activeDocument else ''
                    print(document.name + marker)
        '''), read_only=True)
        return
    # Check Pillow before opening or modifying any Fusion document.
    import PIL  # noqa: F401

    run_id = uuid.uuid4().hex
    run_dir = ROOT / "cad" / "out" / "readme-renders" / run_id
    raw_dir, encoded_dir = run_dir / "raw", run_dir / "encoded"
    raw_dir.mkdir(parents=True)
    encoded_dir.mkdir()
    if args.postprocess_only:
        raw_dir = args.postprocess_only.resolve()
    else:
        client = FusionMCP(args.url, timeout=max(180, args.seconds + 90))
        key = "_readme_render_" + run_id
        failure = None
        try:
            client.script(setup_script(key, run_dir / "source.f3d",
                                       args.model.resolve() if args.model else None, args.document))
            for view in VIEWS:
                print(f"Rendering {view[0]}...", flush=True)
                client.script(render_script(key, view, raw_dir / view[0], args.seconds))
        except BaseException as exc:
            failure = exc
            raise
        finally:
            # Never queue cleanup after an unknown timeout: the earlier operation
            # can still be rendering, and nested scripts can interfere with it.
            uncertain = failure and any(isinstance(failure.__cause__, cls)
                                        for cls in (urllib.error.URLError, TimeoutError))
            if uncertain:
                print("Render outcome unknown. Temporary Fusion copy left open; "
                      "wait for the operation to finish before closing it.", flush=True)
            else:
                try:
                    client.script(cleanup_script(key))
                except Exception as exc:
                    if failure is None:
                        raise
                    print(f"Cleanup also failed: {exc}. The temporary copy may remain open.")
    for view in VIEWS:
        encode_png(raw_dir / view[0], encoded_dir / view[0], view[5])
    # Stage all encodes before replacing any existing README assets. Keep backups
    # of the seven existing render files to make a failed replacement recoverable.
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    backup = run_dir / "previous"
    backup.mkdir()
    for view in VIEWS:
        existing = output / view[0]
        if existing.exists():
            shutil.copy2(existing, backup / view[0])
    installed = []
    try:
        for view in VIEWS:
            target = output / view[0]
            staging = output / (view[0] + "." + run_id + ".tmp")
            shutil.copy2(encoded_dir / view[0], staging)
            os.replace(staging, target)
            installed.append(target)
    except BaseException:
        for target in installed:
            old = backup / target.name
            if old.exists():
                shutil.copy2(old, target)
            else:
                target.unlink()
        raise
    print(f"Updated seven renders in {output}\nRun files and backups: {run_dir}")


if __name__ == "__main__":
    main()
