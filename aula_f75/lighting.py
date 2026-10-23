"""Lighting payloads and the firmware's colour calibration.

Effects (command 0x13) and per-key colours (0x23 + mode 0x80) are stored calibrated by the
firmware; live frames (0x20) are stored raw. Seen side by side, the calibrated white is
neutral and raw white is warm, so the calibration is a correct white balance: send intended
colours to effects, and run live-frame colours through calibrate() to match them.
"""
from __future__ import annotations

from dataclasses import dataclass

from .layout import KEY_SLOTS, SLOTS

# names from the vendor's language file, in mode-id order; all checked on the keyboard
MODES = {
    "off": 0x00, "static": 0x01, "single-on": 0x02, "single-off": 0x03, "glittering": 0x04,
    "falling": 0x05, "colourful": 0x06, "breath": 0x07, "spectrum": 0x08, "outward": 0x09,
    "scrolling": 0x0A, "rolling": 0x0B, "rotating": 0x0C, "explode": 0x0D, "launch": 0x0E,
    "ripples": 0x0F, "flowing": 0x10, "pulsating": 0x11, "tilt": 0x12, "shuttle": 0x13,
    "custom": 0x80,
}

# Firmware calibration, fitted to read-back values: per-channel gain times a brightness
# curve (levels 1-5). Matches the stored table to within about 1 per channel.
GAIN = (0.6575, 0.9911, 0.9885)
BRIGHTNESS = (0.1805, 0.3750, 0.6598, 0.7848, 1.0000)


@dataclass(frozen=True)
class Effect:
    mode: str = "static"
    color: tuple[int, int, int] | None = None   # None = the effect's rainbow
    brightness: int = 5                          # 0-5
    speed: int = 3                               # 0-5
    direction: int = 0                           # 0 or 1

    def payload(self) -> bytes:
        """The 16-byte effect payload, shared by cable (0x13) and dongle (05).
        Static and custom never use the rainbow flag."""
        mode = MODES[self.mode]
        rainbow = 1 if self.color is None and mode not in (0x01, 0x80) else 0
        r, g, b = self.color or ((255, 0, 0) if rainbow else (255, 255, 255))
        return bytes([mode, r, g, b, 0, 0, 0, 0, rainbow, self.brightness, self.speed,
                      self.direction, 0, 0, 0xAA, 0x55])


def color_table(colors: dict[int, tuple[int, int, int]], default=(0, 0, 0)) -> bytes:
    """576-byte per-key table (0x23 / dongle 14): [slot, R, G, B] per key slot, aa 55 at
    the end. colors: {slot: rgb}; keys not listed get default."""
    buf = bytearray(SLOTS * 4)
    for slot in KEY_SLOTS:
        buf[slot * 4:slot * 4 + 4] = bytes([slot, *colors.get(slot, default)])
    buf[-2:] = b"\xaa\x55"
    return bytes(buf)


def calibrate(rgb, brightness: int = 5) -> tuple[int, int, int]:
    """What the firmware stores for rgb at a brightness level 1-5."""
    scale = BRIGHTNESS[max(1, min(5, brightness)) - 1]
    return tuple(round(c * g * scale) for c, g in zip(rgb, GAIN))


def infer_brightness(stored, rgb) -> int | None:
    """The brightness level 1-5 at which rgb is stored as `stored`, or None if no level
    fits within the model's error."""
    error, level = min((sum(abs(a - b) for a, b in zip(stored, calibrate(rgb, lv))), lv)
                       for lv in range(1, 6))
    return level if error <= 12 else None
