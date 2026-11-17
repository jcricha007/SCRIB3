# Compare travel routes

Install the optional optimizer into SCRIB3's Python environment:

```sh
python -m pip install -r requirements-optimizer.txt
```

In Design, choose Compare travel routes, then Compare with vpype. The comparison
runs outside the UI process, can be cancelled, and stops after 30 seconds. It
uses vpype 1.15.0's `linesort --two-opt --passes 8`, without its optional viewer.
Its MIT-licensed project is https://github.com/abey79/vpype .

The preview reports travel in millimeters, including the move from your selected
paper origin. Apply shorter route changes only stroke order/direction. A multiset
comparison rejects lost/changed/duplicated strokes; intentional overdraw and gaps
remain intact. Results that are no better keep the current route. Curve cleanup,
joining and other quality settings are still handled by SCRIB3 before comparison.

The route is used for preview, SVG/DXF/JSON export and reviewed G-code. It is a
session-only choice for the exact drawing and layout; changing either discards it.
Restore built-in route reverses the choice. Applying/restoring invalidates any
previous G-code review. No controller commands are sent by this dialog.
