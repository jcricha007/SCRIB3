from threading import Condition, Timer
from time import monotonic, sleep
from unittest import TestCase

from scrib3.controller import Controller, jog_command, parse_status, setting_changes
from scrib3.firmware import ServoSettings


class FakeSerial:
    """Firmware peer with independently controlled motion and acknowledgements."""
    def __init__(self, *args, **kwargs):
        self.condition = Condition()
        self.rx = bytearray()
        self.writes = []
        self.closed = False
        self.state = "Idle"
        self.settings = {3: 0, 5: 0, 13: 0, 20: 0, 21: 0, 22: 0, 23: 0,
                         24: 25, 25: 500, 26: 250, 27: 1, 30: 1000, 31: 0, 32: 0,
                         100: 250, 101: 250, 110: 500, 111: 500, 120: 10, 121: 10,
                         130: 200, 131: 200}
        self.position = "10,20,0"
        self.wco = "1,2,0"
        self.override = 100
        self.emit_wco = True
        self.reply_status = True
        self.block_jog_ack = False
        self.block_home_ack = False
        self.jog_ack = False
        self.errors = {}
        self.hold_setting = False
        self.fragment = 7
        self.emit("Grbl 1.1h ['$' for help]")

    def emit(self, text):
        with self.condition:
            self.rx.extend((text + "\r\n").encode())
            self.condition.notify_all()

    @property
    def in_waiting(self):
        with self.condition:
            return len(self.rx)

    def read(self, count):
        with self.condition:
            if not self.rx:
                self.condition.wait(.01)
            count = min(count, len(self.rx), self.fragment)
            result = bytes(self.rx[:count])
            del self.rx[:count]
            return result

    def write(self, data):
        self.writes.append(data)
        if data == b"?":
            if self.reply_status:
                wco = f"|WCO:{self.wco}" if self.emit_wco else ""
                self.emit(f"<{self.state}|MPos:{self.position}{wco}|Ov:100,100,{self.override}>")
        elif data == b"\x85":
            if self.state == "Jog":
                self.state = "Idle"
                if self.jog_ack:
                    self.jog_ack = False
                    self.emit("ok")
        elif data == b"\x18":
            self.state = "Alarm"
            self.emit("Grbl 1.1h ['$' for help]")
        else:
            line = data.decode().strip()
            if line in self.errors:
                self.emit(self.errors[line])
            elif line == "$$":
                for number, value in self.settings.items():
                    self.emit(f"${number}={value:g}")
                self.emit("ok")
            elif line == "$I":
                self.emit("[VER:1.1h.20190830:]\nok")
            elif line == "$G":
                self.emit("[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]\nok")
            elif line == "$#":
                self.emit("[G54:1,2,0]\nok")
            elif line.startswith("$J="):
                self.state = "Jog"
                if self.block_jog_ack:
                    self.jog_ack = True
                else:
                    self.emit("ok")
            elif line == "$H":
                self.state = "Home"
                if not self.block_home_ack:
                    self.state = "Idle"
                    self.emit("ok")
            elif line == "$X":
                self.state = "Idle"
                self.emit("ok")
            elif line.startswith("$") and "=" in line:
                number, value = line[1:].split("=")
                self.settings[int(number)] = float(value)
                if not self.hold_setting:
                    self.emit("ok")
            else:
                if line == "G10 L20 P1 X0 Y0":
                    self.wco = self.position
                self.emit("ok")
        return len(data)

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def eventually(predicate, timeout=4):
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if predicate():
            return
        sleep(.01)
    raise AssertionError("Timed out waiting for simulated controller")


