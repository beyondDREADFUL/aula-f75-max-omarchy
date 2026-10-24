"""Music visualiser: spectrum bars streamed as live frames (cable only).

Levels come from cava (pacman -S cava), which brings its own PipeWire/PulseAudio input,
smoothing and auto-sensitivity.
The background behind the bars is off, a named or hex colour, or a slow hue cycle. Live
frames bypass the firmware's white balance, so every colour goes through lighting.calibrate
to look the same as an effect.
"""
from __future__ import annotations

import colorsys
import math
import os
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass

from .layout import COLS, POS, ROWS
from .lighting import calibrate

SOLID = {"white": (255, 255, 255), "red": (255, 0, 0), "orange": (255, 100, 0),
         "yellow": (255, 220, 0), "green": (0, 255, 0), "cyan": (0, 255, 255),
         "blue": (0, 0, 255), "purple": (160, 0, 255)}
BAR_COLORS = ["green-yellow-red", "rainbow", "reverse-rainbow", "gradient", "spectrum-cycle",
              *SOLID, "off"]
BACKGROUNDS = ["off", "spectrum-cycle", *SOLID]


class MusicError(RuntimeError):
    pass


@dataclass
class Options:
    fps: float = 20
    bars: str = "rainbow"              # one of BAR_COLORS
    background: str = "off"            # one of BACKGROUNDS, or RRGGBB
    background_brightness: int = 100   # percent
    amplitude: int = 3                 # sensitivity 1-5
    seconds: float | None = None       # None = until interrupted
    test: bool = False                 # moving test pattern, no audio


def _hsv(h):
    return tuple(int(c * 255) for c in colorsys.hsv_to_rgb(h % 1, 1, 1))


def bar_color(scheme, row, col, t):
    """Colour of a lit key; row 0 is the top (loudest) row, t is seconds since start."""
    if scheme == "green-yellow-red":     # level meter: green at the bottom, red at the top
        return {5: (0, 255, 0), 4: (0, 255, 0), 3: (160, 255, 0), 2: (255, 220, 0),
                1: (255, 120, 0), 0: (255, 0, 0)}[row]
    if scheme == "rainbow":
        return _hsv(col / COLS * 0.8)
    if scheme == "reverse-rainbow":
        return _hsv(0.8 - col / COLS * 0.8)
    if scheme == "gradient":             # vertical blend from cyan (bottom) to magenta (top)
        f = (ROWS - 1 - row) / (ROWS - 1)
        return int(255 * f), int(255 * (1 - f)), 255
    if scheme == "spectrum-cycle":       # all bars slowly cycle through the hues
        return _hsv(t / 10)
    return SOLID[scheme]


def bars_frame(levels, opts: Options, t=0.0):
    """COLS levels 0..1 -> {slot: rgb} (uncalibrated); each column fills from the bottom.
    Bars "off" draws only the background, as in the vendor app."""
    if opts.background == "off":
        bg = (0, 0, 0)
    else:
        base = (_hsv(t / 10) if opts.background == "spectrum-cycle" else
                SOLID.get(opts.background) or tuple(bytes.fromhex(opts.background)))
        bg = tuple(c * opts.background_brightness // 100 for c in base)
    colors = {}
    for slot, (row, col) in POS.items():
        lit = opts.bars != "off" and ROWS - row <= levels[col] * ROWS + 0.5
        colors[slot] = bar_color(opts.bars, row, col, t) if lit else bg
    return colors


CAVA_CONFIG = """[general]
framerate = {fps}
bars = {bars}
autosens = 1
lower_cutoff_freq = 40
higher_cutoff_freq = 16000

[output]
method = raw
raw_target = /dev/stdout
data_format = binary
bit_format = 8bit
channels = mono
mono_option = average
"""


def cava_levels(opts: Options):
    """(iterator of COLS levels 0..1, close). Raises MusicError if cava is missing or prints
    nothing within 3 s."""
    exe = shutil.which("cava")
    if not exe:
        raise MusicError("music needs cava: sudo pacman -S cava")
    with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False) as cfg:
        cfg.write(CAVA_CONFIG.format(fps=max(1, round(opts.fps)), bars=COLS))
    proc = subprocess.Popen([exe, "-p", cfg.name], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    fd = proc.stdout.fileno()

    def close():
        proc.terminate()
        proc.wait()
        os.unlink(cfg.name)
    if not select.select([fd], [], [], 3)[0] or proc.poll() is not None:
        close()
        err = proc.stderr.read().decode(errors="replace").strip()
        raise MusicError(f"cava did not start{': ' + err[-200:] if err else ''}")
    gain = 0.6 + 0.2 * opts.amplitude

    def levels():
        buf = b""
        while True:
            select.select([fd], [], [])
            chunk = os.read(fd, 4096)
            if not chunk:
                raise MusicError("cava stopped")
            buf += chunk
            # one byte per bar per frame; if frames queued up, show only the newest
            whole = len(buf) // COLS * COLS
            if whole:
                frame, buf = buf[whole - COLS:whole], buf[whole:]
                yield [min(1.0, v / 255 * gain) for v in frame]
    return levels(), close


def run(kb, opts: Options, on_start=print) -> tuple[float, int | None]:
    """Stream bars to kb until opts.seconds pass or SIGINT, SIGTERM or SIGUSR1 arrives.
    Returns (frames per second, the signal that stopped it or None)."""
    interval = 1 / opts.fps
    t_start, frames = time.time(), 0

    def draw(levels):
        nonlocal frames
        t = time.time() - t_start
        colors = bars_frame(levels, opts, t)
        kb.frame({slot: calibrate(rgb) for slot, rgb in colors.items()})
        frames += 1

    if opts.test:
        name, close = "test pattern", (lambda: None)

        def pattern():
            while True:
                t = time.time() - t_start
                yield [(math.sin(t * 3 + c * 0.5) + 1) / 2 for c in range(COLS)]
        levels = pattern()
    else:
        name = "cava"
        levels, close = cava_levels(opts)
    # Ctrl+C and SIGTERM only set a flag: stopping inside a frame leaves the keyboard
    # waiting for the rest of it, and it then rejects the next command
    stop = []
    previous = {sig: signal.signal(sig, lambda signum, _: stop.append(signum))
                for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGUSR1)}
    on_start(f"{name}; Ctrl+C to stop")
    try:
        while not stop and (opts.seconds is None or time.time() - t_start < opts.seconds):
            loop_start = time.time()
            draw(next(levels))
            # cava can deliver buffered frames at once; don't exceed fps
            time.sleep(max(0, interval - (time.time() - loop_start)))
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        close()
    return frames / max(1e-6, time.time() - t_start), (stop[0] if stop else None)
