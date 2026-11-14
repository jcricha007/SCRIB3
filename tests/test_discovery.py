from threading import Event
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from scrib3.discovery import detect
from scrib3.__main__ import main
from test_controller import FakeSerial


class DiscoveryTests(TestCase):
    def test_scans_bauds_and_requires_real_grbl_status(self):
        peers = []
        attempts = []
        def factory(port, baud, **kwargs):
            peer = FakeSerial()
            peer.rx.clear()
            peer.reply_status = (port, baud) == ("COM7", 9600)
            if not peer.reply_status:
                peer.emit("Arduino sketch at this baud")
            peers.append(peer)
            attempts.append((port, baud))
            return peer
        result = detect(serial_factory=factory,
                        port_provider=lambda: [SimpleNamespace(device="COM7")], probe_seconds=.04)
        self.assertEqual((result.port, result.baud), ("COM7", 9600))
        self.assertEqual(attempts[0], ("COM7", 115200))
        self.assertTrue(all(p.closed for p in peers))
        self.assertTrue(all(set(p.writes) == {b"?"} for p in peers))

    def test_fixed_baud_and_mac_aliases(self):
        attempts = []
        def factory(port, baud, **kwargs):
            attempts.append((port, baud))
            peer = FakeSerial()
            peer.reply_status = False
            return peer
        with self.assertRaisesRegex(ValueError, "No GRBL"):
            detect(baud=115200, serial_factory=factory, probe_seconds=.02,
                   port_provider=lambda: [SimpleNamespace(device="/dev/tty.usbmodem1"),
                                          SimpleNamespace(device="/dev/cu.usbmodem1")])
        self.assertEqual(attempts, [("/dev/cu.usbmodem1", 115200)])

    def test_cancel_and_busy_ports(self):
        cancel = Event()
        cancel.set()
        with self.assertRaisesRegex(ValueError, "cancelled"):
            detect(port="COM7", cancel=cancel)
        with self.assertRaisesRegex(ValueError, "port is busy"):
            detect(port="COM7", serial_factory=lambda *a, **k: (_ for _ in ()).throw(OSError("port is busy")))

    def test_terminal_connection_preserves_explicit_baud_and_auto_detect(self):
        with patch("scrib3.app.main") as desktop:
            main(["--connect", "auto", "--baud", "115200"])
            desktop.assert_called_once_with(connect="auto", baud=115200)
        with patch("scrib3.discovery.detect", return_value=SimpleNamespace(port="COM7", baud=57600, identity="GRBL")) as scan:
            with patch("builtins.print"):
                main(["--scan", "--connect", "COM7"])
            self.assertEqual(scan.call_args.kwargs["port"], "COM7")
            self.assertIsNone(scan.call_args.kwargs["baud"])
