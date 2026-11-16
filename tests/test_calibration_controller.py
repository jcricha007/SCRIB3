from unittest import TestCase
from scrib3.controller import Controller
from test_controller import FakeSerial, eventually


class CalibrationProtocolTests(TestCase):
    def setUp(self):
        self.peer = FakeSerial()
        self.controller = Controller('test', serial_factory=lambda *a, **k: self.peer)
        self.controller.start()
        eventually(lambda: self.controller.snapshot()['connected'])

    def tearDown(self):
        self.controller.close()
        self.controller.thread.join(2)

    def test_steps_changes_are_explicit_and_motion_is_blocked_until_new_session(self):
        self.assertNotIn(b'$100=5\n', self.peer.writes)
        operation = self.controller.request('settings', values={100: 5, 101: 5})
        eventually(lambda: not self.controller.snapshot()['busy'])
        snap = self.controller.snapshot()
        self.assertEqual(snap['last_result'], (operation, 'settings', None))
        self.assertTrue(snap['reset_required'])
        self.assertEqual((snap['settings'][100], snap['settings'][101]), (5, 5))
        self.controller.request('jog', axis='X', distance=2.54, feed=25)
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertIn('Reset', self.controller.snapshot()['last_result'][2])
        self.assertFalse(any(line.startswith(b'$J=') for line in self.peer.writes))
        self.controller.reset(); self.controller.thread.join(2)
        self.peer.state = 'Idle'
        self.controller = Controller('test', serial_factory=lambda *a, **k: self.peer)
        self.controller.start()
        eventually(lambda: self.controller.snapshot()['connected'])
        self.assertFalse(self.controller.snapshot()['reset_required'])
        self.assertEqual(self.controller.snapshot()['settings'][100], 5)

    def test_calibration_lifts_then_jogs_and_refuses_oversized_tests(self):
        self.controller.request('calibration_jog', axis='X', distance=11, feed=25, command='M3 S180', servo=True)
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertNotIn(b'M3 S180.000\n', self.peer.writes)
        self.controller.request('calibration_jog', axis='Y', distance=-2.54, feed=25, command='M3 S180', servo=True)
        eventually(lambda: not self.controller.snapshot()['busy'])
        commands = [w for w in self.peer.writes if w != b'?']
        self.assertEqual(commands[-3:], [b'M3 S180.000\n', b'G4 P0.500\n', b'$J=G21 G91 Y-2.540 F25.000\n'])

    def test_cancel_during_lift_prevents_calibration_motion(self):
        self.peer.block_dwell = True
        self.controller.request('calibration_jog', axis='X', distance=2.54, feed=25, command='M3 S180', servo=True)
        eventually(lambda: b'G4 P0.500\n' in self.peer.writes)
        self.controller.cancel_jog()
        eventually(lambda: b'\x85' in self.peer.writes)
        self.peer.emit('ok')
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertFalse(any(w.startswith(b'$J=') for w in self.peer.writes))

    def test_acknowledgement_without_matching_readback_is_not_success(self):
        self.peer.errors['$100=5'] = 'ok'  # Peer acknowledges but leaves EEPROM unchanged.
        operation = self.controller.request('settings', values={100: 5})
        eventually(lambda: not self.controller.snapshot()['busy'])
        snap = self.controller.snapshot()
        self.assertEqual(snap['last_result'][:2], (operation, 'settings'))
        self.assertIn('readback did not match', snap['last_result'][2])
        self.assertEqual(snap['settings'][100], 250)
        self.assertTrue(snap['reset_required'])
