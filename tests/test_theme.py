"""Widget-facing parts of the accent controller: theme palette and the effect override."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from theme import config as cfg
from theme import controller
from theme.controller import load_config, theme_palette
from aula_f75.device import Busy, NotFound, Rejected

CONFIG = dict(cfg.DEFAULTS)


class Palette(unittest.TestCase):
    def test_duplicates_are_dropped(self):
        # last-horizon repeats colours under several names (blue = accent, bright_* = base)
        colors = {"accent": "#b59790", "red": "#c38b7b", "blue": "#b59790", "cyan": "#a5a0b6"}
        out = theme_palette(CONFIG, colors)
        self.assertEqual([s for s, _ in out], ["#B59790", "#C38B7B", "#A5A0B6"])
        self.assertEqual(len({t for _, t in out}), len(out))

    def test_missing_and_bad_colours_are_skipped(self):
        out = theme_palette(CONFIG, {"red": "nope", "green": "#00ff00"})
        self.assertEqual([s for s, _ in out], ["#00FF00"])

    def test_theme_target_comes_first(self):
        # a [theme_overrides] entry sets the theme's real target; it replaces the accent
        out = theme_palette(CONFIG, {"accent": "#b59790", "red": "#c38b7b"},
                            ("#B59790", "#D64831"))
        self.assertEqual(out[0], ("#B59790", "#D64831"))
        self.assertEqual([s for s, _ in out], ["#B59790", "#C38B7B"])


class StateDir(unittest.TestCase):
    """Config and state in a temporary directory."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        state = Path(self.dir.name)
        patches = [mock.patch.object(cfg, "STATE_DIR", state),
                   mock.patch.object(cfg, "EFFECT_FILE", state / "effect.json"),
                   mock.patch.object(cfg, "CONFIG_FILE", state / "missing.toml"),
                   mock.patch.object(cfg, "DEVICES_FILE", state / "devices")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)


class EffectOverride(StateDir):
    def test_effect_and_speed_override_the_config(self):
        cfg.save_effect("breath", 4)
        c = load_config()
        self.assertEqual((c["effect"], c["speed"], c["effect_source"]), ("breath", 4, "widget"))

    def test_changing_effect_keeps_speed(self):
        cfg.save_effect("breath", 1)
        cfg.save_effect("ripples")
        self.assertEqual(cfg.effect_override(), {"effect": "ripples", "speed": 1})

    def test_default_returns_to_config(self):
        cfg.save_effect("breath", 4)
        cfg.save_effect(None)
        c = load_config()
        self.assertEqual((c["effect"], c["speed"], c["effect_source"]), ("static", 3, "config"))


class TransitionSetting(StateDir):
    def test_default_is_wave(self):
        self.assertEqual(load_config()["transition"], "wave")

    def test_widget_choice_survives_effect_changes(self):
        cfg.save_transition("explode")
        cfg.save_effect("breath", 2)
        cfg.save_effect(None)
        self.assertEqual(load_config()["transition"], "explode")


class NoAccess(StateDir):
    def test_apply_logs_a_device_it_cannot_open(self):
        # before the 'aula' group applies, opening the hidraw node fails
        log = Path(self.dir.name) / "theme.log"
        denied = PermissionError(13, "Permission denied", "/dev/hidraw9")
        with mock.patch.object(cfg, "LOG_FILE", log), \
                mock.patch.object(cfg, "STATE_FILE", Path(self.dir.name) / "state.json"), \
                mock.patch.object(cfg, "PIN_FILE", Path(self.dir.name) / "pin.json"), \
                mock.patch("theme.controller.open_keyboard", side_effect=denied):
            self.assertEqual(controller.main(["apply", "--color", "#ff0000"]), 1)
        self.assertIn("result=failed ([Errno 13] Permission denied", log.read_text())


