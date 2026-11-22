from unittest import TestCase

from scrib3.controller import Controller
from scrib3.motion_profile import SMOOTH_SETTINGS
from test_controller import FakeSerial, eventually


class AutomaticMotionTests(TestCase):
    def start(self, peer, enabled=True):
        session = Controller('test', serial_factory=lambda *a, **k: peer, apply_motion_defaults=enabled)
        def cleanup():
            session.close(); session.thread.join(2)
            self.assertFalse(session.thread.is_alive())
        self.addCleanup(cleanup)
        session.start()
        return session

    def writes(self, peer):
        return [w for w in peer.writes if w.startswith(b'$') and b'=' in w]

    def test_default_startup_verifies_only_motion_settings_before_connected(self):
        peer = FakeSerial(); peer.settings[1] = 25
        before = dict(peer.settings)
        session = self.start(peer)
        eventually(lambda: session.snapshot()['connected'])
        snap = session.snapshot()
        self.assertFalse(snap['motion_defaults_pending'])
        self.assertFalse(snap['motion_defaults_verifying'])
        self.assertFalse(snap['busy'])
        self.assertFalse(snap['reset_required'])
        self.assertEqual({n: snap['settings'][n] for n in SMOOTH_SETTINGS}, SMOOTH_SETTINGS)
        self.assertEqual({n: v for n, v in peer.settings.items() if n not in SMOOTH_SETTINGS},
                         {n: v for n, v in before.items() if n not in SMOOTH_SETTINGS})
        self.assertEqual(len(self.writes(peer)), 5)
        self.assertTrue(all(w == b'?' or w.startswith(b'$') for w in peer.writes))
        self.assertIn('$110=8890', snap['report'])
        self.assertIn('baseline verified', snap['log'])

    def test_matching_eeprom_is_not_rewritten_and_session_tuning_is_not_overridden(self):
        peer = FakeSerial(); peer.settings.update(SMOOTH_SETTINGS)
        session = self.start(peer)
        eventually(lambda: session.snapshot()['connected'])
        self.assertEqual(self.writes(peer), [])
        session.request('settings', values={110: 7000})
        eventually(lambda: not session.snapshot()['busy'])
        session.request('refresh')
        eventually(lambda: not session.snapshot()['busy'])
        self.assertEqual(peer.settings[110], 7000)
        self.assertEqual(self.writes(peer), [b'$110=7000\n'])

    def test_disabled_automatic_setup_preserves_custom_controller_values(self):
        peer = FakeSerial(); peer.settings[110] = 7000
        session = self.start(peer, enabled=False)
        eventually(lambda: session.snapshot()['connected'])
        self.assertFalse(session.snapshot()['motion_defaults_pending'])
        self.assertEqual(self.writes(peer), [])
        self.assertEqual(peer.settings[110], 7000)

    def test_matching_initial_snapshot_still_requires_matching_final_readback(self):
        class ChangedDuringRead(FakeSerial):
            reads = 0
            def write(self, data):
                if data == b'$$\n':
                    self.reads += 1
                    if self.reads == 2:
                        self.settings[110] = 500
                return super().write(data)
        peer = ChangedDuringRead(); peer.settings.update(SMOOTH_SETTINGS)
        session = self.start(peer)
        eventually(lambda: not session.thread.is_alive())
        self.assertFalse(session.snapshot()['connected'])
        self.assertIn('baseline readback did not match', session.snapshot()['fault'])
        self.assertEqual(self.writes(peer), [])

    def test_alarm_waits_for_operator_then_applies_before_normal_motion(self):
        peer = FakeSerial(); peer.state = 'Alarm'
        session = self.start(peer)
        eventually(lambda: session.snapshot()['connected'])
        self.assertTrue(session.snapshot()['motion_defaults_pending'])
        self.assertEqual(self.writes(peer), [])
        self.assertNotIn(b'$X\n', peer.writes)
        for kind, values in (('jog', dict(axis='X', distance=1, feed=150)), ('zero', {}), ('pen', dict(command='M3 S70'))):
            with self.assertRaisesRegex(ValueError, 'automatic motion setup'):
                session.request(kind, **values)
        session.request('unlock')
        eventually(lambda: not session.snapshot()['motion_defaults_pending'])
        self.assertEqual(peer.settings[110], 8890)
        session.request('zero')
        eventually(lambda: not session.snapshot()['busy'])
        self.assertLess(peer.writes.index(b'$111=8890\n'), peer.writes.index(b'G10 L20 P1 X0 Y0\n'))

    def test_error_or_readback_mismatch_never_enables_motion_or_retries(self):
        for reply in ('error:3', 'ok'):
            with self.subTest(reply=reply):
                peer = FakeSerial(); peer.errors['$110=8890'] = reply
                session = self.start(peer)
                eventually(lambda: not session.thread.is_alive())
                snap = session.snapshot()
                self.assertFalse(snap['connected'])
                self.assertTrue(snap['motion_defaults_pending'])
                self.assertFalse(snap['motion_defaults_verifying'])
                self.assertIn('Automatic motion setup failed', snap['fault'])
                self.assertEqual(peer.writes.count(b'$110=8890\n'), 1)
                if reply == 'error:3':
                    self.assertNotIn(b'$111=8890\n', peer.writes)
                else:
                    self.assertIn('readback did not match', snap['fault'])
                with self.assertRaises(ValueError):
                    session.request('jog', axis='X', distance=1, feed=150)

    def test_disconnect_during_startup_ack_wait_stops_remaining_writes(self):
        peer = FakeSerial(); peer.hold_setting = True
        session = self.start(peer)
        eventually(lambda: self.writes(peer))
        self.assertFalse(session.snapshot()['connected'])
        self.assertTrue(session.snapshot()['busy'])
        self.assertTrue(session.snapshot()['motion_defaults_verifying'])
        with self.assertRaises(ValueError):
            session.request('zero')
        session.close(); session.thread.join(2)
        self.assertEqual(self.writes(peer), [b'$11=0.02\n'])
        self.assertIn(b'\x18', peer.writes)
        self.assertFalse(session.snapshot()['connected'])
        self.assertFalse(session.snapshot()['motion_defaults_verifying'])
