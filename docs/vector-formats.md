# Vector drawings and closed-loop seams

Use **Import drawing** for SVG, DXF, or SCRIB3 drawing JSON. All files are fitted
proportionally to the current paper and margin using their artwork bounds.
Import is not a 1:1 CAD-scale workflow. Review the preview before running.
**Export drawing** saves the fitted geometry to any of these three formats.
The file extension selects the format. Exports contain geometry, not controller
settings, paper zero, or a runnable job. Use Review G-code for machine output.

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
for CAD drawings. PNG/JPEG require tracing to vector paths before import.

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

Warmth alone does not establish overheating; compare a measured motor-case
temperature with that motor's datasheet. The reported `$1=25` tells GRBL to
disable steppers shortly after motion stops. This update leaves it unchanged.
`$1=255` would keep the motors enabled continuously and is not a heat reduction.
Releasing motors also reduces holding torque; re-establish paper zero if an
axis is moved by hand while released.

For a current-limiting driver, the main adjustment is its phase-current limit.
Identify the exact driver board, sense resistors, and motor rated current first;
Vref formulas differ between boards. Use the manufacturer's procedure, stay
within the motor/driver ratings, and retest drawing alignment after reducing
current. Too little current can cause missed steps. Lowering the app's feed
does not itself lower the driver's configured phase current. Cooling and
removing mechanical binding can also help. Disconnect power before changing
motor wiring; never unplug a motor from an energized driver.

References: [ezdxf paths](https://ezdxf.readthedocs.io/en/stable/path.html),
[GRBL configuration](https://github.com/gnea/grbl/wiki/Grbl-v1.1-Configuration),
[Pololu A4988 current limiting and motor connections](https://www.pololu.com/product/1182).
The A4988 reference is an example; John's driver model is not yet identified.
