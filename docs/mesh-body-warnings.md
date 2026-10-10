# Open reference panels and the closed print enclosure

Fusion's warnings about meshes being open and having no positive volume apply
to the P-numbered inspection panels. These are partitions of the enclosure's
surface, not individual solid parts. Each is oriented, but deliberately open
and therefore has zero volume. Closing or thickening them individually would
change their meaning and could alter the enclosure.

The complete `Enclosure - closed print mesh` in `Enclosure (print mesh)` passes
Fusion's closed and oriented checks and has positive volume of
98082.865243 mm3, with 103764 triangles at the time of this audit. The subsequent
front-top cleanup is documented in `front-top-lip-cleanup.md` with its current
volume and triangle count. `exterior-and-plate-cleanup.md` records the later
plate fill and consolidation to 18 inspection regions. Use this body for printing or solid
mesh operations. The reference panels together contain the same triangle
count.

The panel component is now named `Inspection surfaces (open reference panels)`
and hidden by default; its P-numbered regions remain available for inspection.
Their open-mesh warnings remain expected. No geometry was changed in this
audit. The active Fusion document and exported F3D were saved.

Audit and backup: `cad/out/mesh-warning-audit/validation.json` and `before.f3d`.
