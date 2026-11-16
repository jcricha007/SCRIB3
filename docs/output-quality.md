# Output quality

## Curve import

SVG import uses [svgelements 1.9.6](https://github.com/meerk40t/svgelements)
(MIT) for transforms, units, paths and shape parsing. SCRIB3 now flattens its
reified Beziers using control-polygon bounds, and elliptical arcs using a
second-derivative interpolation bound. This replaces fixed length-based
sampling, which could waste points on straight curves and miss tight bends.

The source-coordinate tolerance is 0.00001 times the largest drawing extent.
It scales when fitting to paper: approximately 0.0025 mm for a 250 mm drawing.
This is a geometry approximation, not a statement of machine accuracy. G-code
coordinate rounding and mechanical calibration introduce separate errors.
The existing 100,000-point limit rejects excessive complexity instead of
silently reducing accuracy. Explicit closed loops remain closed; deliberately
open gaps remain open. SVG text, raster images, clipping and masks still need
conversion to supported paths. DXF continues to use ezdxf's flattening.

## Open-source review (2026-11-16)

| Project | License | Decision |
| --- | --- | --- |
| [svgelements](https://github.com/meerk40t/svgelements) | MIT | Keep the existing parser; use its exact segment geometry for adaptive flattening. |
| [rdp](https://github.com/fhirschmann/rdp/tree/v0.8) | MIT | Integrated tolerance-controlled polyline simplification. Its iterative API accepts SCRIB3's finite-segment distance metric. |
| [vpype](https://github.com/abey79/vpype) | MIT | Evaluated for line merging, simplification and travel ordering. Defer the larger stack; SCRIB3 needs a conservative small cleanup stage and already orders endpoints. See the [command reference](https://vpype.readthedocs.io/en/stable/reference.html). |
| [svg2gcode](https://github.com/sameer/svg2gcode) | MIT | Evaluated as an alternative SVG compiler. Keep SCRIB3's validated GRBL postprocessor, unit handling, servo calibration and dry-run controls. |

No controller settings are changed by importing or optimizing geometry.
Validate with a pen-up run and a physical reference plot after changing the
toolpath. Software tests do not establish backlash, belt tension, pen pressure,
steps/mm, or the feed rate suitable for a particular machine.

## Toolpath cleanup

Open **Plot quality** to choose **Original** (no simplification), **Fine**
(0.005 mm) or **Balanced** (0.02 mm, the default). These tolerances apply to the
fitted polyline in millimeters, independently of the display or G-code units.
They are additional to curve import and coordinate-rounding error. Refit after
changing the paper size. The preview and G-code use the same processed drawing.

RDP keeps endpoints, extrema and direction reversals. Closed contours cannot
collapse to lines; small open gaps are not closed. It works in bounded chunks
to avoid unbounded quadratic work on large files. Simplification is not an SVG
redesign tool and does not reconstruct missing detail from coarse source art.

**Remove exactly repeated strokes** is off by default, preserving intentional
overdraw. When selected, exact reversed copies also count as duplicates. The
comparison happens before simplification; nearby distinct strokes remain. It
does not merge partially overlapping lines or loops with different start points.

Endpoint ordering starts at the selected paper origin. If its greedy route is
longer than the source order, SCRIB3 retains the shorter source route. It does
not automatically relocate loop seams or join disconnected strokes.

Quality preferences are saved with the preset. Schema-5 presets migrate to
schema 6 without changing custom feed rates or machine settings. Quality and
duplicate changes invalidate an already-reviewed job before it can run.

## Reviewing the result

The workspace shows output point count, stroke count and pen-up distance,
plus a before/after point summary. **Source overlay** draws the fitted source
in pale blue beneath the processed paths; **Pen-up travel** adds amber dashed
travel lines. Both are display-only. The dark drawing desk, white paper and
shared blue/gray controls apply throughout the desktop. Ctrl+O imports and
Ctrl+R opens review; neither shortcut sends a job to the plotter.

Repeated previews reuse geometry until the source, paper, origin or quality
settings change. A changed quality mode, duplicate option or paper setting
still requires a new job review.

Import `examples/quality-check.svg` for a repeatable comparison:

1. Check the two circles and narrow ellipse in the top row for flat spots.
2. Check the top-right S curve and lower-left sharp turns for lost detail.
3. The lower-middle rectangle has an intentional 0.5 source-unit opening.
4. The lower-right diagonal is drawn twice unless duplicate removal is enabled.
   The two nearby horizontal lines must remain separate.
5. Review a pen-up run, then plot with Original and Balanced modes using the
   same paper, feed and pen. Inspect seams, corners and line continuity.

The SVG is fitted to the selected paper, so the physical test dimensions scale.
The included tests verify geometry and controller protocol with simulated serial
devices; physical plot quality remains a machine acceptance check.