class Isolated(StateDir):
    """Every file the controller touches in the temporary directory, a theme with a known
    accent, and present() faked."""

    def setUp(self):
        super().setUp()
        d = self.state = Path(self.dir.name)
        (d / "theme").mkdir()
        (d / "theme/colors.toml").write_text('accent = "#e06c75"\n')
        (d / "theme.name").write_text("testtheme\n")
        self.present = {"wired": "/dev/hidraw1", "wireless": "/dev/hidraw2"}
        patches = [mock.patch.object(cfg, "STATE_FILE", d / "state.json"),
                   mock.patch.object(cfg, "PIN_FILE", d / "pin.json"),
                   mock.patch.object(cfg, "LOG_FILE", d / "theme.log"),
                   mock.patch.object(cfg, "THEME_DIR", d / "theme"),
                   mock.patch.object(cfg, "THEME_NAME_FILE", d / "theme.name"),
                   mock.patch("theme.controller.present", side_effect=lambda: dict(self.present))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def run_main(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = controller.main(list(argv))
        return code, out.getvalue()

    def log(self):
        return (self.state / "theme.log").read_text()


class StatusJson(Isolated):
    def test_keys(self):
        cfg.save_pin("#00ff00", True)
        cfg.save_state({"brightness": 3, "transport": "wired"})
        code, out = self.run_main("status", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(set(data), {
            "theme", "theme_dir", "pin", "accent", "accent_source", "target",
            "target_description", "effect", "effect_source", "rainbow", "speed", "transition",
            "transition_time", "devices", "config", "state"})
        self.assertEqual(data["theme"], "testtheme")
        self.assertIs(data["rainbow"], False)
        self.assertEqual(data["pin"], {"color": "#00ff00", "exact": True})
        self.assertEqual((data["accent"], data["accent_source"]), ("#E06C75", "accent"))
        self.assertRegex(data["target"], r"^#[0-9A-F]{6}$")
        self.assertEqual(data["devices"], ["wired", "wireless"])
        self.assertEqual(set(data["config"]), {"direction", "prefer", "lcd_clock",
                                               "theme_overrides"})
        self.assertEqual(data["config"]["theme_overrides"], 0)
        self.assertEqual(data["state"], {"brightness": 3, "transport": "wired",
                                         "target": None, "effect": None})

    def test_no_pin_and_no_devices(self):
        self.present = {}
        data = json.loads(self.run_main("status", "--json")[1])
        self.assertIsNone(data["pin"])
        self.assertEqual(data["devices"], [])

    def test_theme_error(self):
        (self.state / "theme/colors.toml").unlink()
        code, out = self.run_main("status", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(list(json.loads(out)), ["error"])


class DevicesFile(Isolated):
    def devices(self):
        return (self.state / "devices").read_text()

    def test_written_sorted(self):
        cfg.save_devices({"wireless": "b", "wired": "a"})
        self.assertEqual(self.devices(), "wired,wireless\n")

    def test_none(self):
        cfg.save_devices({})
        self.assertEqual(self.devices(), "none\n")

    def test_unchanged_content_is_not_rewritten(self):
        cfg.save_devices(["wired"])
        with mock.patch.object(cfg.os, "replace") as replace:
            cfg.save_devices(["wired"])
            replace.assert_not_called()
            cfg.save_devices(["wired", "wireless"])
            replace.assert_called_once()

    def test_apply_writes_it_without_a_keyboard(self):
        self.present = {"wireless": "/dev/hidraw2"}
        with mock.patch("theme.controller.open_keyboard", side_effect=NotFound("no keyboard")):
            self.assertEqual(self.run_main("apply")[0], 0)
        self.assertEqual(self.devices(), "wireless\n")
        self.present = {}
        with mock.patch("theme.controller.open_keyboard", side_effect=NotFound("no keyboard")):
            self.run_main("apply")
        self.assertEqual(self.devices(), "none\n")

    def test_dry_run_does_not_write_it(self):
        self.assertEqual(self.run_main("apply", "--dry-run")[0], 0)
        self.assertFalse((self.state / "devices").exists())


class FakeKb:
    def __init__(self, transport="wired", fail=None):
        self.transport, self.path, self.fail = transport, "/dev/hidraw9", fail
        self.lit, self.clock = [], False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def light(self, effect):
        if self.fail:
            raise self.fail
        self.lit.append(effect)

    def set_clock(self, payload):
        self.clock = True

    def read_table(self, pages=None):
        return []


class Apply(Isolated):
    def apply(self, *argv, kb=None, error=None):
        opener = mock.patch("theme.controller.open_keyboard",
                            side_effect=error, return_value=kb)
        with opener:
            return self.run_main(*argv)

    def test_dry_run_prints_the_summary(self):
        code, out = self.apply("apply", "--dry-run", "--color", "#ff0000", "--exact")
        self.assertEqual(code, 0)
        self.assertIn("theme=testtheme accent=#FF0000 (override-exact) target=#FF0000", out)

    def test_not_found_is_skipped(self):
        self.assertEqual(self.apply("apply", error=NotFound("no keyboard"))[0], 0)
        self.assertIn("result=skipped (no keyboard)", self.log())

    def test_busy_is_deferred(self):
        self.assertEqual(self.apply("apply", error=Busy("busy"))[0], 0)
        self.assertIn("result=deferred (keyboard busy)", self.log())

    def test_bad_colour_fails(self):
        self.assertEqual(self.apply("apply", "--color", "nope")[0], 1)
        self.assertIn("apply failed:", self.log())

    def test_wired_apply_saves_state(self):
        kb = FakeKb()
        cfg.save_state({"brightness": 2})
        self.assertEqual(self.apply("apply", "--color", "#ff0000", "--exact", kb=kb)[0], 0)
        self.assertEqual(len(kb.lit), 1)
        self.assertTrue(kb.clock)
        state = cfg.load_state()
        self.assertEqual((state["target"], state["brightness"], state["transport"]),
                         ("#FF0000", 2, "wired"))
        self.assertIn("brightness=2 effect=static transport=wired verified=skipped result=ok",
                      self.log())

    def test_dongle_has_no_clock_or_verify(self):
        kb = FakeKb("wireless")
        self.assertEqual(self.apply("apply", "--verify", kb=kb)[0], 0)
        self.assertFalse(kb.clock)
        self.assertIn("transport=wireless verified=n/a result=ok", self.log())

    def test_rejected_write_fails(self):
        kb = FakeKb(fail=Rejected("nak"))
        self.assertEqual(self.apply("apply", kb=kb)[0], 1)
        self.assertIn("transport=wired result=failed (nak)", self.log())
        self.assertNotIn("target", cfg.load_state())

    def test_static_to_static_runs_a_transition(self):
        cfg.save_state({"target_rgb": [0, 0, 255], "effect": "static", "brightness": 5})
        with mock.patch("theme.controller.transition.run") as run:
            self.apply("apply", "--color", "#ff0000", "--exact", kb=FakeKb())
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1:3], ((0, 0, 255), (255, 0, 0)))

    def test_pin_is_saved_and_used(self):
        self.apply("apply", "--color", "#00ff00", "--exact", "--pin", kb=FakeKb())
        self.assertEqual(cfg.load_pin(), {"color": "#00ff00", "exact": True})
        self.apply("apply", kb=FakeKb())
        self.assertEqual(cfg.load_state()["target"], "#00FF00")

    def test_set_brightness_forces_the_level(self):
        self.apply("set-brightness", "9", kb=FakeKb())
        self.assertEqual(cfg.load_state()["brightness"], 5)
        self.assertIn("brightness=5", self.log())

    def test_set_effect_applies_it(self):
        self.assertEqual(self.apply("set-effect", "breath", "--speed", "1", kb=FakeKb())[0], 0)
        self.assertEqual(cfg.load_state()["effect"], "breath")
        self.assertTrue((self.state / "devices").exists())


class Rainbow(Isolated):
    apply = Apply.apply

    def setUp(self):
        super().setUp()
        self.kb = FakeKb()
        self.apply("set-rainbow", "on", "--speed", "2", kb=self.kb)

    def test_keeps_the_current_effect_and_sets_the_flag(self):
        effect = self.kb.lit[-1]
        self.assertEqual((effect.mode, effect.color, effect.speed), ("static", None, 2))
        self.assertEqual((effect.payload()[0], effect.payload()[8]), (0x01, 1))
        self.assertIs(cfg.load_state()["rainbow"], True)
        self.assertEqual(json.loads((self.state / "effect.json").read_text()),
                         {"effect": "static", "rainbow": True, "speed": 2})

    def test_keeps_a_configured_effect(self):
        self.apply("set-rainbow", "off", kb=FakeKb())
        cfg.EFFECT_FILE.unlink(missing_ok=True)
        cfg.CONFIG_FILE.write_text('[lighting]\neffect = "breath"\n')
        kb = FakeKb()
        self.apply("set-rainbow", "on", kb=kb)
        self.assertEqual((kb.lit[-1].mode, kb.lit[-1].payload()[8]), ("breath", 1))
        self.assertEqual(cfg.effect_override()["effect"], "breath")

    def test_works_on_the_dongle(self):
        kb = FakeKb("wireless")
        self.apply("apply", kb=kb)
        self.assertEqual((kb.lit[0].mode, kb.lit[0].payload()[8]), ("static", 1))

    def test_set_brightness_keeps_it(self):
        kb = FakeKb()
        self.apply("set-brightness", "2", kb=kb)
        self.assertEqual((kb.lit[0].rainbow, kb.lit[0].brightness), (True, 2))

    def test_another_effect_keeps_it(self):
        kb = FakeKb()
        self.apply("set-effect", "breath", kb=kb)
        self.assertEqual((kb.lit[0].mode, kb.lit[0].rainbow), ("breath", True))
        self.assertIs(cfg.effect_override()["rainbow"], True)

    def test_a_colour_turns_it_off_and_keeps_the_effect(self):
        self.apply("set-effect", "breath", kb=FakeKb())
        kb = FakeKb()
        self.apply("apply", "--color", "#ff0000", "--exact", kb=kb)
        self.assertEqual((kb.lit[0].mode, kb.lit[0].color, kb.lit[0].rainbow),
                         ("breath", (255, 0, 0), False))
        self.assertIs(cfg.load_state()["rainbow"], False)
        self.assertEqual(cfg.effect_override()["effect"], "breath")
        self.assertNotIn("rainbow", cfg.effect_override())

    def test_reset_turns_it_off_and_keeps_the_effect(self):
        kb = FakeKb()
        self.apply("set-rainbow", "off", kb=kb)
        self.assertEqual((kb.lit[-1].mode, kb.lit[-1].rainbow), ("static", False))
        self.assertIsNotNone(kb.lit[-1].color)
        self.assertEqual(cfg.effect_override()["effect"], "static")
        self.assertNotIn("rainbow", cfg.effect_override())

    def test_no_transition_and_no_read_back(self):
        cfg.save_state({"target_rgb": [0, 0, 255], "effect": "static", "brightness": 4})
        kb = FakeKb()
        with mock.patch("theme.controller.transition.run") as run, \
                mock.patch("theme.controller.live_brightness") as live:
            self.apply("apply", "--verify", kb=kb)
        run.assert_not_called()
        live.assert_not_called()
        self.assertEqual((kb.lit[0].rainbow, kb.lit[0].brightness), (True, 4))

    def test_status_json_reports_it(self):
        self.assertIs(json.loads(self.run_main("status", "--json")[1])["rainbow"], True)
        self.assertIn("rainbow: on", self.run_main("status")[1])


if __name__ == "__main__":
    unittest.main()
