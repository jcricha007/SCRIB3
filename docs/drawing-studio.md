# Drawing studio and printer output

SCRIB3 now opens a paper editor. **Board → Machine workbench** opens the existing GRBL connection, setup, calibration and Ollama tools. **Board editor** returns to the drawing. The two workspaces keep their own drawings; **Board → Add workbench artwork** adds the fitted workbench drawing to the board.

## Edit artwork

- Import an SVG at its physical size or fit it to the paper. Color strokes become pen layers. Filled areas can produce outlines, hatching or concentric paths. Opaque shapes hide covered lines when that option is selected. Shape and group clipping, nested transforms, dashes, fill rules and invisible guides are handled. Flatten masks/filters and convert SVG text to paths first.
- Use Select, Shift-click, or drag a box. **Select all** includes every visible unlocked path, including drawings with hundreds of paths. Drag to move the selection, the square handle to scale, or the round handle to rotate. Transform accepts exact scale, angle and translation. Rotate 90°, Center and Fit to paper are available beside the canvas.
- Paper presets include A4, Letter, A3, A5 and Tabloid. The Bed menu retains P1S/H2S and custom centered guides. Swap orientation changes paper dimensions. To turn a portrait drawing sideways, select it, Rotate 90°, then Fit to paper.
- Draw freehand, a line, rectangle, ellipse, star, pentagon or a four-point cubic Bezier. The eraser removes a whole stroke. Grid snap uses 1 mm increments. Pan and wheel zoom change only the view.
- Choose pen colors, recolor selections, hide or lock layers, and change pass order. Fill, offset, array and path cleanup operate on the selection. Cleanup offers bounded simplification, exact duplicate removal and exact-endpoint joining. Undo restores geometry after these operations.
- Save editable `.scrib3` boards, including color order, paper dimensions and layer state. Existing version-1 Windows boards are accepted. Export SVG retains physical page size and separate pen groups.

The board supports 16,000 paths and 400,000 points. Undo keeps up to 32 board states. The editor currently works on complete strokes and sampled curves; individual node and Bezier-control-point editing are pending. Play shows paths in document order; it is not an execution-time or firmware simulator.

## Create drawings

**Create** provides twelve Hershey stroke-font families, six procedural patterns, QR codes, contour offsets and linear/radial repetition. Fill modes are horizontal, vertical, diagonal, crosshatch and concentric. The bundled Hershey data retains its upstream MIT license.

**Import → Photo art** converts tone to engraving lines, squiggles, small stipple loops or thresholded scanlines. Ordinary image import offers the existing centerline/outline tracing preview. For white-on-blue blueprint images, use the tracing dialog's light-ink-on-dark-background option. Text and fine features remain approximations at the source image resolution.

**Import → 3D model** accepts STL, OBJ and mesh 3MF. Yaw and pitch set an orthographic view; choose visible feature edges, all feature edges, or wireframe. The visible-edge mode removes occluded edge intervals using triangle depths. It is a mesh projection, not CAD surface reconstruction. Files are limited to 50 MB and 60,000 faces.

**Import → GeoJSON map** accepts a local WGS84 FeatureCollection. Roads, buildings and water can use separate pens; city-scale longitude/latitude proportions use a local equirectangular projection. There is no online map downloader. QR paths use closely spaced pen strokes; scan the physical result before using it as a label.

## Output targets

| Target | Output | Registration |
| --- | --- | --- |
| Current Arduino GRBL plotter | In-app reviewed execution or G-code | Each color uses the same board origin and paper dimensions, with the configured machine mounting |
| Bambu P1S | G-code or experimental sliced `.gcode.3mf` | 256 × 256 mm bed, further restricted by holder offsets, clearances and the front-left exclusion |
| Bambu H2S | G-code or experimental sliced `.gcode.3mf` | 340 × 320 mm bed, further restricted by holder offsets and clearances |

For GRBL, use **Output → Current pen to GRBL** or **All pens to GRBL**. Configure the existing machine workbench and establish paper zero first. All-pens mode reviews each pass and asks for a pen change after confirmed completion. A stop, failure, controller replacement, reference change or board edit prevents automatic advancement. Hidden layers are omitted. Each pass starts with the pen-up test selected unless the preceding completed pass was reviewed for ink.

## Bambu holder setup

1. Open **Output → Bambu P1S/H2S**. Enter measured tip offsets, contact Z and lift Z. Tip offset means **pen tip coordinate minus nozzle coordinate**. The app leaves these fields blank until you supply measurements.
2. Enter nozzle travel clearances for the installed holder and clips. The P1S profile additionally requires at least 18 mm of left clearance or 28 mm of front clearance. The app intersects reachable pen-tip travel with the bed and rejects unreachable or rounded out-of-bounds coordinates.
3. Preview the complete page. The review shows its physical front-left location, size, scale and pen count. A4 landscape requires shrinking on a P1S. Enable **Shrink paper to reach** explicitly when needed. Every pen uses the same transformation.
4. Export with **Pen-up test** selected first. The job commands heaters off and homes, lifts, then pauses for installation of the calibrated pen/holder. Start with a cool printer and remove the pen and any obstructing holder before homing. The file pauses again between pen colors and ends raised. It holds five seconds at the first drawing point.
5. Inspect the file in Bambu Studio before a physical run. The `.gcode.3mf` contains pre-generated motion, metadata, a checksum and thumbnails. It contains no printable solid; do not re-slice it as a model. Import/preview behavior, pause/resume behavior and the actual holder geometry still need validation on each printer.

The archive structure, checksums, shared registration, pen-up state, finite calibration and travel limits are tested in software. Bambu Studio acceptance and P1S/H2S motion have **not** been tested on hardware. No network upload or direct printer control is included. Time estimates cover constant-speed travel/drawing and lifts, excluding acceleration, homing and manual pauses.

## Run controls

Drawing, jogging and automatic X/Y maximum travel rates start at **1,500 mm/min** (59.055 in/min). Existing schema-7 custom draw/jog values remain unless they equal the previous defaults; subsequent schema-8 custom values are preserved. The automatic controller profile sets maximum rates to 1,500, acceleration to 25 mm/s² and junction deviation to 0.020 mm. Disable automatic motion setup to keep custom controller tuning.

A normal **Stop print** stops sending further drawing commands, lets already accepted moves finish, raises the pen, and retains the connection, settings and home/paper reference. Stopping from pause resumes the already accepted buffer so it can drain. It is a controlled stop, so motion can continue briefly. **Reset / abort**, a disconnect, a firmware restart or an alarm still invalidates the reference. The uploaded servo firmware can move the pen on startup/reset; this build does not change that firmware.

## Remaining parity work

The reference application's complete catalog of roughly 80 tools, all font families, cloud/account features, integrated AI image generation, live maps, individual node editing and device network transmission remain outside this build. The implemented import, editing, tracing, creation and export paths are functional and tested; full 3dplotter parity is not claimed.

The cloud package has been reconciled with the Windows branch at `73f22dc`. Windows serial-open behavior, controlled-stop synchronization, compact controls, bed guides and registered quality processing are retained. See [Windows validation](windows-validation.md).

## Format reference

The sliced-plate metadata and paths were cross-checked against the [Bambu Studio archive reader and writer](https://github.com/bambulab/BambuStudio/blob/355d71eee5a9ebc794693fe57e63674806019770/src/libslic3r/Format/bbs_3mf.cpp). This source review supplements the archive tests; it does not establish desktop or printer acceptance.
