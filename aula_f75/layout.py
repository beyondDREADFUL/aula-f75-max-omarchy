"""Physical layout: key names, LED slots, HID usages, grid positions.

The LED table has 144 slots. Only the 80 slots in KEYS light up (checked by eye, docs/
HANDBOOK.md); 95, 110 and 111 are written by effects but nothing lights up, the rest are
empty. Slot numbers and usages come from the vendor's layouts/rgb-keyboard.xml.
"""

# key name -> (LED slot, HID usage); Fn has no usage of its own
KEYS = {
    "esc": (1, 0x29), "f1": (2, 0x3A), "f2": (3, 0x3B), "f3": (4, 0x3C), "f4": (5, 0x3D),
    "f5": (6, 0x3E), "f6": (7, 0x3F), "f7": (8, 0x40), "f8": (9, 0x41), "f9": (10, 0x42),
    "f10": (11, 0x43), "f11": (12, 0x44), "f12": (13, 0x45),
    "grave": (19, 0x35), "1": (20, 0x1E), "2": (21, 0x1F), "3": (22, 0x20), "4": (23, 0x21),
    "5": (24, 0x22), "6": (25, 0x23), "7": (26, 0x24), "8": (27, 0x25), "9": (28, 0x26),
    "0": (29, 0x27), "minus": (30, 0x2D), "equal": (31, 0x2E), "backspace": (103, 0x2A),
    "delete": (119, 0x4C),
    "tab": (37, 0x2B), "q": (38, 0x14), "w": (39, 0x1A), "e": (40, 0x08), "r": (41, 0x15),
    "t": (42, 0x17), "y": (43, 0x1C), "u": (44, 0x18), "i": (45, 0x0C), "o": (46, 0x12),
    "p": (47, 0x13), "lbracket": (48, 0x2F), "rbracket": (49, 0x30), "backslash": (67, 0x31),
    "pageup": (118, 0x4B),
    "capslock": (55, 0x39), "a": (56, 0x04), "s": (57, 0x16), "d": (58, 0x07), "f": (59, 0x09),
    "g": (60, 0x0A), "h": (61, 0x0B), "j": (62, 0x0D), "k": (63, 0x0E), "l": (64, 0x0F),
    "semicolon": (65, 0x33), "quote": (66, 0x34), "enter": (85, 0x28), "pagedown": (121, 0x4E),
    "lshift": (73, 0xE1), "z": (74, 0x1D), "x": (75, 0x1B), "c": (76, 0x06), "v": (77, 0x19),
    "b": (78, 0x05), "n": (79, 0x11), "m": (80, 0x10), "comma": (81, 0x36), "period": (82, 0x37),
    "slash": (83, 0x38), "rshift": (84, 0xE5), "up": (101, 0x52), "end": (120, 0x4D),
    "lctrl": (91, 0xE0), "lwin": (92, 0xE3), "lalt": (93, 0xE2), "space": (94, 0x2C),
    "fn": (96, None), "rctrl": (98, 0xE4), "left": (99, 0x50), "down": (100, 0x51),
    "right": (102, 0x4F),
}
ALIASES = {"ctrl": "lctrl", "shift": "lshift", "alt": "lalt", "win": "lwin", "super": "lwin"}

KEY_SLOTS = sorted(slot for slot, _ in KEYS.values())
SLOTS = 144

# LED slot -> (row, column) on a 6 x 15 grid, for row/column based drawing
ROWS, COLS = 6, 15
POS = {
    1: (0, 0), 2: (0, 1), 3: (0, 2), 4: (0, 3), 5: (0, 4), 6: (0, 5), 7: (0, 6), 8: (0, 7),
    9: (0, 8), 10: (0, 9), 11: (0, 10), 12: (0, 11), 13: (0, 12),
    19: (1, 0), 20: (1, 1), 21: (1, 2), 22: (1, 3), 23: (1, 4), 24: (1, 5), 25: (1, 6),
    26: (1, 7), 27: (1, 8), 28: (1, 9), 29: (1, 10), 30: (1, 11), 31: (1, 12), 103: (1, 13),
    119: (1, 14),
    37: (2, 0), 38: (2, 1), 39: (2, 2), 40: (2, 3), 41: (2, 4), 42: (2, 5), 43: (2, 6),
    44: (2, 7), 45: (2, 8), 46: (2, 9), 47: (2, 10), 48: (2, 11), 49: (2, 12), 67: (2, 13),
    118: (2, 14),
    55: (3, 0), 56: (3, 1), 57: (3, 2), 58: (3, 3), 59: (3, 4), 60: (3, 5), 61: (3, 6),
    62: (3, 7), 63: (3, 8), 64: (3, 9), 65: (3, 10), 66: (3, 11), 85: (3, 13), 121: (3, 14),
    73: (4, 0), 74: (4, 2), 75: (4, 3), 76: (4, 4), 77: (4, 5), 78: (4, 6), 79: (4, 7),
    80: (4, 8), 81: (4, 9), 82: (4, 10), 83: (4, 11), 84: (4, 12), 101: (4, 13), 120: (4, 14),
    91: (5, 0), 92: (5, 1), 93: (5, 2), 94: (5, 6), 96: (5, 9), 98: (5, 10), 99: (5, 12),
    100: (5, 13), 102: (5, 14),
}


class UnknownKey(KeyError):
    def __str__(self):          # KeyError would print the message in quotes
        return str(self.args[0])


def key(name: str) -> str:
    """Normalize a key name; raises UnknownKey (a KeyError) for unknown names."""
    name = ALIASES.get(name.lower(), name.lower())
    if name not in KEYS:
        raise UnknownKey(f"unknown key {name!r}")
    return name
