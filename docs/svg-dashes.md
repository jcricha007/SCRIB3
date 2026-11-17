# Technical SVG dash import

SVG `stroke-dasharray` and `stroke-dashoffset` now become actual separate pen
strokes. This preserves gaps in hidden lines, centerlines and dashed annotations
through preview, cleanup and G-code. Previously these paths became solid lines.

Supported: inherited and inline dash attributes, numeric/px/mm/cm/in/pt/pc lengths,
odd-length patterns, positive/negative offsets, zero gaps, multiple subpaths,
closed paths, curves and affine transforms (including unequal X/Y scaling).
Dash phase resets on each SVG Move, and runs across other segment vertices.
Curve splitting uses the existing adaptive approximation and its error budget.
The physical pen controls cap shape and width; filled artwork is still imported
as outlines, not hatch fills.

Percentage/font-relative dash lengths, pathLength-calibrated dashes, non-scaling
stroke effects, and zero-length round/square dots require conversion to ordinary
paths before import. These cases produce an explicit error instead of solid lines
or missing dots. Dense patterns respect the existing stroke/point limits.

Krbn's `svg: { centerline: true, background: null }` output is a useful input;
its dashed ghost lines can now be plotted with gaps. This does not install Krbn
or add 3D file import. References:

- https://www.w3.org/TR/SVG2/painting.html#StrokeDashing
- https://github.com/vpalos/Krbn/blob/main/API.md#pen-plotters
