# Lower-right inspection seams and locator plate edge trenches

The user selected P06, P07, P01 and P09 and identified jagged outlines near
the right, rear and bottom sides. Viewing the complete closed enclosure from
the same camera confirmed that the triangular outlines were boundaries of
the inspection surface regions across otherwise flat faces. They were not
protrusions or overlapping solid parts in the print mesh.

Regrouped nine planar inspection faces at the lower-right wall and floor
seams. Each complete face now belongs to one region. Merged P09 into
`P07 - Right fin and rear corner return`, leaving 18 open reference regions.
This removes the misleading triangular offshoots without changing the lower
exterior shape or Starlink attachment geometry. Native Fusion verifies that
the inspection regions partition the complete mesh's 103738 triangles.

The narrow trenches at the left and right ends of the locator plate were
physical recesses. Filled their measured footprints flush with the adjacent
plate at Z=-6.6106 mm. Only these grooves receive new material, totaling
25.314569 mm3; no material is removed. The two nub seats and male nubs, middle
thumb depression, and left/right mating trenches remain unchanged. The added
material has zero intersection with an independent mesh of the official Mini
STEP body exported from Fusion at 0.01 mm surface tolerance.

The final print mesh is one watertight positive solid. The STL volume is
96439.966844 mm3; Fusion reports 96439.966852 mm3, closed and oriented. Saved
the active Fusion document and updated F3D/STL/3MF exports. The 3MF mesh
matches the STL, with the existing print profile preserved. Re-slice before
printing. Source parameters, helper and validator support the plate fill;
the named inspection grouping is reproduced by the saved audit script.

Evidence and backups: `cad/out/exterior-and-plate-cleanup`, including
`before.f3d`, `export_before`, `fusion_before.json`, `validation.json`,
`fusion_validation.json`, the official reference, screenshots and scripts.
Source syntax and delivered mesh checks passed. The full source rebuild
still requires the unavailable original example-mount reference meshes.
