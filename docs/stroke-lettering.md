# Stroke lettering

Design > Stroke lettering / caption opens a preview for Technical sans and Script
Hershey fonts. Type printable ASCII (uppercase, lowercase, numbers, punctuation),
choose alignment, spacing and placement, then Preview and Apply lettering.
Unsupported symbols are reported instead of silently disappearing.

New lettering replaces the drawing. Caption below drawing adds text to the current
source; caption height is a percentage of its largest extent (capital height).
Both modes fit the combined geometry to paper. This is not an absolute-size CAD
label placement tool. Undo design restores the previous drawing. Text remains
ordinary polylines through SVG, DXF, JSON and G-code export.

The two fonts are a selected subset of `techninja/hersheytextjs/hersheytext.json`,
blob `199430178bc742f993b7b9e5c235b55e312883f8`, discovered through
https://github.com/golanlevin/p5-single-line-font-resources . Original Hershey font
data was developed by Dr. A. V. Hershey; the JSON port is by James T. Its MIT notice
is retained in `scrib3/fonts/LICENSE-hersheytextjs.txt`. No other fonts or rendering
code from the larger mixed-license archive are bundled.
