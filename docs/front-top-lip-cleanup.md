# Interior front wall at its top edge

The selected P16 area contained three obsolete shallow grooves beneath the
front wall's top edge, and a step at the X=+/-60 mm limit of the previous side
cleanup. Those features interrupted the otherwise straight inner wall.

The inner front-wall face is now continuous at Y=-144.7 mm, matching the
adjoining 2.7 mm nominal wall. The central inward step was trimmed from
Z=-20 mm to the top, and the three shallow groove remnants were filled only
as far as that inner plane. This removes 1761.526016 mm3 and fills
93.316999 mm3. The external front skin, display opening, trenches and two
locating nubs remain unchanged; geometric comparisons found zero change in
the protected regions and outside the explicit cleanup bounds.

Eighteen inward-face ray checks confirm the same plane above, through and
below the former grooves. The exported STL is one watertight positive solid
with 103722 triangles and volume 96414.656226 mm3. Fusion separately confirms
closed and consistently oriented geometry with positive volume
96414.652276 mm3; its imported coordinates have a small rounding difference.

Updated the source parameters and cleanup helper, active Fusion print body
and all 19 named inspection regions, and F3D/STL/3MF exports. The 3MF print
profile is preserved, and its mesh matches the STL. Re-slice before printing.
Inspection regions remain open reference surfaces; use the complete print
body for printing and solid mesh operations.

Backups and validation: `cad/out/front-top-lip-cleanup`, including the prior
Fusion archive, exports, parameters, geometry comparisons and screenshots.
The original reference meshes needed for a full source rebuild remain
unavailable; the change was applied to the current closed Fusion mesh. The
source syntax and delivered geometry checks passed.
