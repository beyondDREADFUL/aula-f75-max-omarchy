"""Packet builders, checked against bytes that were verified on the keyboard (cable and
dongle, 2026-10-23) and against the read-back calibration measured in docs/HANDBOOK.md."""
import datetime
import unittest

from aula_f75 import keymap, lcd, lighting
from aula_f75.device import Dongle, Wired
from aula_f75.layout import KEY_SLOTS, KEYS, POS


class FakeDev:
    """Records what a transport writes; answers feature reads with an accepting echo."""

    def __init__(self):
        self.features, self.writes, self.last = [], [], b""

    def set_feature(self, payload, size=64):
        self.last = bytes(payload).ljust(64, b"\0")
        self.features.append(self.last.rstrip(b"\0").hex(" "))

    def get_feature(self, size=64):
        return self.last[:3] + b"\x01" + self.last[4:]

    def write(self, payload):
        self.writes.append(bytes(payload))

    def read(self, size, timeout):
        return None

    def close(self):
        pass


def fake(cls):
    kb = cls.__new__(cls)
    kb.dev, kb.path, kb._lock_fd = FakeDev(), "/dev/fake", -1
    return kb


class Layout(unittest.TestCase):
    def test_80_keys_all_on_the_grid(self):
        self.assertEqual(len(KEY_SLOTS), 80)
        self.assertEqual(set(KEY_SLOTS), set(POS))


class Effects(unittest.TestCase):
    def test_static_payload(self):
        # sent by `f75ctl light static -c 00ff00`, whole keyboard turned green
        self.assertEqual(lighting.Effect("static", (0, 255, 0)).payload().hex(" "),
                         "01 00 ff 00 00 00 00 00 00 05 03 00 00 00 aa 55")

    def test_effect_without_colour_is_rainbow(self):
        p = lighting.Effect("breath").payload()
        self.assertEqual((p[0], p[1:4], p[8]), (0x07, b"\xff\x00\x00", 1))

    def test_wired_transaction_framing(self):
        kb = fake(Wired)
        kb.light(lighting.Effect("static", (0, 255, 0)))
        self.assertEqual(kb.dev.features, [
            "04 18", "04 13 00 00 00 00 00 00 01",
            "01 00 ff 00 00 00 00 00 00 05 03 00 00 00 aa 55", "04 02", "04 f0"])

    def test_dongle_lighting_message(self):
        kb = fake(Dongle)
        kb._send = Dongle._send.__get__(kb)
        kb.light(lighting.Effect("static", (0, 255, 255)))
        msg = kb.dev.writes[0]
        self.assertEqual(msg[:19].hex(" "),
                         "05 10 00 01 00 ff ff 00 00 00 00 00 05 03 00 00 00 aa 55")
        self.assertEqual(msg[31], sum(msg[:31]) & 0xFF)


class Calibration(unittest.TestCase):
    # requested colour, brightness -> value read back from the keyboard
    MEASURED = [((255, 0, 0), 5, (0xa8, 0, 0)), ((255, 255, 255), 5, (0xa8, 0xfd, 0xfd)),
                ((243, 72, 32), 5, (0xa0, 0x47, 0x1f)), ((0, 0, 255), 5, (0, 0, 0xfd)),
                ((255, 0, 0), 3, (0x6e, 0, 0)), ((255, 255, 255), 3, (0x6e, 0xa6, 0xa6)),
                ((243, 72, 32), 3, (0x69, 0x2f, 0x14))]

    def test_model_matches_read_back(self):
        for rgb, level, stored in self.MEASURED:
            got = lighting.calibrate(rgb, level)
            self.assertLessEqual(max(abs(a - b) for a, b in zip(got, stored)), 1, (rgb, level))

    def test_brightness_is_inferred(self):
        for rgb, level, stored in self.MEASURED:
            self.assertEqual(lighting.infer_brightness(stored, rgb), level)

    def test_unrelated_colour_gives_no_level(self):
        self.assertIsNone(lighting.infer_brightness((0, 0xfd, 0), (255, 0, 0)))


class Tables(unittest.TestCase):
    def test_color_table(self):
        t = lighting.color_table({1: (255, 0, 0)}, default=(32, 32, 32))
        self.assertEqual(len(t), 576)
        self.assertEqual(t[4:8], bytes([1, 255, 0, 0]))
        self.assertEqual(t[94 * 4:95 * 4], bytes([94, 32, 32, 32]))
        self.assertEqual(t[0:4], bytes(4))         # empty slot stays empty
        self.assertEqual(t[-2:], b"\xaa\x55")

    def test_remap_and_macro_in_one_layer(self):
        entries, macros = keymap.parse_assignments(["capslock=esc", "f1=a,b,c", "f2=ctrl+a"])
        self.assertEqual(entries[KEYS["capslock"][0]], (2, 0, 0x29, 0))
        self.assertEqual(entries[KEYS["f1"][0]], (6, 0, 0, 0))
        self.assertEqual(entries[KEYS["f2"][0]], (6, 1, 0, 0))
        self.assertEqual(macros, [[["a"], ["b"], ["c"]], [["lctrl", "a"]]])

    def test_combo_events(self):
        # f1=shift+h,i typed "Hi" on the keyboard
        blob = keymap.macro_blob([[["lshift", "h"], ["i"]]])
        off = int.from_bytes(blob[0:2], "little")
        words = blob[off + 8:off + 8 + 12 * 4]
        events = [(words[i + 2], words[i + 3]) for i in range(0, len(words), 8)]
        self.assertEqual(events, [(0xE1, 0xB0), (0x0B, 0xB0), (0x0B, 0x30), (0xE1, 0x30),
                                  (0x0C, 0xB0), (0x0C, 0x30)])
        self.assertEqual(blob[-2:], b"\xaa\x55")
        self.assertEqual(len(blob) % 64, 0)

    def test_unknown_key(self):
        with self.assertRaises(KeyError):
            keymap.parse_assignments(["nokey=a"])


class Lcd(unittest.TestCase):
    def test_clock_payload(self):
        # 2026-10-23 was a Friday, sent as 5
        t = datetime.datetime(2026, 10, 23, 21, 11, 44)
        self.assertEqual(lcd.clock_payload(t).hex(" "), "00 01 5a 1a 0a 17 15 0b 2c 00 05")


if __name__ == "__main__":
    unittest.main()
