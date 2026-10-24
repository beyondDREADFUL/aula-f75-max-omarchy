"""f75ctl: command line for everything the keyboard can do (the vendor app's features)."""
from __future__ import annotations

import argparse
import signal
import sys
import time

from . import keymap, lcd, lighting, music
from .device import Busy, NotFound, Rejected, Unsupported, Wired, open_keyboard
from .layout import KEYS, key


class _Printer:
    """Stands in for the hidraw device in --dry-run: prints feature reports."""
    last = b""

    def set_feature(self, payload, size=64):
        self.last = bytes(payload).ljust(64, b"\0")
        print(self.last.rstrip(b"\0").hex(" ") or "(zeros)")

    def get_feature(self, size=64):
        return self.last[:3] + b"\x01" + self.last[4:]

    def close(self):
        pass


def _dry_keyboard():
    kb = Wired.__new__(Wired)
    kb.dev, kb.path, kb._lock_fd = _Printer(), "(dry run)", -1
    return kb


def rgb(text: str):
    text = text.lstrip("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError("colour must be RRGGBB")
    return tuple(bytes.fromhex(text))


def _background(text: str) -> str:
    if text in music.BACKGROUNDS or text == "theme":
        return text
    hexpart = text.lstrip("#").lower()
    if len(hexpart) != 6 or any(c not in "0123456789abcdef" for c in hexpart):
        raise argparse.ArgumentTypeError(
            f"{text!r}: use off, spectrum-cycle, theme, a colour name or RRGGBB")
    return hexpart


def cmd_light(kb, a):
    kb.light(lighting.Effect(a.mode, a.color, a.brightness, a.speed, a.direction))


def cmd_demo(kb, a):
    for name, mode in lighting.MODES.items():
        if name in ("off", "custom") or mode < a.start:
            continue
        print(f"{mode:#04x} {name}", flush=True)
        kb.light(lighting.Effect(name, (255, 0, 0) if name == "static" else None))
        time.sleep(a.seconds)


def cmd_keycolors(kb, a):
    colors = {}
    for spec in a.assign:
        name, _, col = spec.partition("=")
        colors[KEYS[key(name)][0]] = rgb(col)
    kb.key_colors(lighting.color_table(colors, rgb(a.default)), a.brightness)


def _write_layer(kb, a, all_macros):
    entries, macros = keymap.parse_assignments(a.assign, all_macros)
    if macros:     # the macro store is shared by both layers
        kb.write_macros(keymap.macro_blob(macros, a.delay))
    kb.write_layer(keymap.layer_table(entries), a.fn_layer)


def cmd_music(kb, a):
    if kb.transport != "wired":
        raise Unsupported("music needs the USB cable (live frames don't go over 2.4G)")
    opts = music.Options(a.fps, a.color, a.background, a.background_brightness, a.amplitude,
                         a.seconds, a.test)
    reload = None
    if a.background == "theme":
        # the accent controller's colour (theme, override or pin); SIGHUP reads it again,
        # which the controller sends when the theme changes while music holds the keyboard
        from theme.controller import current_target

        def reload(opts):
            try:
                opts.background = current_target().lstrip("#").lower()
            except (ValueError, OSError, RuntimeError) as exc:
                if opts.background == "theme":
                    raise music.MusicError(f"could not read the theme colour: {exc}") from exc
                print(f"music: kept the background ({exc})", flush=True)
                return
            print(f"music: background #{opts.background}", flush=True)
        reload(opts)
    fps, stopped_by = music.run(kb, opts, on_start=lambda what: print(f"music: {what}"),
                                reload=reload)
    print(f"{fps:.1f} fps", flush=True)
    kb.close()
    if stopped_by == signal.SIGUSR1:
        return          # stopped to restart with other settings: leave the keyboard as is
    if a.after == "theme":
        # hand the keyboard back to the theme accent (also applies a theme change that was
        # deferred while music held the keyboard)
        from theme.controller import main as theme
        theme(["apply"])
    else:
        with open_keyboard() as kb2:
            kb2.light(lighting.Effect(a.after))


def cmd_battery(kb, a):
    print(f"battery {kb.battery()}%")


def cmd_gif(kb, a):
    blob, frames = lcd.image_blob(a.file)
    print(f"{frames} frame(s), {len(blob) // lcd.CHUNK} chunks")
    kb.upload_image(blob, frames,
                    progress=lambda i, n: print(f"\rchunk {i}/{n}", end="", flush=True))
    print()


def build_parser():
    p = argparse.ArgumentParser(prog="f75ctl", description="Control the AULA F75 Max.")
    p.add_argument("--dry-run", action="store_true", help="print cable packets, send nothing")
    p.add_argument("--dongle", action="store_true",
                   help="use the 2.4G dongle even when the cable is connected")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("theme", help="follow the Omarchy theme accent: apply, status, unpin, "
                   "set-effect, ... (see `f75ctl theme -h`)")

    s = sub.add_parser("light", help="set a lighting effect")
    s.add_argument("mode", choices=lighting.MODES)
    s.add_argument("-c", "--color", type=rgb, metavar="RRGGBB",
                   help="single colour (default: white for static, rainbow for effects)")
    s.add_argument("-b", "--brightness", type=int, default=5, choices=range(6))
    s.add_argument("-s", "--speed", type=int, default=3, choices=range(6))
    s.add_argument("-d", "--direction", type=int, default=0, choices=(0, 1))
    s.set_defaults(fn=cmd_light)

    s = sub.add_parser("demo", help="step through every effect, printing its name")
    s.add_argument("--seconds", type=float, default=5)
    s.add_argument("--start", type=lambda v: int(v, 0), default=1, help="first mode id")
    s.set_defaults(fn=cmd_demo)

    s = sub.add_parser("keycolors", help="per-key colours, e.g. esc=ff0000 w=00ff00")
    s.add_argument("assign", nargs="+")
    s.add_argument("--default", default="000000", help="colour for unlisted keys")
    s.add_argument("-b", "--brightness", type=int, default=5, choices=range(6))
    s.set_defaults(fn=cmd_keycolors)

    for name, all_macros, text in (
            ("remap", False, "remaps and macros in one layer, e.g. capslock=esc f1=a,b,c "
                             "f2=ctrl+c (replaces the whole layer)"),
            ("macro", True, "bind key sequences, e.g. f1=a,b,c (replaces the whole layer)")):
        s = sub.add_parser(name, help=text)
        s.add_argument("assign", nargs="+")
        s.add_argument("--delay", type=int, default=100, help="ms between macro key events")
        s.add_argument("--fn-layer", action="store_true")
        s.set_defaults(fn=lambda kb, a, m=all_macros: _write_layer(kb, a, m))

    s = sub.add_parser("reset-keymap", help="restore the default key layout")
    s.add_argument("--fn-layer", action="store_true")
    s.set_defaults(fn=lambda kb, a: kb.write_layer(keymap.layer_table({}), a.fn_layer))

    sub.add_parser("clock", help="sync the LCD clock to system time").set_defaults(
        fn=lambda kb, a: kb.set_clock(lcd.clock_payload()))

    s = sub.add_parser("gif", help="upload an image or animated GIF to the LCD (needs pillow)")
    s.add_argument("file")
    s.set_defaults(fn=cmd_gif)

    s = sub.add_parser("music", help="spectrum visualiser from system sound (Ctrl+C stops)")
    s.add_argument("--test", action="store_true", help="moving test pattern, no audio needed")
    s.add_argument("--seconds", type=float, help="stop after this many seconds")
    s.add_argument("--fps", type=float, default=20)
    s.add_argument("--color", choices=music.BAR_COLORS, default="rainbow", help="bar colours")
    s.add_argument("--amplitude", type=int, default=3, choices=range(1, 6), help="sensitivity")
    s.add_argument("--background", type=_background, default="off",
                   help="off, spectrum-cycle, a colour name, RRGGBB, or theme (the accent "
                        "controller's colour, followed on SIGHUP)")
    s.add_argument("--background-brightness", type=int, default=100, metavar="PERCENT")
    s.add_argument("--after", choices=["theme", *lighting.MODES], default="theme",
                   help="what to show when done (default: the theme accent)")
    s.set_defaults(fn=cmd_music)

    sub.add_parser("battery", help="battery level (2.4G only)").set_defaults(fn=cmd_battery)
    sub.add_parser("keys", help="list key names").set_defaults(fn=None)
    return p


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["theme"]:
        # the Omarchy theme integration has its own commands (theme/controller.py)
        from theme.controller import main as theme
        return theme(argv[1:])
    a = build_parser().parse_args(argv)
    if a.fn is None:
        print(" ".join(KEYS))
        return 0
    try:
        kb = _dry_keyboard() if a.dry_run else open_keyboard(
            "wireless" if a.dongle or a.cmd == "battery" else "auto")
        with kb:
            a.fn(kb, a)
    except (NotFound, Busy, Rejected, Unsupported, KeyError, ValueError,
            music.MusicError) as exc:
        print(f"f75ctl: {exc}", file=sys.stderr)
        return 1
    return 0
