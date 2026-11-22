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
| [vpype](https://github.com/abey79/vpype) | MIT | Its line merging, loop entry and two-opt workflows informed this pass. SCRIB3 implements bounded routing and exact-endpoint joining locally; vpype is not a runtime dependency. See the [command reference](https://vpype.readthedocs.io/en/stable/reference.html). |
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
overdraw. Exact reversed copies and closed loops with the same vertices but a
different starting vertex also count as duplicates. Comparison happens before
simplification or joining; nearby distinct strokes remain. Different vertex
sampling, partial overlaps and nearly coincident geometry are not deduplicated.

**Join fragments that meet exactly** is off by default. It joins open paths
only when exactly two endpoints meet at the same coordinate. Branches, vertices
inside other strokes, and existing closed contours block joining. There is no
snap tolerance: even very small nonzero gaps remain open. It can reverse and
reorder fragments to create a continuous stroke; the pen draws every original
segment once before any selected simplification. Use this for fragmented CAD
outlines; leave it off when individual pen lifts are intentional.

**Optimize travel** starts at the selected paper origin and compares greedy
ordering with the source route. Three local two-opt passes reverse sections of
the route, including stroke directions, whenever that shortens travel. Searches
span up to 32 strokes per section to bound processing time. The returned route
never increases the cleanup result's pen-up distance. It is a heuristic, not a
globally optimal route or an ink-drying scheduler.

**Choose shorter entry points on closed loops** is enabled by default and only
applies when Optimize travel is on. It chooses existing vertices using both
incoming and outgoing travel, keeping the exact outline. Disable it to retain
the source seams. Seam overlap still applies at the chosen start; it can darken
that part of the loop. Travel metrics do not include the overlap extension or a
return home, and are not a prediction of physical plotting time.

Quality preferences are saved with the preset. Schema-5 and schema-6 presets
migrate to schema 7 without changing custom feed rates or machine settings.
Joining defaults off and loop entry optimization defaults on. Quality,
duplicate, joining and loop-entry changes invalidate an already-reviewed job.

## Reviewing the result

The workspace shows output point count, stroke count and pen-up distance,
plus a before/after point summary. **Source overlay** draws the fitted source
in pale blue beneath the processed paths; **Pen-up travel** adds amber dashed
travel lines. Both are display-only. The dark drawing desk, white paper and
shared blue/gray controls apply throughout the desktop. Ctrl+O imports and
Ctrl+R opens review; neither shortcut sends a job to the plotter.

Repeated previews reuse geometry until the source, paper, origin or quality
settings change. A changed quality mode, routing option or paper setting
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

## Routing comparison

Import `examples/routing-check.svg` to compare separate rectangle fragments,
a duplicated square with a shifted seam, an intentional gap, a three-way branch,
and a circle. Enable exact joining and duplicate removal to turn 16 strokes
into 12. The gap and three-way branch must remain separate.

Measured with US Letter landscape, 12.7 mm margin, top-left paper origin and
Original quality (so simplification cannot affect this comparison):

| Fixture | Prior greedy travel | New routing only | Routing + exact joining + duplicate removal |
| --- | ---: | ---: | ---: |
| `quality-check.svg` | 590.35 mm | 501.47 mm | 498.36 mm |
| `routing-check.svg` | 775.33 mm | 676.33 mm | 609.96 mm |

Routing alone preserves the complete segment multiset, including intentional
overdraw. The last column removes one explicitly duplicated stroke from each
fixture. Tests also cover reversed fragments, cycles, repeated loop vertices,
2,000-fragment chains, both paper origins, G-code units/mounts, dry runs, SVG
export/reimport, preset migration and stale-review prevention.

### Check exported coordinate precision in Review G-code

The G-code review starts with the coordinate grid and a stroke count from the
same commands shown below it. If a short stroke becomes a single XY
position after rounding, it is omitted and the review shows a warning. The
summary also counts adjacent points that share an output position, including
in strokes that remain. An entirely unplottable drawing is still refused.
The summary does not become part of the saved .gcode, change settings, or
connect to a controller. It describes **file coordinate rounding**, not the
machine's steps per unit, pen width, or physical accuracy.
