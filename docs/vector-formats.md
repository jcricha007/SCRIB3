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

John's motor screenshot identifies **McMaster-Carr 6627T66**, a bipolar NEMA 17
motor rated **0.7 A maximum per phase**, with 9.82 Ω resistance per phase. The
shield listing is a Xinimark CNC Shield V3 for A4988 plug-in modules. Confirm
the installed driver modules and read their sense-resistor markings: the
listing picture does not establish their resistance or current adjustment.

For an A4988, `I_limit = Vref / (8 × R_sense)`. SCRIB3/GRBL cannot change this
analog setting on the driver module. Keep the calculated limit at or below
0.7 A for these motors; a 0.5 A limit is a reasonable lower-current trial if
it provides enough torque. Measure the existing Vref first rather than
assuming that its current setting is too high.

| Confirmed sense-resistor marking | Resistance | Vref for 0.5 A trial | Vref for 0.7 A limit |
| --- | --- | --- | --- |
| R050 | 0.050 Ω | 0.200 V | 0.280 V |
| R068 | 0.068 Ω | 0.272 V | 0.381 V |
| R100 | 0.100 Ω | 0.400 V | 0.560 V |

These are calculated examples, not an identification of the installed boards.
At the same winding resistance, reducing the limit from 0.7 to 0.5 A would
reduce copper heating to approximately `(0.5 / 0.7)² = 51%` of its previous
value. Actual temperatures depend on duty, cooling, and installation. Retest
alignment and skipped steps at 350 in/min after any current reduction.

Use the driver maker's Vref procedure. Full-step coil current is approximately
70.7% of the A4988 current-limit value; power-supply current is not coil current.
Lowering app feed does not itself change the driver's current limit. Cooling
and removing mechanical binding can also help. Disconnect power before
changing motor wiring; never unplug a motor from an energized driver. The
motor listing's 266°F insulation maximum is not a recommended case temperature.

References: [ezdxf paths](https://ezdxf.readthedocs.io/en/stable/path.html),
[GRBL configuration](https://github.com/gnea/grbl/wiki/Grbl-v1.1-Configuration),
[Allegro A4988 datasheet, current-limit equation](https://www.allegromicro.com/-/media/files/datasheets/a4988-datasheet.pdf),
[Pololu A4988 current limiting and motor connections](https://www.pololu.com/product/1182).
Motor specifications above come from John's supplied McMaster-Carr screenshot;
the installed driver sense resistance and measured Vref remain to be confirmed.
