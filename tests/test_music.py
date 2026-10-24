"""The visualiser reloads its options on SIGHUP between frames; the controller finds it."""
import os
import signal
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from accent import config as cfg
from accent.controller import music_following_theme
from aula_f75 import music


class FakeKb:
    def __init__(self):
        self.frames = []

    def frame(self, colors):
        self.frames.append(colors)


class Reload(unittest.TestCase):
    def test_sighup_reloads_between_frames(self):
        kb, calls = FakeKb(), []

        def reload(opts):
            calls.append(len(kb.frames))
            opts.background = "00ff00"
        opts = music.Options(fps=50, bars="off", background="ff0000", seconds=0.5, test=True)
        threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGHUP)).start()
        _, stopped_by = music.run(kb, opts, on_start=lambda _: None, reload=reload)
        self.assertIsNone(stopped_by)
        self.assertEqual(len(calls), 1)
        before, after = kb.frames[calls[0] - 1], kb.frames[-1]
        self.assertNotEqual(before, after)          # the background changed colour
        self.assertEqual(signal.getsignal(signal.SIGHUP), signal.SIG_DFL)


class FindMusic(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name)
        p = mock.patch.object(cfg, "STATE_DIR", self.state)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)

    def write(self, pid, background):
        (self.state / "music.pid").write_text(f"{pid}\n")
        (self.state / "music.background").write_text(f"{background}\n")

    def test_only_an_f75ctl_process_with_the_theme_background(self):
        self.assertIsNone(music_following_theme())                  # no files
        self.write(os.getpid(), "theme")                            # not f75ctl
        self.assertIsNone(music_following_theme())
        with mock.patch.object(Path, "read_bytes", return_value=b"python3\0f75ctl\0music"):
            self.assertEqual(music_following_theme(), os.getpid())
            self.write(os.getpid(), "off")
            self.assertIsNone(music_following_theme())


if __name__ == "__main__":
    unittest.main()