class ProtocolTests(TestCase):
    def setUp(self):
        self.peer = FakeSerial()
        self.controller = Controller("test-port", serial_factory=lambda *a, **k: self.peer)
        self.controller.start()
        eventually(lambda: self.controller.snapshot()["connected"])

    def tearDown(self):
        self.controller.close()
        self.controller.thread.join(2)
        self.assertFalse(self.controller.thread.is_alive())

    def run_operation(self, kind, **values):
        self.controller.request(kind, **values)
        eventually(lambda: not self.controller.snapshot()["busy"])

    def test_connection_is_read_only_and_fragmented_reports_keep_positions(self):
        self.assertEqual(set(self.peer.writes), {b"?", b"$I\n", b"$$\n", b"$G\n", b"$#\n"})
        snap = self.controller.snapshot()
        self.assertEqual(snap["work"], (9, 18, 0))
        self.assertEqual(ServoSettings.from_report(snap["report"]).rpm_max, 1000)
        self.peer.settings[13] = 1
        self.peer.emit_wco = False
        self.run_operation("refresh")
        self.assertIsNone(self.controller.snapshot()["work"])
        self.peer.emit_wco = True
        eventually(lambda: self.controller.snapshot()["work"] is not None)
        self.assertAlmostEqual(self.controller.snapshot()["work"][0], 228.6)
        self.controller.close()
        self.controller.thread.join(1)
        self.assertNotIn(b"\x18", self.peer.writes)

    def test_jog_ack_does_not_enable_more_motion_until_idle(self):
        self.run_operation("jog", axis="X", distance=1, feed=300)
        self.assertEqual(self.controller.snapshot()["state"], "Jog")
        self.run_operation("jog", axis="Y", distance=5, feed=300)
        self.assertEqual([w for w in self.peer.writes if w.startswith(b"$J=")],
                         [b"$J=G21 G91 X1.000 F300.000\n"])
        self.controller.cancel_jog()
        eventually(lambda: self.controller.snapshot()["state"] == "Idle")
        self.assertIn(b"\x85", self.peer.writes)

    def test_cancel_works_while_ack_is_delayed_and_double_click_is_rejected(self):
        self.peer.block_jog_ack = True
        self.controller.request("jog", axis="Y", distance=-5, feed=300)
        eventually(lambda: self.peer.state == "Jog")
        with self.assertRaisesRegex(ValueError, "current controller operation"):
            self.controller.request("jog", axis="X", distance=1, feed=300)
        self.controller.cancel_jog()
        eventually(lambda: not self.controller.snapshot()["busy"])
        self.assertEqual(self.controller.snapshot()["state"], "Idle")
        self.assertEqual(sum(w.startswith(b"$J=") for w in self.peer.writes), 1)

    def test_homing_requires_enabled_setting_and_reset_interrupts_long_wait(self):
        self.run_operation("home")
        self.assertNotIn(b"$H\n", self.peer.writes)
        self.run_operation("settings", values={22: 1})
        self.peer.block_home_ack = True
        self.controller.request("home")
        eventually(lambda: self.peer.state == "Home")
        self.controller.reset()
        self.controller.thread.join(1)
        self.assertFalse(self.controller.thread.is_alive())
        self.assertIn(b"\x18", self.peer.writes)
        self.assertNotIn(b"$X\n", self.peer.writes)
        self.assertIsNone(self.controller.snapshot()["work"])

    def test_fresh_status_blocks_motion_when_cached_idle_becomes_run(self):
        self.peer.state = "Run"
        self.run_operation("zero")
        self.run_operation("jog", axis="X", distance=1, feed=300)
        self.assertFalse(any(w.startswith((b"G10", b"$J=")) for w in self.peer.writes))

    def test_eeprom_write_waits_for_ack_before_further_serial_queries(self):
        self.peer.hold_setting = True
        self.controller.request("settings", values={22: 1})
        eventually(lambda: b"$22=1\n" in self.peer.writes)
        count = len(self.peer.writes)
        sleep(.4)
        self.assertEqual(len(self.peer.writes), count)
        self.peer.emit("ok")
        eventually(lambda: not self.controller.snapshot()["busy"])
        self.assertEqual(self.controller.snapshot()["settings"][22], 1)

    def test_partial_settings_failure_reads_back_successes_and_stops_batch(self):
        self.peer.errors["$24=30"] = "error:3"
        self.run_operation("settings", values={22: 1, 24: 30, 25: 600})
        self.assertEqual(self.controller.snapshot()["settings"][22], 1)
        self.assertEqual(self.controller.snapshot()["settings"][24], 25)
        self.assertNotIn(b"$25=600\n", self.peer.writes)
        self.assertIn("$22=1", self.controller.snapshot()["report"])

    def test_origin_and_servo_validation(self):
        self.run_operation("zero")
        commands = [w for w in self.peer.writes if w != b"?"]
        self.assertEqual(commands[-2:], [b"G21 G54 G92.1\n", b"G10 L20 P1 X0 Y0\n"])
        self.assertEqual(self.controller.snapshot()["work"], (0, 0, 0))
        self.run_operation("pen", command="M3 S1000", servo=True)
        self.assertNotIn(b"M3 S1000.000\n", self.peer.writes)
        self.run_operation("pen", command="M3 S100", servo=True)
        self.assertIn(b"M3 S100.000\n", self.peer.writes)
        self.peer.override = 150
        before = len(self.peer.writes)
        self.run_operation("pen", command="M3 S200", servo=True)
        self.assertNotIn(b"M3 S200.000\n", self.peer.writes[before:])
        self.run_operation("pen", command="G1 Z2 F100", servo=False)
        commands = [w for w in self.peer.writes if w != b"?"]
        self.assertEqual(commands[-2:], [b"G21 G90 G94 G54 G49\n", b"G1 Z2.000 F100.000\n"])

    def test_alarm_invalidates_connection_without_retrying(self):
        self.peer.errors["$J=G21 G91 X1.000 F300.000"] = "ALARM:1"
        self.controller.request("jog", axis="X", distance=1, feed=300)
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertFalse(self.controller.snapshot()["connected"])
        self.assertEqual(sum(w.startswith(b"$J=") for w in self.peer.writes), 1)
        self.assertEqual(self.controller.snapshot()["settings"], {})

    def test_lost_status_disconnects_and_clears_snapshot(self):
        self.peer.reply_status = False
        eventually(lambda: not self.controller.thread.is_alive(), timeout=4)
        snap = self.controller.snapshot()
        self.assertFalse(snap["connected"])
        self.assertEqual(snap["report"], "")
        self.assertIsNone(snap["work"])

    def test_missing_ack_aborts_without_retrying_the_move(self):
        self.peer.block_jog_ack = True
        self.controller.request("jog", axis="X", distance=1, feed=300)
        eventually(lambda: not self.controller.thread.is_alive(), timeout=6)
        self.assertIn(b"\x18", self.peer.writes)
        self.assertEqual(sum(w.startswith(b"$J=") for w in self.peer.writes), 1)

    def test_unexpected_restart_clears_live_settings(self):
        self.peer.emit("Grbl 1.1h ['$' for help]")
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertEqual(self.controller.snapshot()["settings"], {})
        self.assertIn("restarted", self.controller.snapshot()["fault"])

    def test_disconnect_during_motion_sends_reset_before_closing(self):
        self.run_operation("jog", axis="X", distance=1, feed=300)
        self.controller.close()
        self.controller.thread.join(1)
        self.assertTrue(self.peer.closed)
        self.assertIn(b"\x18", self.peer.writes)


