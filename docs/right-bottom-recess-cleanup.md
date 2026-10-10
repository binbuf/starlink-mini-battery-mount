# Physical rectangular setback at the right bottom edge

The earlier lower-right cleanup regrouped inspection surface boundaries. It
did not remove the physical long rectangular setback beneath the right fin
return. The user clarified this feature in the complete print body's view.

Filled the setback across Y=[-124,-51.5] mm, X approximately [72.7,75.15] mm,
using the existing rear 45-degree bottom bevel's X/Z profile. The bevel now
continues along the formerly recessed section. Added 253.116995 mm3 without
removing material. The bevel is below Z=-33.5605 mm and therefore below the
Mini attachment trench. Geometric comparisons show zero change to all
attachment geometry above Z=-30 mm, the battery envelope, and the floor
bottom. Added material has zero intersection with the official Mini STEP
reference tessellated in Fusion during the preceding audit.

Four rays across the completed long bevel verify the continued 45-degree
plane. Fusion and the reloaded STL report a closed, oriented, positive-volume
enclosure: 103754 triangles, STL volume 96693.083847 mm3. The 18 inspection
regions still partition the full mesh, with the new bevel in P07.

Saved the Fusion document and updated F3D/STL/3MF exports. The 3MF profile is
preserved and its geometry matches the STL; re-slice before printing. Source
parameters, surface_detail_cleanup.py and the validator include the physical
fill. Source syntax and delivered geometry checks passed; the original
example-mount reference meshes remain unavailable for a full source rebuild.

Backups and evidence: `cad/out/right-bottom-recess-cleanup`, including
`before.f3d`, prior exports and parameters, validation JSON, before/after
screenshots and the reproducible scripts. This supersedes the earlier
inspection-only explanation for the rectangular setback.
