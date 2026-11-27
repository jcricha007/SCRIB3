# Drawing studio and printer output

SCRIB3 starts with **Machine & calibration → Control**. Select the Arduino port and baud and click **Connect**, or choose **Auto detect**. Here you can jog X/Y, operate the pen, establish a manual home and paper zero, and open **Setup** for calibration. **Open drawing board** opens the artwork editor in a second, independently movable window. The machine window shows the board and its active pen. Closing the board keeps its contents in this session. Quitting from the machine window prompts to save a changed board.

Use **Board → Machine & calibration** to bring the GRBL controls forward. The original **Design** tab still prepares a workbench drawing, which you can place using **Board → Add workbench artwork**.

## Edit artwork

- On SVG import, choose **Keep SVG page coordinates** for layers exported from a common artboard. Two marks 100 mm apart in the source stay 100 mm apart when imported separately. **Center at true size** positions each file independently. **Fit to paper** scales its visible artwork. Color strokes become pen layers. Filled areas can produce outlines, hatching or concentric paths. Opaque shapes hide covered lines when that option is selected. Shape and group clipping, nested transforms, dashes, fill rules and invisible guides are handled. Flatten masks/filters and convert SVG text to paths first.
- Use Select, Shift-click, or drag a box. **Select all** includes every visible unlocked path, including drawings with hundreds of paths. Drag to move the selection, the square handle to scale, or the round handle to rotate. Transform accepts exact scale, angle and translation. Rotate 90°, Center and Fit to paper are available beside the canvas.
- Paper presets include A4, Letter, A3, A5 and Tabloid. The Bed menu retains P1S/H2S and custom centered guides. Swap orientation changes paper dimensions. To turn a portrait drawing sideways, select it, Rotate 90°, then Fit to paper.
- Draw freehand, a line, rectangle, ellipse, star, pentagon or a four-point cubic Bézier. **Edit nodes** lets you select a stroke and drag its vertices or cubic control handles. Imported cubic paths retain their handles when clipping, dashing or fill conversion has not changed their geometry. The eraser removes a whole stroke. Grid snap uses 1 mm increments. Pan and wheel zoom change only the view.
- Choose pen colors, recolor selections, hide or lock layers, and change pass order. Fill, offset, array and path cleanup operate on the selection. **Edit → Preview line cleanup** overlays the original in orange and the result in blue. Set smoothing tolerance and pen width in millimeters, then zoom over a detail to compare. The preview reports point counts, between-stroke lifts and exact repeats. Click **Apply** to commit or **Cancel** to keep the selection as drawn. Cleanup protects sharp corners, authored lettering and editable cubics. Duplicate removal and endpoint joining operate within each pen and group.
- Save editable `.scrib3` boards, including color order, paper dimensions and layer state. Existing version-1 Windows boards are accepted. Export SVG retains physical page size and separate pen groups.

Use **Edit → Name group** to organize a selection or **Select named group** to pick an imported group. Select a stroke of SCRIB3 lettering and use **Edit → Edit lettering** to change its text, height or font in place. **Edit → Save selection as element** and **Import → Saved element** reuse a logo or title across projects. Each insertion can be edited independently. On macOS, use Command+A to select all and Command+Z to undo. Control shortcuts also work.

The board supports 16,000 paths and 400,000 points. Undo keeps up to 32 states. The `.scrib3` file stores editable lettering, cubic handles and nested groups. Existing version-1 boards open directly. Play shows paths in document order.

## Create drawings

**Create** provides twelve Hershey stroke-font families, six procedural patterns, QR codes, contour offsets and linear/radial repetition. Fill modes are horizontal, vertical, diagonal, crosshatch and concentric. The bundled Hershey data retains its upstream MIT license.

**Import → Photo art** converts tone to engraving lines, squiggles, small stipple loops or thresholded scanlines. Ordinary image import offers the existing centerline/outline tracing preview. For white-on-blue blueprint images, use the tracing dialog's light-ink-on-dark-background option. Text and fine features remain approximations at the source image resolution.

**Import → 3D model** accepts STL, OBJ and mesh 3MF. Yaw and pitch set an orthographic view; choose visible feature edges, all feature edges, or wireframe. The visible-edge mode removes occluded edge intervals using triangle depths. It is a mesh projection, not CAD surface reconstruction. Files are limited to 50 MB and 60,000 faces.

**Import → Engineering drawing sheet** projects a Z-up STL, OBJ or mesh 3MF into third-angle top, front and right views plus an isometric view. Preview an individual view or the full sheet. Choose current paper, A4 or Letter and enter a single scale in millimeters per model unit, or leave it blank to fit. **Apply four views** adds grouped geometry and editable lettering to the board. Save a reusable border, title block and logo with **Board → Save sheet template**. **Board → New from template** starts the next sheet with that furniture and its paper size.

