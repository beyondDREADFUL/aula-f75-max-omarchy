"""Animated colour changes, streamed as live frames (cable only).

Order matters (seen on the keyboard): the first frame shows the old colour so the keyboard
displays live frames, then the new effect is set at live-frame pacing so it fits between two
frames, then the animation runs. When the frames stop, the keyboard is already on the new
effect, so neither end flashes. Setting the effect at the normal 35 ms pacing, or after the
animation, showed the new or the old colour for a moment.
"""
from __future__ import annotations

import math
import time

from .layout import COLS, POS, ROWS
from .lighting import Effect, calibrate

STYLES = ["none", "fade", "wave", "explode"]
FPS = 20
EDGE = 0.25          # width of the soft edge in wave and explode, as a share of the sweep


def delay(style: str, slot: int) -> float:
    """0..1: how far into the sweep this key starts changing."""
    row, col = POS[slot]
    if style == "wave":                      # left to right
        return col / (COLS - 1)
    if style == "explode":                   # out from the middle
        cx, cy = (COLS - 1) / 2, (ROWS - 1) / 2
        return math.hypot((col - cx) / cx, (row - cy) / cy) / math.sqrt(2)
    return 0.0


def mix(style: str, slot: int, t: float, old, new) -> tuple[int, int, int]:
    """The colour of a key at time t (0..1) of the transition."""
    k = t if style == "fade" else (t * (1 + EDGE) - delay(style, slot)) / EDGE
    k = min(1.0, max(0.0, k))
    k = k * k * (3 - 2 * k)                  # smoothstep
    return tuple(round(a + (b - a) * k) for a, b in zip(old, new))


def run(kb, old, new, effect: Effect, style: str = "wave", seconds: float = 1.0) -> None:
    """Change the keys from `old` to `new` with an animation, ending on `effect` (which
    should show `new`). kb must be wired; style "none" just sets the effect."""
    if style == "none" or kb.transport != "wired":
        kb.light(effect)
        return
    level = effect.brightness
    kb.frame({s: calibrate(old, level) for s in POS})
    kb.light(effect, fast=True)
    n = max(2, round(seconds * FPS))
    for i in range(n + 1):
        start = time.time()
        kb.frame({s: calibrate(mix(style, s, i / n, old, new), level) for s in POS})
        time.sleep(max(0, 1 / FPS - (time.time() - start)))
