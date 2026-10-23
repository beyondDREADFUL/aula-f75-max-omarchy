"""Music visualiser: spectrum bars streamed as live frames (cable only).

Levels come from cava when it is installed (its own PipeWire/PulseAudio input, smoothing and
auto-sensitivity), else from a numpy FFT of the system audio (needs numpy and soundcard).
The background can be off, a named or hex colour, a slow hue cycle, or "ambilight": the
screen's dominant colour, sampled with grim. Live frames bypass the firmware's white balance, so every
colour goes through lighting.calibrate to look the same as an effect.
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
import threading
import time
from dataclasses import dataclass

from .layout import COLS, POS, ROWS
from .lighting import calibrate

SOLID = {"white": (255, 255, 255), "red": (255, 0, 0), "orange": (255, 100, 0),
         "yellow": (255, 220, 0), "green": (0, 255, 0), "cyan": (0, 255, 255),
         "blue": (0, 0, 255), "purple": (160, 0, 255)}
BAR_COLORS = ["green-yellow-red", "rainbow", "reverse-rainbow", "gradient", "spectrum-cycle",
              *SOLID, "off"]
BACKGROUNDS = ["off", "spectrum-cycle", "ambilight", *SOLID]
SOURCES = ["auto", "cava", "builtin"]
AMBILIGHT_AREAS = ["window", "monitor", "all"]   # what ambilight follows


class MusicError(RuntimeError):
    pass


@dataclass
class Options:
    fps: float = 20
    bars: str = "rainbow"              # one of BAR_COLORS
    background: str = "off"            # one of BACKGROUNDS, or RRGGBB
    background_brightness: int = 100   # percent
    amplitude: int = 3                 # sensitivity 1-5
    source: str = "auto"               # one of SOURCES
    seconds: float | None = None       # None = until interrupted
    test: bool = False                 # moving test pattern, no audio
    ambilight_area: str = "window"     # one of AMBILIGHT_AREAS


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


def bars_frame(levels, opts: Options, t=0.0, ambient=(0, 0, 0)):
    """COLS levels 0..1 -> {slot: rgb} (uncalibrated); each column fills from the bottom.
    Bars "off" draws only the background, as in the vendor app."""
    if opts.background == "off":
        bg = (0, 0, 0)
    else:
        base = (_hsv(t / 10) if opts.background == "spectrum-cycle" else
                ambient if opts.background == "ambilight" else
                SOLID.get(opts.background) or tuple(bytes.fromhex(opts.background)))
        bg = tuple(c * opts.background_brightness // 100 for c in base)
    colors = {}
    for slot, (row, col) in POS.items():
        lit = opts.bars != "off" and ROWS - row <= levels[col] * ROWS + 0.5
        colors[slot] = bar_color(opts.bars, row, col, t) if lit else bg
    return colors


def _hyprctl(what: str):
    import json
    try:
        out = subprocess.run(["hyprctl", "-j", what], capture_output=True, text=True,
                             timeout=2).stdout
        return json.loads(out)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def capture_area(area: str) -> list[str]:
    """grim arguments for the area ambilight follows: the focused window (or its monitor
    when nothing has focus), the focused monitor, or every monitor. Outside Hyprland it is
    always every monitor."""
    if area == "window":
        win = _hyprctl("activewindow")
        if isinstance(win, dict) and win.get("size"):
            (x, y), (w, h) = win["at"], win["size"]
            return ["-g", f"{x},{y} {w}x{h}"]
        area = "monitor"
    if area == "monitor":
        for mon in _hyprctl("monitors") or []:
            if mon.get("focused"):
                return ["-o", mon["name"]]
    return []


def screen_color(area: str = "window"):
    """The dominant colour of the area (see capture_area) at full brightness, or black when
    it is mostly neutral. Each pixel counts by its chroma, so grey, white and black areas
    don't count: a plain desktop averages out to near grey, which shows as white on the keys."""
    shot = subprocess.run(["grim", *capture_area(area), "-t", "ppm", "-s", "0.05", "-"],
                          capture_output=True, check=True).stdout
    # binary PPM: "P6", width, height, maxval as ASCII separated by whitespace, then RGB
    fields, pos = [], 0
    while len(fields) < 4:
        while shot[pos:pos + 1].isspace():
            pos += 1
        end = pos
        while not shot[end:end + 1].isspace():
            end += 1
        fields.append(shot[pos:end])
        pos = end
    raw = shot[pos + 1:]
    total, weight, pixels = [0, 0, 0], 0, len(raw) // 3
    for k in range(0, pixels * 3, 3):
        r, g, b = raw[k], raw[k + 1], raw[k + 2]
        w = max(r, g, b) - min(r, g, b)
        weight += w
        total[0] += r * w
        total[1] += g * w
        total[2] += b * w
    if pixels == 0 or weight / pixels < 12:      # mostly neutral: no background
        return (0, 0, 0)
    avg = [c / weight for c in total]
    return tuple(int(c * 255 / max(avg)) for c in avg)


