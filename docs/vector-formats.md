# Vector drawings and closed-loop seams

Use **Import drawing** for SVG, AI, DWG, PSD, PDF, PNG, JPEG, BMP, static WebP, single-page TIFF, DXF, or SCRIB3 drawing JSON.
The [artwork import guide](artwork-import.md) describes converter installation,
page selection, image tracing and format limitations. All files are fitted
proportionally to the current paper and margin using their artwork bounds.
Import is not a 1:1 CAD-scale workflow. Review the preview before running.
**Export drawing** saves the fitted geometry to SVG, DXF or drawing JSON.
The file extension selects the format. Exports contain geometry, not controller
settings, paper zero, or a runnable job. Use Review G-code for machine output.
Exports are staged beside the destination and replace it only after the drawing
has been encoded. A save failure leaves an existing file intact; export refuses
links, directories, and destinations observed to change while saving.

| Format | Supported content |
| --- | --- |
| SVG | Vector paths, circles, ellipses, polygons, polylines, and transformed shapes. Outlines only. Convert text/images to paths and flatten masks/clipping/filters first. |
| DXF | Model-space LINE, ARC, CIRCLE, ELLIPSE, SPLINE, LWPOLYLINE with bulges, and flat POLYLINE. Transformed/nested INSERT blocks and block arrays are supported. |
| Drawing JSON | Explicit open or closed polylines, suitable for designs generated in chat or code. |

DXF coordinates are converted from CAD Y-up to the drawing workspace Y-down;
the fitted paper then uses the selected machine mounting (+Y right, −X down
for John's setup). Hidden/off/frozen geometry is ignored. Visible unsupported
entities fail the entire import with an explanation: text, hatches, dimensions,
meshes, unresolved external references, and clipped/attributed blocks need
conversion to plain paths in CAD. Paths must lie parallel to the XY plane.
Paper-space layouts are not imported. DXF export writes millimeter polylines,
so sampled curves do not become analytic circles/splines again.

Limits: SVG 2 MB; DXF/JSON 10 MB; 2,000 strokes; 100,000 points. DXF curve
flattening uses a source tolerance of artwork extent / 10,000 (with a minimum
1e-9 source units) before paper fitting. Geometry is never sent directly to the
controller during import.

## Drawing JSON version 1

Coordinates use +X right and +Y down, like SVG. `units` accepts `mm`, `in`, or
`unitless`; import still fits the artwork bounds to paper. Each stroke has
`points` and a boolean `closed`. Closing a stroke appends its first point if
needed. Repeating the first point explicitly also represents a closed loop.
No commands, scripts, or machine settings are accepted.

```json
{
  "format": "scrib3-drawing",
  "version": 1,
  "units": "mm",
  "strokes": [
    {"closed": true, "points": [[0, 0], [20, 0], [20, 20], [0, 20]]},
    {"closed": false, "points": [[5, 5], [15, 10], [5, 15]]}
  ]
}
```

SVG is the most convenient format for new designs in chat: it supports exact
circles and curves, previews in common tools, and imports here. DXF is useful
for CAD drawings. Supported raster images and the saved merged PSD image can be traced directly
inside SCRIB3.

## Closing small gaps

The original rosette generator already returned to each circle's start in
exported millimeter and inch G-code. This update makes its repeated endpoint
exact in source geometry and adds an optional **Plot quality → Overlap**.
Overlap follows the existing loop for the chosen distance after closure,
before the pen lifts. It never joins separate strokes or closes an open path.
It is limited to one additional lap for a very small loop.

Try **Use 0.5 mm → Apply and save**, then open a fresh G-code review. Set 0 to
disable, or adjust within 0–5 mm. Fresh/restored presets use 0.5 mm. Existing
saved presets migrate with overlap disabled, preserving their prior behavior.
The review reports overlap and includes it in both ink and pen-up test paths.
Changing overlap invalidates an already-open review's Run command.

Overlap can help a pen-contact gap at the seam and may darken that area. It
does not establish the cause of gaps on the machine. If gaps remain or occur
mid-stroke, compare a lower draw feed, adequate pen settle/contact, belt or
coupler play, and missed steps. The runner waits for queued XY motion to finish
before lifting the pen. At the reported 5 steps/mm, one commandable step is
0.2 mm; G-code decimal precision cannot remove that mechanical resolution.

Use the small [seam-check SVG](../examples/seam-check.svg) or
[DXF](../examples/seam-check.dxf) for a comparison. The two circles and square
are closed; the bottom arc is intentionally open. Fit to a small paper area
and compare overlap 0 and 0.5 mm at the same drawing speed.

## Warm motors

The later module purchase listing identifies **DRV8825** drivers. The shield's
"A4988" product title describes compatibility, not the installed driver chip.
John's **McMaster-Carr 6627T66** motors are rated **0.7 A maximum per phase**.
The agreed provisional hardware target is **0.60 A per driver**, which requires
**0.300 V Vref when that module's sense resistors are R100 (0.100 Ω)**.
The upper module's R100 markings are visible; confirm the lower module too.

SCRIB3/GRBL cannot set or measure this analog current limit. Follow the
[hardware baseline and acceptance test](hardware-baseline.md) to measure and
adjust each driver, then check motion, circle seams, and temperature. That
guide supersedes the earlier A4988 calculation. The current target remains
provisional until the physical tests are recorded.

Reference: [ezdxf paths](https://ezdxf.readthedocs.io/en/stable/path.html).
