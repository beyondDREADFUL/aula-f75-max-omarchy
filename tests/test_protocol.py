"""Packet builders, checked against bytes that were verified on the keyboard (cable and
dongle, 2026-10-23) and against the read-back calibration measured in docs/HANDBOOK.md."""
import datetime
import unittest
import unittest.mock

from aula_f75 import keymap, lcd, lighting
from aula_f75.device import Dongle, Rejected, Unsupported, Wired, settings_block
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


class SettingsDev(FakeDev):
    """Answers a settings write the way the keyboard does: the end reply carries the sum of
    the data packet (plus bad_sum, to test a rejection) and the packet count. log keeps the
    order of the writes and reads."""

    def __init__(self, bad_sum=0):
        super().__init__()
        self.bad_sum, self.prev, self.log = bad_sum, b"", []

    def set_feature(self, payload, size=64):
        self.log.append("set")
        self.prev = self.last
        super().set_feature(payload, size)

    def get_feature(self, size=64):
        self.log.append("get")
        reply = bytearray(super().get_feature(size))
        if self.last[:2] == b"\x04\x02":
            reply[4:6] = bytes([(sum(self.prev) + self.bad_sum) & 0xFF, 1])
        return bytes(reply)


def fake(cls, dev=None):
    kb = cls.__new__(cls)
    kb.dev, kb.path, kb._lock_fd = dev or FakeDev(), "/dev/fake", -1
    return kb


class Layout(unittest.TestCase):
    def test_80_keys_all_on_the_grid(self):
        self.assertEqual(len(KEY_SLOTS), 80)
        self.assertEqual(set(KEY_SLOTS), set(POS))

    def test_right_alt_is_slot_98_right_of_space(self):
        self.assertEqual(KEYS["ralt"], (98, 0xE6))
        self.assertNotIn("rctrl", KEYS)
        self.assertEqual(POS[98], (5, 9))          # Space, Right Alt, Fn in that order
        self.assertEqual(POS[96], (5, 10))


class Effects(unittest.TestCase):
    def test_static_payload(self):
        # sent by `f75ctl light static -c 00ff00`, whole keyboard turned green
        self.assertEqual(lighting.Effect("static", (0, 255, 0)).payload().hex(" "),
                         "01 00 ff 00 00 00 00 00 00 05 03 00 00 00 aa 55")

    def test_rainbow_flag_on_a_coloured_effect(self):
        p = lighting.Effect("breath", rainbow=True).payload()
        self.assertEqual((p[0], p[1:4], p[8]), (0x07, b"\xff\x00\x00", 1))

    def test_static_with_the_rainbow_flag(self):
        p = lighting.Effect("static", rainbow=True).payload()
        self.assertEqual((p[0], p[8]), (0x01, 1))

    def test_static_without_colour_is_white(self):
        p = lighting.Effect("static").payload()
        self.assertEqual((p[1:4], p[8]), (b"\xff\xff\xff", 0))

    def test_off_and_custom_ignore_the_flag(self):
        for mode in ("off", "custom"):
            self.assertEqual(lighting.Effect(mode, (0, 0, 0), rainbow=True).payload()[8], 0)

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
        with self.assertRaises(KeyError) as caught:
            keymap.parse_assignments(["nokey=a"])
        self.assertEqual(str(caught.exception), "unknown key 'nokey'")


