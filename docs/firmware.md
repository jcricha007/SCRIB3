# Supplied GRBL firmware

The 39 source files supplied on November 11, 2026 identify GRBL 1.1h, build 20190830, with an RC-servo modification. SCRIB3's **Uploaded RC-servo** profile describes these specific sources. The controller's version banner alone cannot identify this modification.

## Configuration in the supplied sources

| Item | Source configuration |
| --- | --- |
| CPU target | ATmega328P with the Arduino Uno pin map |
| Serial connection | 115200 baud |
| Pen signal | D11, timer 2, fast PWM with a 1024 prescaler |
| Pen-position commands | M3 with an S value, or M5 |
| Servo timer endpoints | 7 and 31, with inverted direction enabled |
| Homing sequence | X and Y together |
| Initial settings template | Generic defaults, including 250 steps/mm, 500 mm/min maximum axis rate, and 200 mm axis travel |
| Initial spindle settings | $30=1000, $31=0, $32=0 |

The values in defaults.h initialize EEPROM when stored settings cannot be read. A controller with existing settings can report different values. Measure the assembled machine and calibrate it before treating its travel or steps/mm as established.

## Servo mapping

With laser mode disabled and the spindle override at 100%, the supplied spindle_control.c calculates the timer count for M3 from the following expression.

~~~text
floor(31 - S * (100 / ($30 - $31)))
~~~

M5 selects timer count 31. Startup and reset also call spindle_stop(), which selects that same position. Opening the USB serial connection can therefore reset the board and move the servo.

The mapping's direction identifies how the signal changes. The linkage determines which position raises the pen. S values are firmware-scaled inputs and require calibration against observed lift motion.

For the source defaults, the expression gives the following reference values.

| S value | Calculated timer count |
| --- | --- |
| 0 | 31 |
| 100 | 21 |
| 200 | 11 |
| 240 | 7 |
| 250 | 6 |
| 1000 | -69 before conversion to uint8_t |

These are calculated reference values. The source expression can exceed its declared endpoint range, and negative results are outside the uint8_t conversion range. SCRIB3 rejects commands outside timer counts 7 through 31 when the uploaded profile is selected. It also rejects commands that quantize to the same timer count.

The profile uses reported $30/$31 values, requires $32=0 and spindle override 100%, and checks the S value after G-code formatting. These checks use a settings snapshot. Read GRBL again after changing the controller settings or override. The mechanically usable servo travel still needs to be established on the assembled plotter.

## First setup step

1. With the plotter idle, connect the Arduino over USB.
2. Select **Machine → Firmware profile → Uploaded RC-servo** in SCRIB3.
3. Choose **Find ports**, select the Arduino port, and select **Read GRBL**.
4. Copy the resulting report for review. It includes the build information, settings, parser modes, coordinate offsets, and override status.

A previous successful G-code file is optional. After checking the installed firmware and calibrating the lift, use a small generated drawing to establish the first plot.

## Source provenance

The compatibility profile was reviewed against these supplied files.

| File | SHA-256 |
| --- | --- |
| config.h | 9d5a7d4d1f7ae062c70d5f9d9eb00136f81d9cc04c3883041543af950cf895ca |
| spindle_control.c | 9cd9577ac0f6718269a074f30c6ad17ac1d5c3f382835c937b80a1d6a9e84a47 |
| cpu_map.h | 90b2f7a63b819ef8bc69fa34ecb27e101c99157a05569da9c2d2389d57f32045 |
| defaults.h | 277cd8e095fb811dc2102690d0266ae1a1f9e134ecf010ef15f55ccaa36036ba |
| grbl.h | 37882d5466dd0649b82caca588588975c86b5f7c7968623a8b094fdc14ce9aeb |
