# Guided travel calibration

Open **Control → Setup → Motion → Guided calibration…** while connected and Idle. The guide reads the Arduino rather than assuming its stored settings match the application's defaults.

The bundled starting values are X/Y **5.000 steps/mm**, equivalent to **127 steps/in**. These come from John's measurement: 250 × 0.1 / 5 = 5. They are a starting correction, not a claim of verified accuracy. The pen defaults remain up `M3 S180` and down `M3 S70`.

## First setup

1. If the controller still shows 250 steps/mm, choose **Apply saved X/Y starting calibration**. This writes only the differing X/Y steps settings. Connection and preset loading never apply settings automatically.
2. Wait for readback, then use **Control → Reset / abort**, reconnect, and reopen the guide. Reset can lower the pen to the firmware's original M5 position. Keep its tip clear. Motion stays blocked after a steps/mm change until reset/reconnection; disconnecting with a pending calibration reset also resets the controller.
3. Select X or Y, a direction with clear travel, and a small requested distance. The default is 0.1 inch / 2.54 mm. Tests are limited to 10 mm at 25 mm/min. **Raise pen + test move** uses the configured lift command and waits at least 0.5 seconds before jogging. **Cancel test** discards the measurement; the regular Cancel jog and Reset / abort controls remain available.
4. Wait for Idle. Measure the physical travel of the carriage relative to the frame with a ruler or caliper. Enter that positive distance in the units displayed by the guide. It captures its units when opened.
5. **Calculate correction** previews the new steps/mm. **Apply measured correction** writes only the tested axis, checks the readback, and saves the updated application preset. Reset/reconnect and repeat the measurement to verify it, then calibrate the other axis.
6. Re-establish manual home/paper zero after calibration. Set usable travel and drawing feed separately before exporting a job.

The correction is `current steps/mm × controller test travel ÷ measured physical travel`. The guide uses completed controller travel, accounting for whole-step rounding. At 5 steps/mm, a 2.54 mm request can round to 13 steps, or 2.6 mm. A ruler measurement of 2.6 mm should therefore retain 5 steps/mm. For a finer scale measurement, use a longer test up to the 10 mm limit after confirming small moves are correct.

The guide rejects interrupted tests, changed positions/settings, missing coordinates, connection changes, and nonpositive measurements. It will not infer actual travel from GRBL's reported position: that position is calculated from commanded steps and is not an independent sensor measurement. Fully automatic physical calibration would require additional measurement hardware. Switch homing remains a separate feature and is not enabled by this guide.

References: [GRBL settings](https://github.com/gnea/grbl/wiki/Grbl-v1.1-Configuration), plus the uploaded firmware's `settings.c`, `planner.c`, and `jog.c`.
