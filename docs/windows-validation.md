# Windows integration validation - 23 November 2026

The cloud upgrade at `f70a40402865472133b7e07c485e0a6559f0813b` has been
reconciled with the Windows work through `73f22dc`. The supplied ZIP matched
SHA-256 `ec2dfe61774b9d13635c9076a758d9671af56d573c2270dea860aa9c59cfd796`.
The original Windows worktree and unfinished draft were preserved separately.

## Included and retained

- Expanded canvas: selection, transformations, colored layers and order, save/load,
  undo/redo, fill/offset/arrays, physical SVG import with clipping and occlusion.
- Photo art, mesh edge projection, local GeoJSON, QR codes, patterns and twelve
  stroke fonts. Existing version-1 boards, custom bed guides and Tabloid paper work.
- GRBL current-pen and sequential color review. The Windows synchronized Stop
  logic, inactive DTR/RTS request, first-point hold, preset migration and compact
  workbench remain. Each pass uses the same origin and quality-processing options.
- Calibrated P1S/H2S G-code and experimental sliced-plate export, with explicit
  shrink-to-reach, per-model metadata, checksum, preview and pen-up default.
- Both CI workflows install pytest and collect function tests as well as classes.

## Checks

A new Windows Python 3.12.10 environment was created with the shipped launcher.
`Run-SCRIB3.ps1 -Check` completed successfully and `pip check` found no broken
requirements. The full native Tk regression result is recorded in PR #25.

The focused editor/import/printer run passed 23 tests and 8 subtests. It checks
legacy-board reopening, bed guides, actual canvas events, color sequencing,
100,001-point review, holder bounds, SVG geometry, fonts and export structure.
A separate 3,000-path native editor smoke selected, rotated and fitted a drawing,
then generated pen-up GRBL, P1S and H2S output.

The included demo exported for P1S at 82.828% and H2S at 100% using synthetic
software-test calibration. All three pens use shared page registration. Both
archives passed ZIP and MD5 checks and contained no contact-height moves in
pen-up mode. These fixtures are not measured hardware calibration.

## Remaining acceptance

Bambu Studio could not be opened because desktop-access approval timed out.
Desktop import/preview and printer pause/resume behavior are unverified. No
hardware motion was sent. Calibrate the actual holder and perform small pen-up
checks on the GRBL plotter, P1S and H2S before an ink run. Inactive modem lines
reduce reset pulses but do not guarantee driver/firmware startup behavior.

Full 3dplotter parity is not claimed: individual node editing, the complete tool
catalog, online maps, integrated cloud image generation and direct network
printer transmission remain future work. See [the studio guide](drawing-studio.md).