class Settings(unittest.TestCase):
    def test_block_bytes(self):
        self.assertEqual(settings_block(3, 2).hex(" "),
                         "00 01 00 00 00 00 03 00 02 00 00 00 00 00 aa 55")

    def test_invalid_values(self):
        for sleep, debounce in ((4, 1), (-1, 1), (0, 0), (0, 6)):
            with self.assertRaises(ValueError):
                settings_block(sleep, debounce)

    def test_cable_framing_has_no_read_back_of_the_data_packet(self):
        kb = fake(Wired, SettingsDev())
        with unittest.mock.patch("time.sleep"):
            kb.settings(3, 2)
        self.assertEqual(kb.dev.features, [
            "04 18", "04 17 01 00 00 00 00 00 01",
            f"00 01 00 00 00 00 03 00 02{' 00' * 53} aa 55", "04 02"])
        # write, read; write, read; the data packet is written and not read back
        self.assertEqual(kb.dev.log, ["set", "get", "set", "get", "set", "set", "get"])

    def test_cable_rejects_a_wrong_sum(self):
        kb = fake(Wired, SettingsDev(bad_sum=1))
        with unittest.mock.patch("time.sleep"), self.assertRaises(Rejected):
            kb.settings(0, 1)
        self.assertEqual(kb.dev.features.count("04 18"), 2)     # one retry

    def test_dongle_message(self):
        kb = fake(Dongle)
        kb._send = Dongle._send.__get__(kb)
        with unittest.mock.patch("time.sleep"):
            kb.settings(3, 2)
        msg = kb.dev.writes[0]
        self.assertEqual(msg[:19].hex(" "),
                         "07 10 00 00 01 00 00 00 00 03 00 02 00 00 00 00 00 aa 55")
        self.assertEqual(msg[31], sum(msg[:31]) & 0xFF)


class Resets(unittest.TestCase):
    def test_dongle_reset_messages(self):
        kb = fake(Dongle)
        kb._send = Dongle._send.__get__(kb)
        with unittest.mock.patch("time.sleep"):
            kb.reset()
            kb.reset(factory=True)
        for msg, cmd in zip(kb.dev.writes, (0x1F, 0x0F)):
            self.assertEqual(msg[:3].hex(" "), f"{cmd:02x} 00 00")
            self.assertEqual(msg[31], sum(msg[:31]) & 0xFF)

    def test_cable_has_no_reset(self):
        with self.assertRaises(Unsupported):
            fake(Wired).reset()


class Lcd(unittest.TestCase):
    def test_clock_payload(self):
        # 2026-10-23 was a Friday, sent as 5
        t = datetime.datetime(2026, 10, 23, 21, 11, 44)
        self.assertEqual(lcd.clock_payload(t).hex(" "), "00 01 5a 1a 0a 17 15 0b 2c 00 05")


if __name__ == "__main__":
    unittest.main()


class Transitions(unittest.TestCase):
    def test_delays_span_the_sweep(self):
        from aula_f75 import transition
        for style in ("wave", "explode"):
            delays = [transition.delay(style, s) for s in KEY_SLOTS]
            self.assertGreaterEqual(min(delays), 0.0)
            self.assertLessEqual(max(delays), 1.0)
        self.assertEqual(transition.delay("wave", 1), 0.0)       # Esc starts the wave
        # wave: Esc (left) starts before Delete (right); explode: the middle before Esc
        self.assertLess(transition.delay("wave", 1), transition.delay("wave", 119))
        self.assertLess(transition.delay("explode", 78), transition.delay("explode", 1))

    def test_every_key_starts_old_and_ends_new(self):
        from aula_f75 import transition
        old, new = (255, 0, 0), (0, 0, 255)
        for style in ("fade", "wave", "explode"):
            for s in KEY_SLOTS:
                self.assertEqual(transition.mix(style, s, 0.0, old, new), old)
                self.assertEqual(transition.mix(style, s, 1.0, old, new), new)

    def test_fast_effect_has_the_normal_framing(self):
        kb = fake(Wired)
        kb.light(lighting.Effect("static", (0, 255, 0)), fast=True)
        self.assertEqual(kb.dev.features, [
            "04 18", "04 13 00 00 00 00 00 00 01",
            "01 00 ff 00 00 00 00 00 00 05 03 00 00 00 aa 55", "04 02", "04 f0"])

    def test_run_starts_on_the_old_colour_and_sets_the_effect_first(self):
        from aula_f75 import transition
        kb = fake(Wired)
        kb.transport = "wired"
        frames = []
        kb.frame = lambda colors: frames.append(colors)
        effect = lighting.Effect("static", (0, 0, 255))
        with unittest.mock.patch("time.sleep"):
            transition.run(kb, (255, 0, 0), (0, 0, 255), effect, "wave", 0.5)
        self.assertEqual(frames[0][1], lighting.calibrate((255, 0, 0)))
        self.assertEqual(frames[-1][1], lighting.calibrate((0, 0, 255)))
        self.assertEqual(kb.dev.features[0], "04 18")      # effect set after the first frame