class Ambilight:
    """Samples the screen in a thread (a capture takes 0.1-0.3 s) and eases the shown colour
    25 % toward it per frame."""

    def __init__(self, area: str = "window"):
        if not shutil.which("grim"):
            raise MusicError("the ambilight background needs grim (Wayland screenshots)")
        self.area = area
        self.target = self.shown = screen_color(area)
        self.error = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                self.target = screen_color(self.area)
            except Exception as exc:      # noqa: BLE001 - reported from the drawing side
                self.error = exc
                return
            time.sleep(0.05)

    def color(self):
        if self.error:
            raise MusicError(f"screen capture failed: {self.error}")
        self.shown = tuple(s + (t - s) * 0.25 for s, t in zip(self.shown, self.target))
        return tuple(int(c) for c in self.shown)


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
    """(name, iterator of COLS levels 0..1, close), or None if cava is missing or prints
    nothing within 3 s."""
    exe = shutil.which("cava")
    if not exe:
        return None
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
        print(f"cava did not start{': ' + err[-200:] if err else ''}", file=sys.stderr)
        return None
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
    return "cava", levels(), close


def builtin_levels(opts: Options):
    """(name, iterator of COLS levels 0..1, close) from a numpy FFT of the system audio."""
    try:
        import numpy as np
        import soundcard as sc
    except ImportError as exc:
        raise MusicError("music needs cava, or: pip install numpy soundcard") from exc
    rate, n = 48000, 2048
    spk = sc.default_speaker()
    # small blocks so short reads return promptly
    rec = sc.get_microphone(id=str(spk.name), include_loopback=True).recorder(
        samplerate=rate, channels=1, blocksize=256)
    rec.__enter__()
    edges = np.geomspace(40, 16000, COLS + 1)
    freqs = np.fft.rfftfreq(n, 1 / rate)
    bands = [(freqs >= lo) & (freqs < hi) for lo, hi in zip(edges[:-1], edges[1:])]

    def levels():
        lv, peak, data, consumed, t0 = np.zeros(COLS), 1e-3, np.zeros(n), 0, time.time()
        while True:
            # read exactly the audio produced since the last read; a fixed amount per
            # frame let the backlog grow and the bars fell seconds behind the music
            new = rec.record(numframes=max(int(rate * (time.time() - t0)) - consumed, 256))[:, 0]
            consumed += len(new)
            data = np.concatenate([data, new])[-n:]
            spec = np.abs(np.fft.rfft(data * np.hanning(n)))
            power = np.log1p(np.array([spec[m].mean() if m.any() else 0 for m in bands]) * 50)
            peak = max(peak * 0.995, power.max())          # slow auto-gain
            target = np.clip(power / peak, 0, 1) if peak > 0.05 else np.zeros(COLS)
            target = np.clip(target * (0.6 + 0.2 * opts.amplitude), 0, 1)
            lv = np.maximum(target, lv * 0.75)             # fast attack, smooth decay
            yield lv
    return spk.name, levels(), lambda: rec.__exit__(None, None, None)


def run(kb, opts: Options, on_start=print) -> tuple[float, int | None]:
    """Stream bars to kb until opts.seconds pass or SIGINT, SIGTERM or SIGUSR1 arrives.
    Returns (frames per second, the signal that stopped it or None)."""
    interval = 1 / opts.fps
    amb = Ambilight(opts.ambilight_area) if opts.background == "ambilight" else None
    t_start, frames = time.time(), 0

    def draw(levels):
        nonlocal frames
        t = time.time() - t_start
        colors = bars_frame(levels, opts, t, amb.color() if amb else (0, 0, 0))
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
        source = cava_levels(opts) if opts.source != "builtin" else None
        if source is None:
            if opts.source == "cava":
                raise MusicError("cava is not installed or did not start")
            source = builtin_levels(opts)
        name, levels, close = source
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
            # sources can return early with buffered audio; don't exceed fps
            time.sleep(max(0, interval - (time.time() - loop_start)))
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        close()
    return frames / max(1e-6, time.time() - t_start), (stop[0] if stop else None)
