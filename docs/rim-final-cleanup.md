# Remaining P16 internal rim cleanup

The first internal-lip cleanup removed lower support ramps, but its 4 mm
perimeter inset and Y=-59.5 cutoff retained an upper stepped lip and a short
remnant at the locator-plate junction. The user identified these in P16.

The cleanup now uses a 2.7 mm nominal perimeter-wall target, reaches
Y=[-144.7,-48] mm and abs(X)>=60 mm, and still stops on the cavity side of
the existing analytic inner fin planes. It does not add material. The upper
inside contour follows straight polygon segments, without the inherited
stepped lip. The locator-plate junction no longer has the arbitrary earlier
Y=-59.5 cutoff. The exterior outline and two male nubs are preserved.

Removed an additional 3144.096019 mm3. Boolean comparisons confirm zero
change in the measured left/right track-backing regions and central nub
region, and negligible change outside the internal cutter scope. The final
remaining-material check inside the cleared envelope returned zero. Fusion
reports the mesh closed and oriented; the published STL reloads as one
watertight positive solid with 103764 triangles.

Updated source parameters and internal_rim_cleanup.py, the active Fusion
print and inspection meshes, and export F3D/STL/3MF. The existing 3MF profile
was preserved and its geometry verified against the STL. The PLA prototype
file was absent from export and was not recreated. Re-slice before printing.
Removed automatically appended numeric mesh-name suffixes while replacing
meshes, keeping P16 and the other region names consistent.

Source rebuild remains dependent on the missing original example-mount
reference meshes; this edit was applied to the current closed Fusion mesh.
The updated source syntax and delivered cleanup-envelope test passed.

Backups and evidence: cad/out/rim-final-cleanup, including before.f3d,
export_before, parameters_before.json, validation.json, before.png, after.png.
This supersedes the earlier, narrower scope in internal-rim-removal.md.