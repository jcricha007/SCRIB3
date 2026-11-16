from dataclasses import replace
from time import monotonic, sleep
from unittest import TestCase

from scrib3.controller import Controller
from scrib3.drawing import Sheet
from scrib3.firmware import ServoSettings
from scrib3.gcode import Machine
from scrib3.jobs import PlotJob
from test_controller import FakeSerial, eventually


class JobSerial(FakeSerial):
    def __init__(self):
        super().__init__()
        self.settings[100] = self.settings[101] = 5
        self.block_moves = True
        self.normal_moves = []

    def write(self, data):
        if data in (b'!', b'~'):
            self.writes.append(data)
            self.state = 'Hold:0' if data == b'!' else ('Run' if self.normal_moves and self.block_moves else 'Idle')
            return len(data)
        if data.startswith(b'G1 X') and data.decode().strip() not in self.errors:
            self.normal_moves.append(data)
            if self.block_moves:
                self.state = 'Run'
        return super().write(data)


class JobProtocolTests(TestCase):
    def setUp(self):
        self.peer = JobSerial()
        self.controller = Controller('jobs', serial_factory=lambda *a, **k: self.peer)
        self.controller.start()
        eventually(lambda: self.controller.snapshot()['connected'])
        self.controller.request('zero')
        eventually(lambda: not self.controller.snapshot()['busy'])

    def tearDown(self):
        self.controller.close()
        self.controller.thread.join(2)
        self.assertFalse(self.controller.thread.is_alive())

    def job(self, dry=False, units='mm'):
        snap = self.controller.snapshot()
        return PlotJob((((1, 1), (3, 1)), ((3, 2), (4, 2))), Sheet(10, 10, 0),
                       Machine(10, 10, 60, 'M3 S180', 'M3 S70', .5, ServoSettings(1000, 0, 0, 100)),
                       units, dry, tuple(sorted(snap['settings'].items())), snap['reference'])

    def finish_moves(self):
        end = monotonic()+5
        while monotonic() < end and self.controller.snapshot()['busy']:
            if self.peer.state == 'Run':
                self.peer.state = 'Idle'
            sleep(.02)
        eventually(lambda: not self.controller.snapshot()['busy'])

    def test_stream_waits_for_motion_completion_and_final_pen_up(self):
        job = self.job()
        self.controller.request('run_job', job=job)
        eventually(lambda: self.peer.state == 'Run')
        count = len(self.peer.writes)
        sleep(.35)
        self.assertTrue(self.controller.snapshot()['busy'])
        self.assertTrue(all(w == b'?' for w in self.peer.writes[count:]))
        self.assertEqual(len(self.peer.normal_moves), 1)
        self.finish_moves()
        snap = self.controller.snapshot()
        self.assertEqual(snap['job']['state'], 'completed')
        self.assertEqual(snap['job']['completed'], len(job.commands()))
        self.assertEqual(snap['state'], 'Idle')
        commands = [w for w in self.peer.writes if w != b'?']
        self.assertEqual(commands[-2:], [b'M3 S180.000\n', b'G4 P0.500\n'])

    def test_pause_resume_and_stop_use_realtime_controls_without_new_lines(self):
        self.controller.request('run_job', job=self.job())
        eventually(lambda: self.peer.state == 'Run')
        self.controller.pause_job()
        eventually(lambda: self.peer.state == 'Hold:0')
        before = len(self.peer.normal_moves)
        sleep(.3)
        self.assertEqual(len(self.peer.normal_moves), before)
        self.assertEqual(self.controller.snapshot()['job']['state'], 'paused')
        self.controller.resume_job()
        eventually(lambda: b'~' in self.peer.writes)
        self.assertEqual(self.controller.snapshot()['job']['state'], 'running')
        self.controller.reset()
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertEqual(self.controller.snapshot()['job']['state'], 'stopped')
        self.assertIn(b'\x18', self.peer.writes)
        self.assertFalse(self.controller.snapshot()['origin_set'])
        self.assertEqual(len(self.peer.normal_moves), before)

    def test_error_stops_without_sending_following_lines_or_retrying(self):
        job = self.job()
        command = next(line for line in job.commands() if line.startswith('G1 X'))
        self.peer.errors[command] = 'error:20'
        self.controller.request('run_job', job=job)
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertEqual(self.controller.snapshot()['job']['state'], 'failed')
        self.assertEqual(self.peer.writes.count(command.encode()+b'\n'), 1)
        self.assertFalse(any(line.startswith(b'G0 X3.') for line in self.peer.writes))
        self.assertIn(b'\x18', self.peer.writes)

    def test_stale_review_or_missing_origin_does_not_send_a_program(self):
        job = self.job()
        self.controller.request('zero')
        eventually(lambda: not self.controller.snapshot()['busy'])
        before = len(self.peer.writes)
        self.controller.request('run_job', job=job)
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertIn('review', self.controller.snapshot()['last_result'][2])
        self.assertTrue(all(w == b'?' for w in self.peer.writes[before:]))
        job = self.job()
        self.peer.settings[110] = 123
        self.controller.request('refresh')
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.controller.request('run_job', job=job)
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertIn('settings changed', self.controller.snapshot()['last_result'][2])
        self.assertFalse(self.peer.normal_moves)

    def test_inch_dry_run_never_lowers_pen(self):
        self.peer.block_moves = False
        job = self.job(dry=True, units='in')
        self.controller.request('run_job', job=job)
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertEqual(self.controller.snapshot()['job']['state'], 'completed')
        self.assertNotIn(b'M3 S70.000\n', self.peer.writes)
        self.assertIn(b'G20 G90 G94 G17 G54 G49\n', self.peer.writes)
