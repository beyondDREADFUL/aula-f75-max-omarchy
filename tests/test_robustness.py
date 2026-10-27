"""The keyboard lock, dongle detection and the music loop's stop under a silent cava.
Run: python3 -m unittest discover tests"""
import os
import stat
import sys
import tempfile
import threading
import time
import types
import unittest
import unittest.mock
from pathlib import Path

from aula_f75 import device, hidraw, music
from aula_f75.layout import COLS


class Lock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        patcher = unittest.mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.state = self.home / ".local/state/omarchy/aula-f75"

    def test_one_path_for_session_and_service(self):
        with unittest.mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1"}):
            self.assertEqual(device.lock_path(), self.state / "device.lock")

    def test_created_0600_in_a_0700_state_dir(self):
        fd = device._lock(1)
        try:
            self.assertEqual(stat.S_IMODE(os.stat(self.state / "device.lock").st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(self.state).st_mode), 0o700)
            self.assertFalse(os.get_inheritable(fd))
        finally:
            os.close(fd)

    def test_second_holder_is_busy(self):
        fd = device._lock(1)
        try:
            with self.assertRaises(device.Busy):
                device._lock(0.1)
        finally:
            os.close(fd)

    def test_refuses_a_symlinked_lock_file(self):
        self.state.mkdir(parents=True, mode=0o700)
        target = self.home / "victim"
        (self.state / "device.lock").symlink_to(target)
        with self.assertRaises(OSError):
            device._lock(0.1)
        self.assertFalse(target.exists())

    def test_refuses_a_symlinked_state_dir(self):
        real = self.home / "elsewhere"
        real.mkdir(mode=0o700)
        self.state.parent.mkdir(parents=True)
        self.state.symlink_to(real)
        with self.assertRaises(OSError):
            device._lock(0.1)
        self.assertFalse((real / "device.lock").exists())

    def test_refuses_a_group_writable_state_dir(self):
        self.state.mkdir(parents=True)
        os.chmod(self.state, 0o770)
        with self.assertRaisesRegex(OSError, "not writable by group or others"):
            device._lock(0.1)

    def test_refuses_a_state_dir_owned_by_someone_else(self):
        self.state.mkdir(parents=True, mode=0o700)
        real_stat = os.stat

        def fake_stat(path, *args, **kwargs):
            st = real_stat(path, *args, **kwargs)
            if Path(path) == self.state:
                return types.SimpleNamespace(st_mode=st.st_mode, st_uid=os.getuid() + 1)
            return st
        with unittest.mock.patch.object(device.os, "stat", fake_stat):
            with self.assertRaisesRegex(OSError, "owned by uid"):
                device._lock(0.1)
        self.assertFalse((self.state / "device.lock").exists())


class DongleDetection(unittest.TestCase):
    def test_usage_page(self):
        self.assertEqual(hidraw.usage_page(bytes.fromhex("06 60 ff 09 61 a1 01")), 0xFF60)
        self.assertEqual(hidraw.usage_page(bytes.fromhex("05 01 09 06 a1 01")), 0x01)
        self.assertIsNone(hidraw.usage_page(bytes.fromhex("09 06 a1 01")))
        self.assertIsNone(hidraw.usage_page(b"\x06\x60"))
        self.assertIsNone(hidraw.usage_page(b""))

    def nodes(self, *found):
        return unittest.mock.patch.object(hidraw, "nodes", return_value=list(found))

    def test_dongle_needs_its_name_and_usage_page(self):
        apple = hidraw.Node("/dev/hidraw1", *device.DONGLE, 3, "Apple Keyboard", 0xFF60)
        other = hidraw.Node("/dev/hidraw2", *device.DONGLE, 3, "2.4G Dongle", 0x0001)
        aula = hidraw.Node("/dev/hidraw3", *device.DONGLE, 3, "2.4G Dongle", 0xFF60)
        with self.nodes(apple, other):
            self.assertNotIn("wireless", device.present())
        with self.nodes(apple, other, aula):
            self.assertEqual(device.present()["wireless"], "/dev/hidraw3")

    def test_wired_lookup_is_unchanged(self):
        wired = hidraw.Node("/dev/hidraw4", *device.WIRED, 3)
        with self.nodes(wired):
            self.assertEqual(device.present(), {"wired": "/dev/hidraw4"})


class MusicStop(unittest.TestCase):
    def test_silent_cava_does_not_block_a_stop(self):
        # a "cava" that prints one frame and then hangs without output
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "cava"
            exe.write_text(f"#!{sys.executable}\nimport sys, time\n"
                           f"sys.stdout.buffer.write(bytes({COLS})); sys.stdout.flush()\n"
                           "time.sleep(60)\n")
            exe.chmod(0o755)
            stop = threading.Event()
            with unittest.mock.patch.object(music.shutil, "which", return_value=str(exe)):
                levels, close = music.cava_levels(music.Options(), stop.is_set)
            try:
                self.assertEqual(len(next(levels)), COLS)
                threading.Timer(0.2, stop.set).start()
                start = time.monotonic()
                self.assertIsNone(next(levels, None))
                self.assertLess(time.monotonic() - start, 2)
            finally:
                close()


if __name__ == "__main__":
    unittest.main()