**Import → GeoJSON map** accepts a local WGS84 FeatureCollection. Roads, buildings and water can use separate pens; city-scale longitude/latitude proportions use a local equirectangular projection. There is no online map downloader. QR paths use closely spaced pen strokes; scan the physical result before using it as a label.

## Output targets

| Target | Output | Registration |
| --- | --- | --- |
| Current Arduino GRBL plotter | In-app reviewed execution or G-code | Each color uses the same board origin and paper dimensions, with the configured machine mounting |
| Bambu P1S | G-code or experimental sliced `.gcode.3mf` | 256 × 256 mm bed, further restricted by holder offsets, clearances and the front-left exclusion |
| Bambu H2S | G-code or experimental sliced `.gcode.3mf` | 340 × 320 mm bed, further restricted by holder offsets and clearances |

For GRBL, use **Output → Current pen to GRBL** or **All pens to GRBL**. Configure the existing machine workbench and establish paper zero first. All-pens mode reviews each pass and asks for a pen change after confirmed completion. A stop, failure, controller replacement, reference change or board edit prevents automatic advancement. Hidden layers are omitted. Each pass starts with the pen-up test selected unless the preceding completed pass was reviewed for ink.

## P1S holder setup and registration

1. In **Machine & calibration**, choose **P1S setup → Guided holder setup**. At one carriage position, measure nozzle and tip XY relative to the same reference, or enter the tip-minus-nozzle offsets directly. Enter the Z heights for light contact and for lifted travel with your paper and holder. Review the clip clearances, then **Apply measurements**. **Save holder** keeps the P1S settings for later sessions.
2. Preview **A4 pen-up footprint**. This job stays at lift Z. Its rectangle and center cross use the common page placement. Select **Shrink paper to reach** to fit the planned A4 layout within the calibrated travel. Use the physical width, height and front-left coordinates shown in the review to position the stock. **Show pen-up travel** overlays moves between strokes.
3. Check the pen lines and travel in SCRIB3. Choose **Open in Bambu Studio** and save the reviewed `.gcode.3mf`. SCRIB3 passes that exact file to the local Studio installation. In the default Studio preview, these extrusion-free jobs can show a bare bed. The job homes with the pen and any obstructing attachment removed, then pauses for installation. Inspect the physical footprint before an ink run.
4. Choose **Two-pen registration** and preview the 50 × 50 mm sheet. Start with **Pen-up test**. For the ink check, clear that box after confirming the holder and paper position. Change pens at the programmed pause, keeping the paper and holder reference fixed. The second pen's five diamonds should center on the first pen's crosses. The same transform places both passes.
5. Choose **Current drawing board** to review the visible pen layers using the same measured setup. Export G-code or a sliced plate. In the machine window, **GRBL controls** returns to the Arduino session.

The H2S export dialog remains under **Drawing board → Output → Bambu H2S**. Its existing holder fields accept measured tip offsets, contact/lift Z and clearances. Both profiles check reachable nozzle and pen-tip coordinates, start with heaters off and include the first-point dwell. Physical travel, light pen pressure and pen-change registration need confirmation on the installed holder.

## Run controls

Drawing, jogging and automatic X/Y maximum travel rates start at **1,500 mm/min** (59.055 in/min). Existing schema-7 custom draw/jog values remain unless they equal the previous defaults; subsequent schema-8 custom values are preserved. The automatic controller profile sets maximum rates to 1,500, acceleration to 25 mm/s² and junction deviation to 0.020 mm. Disable automatic motion setup to keep custom controller tuning.

A normal **Stop print** stops sending further drawing commands, lets already accepted moves finish, raises the pen, and retains the connection, settings and home/paper reference. Stopping from pause resumes the already accepted buffer so it can drain. It is a controlled stop, so motion can continue briefly. **Reset / abort**, a disconnect, a firmware restart or an alarm still invalidates the reference. The uploaded servo firmware can move the pen on startup/reset; this build does not change that firmware.

## Remaining parity work

Possible future additions include more stroke fonts, live map sources and direct printer-network transfer. [Windows workbench validation](windows-validation.md)

## Format reference

Bambu Studio 2.9.2.62 on Linux opened both the P1S pen-up footprint and two-pen registration archives as sliced P1S plates. SCRIB3 tests check the G-code bytes and checksum, pen-change pauses, commanded heights and XY registration. [Bambu Studio archive reader and writer](https://github.com/bambulab/BambuStudio/blob/v02.09.02.62/src/libslic3r/Format/bbs_3mf.cpp)
