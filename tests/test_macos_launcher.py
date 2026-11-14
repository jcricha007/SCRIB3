import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

LAUNCHER = Path(__file__).resolve().parents[1] / "Run-SCRIB3.command"


@skipUnless(os.name == "posix", "The macOS shell launcher requires a POSIX shell.")
class MacLauncherTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix="scrib3 mac ")
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.repo = self.folder / "SCRIB3 with spaces"
        self.repo.mkdir()
        self.launcher = self.repo / LAUNCHER.name
        shutil.copyfile(LAUNCHER, self.launcher)
        self.bin = self.folder / "fake bin"
        self.bin.mkdir()
        self.executable("uname", "#!/bin/sh\nprintf 'Darwin\\n'\n")
        self.environment = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin")
        self.environment.pop("SCRIB3_PYTHON", None)

    def executable(self, name, content):
        file = self.bin / name
        file.write_text(content)
        file.chmod(0o755)
        return file

    def run_launcher(self, *args):
        return subprocess.run(
            ["/bin/bash", str(self.launcher), *args],
            cwd=self.folder,
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_launch_from_another_directory_preserves_paths_and_check_argument(self):
        python = self.executable(
            "python with spaces",
            '#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "%s\\n" "$@"\n',
        )
        self.environment["SCRIB3_PYTHON"] = str(python)
        result = self.run_launcher("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(),
                         [str(self.repo / "scripts" / "start_macos.py"), "--check"])

    def test_failed_setup_propagates_exit_status(self):
        python = self.executable(
            "python failure",
            '#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nexit 7\n',
        )
        self.environment["SCRIB3_PYTHON"] = str(python)
        result = self.run_launcher()
        self.assertEqual(result.returncode, 7)

    def test_python_without_tk_falls_back_to_compatible_python(self):
        self.executable("python3.13", "#!/bin/sh\nexit 1\n")
        self.executable(
            "python3.12",
            '#!/bin/sh\nif [ "$1" = "-c" ]; then exit 0; fi\nprintf "fallback launched\\n"\n',
        )
        result = self.run_launcher("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "fallback launched")