class ValidationTests(TestCase):
    def test_jog_inputs_cannot_inject_commands_or_round_to_zero(self):
        for axis, distance, feed in (("X\n$H", 1, 300), ("X", "1\n$H", 300),
                                     ("Y", .00001, 300), ("X", float("nan"), 100),
                                     ("X", 101, 300), ("X", 1, "100\nM3 S100")):
            with self.subTest(axis=axis, distance=distance, feed=feed), self.assertRaises(ValueError):
                jog_command(axis, distance, feed)

    def test_setting_dependencies_and_unknown_fields_are_rejected(self):
        for changes in ({20: 1}, {3: .5}, {999: 1}, {30: 0}, {31: float("nan")}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                setting_changes(changes, FakeSerial().settings)

    def test_status_validates_coordinates_and_accepts_work_positions(self):
        self.assertIsNone(parse_status("<Idle|MPos:nan,0,0>"))
        self.assertIsNone(parse_status("hello Arduino"))
        self.assertIsNone(parse_status("<Idle|MPos:0,0>"))
        status = parse_status("<Hold:0|WPos:1,2,3|Pn:XY|WCO:4,5,6>")
        self.assertFalse(status.machine_coordinates)
        self.assertEqual(status.pins, "XY")


class StartupTests(TestCase):
    def test_usb_reset_bootloader_can_drop_the_first_status_query(self):
        peer = FakeSerial()
        peer.rx.clear()
        peer.reply_status = False
        controller = Controller("booting-port", serial_factory=lambda *a, **k: peer)
        def boot():
            peer.reply_status = True
            peer.emit("Grbl 1.1h ['$' for help]")
        timer = Timer(.4, boot)
        timer.start()
        controller.start()
        try:
            eventually(lambda: controller.snapshot()["connected"])
            self.assertFalse(any(w.startswith((b"$J=", b"$H", b"$X")) for w in peer.writes))
        finally:
            timer.join(1)
            controller.close()
            controller.thread.join(1)
