"""Widget-facing parts of the accent controller: theme palette and the effect override."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from accent import config as cfg
from accent.controller import load_config, theme_palette

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


class EffectOverride(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        state = Path(self.dir.name)
        patches = [mock.patch.object(cfg, "STATE_DIR", state),
                   mock.patch.object(cfg, "EFFECT_FILE", state / "effect.json"),
                   mock.patch.object(cfg, "CONFIG_FILE", state / "missing.toml")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)

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


if __name__ == "__main__":
    unittest.main()


class TransitionSetting(EffectOverride):
    def test_default_is_wave(self):
        self.assertEqual(load_config()["transition"], "wave")

    def test_widget_choice_survives_effect_changes(self):
        cfg.save_transition("explode")
        cfg.save_effect("breath", 2)
        cfg.save_effect(None)
        self.assertEqual(load_config()["transition"], "explode")
