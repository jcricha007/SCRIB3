# John's plotter baseline and acceptance test

The software baseline is **59.06 in/min drawing and travel**. The provisional
hardware current limit is **0.60 A on each X/Y driver**. SCRIB3 applies the
motion profile automatically on connection; current must be set with each
driver's potentiometer and checked with a meter. Neither a PR merge nor a
GRBL command changes or confirms the driver current.

## Hardware and settings

| Item | Recorded baseline or evidence |
| --- | --- |
| Controller | Arduino, GRBL 1.1h / uploaded RC-servo firmware |
| Shield | Xinimark CNC Shield V3 |
| Installed drivers | DRV8825, identified by the supplied EC Buying purchase listing and matching purple modules |
| Current-sense resistors | Upper module: R100 visible in the photos. Confirm both sense resistors on the lower module before using the same Vref target. |
| Motors | McMaster-Carr 6627T66, bipolar NEMA 17, 1.8°, 0.7 A maximum per phase, 9.82 Ω per phase |
| Trial current limit | 0.60 A per driver; not yet physically measured or validated |
| Drawing feed / X/Y maximum rate | 59.06 in/min / 1,500 mm/min |
| X/Y acceleration / junction deviation | 25 mm/s² / 0.020 mm |
| Manual jog feed | 1,500 mm/min, independent of drawing feed |
| X/Y calibration | Reported 5.000 steps/mm (127 steps/in); verify against measured travel |
| Pen | Up: `M3 S180`; down: `M3 S70`; settle: 0.5 s |
| Paper | Letter landscape; 11-inch edge along Y; top-left home; +Y right, −X down |
| Stepper idle delay | Reported `$1=25`; automatic setup leaves this unchanged |

The last reported `$130/$131=200` values do not prove physical travel. Full
Letter requires 215.9 mm of negative X and 279.4 mm of positive Y from home.
Measure the usable envelope; do not enlarge configured limits to make a job
pass review. See [paper and motion setup](smooth-motion-paper.md).

## Set the provisional current limit

For a DRV8825, `I_limit = Vref / (5 × R_sense)`. With confirmed R100 resistors,
`R_sense = 0.100 Ω`, so `Vref = I_limit / 2`:

| Current limit | Calculated Vref with R100 | Purpose |
| --- | --- | --- |
| 0.50 A | 0.250 V | Lower-current comparison if needed |
| **0.60 A** | **0.300 V** | **Requested starting target on each driver** |
| 0.70 A | 0.350 V | Motor's nominal maximum phase-current rating, not the trial target |

These are nominal calculations. TI notes reduced current accuracy below
1 V Vref, so 0.300 V does not certify exactly 0.600 A of coil current. Do not
apply the earlier A4988 voltage calculation to these drivers. Do not increase
the limit above the motor rating to compensate for reduced torque.

1. Stop all motion. With both USB and motor power off, identify X and Y from
   the shield labels, confirm the sense-resistor markings, and identify a
   known GND and the module maker's VREF test point. Do not infer the test
   point solely from the adjustment screw's appearance.
2. Set the multimeter to DC volts with leads in **COM** and **V**, not a current
   socket. Keep the motor connectors seated. Restore power with the controller
   Idle; opening USB can reset the board and move the pen servo. Measure VREF
   relative to GND on each module, avoiding adjacent contacts. Record both
   initial readings before adjusting anything.
3. Follow the module maker's adjustment procedure. A cautious approach is to
   turn both supplies off, make a tiny adjustment with an insulated tool, then
   repower and remeasure. Repeat toward **0.300 V** for each confirmed R100
   driver; do not assume a clockwise turn increases Vref. Record final readings.
4. Remove probes before motion. Reconnect SCRIB3 if needed and re-establish
   paper zero/home after a reset or power cycle. Never unplug a motor or move
   a driver module while powered.

Power-supply current is not coil current. Full-step winding current is about
70.7% of the configured limit; microstepping varies the winding currents.
Keep the existing microstep jumpers and steps/mm unchanged during this trial.
Changing microstepping requires separate recalibration.

## Run the acceptance test

