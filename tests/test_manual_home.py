from unittest import TestCase

from scrib3.controller import Controller
from test_controller import FakeSerial, eventually


class ManualHomeTests(TestCase):
    def setUp(self):
        self.peer = FakeSerial()
        self.controller = Controller('home-test', serial_factory=lambda *a, **k: self.peer)
        self.controller.start()
        eventually(lambda: self.controller.snapshot()['connected'])

    def tearDown(self):
        self.controller.close()
        self.controller.thread.join(2)
        self.assertFalse(self.controller.thread.is_alive())

    def operation(self, kind, **values):
        self.controller.request(kind, **values)
        eventually(lambda: not self.controller.snapshot()['busy'])

    def go(self, **values):
        self.operation('go_home', **({'feed': 101.6, 'command': 'M3 S180', 'servo': True} | values))

    def test_manual_reference_works_without_switches_and_return_ignores_new_paper_origin(self):
        self.operation('set_home')
        self.assertEqual(self.controller.snapshot()['manual_home'], (10, 20))
        self.assertEqual(self.controller.snapshot()['work'][:2], (0, 0))
        self.assertEqual(self.peer.settings[22], 0)
        self.assertNotIn(b'$H\n', self.peer.writes)
        self.assertNotIn(b'$X\n', self.peer.writes)
        self.peer.position = '30,40,0'
        self.operation('zero')
        self.assertEqual(self.controller.snapshot()['manual_home'], (10, 20))
        self.go()
        commands = [w for w in self.peer.writes if w != b'?']
        self.assertEqual(commands[-3:], [b'M3 S180.000\n', b'G4 P0.500\n',
                                         b'$J=G21 G90 G53 X10.000 Y20.000 F101.600\n'])
        self.assertEqual(self.controller.snapshot()['state'], 'Jog')
        self.controller.cancel_jog()
        eventually(lambda: self.controller.snapshot()['state'] == 'Idle')

    def test_home_is_invalidated_by_calibration_alarm_and_disconnect(self):
        self.operation('set_home')
        self.operation('settings', values={100: 200})
        self.assertIsNone(self.controller.snapshot()['manual_home'])
        before = len(self.peer.writes)
        self.go()
        self.assertFalse(any(w.startswith(b'$J=') for w in self.peer.writes[before:]))
        self.operation('set_home')
        self.peer.state = 'Alarm'
        eventually(lambda: self.controller.snapshot()['state'] == 'Alarm')
        self.assertIsNone(self.controller.snapshot()['manual_home'])
        self.operation('set_home')
        self.assertIsNone(self.controller.snapshot()['manual_home'])
        self.controller.reset()
        self.controller.thread.join(1)
        self.assertIsNone(self.controller.snapshot()['manual_home'])

    def test_pen_error_or_invalid_command_prevents_xy_return(self):
        self.operation('set_home')
        self.go(command='M3 S1000')
        self.assertFalse(any(w.startswith(b'$J=') for w in self.peer.writes))
        self.peer.errors['M3 S180.000'] = 'error:3'
        self.go()
        self.assertFalse(any(w.startswith(b'$J=') for w in self.peer.writes))

    def test_cancel_during_pen_settle_prevents_following_xy_move(self):
        self.operation('set_home')
        self.peer.block_dwell = True
        self.controller.request('go_home', feed=101.6, command='M3 S180', servo=True)
        eventually(lambda: b'G4 P0.500\n' in self.peer.writes)
        self.controller.cancel_jog()
        eventually(lambda: b'\x85' in self.peer.writes)
        self.peer.emit('ok')
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertFalse(any(w.startswith(b'$J=') for w in self.peer.writes))

    def test_failed_zero_does_not_store_home_and_inches_report_is_normalized(self):
        self.peer.errors['G10 L20 P1 X0 Y0'] = 'error:3'
        self.operation('set_home')
        self.assertIsNone(self.controller.snapshot()['manual_home'])
        self.peer.errors.clear()
        self.peer.settings[13] = 1
        self.peer.position = '1,2,0'
        self.operation('refresh')
        self.operation('set_home')
        self.assertEqual(self.controller.snapshot()['manual_home'], (25.4, 50.8))
        self.go()
        self.assertIn(b'$J=G21 G90 G53 X25.400 Y50.800 F101.600\n', self.peer.writes)
