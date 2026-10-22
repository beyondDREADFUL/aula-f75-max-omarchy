"""Tests for the pure colour functions.  Run: python3 -m unittest discover tests"""
import colorsys
import importlib.machinery
import importlib.util
import unittest
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "bin" / "omarchy-keyboard-accent"
loader = importlib.machinery.SourceFileLoader("accent", str(path))
spec = importlib.util.spec_from_loader("accent", loader)
accent = importlib.util.module_from_spec(spec)
loader.exec_module(accent)

CONFIG = dict(accent.DEFAULT_CONFIG)


def hue(rgb):
    return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[0] * 360


def hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


class ParseColor(unittest.TestCase):
    def test_accepted_forms(self):
        for text in ("#FF8000", "ff8000", "0xFF8000", " #ff8000 ", "rgb(255, 128, 0)", "rgba(255,128,0,0.5)"):
            self.assertEqual(accent.parse_color(text), (255, 128, 0), text)

    def test_short_form(self):
        self.assertEqual(accent.parse_color("#f80"), (255, 136, 0))

    def test_rgb_is_clamped(self):
        self.assertEqual(accent.parse_color("rgb(300, -5, 10)"), (255, 0, 10))

    def test_rejects_bad_input(self):
        for text in ("", "   ", "#12345", "#GGGGGG", "rgb(1,2)", "rgb(a,b,c)", "red"):
            with self.assertRaises(ValueError, msg=text):
                accent.parse_color(text)

    def test_hexstr_round_trip(self):
        self.assertEqual(accent.hexstr((1, 171, 255)), "#01ABFF")
        self.assertEqual(accent.parse_color(accent.hexstr((1, 171, 255))), (1, 171, 255))


class Vivid(unittest.TestCase):
    def target(self, hexcolor, **override):
        config = dict(CONFIG, **override)
        return accent.vivid(accent.parse_color(hexcolor), config)[0]

    def test_grey_becomes_soft_white(self):
        r, g, b = self.target("#808080")
        self.assertGreater(min(r, g, b), 200)
        self.assertGreater(r, b)  # warm tint, not pure red

    def test_pale_accent_becomes_soft_white(self):
        self.assertGreater(min(self.target("#E8E0D0")), 200)

    def test_hue_is_kept_for_muted_accents(self):
        for source in ("#7aa2f7", "#82FB9C", "#cba6f7", "#78824b"):
            out = self.target(source, underglow_correction=False)
            self.assertLess(hue_gap(hue(out), hue(accent.parse_color(source))), 3, source)

    def test_muted_accent_gets_more_saturated(self):
        before = colorsys.rgb_to_hls(*(c / 255 for c in accent.parse_color("#7aa2f7")))[2]
        after = colorsys.rgb_to_hls(*(c / 255 for c in self.target("#7aa2f7", underglow_correction=False)))[2]
        self.assertGreater(after, before)

    def test_lightness_is_clamped(self):
        for source in ("#7aa2f7", "#205EA6", "#F34820"):
            out = self.target(source, underglow_correction=False)
            lightness = colorsys.rgb_to_hls(*(c / 255 for c in out))[1]
            self.assertGreaterEqual(lightness, CONFIG["min_lightness"] - 0.01, source)
            self.assertLessEqual(lightness, CONFIG["max_lightness"] + 0.01, source)

    def test_channels_stay_in_range(self):
        for source in ("#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#123456"):
            for channel in self.target(source):
                self.assertTrue(0 <= channel <= 255, source)


class Underglow(unittest.TestCase):
    def test_correction_pulls_underglow_hue_closer(self):
        warm = (230, 150, 20)
        corrected = accent.balance_for_underglow(warm)

        def glow(rgb):
            return tuple(rgb[i] * accent.CHANNEL_GAIN[i] for i in range(3))

        self.assertLessEqual(
            hue_gap(hue(glow(corrected)), hue(warm)),
            hue_gap(hue(glow(warm)), hue(warm)),
        )

    def test_blue_is_left_alone(self):
        self.assertEqual(accent.balance_for_underglow((30, 100, 240)), (30, 100, 240))

    def test_expected_effect_applies_gain_and_brightness(self):
        full = accent.expected_effect((200, 200, 200), 5)
        low = accent.expected_effect((200, 200, 200), 1)
        self.assertLess(full[0], full[1])  # red is cut
        self.assertTrue(all(l <= f for l, f in zip(low, full)))


if __name__ == "__main__":
    unittest.main()
