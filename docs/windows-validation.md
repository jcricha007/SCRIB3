# Windows validation and remaining integration

This branch publishes the Windows board editor and GRBL run-control work built
on main `7a60edab778ae73ef9328ac1d76df7855ac18e27`.

## Included

- Paper-space board editor: path selection, move/rotate/scale handles, numeric
  transforms, paper fit and alignment, shapes, lettering, Bezier drawing,
  hatching, colored layers, lock/hide, undo/redo, editable board save/load and SVG export.
- Registered GRBL pen passes and importing the workbench drawing onto the board.
- Controlled Stop print drains queued motion, raises the pen and keeps the serial
  session and existing reference. Emergency reset remains a separate action.
- A five-second pen-up hold at the first drawing point and 1,500 mm/min defaults.
- Inactive DTR/RTS requested before serial open to reduce Arduino reset pulses.
- Compact workbench controls and larger board job limits.
- CI uses pytest to collect both unittest classes and pytest function tests.

## Validation

On 2026-11-23, Python 3.12.10 / pytest 9.1.1 on Windows ran the entire test suite
with `SCRIB3_DESKTOP_TESTS=1`. Native Tk checks ran alongside simulated GRBL
controller tests. Results for the final published tree are recorded in the PR.
No physical controller was connected and no drawing job was sent to hardware.
Inactive modem lines cannot guarantee that an Arduino driver never pulses reset.

## Still pending

The earlier cloud upgrade package is not present in this Windows checkout.
Its additional creator tools, richer SVG processing, font collection, and Bambu
printer export workflow have not been integrated into this branch. The draft PR
must not be described as full 3dplotter parity or qualified P1S/H2S support.

Bed outlines are layout guides, not printer-output profiles. The uncommitted
printer-output draft is preserved separately from this published source until
its missing packaging and UI integration can be reconciled with the cloud work.
Physical GRBL acceptance and calibrated pen-holder checks on P1S/H2S remain open.

The missing package is `SCRIB3-studio-upgrade.zip`, expected SHA-256
`ec2dfe61774b9d13635c9076a758d9671af56d573c2270dea860aa9c59cfd796`.
