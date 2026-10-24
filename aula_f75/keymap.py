"""Keymap layers and macros.

A layer (base 0x11, Fn 0x27; dongle 03 per key) is 144 entries of 4 bytes, indexed by LED
slot: [2, 0, usage, 0] remaps a key, [6, macro slot, 0, 0] binds a macro, all zero keeps the
default. Writing a layer replaces all of it. The macro store (0x15, dongle 09) is shared.
"""
from __future__ import annotations

from .layout import KEYS, SLOTS, key

MACRO_SLOTS = 100


def parse_assignments(specs: list[str], all_macros: bool = False):
    """["capslock=esc", "f1=shift+h,i"] -> (layer entries {slot: 4 bytes}, macros).
    "," separates macro steps, "+" presses keys together. A single plain key is a remap
    unless all_macros. Each macro is a list of steps, each step a list of key names."""
    entries, macros = {}, []
    for spec in specs:
        src, sep, dst = spec.partition("=")
        if not sep:
            raise ValueError(f"bad assignment {spec!r}: expected e.g. capslock=esc or f1=a,b,c")
        slot = KEYS[key(src)][0]
        steps = [[key(k) for k in step.split("+")] for step in dst.split(",") if step]
        if not steps:
            raise ValueError(f"bad assignment {spec!r}: nothing to map to")
        if any(KEYS[k][1] is None for step in steps for k in step):
            raise ValueError("cannot map to Fn")
        if all_macros or len(steps) > 1 or len(steps[0]) > 1:
            entries[slot] = (6, len(macros), 0, 0)
            macros.append(steps)
        else:
            entries[slot] = (2, 0, KEYS[steps[0][0]][1], 0)
    if len(macros) > MACRO_SLOTS:
        raise ValueError(f"at most {MACRO_SLOTS} macros")
    return entries, macros


def layer_table(entries: dict[int, tuple]) -> bytes:
    """576-byte layer table with aa 55 at the end; an empty dict restores the default."""
    buf = bytearray(SLOTS * 4)
    for slot, vals in entries.items():
        buf[slot * 4:slot * 4 + 4] = bytes(vals)
    buf[-2:] = b"\xaa\x55"
    return bytes(buf)


def macro_blob(macros, delay_ms: int = 100) -> bytes:
    """The macro store. 100 slots of [offset u16, 0, 0] (first macro at 400), then per
    macro an 8-byte header [word count u16, 0*6] and 2 words per event: [0, 0, usage,
    b0 press / 30 release], [delay_ms u16, 00, 50]. A step's keys are pressed in order and
    released in reverse. Sized to whole 64-byte packets plus one, aa 55 at the end."""
    body, offsets = bytearray(), []
    for steps in macros:
        offsets.append(MACRO_SLOTS * 4 + len(body))
        events = []
        for combo in steps:
            events += [(KEYS[k][1], 0xB0) for k in combo]
            events += [(KEYS[k][1], 0x30) for k in reversed(combo)]
        words = bytearray()
        for n, (usage, flag) in enumerate(events):
            ms = 10 if n == len(events) - 1 else delay_ms
            words += bytes([0, 0, usage, flag]) + ms.to_bytes(2, "little") + b"\x00\x50"
        body += (len(words) // 4).to_bytes(2, "little") + bytes(6) + words
    used = MACRO_SLOTS * 4 + len(body)
    blob = bytearray(((used + 63) // 64 + 1) * 64)
    for i, off in enumerate(offsets):
        blob[i * 4:i * 4 + 2] = off.to_bytes(2, "little")
    blob[MACRO_SLOTS * 4:used] = body
    blob[-2:] = b"\xaa\x55"
    return bytes(blob)
