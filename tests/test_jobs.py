from dataclasses import replace
from time import monotonic, sleep
from unittest import TestCase
from unittest.mock import patch

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
        self.block_ack_at = None

    def write(self, data):
        if data in (b'!', b'~'):
            self.writes.append(data)
            self.state = 'Hold:0' if data == b'!' else ('Run' if self.normal_moves and self.block_moves else 'Idle')
            return len(data)
        if data.startswith(b'G1 X') and data.decode().strip() not in self.errors:
            self.normal_moves.append(data)
            if self.block_moves:
                self.state = 'Run'
            if len(self.normal_moves) == self.block_ack_at:
                self.writes.append(data)
                return len(data)
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
        return PlotJob((((1, 1), (2, 1), (3, 1), (4, 1)), ((5, 2), (6, 2))), Sheet(10, 10, 0),
                       Machine(10, 10, 60, 'M3 S180', 'M3 S70', .5, ServoSettings(1000, 0, 0, 100)),
                       units, dry, tuple(sorted(snap['settings'].items())), snap['reference'])

    def finish_moves(self):
        end = monotonic()+5
        while monotonic() < end and self.controller.snapshot()['busy']:
            if self.peer.state == 'Run':
                self.peer.state = 'Idle'
            sleep(.02)
        eventually(lambda: not self.controller.snapshot()['busy'])

    def test_segments_fill_planner_before_idle_but_pen_lift_waits_for_motion(self):
        job = self.job()
        self.controller.request('run_job', job=job)
        eventually(lambda: len(self.peer.normal_moves) == 3)
        count = len(self.peer.writes)
        sleep(.35)
        self.assertTrue(self.controller.snapshot()['busy'])
        self.assertTrue(all(w == b'?' for w in self.peer.writes[count:]))
        self.assertEqual(len(self.peer.normal_moves), 3)
        snap = self.controller.snapshot()
        self.assertGreater(snap['job']['accepted'], snap['job']['completed'])
        self.assertEqual(self.peer.writes.count(b'M3 S180.000\n'), 1)
        self.finish_moves()
        snap = self.controller.snapshot()
        self.assertEqual(snap['job']['state'], 'completed')
        self.assertEqual(snap['job']['completed'], len(job.commands()))
        self.assertEqual(snap['state'], 'Idle')
        commands = [w for w in self.peer.writes if w != b'?']
        self.assertEqual(commands[-2:], [b'M3 S180.000\n', b'G4 P0.500\n'])

    def test_full_planner_delayed_ack_blocks_following_lines_without_retries(self):
        self.peer.block_ack_at = 2
        self.controller.request('run_job', job=self.job())
        eventually(lambda: len(self.peer.normal_moves) == 2)
        sleep(.35)
        self.assertEqual(len(self.peer.normal_moves), 2)
        self.peer.emit('ok')
        eventually(lambda: len(self.peer.normal_moves) == 3)
        self.finish_moves()
        self.assertEqual(self.controller.snapshot()['job']['state'], 'completed')
        self.assertEqual(len(self.peer.normal_moves), 4)

    def test_alarm_during_queued_motion_aborts_before_pen_transition(self):
        self.controller.request('run_job', job=self.job())
        eventually(lambda: len(self.peer.normal_moves) == 3)
        self.peer.state = 'Alarm'
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertEqual(self.controller.snapshot()['job']['state'], 'failed')
        self.assertEqual(self.peer.writes.count(b'M3 S180.000\n'), 1)
        self.assertIn(b'\x18', self.peer.writes)

    def test_pause_during_full_planner_wait_keeps_next_segment_unsent(self):
        self.peer.block_ack_at = 2
        self.controller.request('run_job', job=self.job())
        eventually(lambda: len(self.peer.normal_moves) == 2)
        self.controller.pause_job()
        eventually(lambda: self.peer.state == 'Hold:0')
        self.peer.emit('ok')
        sleep(.3)
        self.assertEqual(len(self.peer.normal_moves), 2)
        self.assertEqual(self.controller.snapshot()['job']['state'], 'paused')
        self.controller.resume_job()
        eventually(lambda: len(self.peer.normal_moves) == 3)
        self.finish_moves()
        self.assertEqual(self.controller.snapshot()['job']['state'], 'completed')

    def test_disconnect_with_full_planner_aborts_queued_motion(self):
        self.peer.block_ack_at = 2
        self.controller.request('run_job', job=self.job())
        eventually(lambda: len(self.peer.normal_moves) == 2)
        self.controller.close()
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertEqual(len(self.peer.normal_moves), 2)
        self.assertEqual(self.controller.snapshot()['job']['state'], 'stopped')
        self.assertIn(b'\x18', self.peer.writes)
        self.assertFalse(self.controller.snapshot()['origin_set'])

    def test_z_pen_lift_waits_until_queued_xy_segments_finish(self):
        job = replace(self.job(), machine=Machine(10, 10, 60, 'G0 Z2', 'G1 Z0 F30', .5))
        self.controller.request('run_job', job=job)
        eventually(lambda: len(self.peer.normal_moves) == 3)
        self.assertEqual(self.peer.writes.count(b'G0 Z2.000\n'), 1)
        self.finish_moves()
        self.assertEqual(self.controller.snapshot()['job']['state'], 'completed')
        self.assertEqual(self.peer.writes.count(b'G0 Z2.000\n'), 3)

    def test_missing_ack_after_motion_ends_aborts_without_waiting_an_hour(self):
        self.peer.block_ack_at = 1
        with patch('scrib3.controller.JOB_IDLE_ACK_TIMEOUT', .2):
            self.controller.request('run_job', job=self.job())
            eventually(lambda: len(self.peer.normal_moves) == 1)
            self.peer.state = 'Idle'
            eventually(lambda: not self.controller.thread.is_alive())
        self.assertIn('did not acknowledge', self.controller.snapshot()['fault'])
        self.assertEqual(len(self.peer.normal_moves), 1)
        self.assertIn(b'\x18', self.peer.writes)

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

    def test_stop_during_start_hold_keeps_pen_up_home_and_serial(self):
        self.controller.request('set_home')
        eventually(lambda: not self.controller.snapshot()['busy'])
        before = self.controller.snapshot()
        original = self.peer.write

        def hold_start(data):
            if data == b'G4 P10.000\n':
                self.peer.writes.append(data)
                return len(data)
            return original(data)

        self.peer.write = hold_start
        operation = self.controller.request('run_job', job=self.job())
        eventually(lambda: b'G4 P10.000\n' in self.peer.writes)
        self.controller.stop_job(operation)
        self.peer.emit('ok')
        eventually(lambda: not self.controller.snapshot()['busy'])
        after = self.controller.snapshot()
        self.assertEqual(after['job']['state'], 'stopped')
        for key in ('connected', 'origin_set', 'manual_home', 'settings', 'reference'):
            self.assertEqual(after[key], before[key])
        self.assertNotIn(b'M3 S70.000\n', self.peer.writes)
        self.assertNotIn(b'\x18', self.peer.writes)
        self.assertFalse(self.peer.closed)
        self.peer.write = original
        self.peer.block_moves = False
        self.controller.request('run_job', job=self.job())
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertEqual(self.controller.snapshot()['job']['state'], 'completed')

    def test_first_point_arrival_and_dwell_ack_precede_ink_and_final_lift_stays_put(self):
        self.peer.block_moves = False
        job = self.job()
        first_xy = next(cmd.encode() + b'\n' for cmd in job.commands() if cmd.startswith('G0 X'))
        dwell = b'G4 P10.000\n'
        original = self.peer.write

        def stage_start(data):
            if data == first_xy:
                self.peer.state = 'Run'
            if data == dwell:
                self.peer.writes.append(data)
                return len(data)
            return original(data)

        self.peer.write = stage_start
        self.controller.request('run_job', job=job)
        eventually(lambda: first_xy in self.peer.writes)
        sleep(.3)
        self.assertIn(b'M3 S180.000\n', self.peer.writes)
        self.assertNotIn(dwell, self.peer.writes)
        self.peer.state = 'Idle'
        eventually(lambda: dwell in self.peer.writes)
        self.assertNotIn(b'M3 S70.000\n', self.peer.writes)
        self.assertFalse(self.peer.normal_moves)
        self.peer.emit('ok')
        eventually(lambda: not self.controller.snapshot()['busy'])
        actual = [w.decode().strip() for w in self.peer.writes[self.peer.writes.index(first_xy):] if w != b'?']
        self.assertEqual(actual, list(job.commands())[job.commands().index(first_xy.decode().strip()):])
        self.assertEqual(actual[-3:], ['G1 X6.000 Y2.000 F60.000', 'M3 S180.000', 'G4 P0.500'])
        self.assertEqual(self.controller.snapshot()['state'], 'Idle')

    def test_pause_at_pen_down_write_waits_for_this_jobs_resume(self):
        self.peer.block_moves = False
        original = self.controller._command
        paused = False

        def pause_at_write(command, *args, **kwargs):
            nonlocal paused
            if command == 'M3 S70.000' and not paused:
                paused = True
                self.controller.pause_job(self.controller.operation_id)
            return original(command, *args, **kwargs)

        with patch.object(self.controller, '_command', side_effect=pause_at_write):
            operation = self.controller.request('run_job', job=self.job())
            eventually(lambda: self.controller.snapshot()['job']['state'] == 'paused')
            self.controller.resume_job(operation - 1)
            sleep(.1)
            self.assertNotIn(b'M3 S70.000\n', self.peer.writes)
            self.assertNotIn(b'~', self.peer.writes)
            self.controller.resume_job(operation)
            eventually(lambda: not self.controller.snapshot()['busy'])
            self.assertEqual(self.controller.snapshot()['job']['state'], 'completed')

    def test_override_change_during_first_hold_aborts_before_lowering(self):
        original = self.peer.write
        def change_override(data):
            if data == b'G4 P10.000\n':
                self.peer.override = 50
                self.peer.writes.append(data)
                return len(data)
            return original(data)
        self.peer.write = change_override
        self.controller.request('run_job', job=self.job())
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertIn('override changed', self.controller.snapshot()['fault'])
        self.assertNotIn(b'M3 S70.000\n', self.peer.writes)

    def test_stop_while_paused_at_stationary_first_point_never_lowers(self):
        original = self.peer.write
        def idle_dwell(data):
            if data in (b'G4 P10.000\n', b'!'):
                self.peer.writes.append(data)
                return len(data)
            return original(data)
        self.peer.write = idle_dwell
        operation = self.controller.request('run_job', job=self.job())
        eventually(lambda: b'G4 P10.000\n' in self.peer.writes)
        self.controller.pause_job(operation)
        eventually(lambda: self.controller.snapshot()['job']['state'] == 'paused')
        self.controller.stop_job(operation)
        self.peer.emit('ok')
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertEqual(self.controller.snapshot()['job']['state'], 'stopped')
        self.assertNotIn(b'M3 S70.000\n', self.peer.writes)
        self.assertNotIn(b'~', self.peer.writes)

    def test_stop_while_paused_with_an_unacknowledged_move(self):
        self.peer.block_ack_at = 2
        operation = self.controller.request('run_job', job=self.job())
        eventually(lambda: len(self.peer.normal_moves) == 2)
        self.controller.pause_job()
        eventually(lambda: self.peer.state == 'Hold:0')
        self.controller.stop_job(operation)
        eventually(lambda: b'~' in self.peer.writes)
        self.peer.emit('ok')
        self.finish_moves()
        self.assertEqual(self.controller.snapshot()['job']['state'], 'stopped')
        self.assertEqual(len(self.peer.normal_moves), 2)
        self.assertEqual(self.peer.writes.count(b'M3 S180.000\n'), 2)
        self.assertNotIn(b'\x18', self.peer.writes)

    def test_error_stops_without_sending_following_lines_or_retrying(self):
        job = self.job()
        command = next(line for line in job.commands() if line.startswith('G1 X'))
        self.peer.errors[command] = 'error:20'
        self.controller.request('run_job', job=job)
        eventually(lambda: not self.controller.thread.is_alive())
        self.assertEqual(self.controller.snapshot()['job']['state'], 'failed')
        self.assertEqual(self.peer.writes.count(command.encode()+b'\n'), 1)
        self.assertFalse(any(line.startswith(b'G1 X3.') for line in self.peer.writes))
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

    def test_live_travel_must_cover_the_reviewed_job_before_any_motion(self):
        for x_limit, error in ((0, '$130 and $131'), (5, 'paper does not fit')):
            with self.subTest(x_limit=x_limit):
                self.peer.settings[130] = x_limit
                self.controller.request('refresh')
                eventually(lambda: not self.controller.snapshot()['busy'])
                before = len(self.peer.writes)
                self.controller.request('run_job', job=self.job())
                eventually(lambda: not self.controller.snapshot()['busy'])
                self.assertIn(error, self.controller.snapshot()['last_result'][2])
                self.assertTrue(all(w == b'?' for w in self.peer.writes[before:]))

    def test_inch_dry_run_never_lowers_pen(self):
        self.peer.block_moves = False
        job = self.job(dry=True, units='in')
        self.controller.request('run_job', job=job)
        eventually(lambda: not self.controller.snapshot()['busy'])
        self.assertEqual(self.controller.snapshot()['job']['state'], 'completed')
        self.assertNotIn(b'M3 S70.000\n', self.peer.writes)
        self.assertIn(b'G20 G90 G94 G17 G54 G49\n', self.peer.writes)