1. **Confirm startup.** Update and launch after merging. Wait for Idle and
   automatic setup to finish. Check drawing feed **59.06 in/min** and readback
   `$110=$111=1500`, `$120=$121=25`, `$11=0.020`. There is no required
   **Apply app + controller** step. Check that motor power is actually on:
   USB communication and `ok` replies alone do not prove powered movement.
2. **Check direction and return.** Raise the pen and mark its physical starting
   position at the top-left reference, then select **Control → Set home**.
   With one inch of measured clearance right and down, set jog distance to
   **1 in** and use **Y+**, **X−**, **Y−**, **X+**, waiting for Idle each time.
   This traces a one-inch square at the slower jog feed. Measure both sides
   and check return to the physical mark; displayed zero alone cannot detect
   lost steps. At 5 steps/mm a one-inch command rounds to available 0.2 mm steps.
3. **Check the drawing motion with the pen up.** In Design, keep the top-left
   mounting and use a temporary **4 × 3 in** paper area with **0.25 in** margin,
   within measured usable travel. Import [seam-check.svg](../examples/seam-check.svg)
   or [seam-check.dxf](../examples/seam-check.dxf), then **Fit to paper**.
   Re-establish home after any layout/reference change. Open a fresh **Review
   G-code**, keep **Pen-up test** selected, and run. The reviewed paths should
   stay in negative X and positive Y. After Idle, use **Go home** and compare
   with the physical mark without moving the axes by hand.
4. **Compare seams with ink.** Run separate copies of the same seam-check
   drawing at overlap **0** and **0.5 mm**, keeping feed, pen, paper size, and
   settle time unchanged. Set overlap in **Plot quality**, apply/save,
   and open a new review for each run; uncheck Pen-up test for ink. The two
   circles and square should close; the bottom arc must remain open. Then test
   **Rosette**, detail **12**, at the preferred overlap. Record any seam gap,
   mid-stroke gap, darkened seam, stall, or displaced return position.
5. **Check a longer run.** If short tests pass, repeat drawings for about
   15 minutes while attended. Measure each motor's case temperature at the
   same location before motion and at 5, 10, and 15 minutes, recording ambient
   temperature too. Check return position again after the run. Feed is a
   requested maximum: the retained acceleration and short curves can prevent
   reaching 59.06 in/min. This test evaluates the chosen profile on these paths.

Stop the test if motion stalls, binds, loses position, or the driver cuts out.
Resolve the cause and re-establish home before continuing. Reset can lower
the pen on the installed servo firmware. Lowering speed does not lower the
driver's current limit; airflow and reducing mechanical binding may also help.

`$1=25` releases motor holding current shortly after motion stops; `$1=255`
would keep it enabled. Release reduces holding torque, so do not rely on the
saved reference if the carriage shifts. Warmth by touch is not a temperature
measurement. The motor listing's 266°F Class B insulation maximum is not a
case-temperature target. Confirm the applicable manufacturer temperature
limit before treating a temperature result as thermal acceptance; a short
run and an apparently stable trend do not establish long-duration limits.

## Record results before adopting the baseline

| Observation | X | Y |
| --- | --- | --- |
| Sense-resistor marking confirmed | Pending | Pending |
| Initial Vref (V) | Pending | Pending |
| Final Vref (V), target 0.300 for R100 | Pending | Pending |
| Measured one-inch jog (in or mm) | Pending | Pending |
| Return error after short / long run (mm) | Pending | Pending |
| Motor case at start / 5 / 10 / 15 min (°C) | Pending | Pending |

Also record ambient temperature, test duration, paper size, overlap, seam
results, and any abnormal noise or motion. The 0.60 A setting remains
provisional until measured Vref, repeatable positioning, acceptable line
quality, and an appropriate thermal check support it. No physical current
adjustment or hardware acceptance result is asserted by this PR.

Sources: John's supplied motor screenshot, driver purchase listing, board
photos, GRBL log, and reported speed trial;
[TI DRV8825 datasheet, current regulation and Vref limits](https://www.ti.com/lit/ds/symlink/drv8825.pdf);
[Pololu DRV8825 current limiting](https://www.pololu.com/product/2133/)
(reference circuit; confirm the clone module's components and test point);
[GRBL settings](https://github.com/gnea/grbl/wiki/Grbl-v1.1-Configuration).
