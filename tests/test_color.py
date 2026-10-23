"""Colour parsing and the automatic colour choice. Run: python3 -m unittest discover tests"""
import colorsys
import unittest

from accent.color import hexstr, parse_color, vivid
from accent.config import DEFAULTS

CONFIG = dict(DEFAULTS)


def hue(rgb):
    return colorsys.rgb_to_hsv(*(c / 255 for c in rgb))[0] * 360


def hue_gap(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def lightness(rgb):
    return colorsys.rgb_to_hls(*(c / 255 for c in rgb))[1]


def saturation(rgb):
    return colorsys.rgb_to_hls(*(c / 255 for c in rgb))[2]


class ParseColor(unittest.TestCase):
    def test_accepted_forms(self):
        for text in ("#FF8000", "ff8000", "0xFF8000", " #ff8000 ", "rgb(255, 128, 0)",
                     "rgba(255,128,0,0.5)"):
            self.assertEqual(parse_color(text), (255, 128, 0), text)

    def test_short_form(self):
        self.assertEqual(parse_color("#f80"), (255, 136, 0))

    def test_rgb_is_clamped(self):
        self.assertEqual(parse_color("rgb(300, -5, 10)"), (255, 0, 10))

    def test_rejects_bad_input(self):
        for text in ("", "   ", "#12345", "#GGGGGG", "rgb(1,2)", "rgb(a,b,c)", "red"):
            with self.assertRaises(ValueError, msg=text):
                parse_color(text)

    def test_hexstr_round_trip(self):
        self.assertEqual(hexstr((1, 171, 255)), "#01ABFF")
        self.assertEqual(parse_color(hexstr((1, 171, 255))), (1, 171, 255))


class Vivid(unittest.TestCase):
    def target(self, hexcolor):
        return vivid(parse_color(hexcolor), CONFIG)

    def test_grey_becomes_soft_white(self):
        r, g, b = self.target("#808080")
        self.assertGreater(min(r, g, b), 200)
        self.assertGreater(r, b)  # warm tint, not pure red

    def test_pale_accent_becomes_soft_white(self):
        self.assertGreater(min(self.target("#E8E0D0")), 200)

    def test_hue_is_kept(self):
        # nothing compensates for the LEDs any more, so the hue is kept for every accent
        for source in ("#7aa2f7", "#82FB9C", "#cba6f7", "#78824b", "#F34820", "#E6A014"):
            self.assertLess(hue_gap(hue(self.target(source)), hue(parse_color(source))), 3, source)

    def test_muted_accent_gets_more_saturated(self):
        self.assertGreater(saturation(self.target("#7aa2f7")), saturation(parse_color("#7aa2f7")))

    def test_saturated_accent_is_kept(self):
        self.assertAlmostEqual(saturation(self.target("#F34820")),
                               saturation(parse_color("#F34820")), places=2)

    def test_lightness_is_clamped(self):
        for source in ("#7aa2f7", "#205EA6", "#F34820"):
            self.assertGreaterEqual(lightness(self.target(source)), CONFIG["min_lightness"] - 0.01)
            self.assertLessEqual(lightness(self.target(source)), CONFIG["max_lightness"] + 0.01)

    def test_channels_stay_in_range(self):
        for source in ("#000000", "#FFFFFF", "#FF0000", "#00FF00", "#0000FF", "#123456"):
            self.assertTrue(all(0 <= c <= 255 for c in self.target(source)), source)


if __name__ == "__main__":
    unittest.main()
