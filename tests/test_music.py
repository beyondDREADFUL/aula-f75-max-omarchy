"""The visualiser reloads its options on SIGHUP between frames; the controller finds it."""
import io
import json
import os
import signal
import tempfile
import threading
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest import mock

from theme import config as cfg
from theme import controller
from theme.controller import music_following_theme
from aula_f75 import lighting, music


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

    def test_pid_file_start_time_must_match(self):
        pid = os.getpid()
        start = controller.proc_start_time(pid)
        self.assertTrue(start and start.isdigit())
        cmd = b"python3\0f75ctl\0music\0--color"
        with mock.patch.object(Path, "read_bytes", return_value=cmd):
            self.write(f"{pid} {start}", "theme")
            self.assertEqual(music_following_theme(), pid)
            self.write(f"{pid} {int(start) + 1}", "theme")      # a reused pid
            self.assertIsNone(music_following_theme())
        with mock.patch.object(Path, "read_bytes", return_value=b"python3\0f75ctl\0theme"):
            self.write(f"{pid} {start}", "theme")               # not the visualiser
            self.assertIsNone(music_following_theme())

    def test_start_time_survives_parentheses_in_the_command_name(self):
        stat = "1 (a b) c) S " + " ".join(str(i) for i in range(4, 60))
        with mock.patch.object(Path, "read_text", return_value=stat):
            self.assertEqual(controller.proc_start_time(1), "22")

    def test_only_an_f75ctl_process_with_the_theme_background(self):
        self.assertIsNone(music_following_theme())                  # no files
        self.write(os.getpid(), "theme")                            # not f75ctl
        self.assertIsNone(music_following_theme())
        with mock.patch.object(Path, "read_bytes", return_value=b"python3\0f75ctl\0music"):
            self.assertEqual(music_following_theme(), os.getpid())
            self.write(os.getpid(), "off")
            self.assertIsNone(music_following_theme())


class WidgetChoices(unittest.TestCase):
    def choices(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(controller.main(["choices", "--json"]), 0)
        return json.loads(out.getvalue())

    def test_every_bar_name_draws(self):
        for name in self.choices()["bars"]:
            self.assertIn(name, music.BAR_COLORS)
            self.assertEqual(len(music.bar_color(name, 0, 0, 0.0)), 3)

    def test_every_background_name_is_accepted(self):
        from aula_f75 import cli
        for name in self.choices()["backgrounds"]:
            self.assertEqual(cli._background(name), name)

    def test_choices_shape_and_source(self):
        data = self.choices()
        self.assertEqual(list(data), ["effects", "bars", "backgrounds"])
        self.assertEqual(data["bars"], [b for b in music.BAR_COLORS if b != "off"])
        self.assertEqual(data["backgrounds"], ["off", "theme", "spectrum-cycle", *music.SOLID])
        self.assertEqual(data["effects"], [m for m in lighting.MODES if m not in ("off", "custom")])


if __name__ == "__main__":
    unittest.main()
