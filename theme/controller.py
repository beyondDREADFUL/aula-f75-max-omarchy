"""`f75ctl theme`: apply the Omarchy theme accent to the keyboard and report state.

Wired apply: read page 0 of the LED table (keys Esc-F12) to learn the brightness the user
set with the keyboard's own keys, then one effect command in the target colour, then the
LCD clock. The dongle has no read-back, so it reuses the stored brightness.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import signal
import sys
import tomllib
from collections import Counter
from datetime import datetime
from pathlib import Path

from aula_f75 import lighting, music, transition
from aula_f75.device import Busy, NotFound, Rejected, open_keyboard, present
from aula_f75.layout import KEY_SLOTS
from aula_f75.lcd import clock_payload

from . import config as cfg
from .color import describe, hexstr, parse_color, vivid

STATE_VERSION = 2
EXIT_SKIPPED = 3          # with --strict: no keyboard, or it is busy, so nothing was applied
VERIFY_TOLERANCE = 18      # summed channel difference; the model is within ~1 per channel


def resolve_target(config: dict, color: str | None = None, exact: bool = False):
    """(target rgb, accent rgb, source). Order: explicit colour (as written with exact),
    a pin, fixed mode, a [theme_overrides] entry (used as written), the theme accent."""
    if color:
        accent = parse_color(color)
        return (accent, accent, "override-exact") if exact else (vivid(accent, config), accent,
                                                                 "override")
    if config["color_mode"] == "fixed":
        accent = parse_color(config["fixed_color"])
        return vivid(accent, config), accent, "fixed"
    text, key = cfg.theme_accent()
    accent = parse_color(text)
    slug = cfg.theme_slug()
    if slug and slug in config["theme_overrides"]:
        try:
            target = parse_color(config["theme_overrides"][slug])
            return target, accent, f"theme_override:{slug}"
        except ValueError as exc:
            cfg.log(f"invalid theme override for {slug}: {exc}")
    return vivid(accent, config), accent, key


def current_target() -> str:
    """#RRGGBB the keys would show for the theme now (a pin and overrides included)."""
    config = load_config()
    color, exact = None, False
    if pin := cfg.load_pin():
        color, exact = pin["color"], pin["exact"]
    return hexstr(resolve_target(config, color, exact)[0])


def proc_start_time(pid: int) -> str | None:
    """Field 22 of /proc/PID/stat (start time in ticks), or None. The comm field (2) may
    hold spaces and parentheses, so split after the last ')': field 22 is index 19 then."""
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
        return text[text.rindex(")") + 1:].split()[19]
    except (OSError, ValueError, IndexError):
        return None


def music_following_theme() -> int | None:
    """The pid of the widget's music visualiser if it shows the theme colour behind the bars.
    music.pid holds `PID STARTTIME`; both must match the live process (so a reused pid is not
    mistaken for it) and its command line must be f75ctl music. A bare `PID` (older file) is
    accepted only through the command line check."""
    try:
        fields = (cfg.STATE_DIR / "music.pid").read_text().split()
        pid = int(fields[0])
        background = (cfg.STATE_DIR / "music.background").read_text().strip()
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (OSError, ValueError, IndexError):
        return None
    if len(fields) > 1 and fields[1] != proc_start_time(pid):
        return None
    if background != "theme" or b"f75ctl" not in cmdline or b"music" not in cmdline:
        return None
    return pid


def _dominant(entries, slots):
    values = [e[1:] for e in entries if e[0] in slots and e[1] | e[2] | e[3]]
    if not values:
        return None, 0
    value, count = Counter(values).most_common(1)[0]
    return value, count / len(values)


def live_brightness(kb, last_target, fallback: int) -> int:
    """The brightness level the keys are showing now, from page 0 of the table, if it is
    uniform and matches the last colour we set; else fallback."""
    if last_target is None:
        return fallback
    stored, share = _dominant(kb.read_table(pages=1), set(KEY_SLOTS))
    if stored is None or share < 0.8:
        return fallback
    return lighting.infer_brightness(stored, last_target) or fallback


def verify(kb, target, brightness) -> bool:
    stored, _ = _dominant(kb.read_table(), set(KEY_SLOTS))
    expected = lighting.calibrate(target, brightness)
    return stored is not None and sum(abs(a - b) for a, b in zip(stored, expected)) <= VERIFY_TOLERANCE


PALETTE_KEYS = ("accent", "red", "yellow", "green", "cyan", "blue", "magenta")
NEAR_COLOUR = 60          # RGB distance below which two swatches look the same


def load_config() -> dict:
    """The config with the widget's effect and speed applied."""
    config = cfg.load_config()
    chosen = cfg.effect_override()
    config["effect_source"] = "widget" if "effect" in chosen else "config"
    config.update(chosen)
    config["rainbow"] = bool(config.get("rainbow")) and config["effect"] not in cfg.NO_COLOR_EFFECTS
    return config


def _near(a: str, b: str) -> bool:
    """True when two '#RRGGBB' colours are within NEAR_COLOUR of each other in RGB."""
    ra, rb = (tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for h in (a, b))
    return math.dist(ra, rb) < NEAR_COLOUR


def theme_palette(config: dict, colors: dict, first=None) -> list[tuple[str, str]]:
    """[(theme colour, LED colour)] for the theme's accent and named colours, each through
    the automatic choice, without repeating a theme or LED colour, or keeping one whose LED
    colour looks like one already kept (two near-identical swatches waste a slot). `first`
    (the theme's actual target, which a [theme_overrides] entry can set) replaces the accent's
    entry."""
    seen, out = set(), []
    if first:
        seen.update(first)
        out.append(first)
    for key in PALETTE_KEYS[1:] if first else PALETTE_KEYS:
        try:
            source = parse_color(colors[key])
        except (KeyError, ValueError):
            continue
        source, target = hexstr(source), hexstr(vivid(source, config))
        if source not in seen and target not in seen and not any(_near(target, t) for _, t in out):
            seen.update((source, target))
            out.append((source, target))
    return out


def _resolve_and_pin(args, config):
    """(target, accent, source) for this apply; saves a --pin colour first."""
    color, exact = args.color, args.exact
    if color and args.pin and not args.dry_run:
        parse_color(color)
        cfg.save_pin(color, exact)
    elif not color and (pin := cfg.load_pin()):
        color, exact = pin["color"], pin["exact"]
    return resolve_target(config, color, exact)


def _record_devices() -> None:
    # udev runs apply on every plug and unplug; the widget watches this file
    try:
        cfg.save_devices(present())
    except OSError as exc:
        cfg.log(f"could not write {cfg.DEVICES_FILE}: {exc}")


def _hand_to_music(args, summary) -> bool:
    """True if the music visualiser took the new colour."""
    if (not args.color or args.pin) and (pid := music_following_theme()):
        # music holds the keyboard: have it reload the background colour between frames,
        # instead of waiting 15 s for the lock; it applies the theme itself when it stops
        try:
            os.kill(pid, signal.SIGHUP)
            cfg.log(f"{summary} result=music background")
            return True
        except OSError:
            pass
    return False


def _open_logged(config, summary, strict=False):
    """The open keyboard, or the return code when it can't be opened (logged). A missing
    keyboard (skipped) or a busy one (deferred) returns 0, which the theme hook and the
    systemd service rely on; with strict they return EXIT_SKIPPED."""
    skipped = EXIT_SKIPPED if strict else 0
    try:
        return open_keyboard(config["device_prefer"])
    except NotFound as exc:
        cfg.log(f"{summary} result=skipped ({exc})")
        return skipped
    except Busy:
        # music mode or f75ctl holds the keyboard; they hand back with `apply` when done
        cfg.log(f"{summary} result=deferred (keyboard busy)")
        return skipped
    except OSError as exc:
        # e.g. no access to the hidraw node before the 'aula' group applies
        cfg.log(f"{summary} result=failed ({exc})")
        return 1


def _last_target(state):
    last = state.get("target_rgb")
    return tuple(last) if isinstance(last, list) and len(last) == 3 else None


def _choose_brightness(args, kb, state, config) -> int:
    try:
        stored = int(state.get("brightness", config["default_brightness"]))
    except (TypeError, ValueError, OverflowError):
        stored = config["default_brightness"]      # corrupt state.json
    stored = min(max(stored, 1), 5)
    if args.brightness is not None:
        return min(max(args.brightness, 1), 5)
    if config["rainbow"]:
        return stored       # a still rainbow isn't uniform, so the keys would read wrong
    if kb.transport == "wired" and state.get("effect", "static") == "static":
        # only a static colour can be read back: an animated effect shows the keys
        # dimmed part of the time, which would read as a lower level
        return live_brightness(kb, _last_target(state), stored)
    return stored


def _write(args, kb, state, config, target, brightness) -> str:
    """Show the effect (through a transition where possible), set the clock and verify.
    Returns the verify result: "n/a", "skipped", "True" or "False"."""
    last = _last_target(state)
    # the rainbow flag has no single colour to move to or verify
    rainbow = config["rainbow"]
    effect = lighting.Effect(config["effect"], None if rainbow else target, brightness,
                             config["speed"], config["direction"], rainbow=rainbow)
    # animate only from one static colour to another: an animated effect has no
    # single colour to start from, and the dongle can't show live frames
    if (not rainbow and kb.transport == "wired" and last and last != target
            and config["effect"] == "static" and state.get("effect", "static") == "static"):
        transition.run(kb, last, target, effect, config["transition"],
                       config["transition_time"])
    else:
        kb.light(effect)
    if kb.transport != "wired":
        return "n/a"
    if config["lcd_clock"]:
        kb.set_clock(clock_payload())
    if args.verify and config["effect"] == "static" and not rainbow:
        return str(verify(kb, target, brightness))
    return "skipped"


def _save_and_log(kb, summary, theme, accent, source, target, brightness, config, verified,
                  picked=False):
    cfg.save_state({
        "version": STATE_VERSION, "theme": theme, "accent": hexstr(accent),
        "accent_source": source, "target": hexstr(target), "target_rgb": list(target),
        "brightness": brightness, "effect": config["effect"], "rainbow": config["rainbow"],
        "picked": picked,       # a colour chosen by hand: effect, speed and brightness keep it
        "transport": kb.transport,
        "device_path": kb.path, "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    cfg.log(f"{summary} brightness={brightness} effect={config['effect']} "
            f"transport={kb.transport} verified={verified} result=ok")


def cmd_apply(args) -> int:
    if not args.dry_run:
        _record_devices()
        if args.color and not getattr(args, "keep_rainbow", False):
            cfg.clear_rainbow()     # a colour picked on purpose replaces the rainbow
    config = load_config()
    state = cfg.load_state()
    theme = cfg.theme_slug() or args.theme or state.get("theme") or "unknown"
    try:
        target, accent, source = _resolve_and_pin(args, config)
    except (ValueError, OSError, RuntimeError) as exc:
        cfg.log(f"apply failed: {exc}")
        return 1
    summary = (f"theme={theme} accent={hexstr(accent)} ({source}) target={hexstr(target)} "
               f"{describe(target)}")
    if args.dry_run:
        print(summary)
        return 0
    if _hand_to_music(args, summary):
        return 0
    kb = _open_logged(config, summary, getattr(args, "strict", False))
    if isinstance(kb, int):
        return kb
    try:
        with kb:
            brightness = _choose_brightness(args, kb, state, config)
            verified = _write(args, kb, state, config, target, brightness)
    except (Rejected, OSError) as exc:
        cfg.log(f"{summary} transport={kb.transport} result=failed ({exc})")
        return 1
    _save_and_log(kb, summary, theme, accent, source, target, brightness, config, verified,
                  picked=bool(args.color))
    if verified == "False":
        return 1
    if getattr(args, "unpin", False) and not args.pin:
        cfg.clear_pin()         # only now: a failed apply keeps the pin
    return 0


def _reapply(brightness=None, strict=False) -> int:
    """`f75ctl theme apply`, optionally forcing a brightness. A colour chosen by hand (and
    not pinned) is kept, so a speed or effect change doesn't fall back to the theme."""
    args = build_parser().parse_args(["apply"])
    args.brightness = brightness
    args.strict = strict
    state = cfg.load_state()
    if state.get("picked") and cfg.load_pin() is None and state.get("target"):
        args.color, args.exact = state["target"], True
        args.keep_rainbow = True    # the colour is only being re-sent, not chosen again
    return cmd_apply(args)


def cmd_set_effect(args) -> int:
    if args.effect == "default":
        cfg.save_effect(None)
    elif args.effect in lighting.MODES and args.effect not in cfg.NO_COLOR_EFFECTS:
        cfg.save_effect(args.effect, args.speed)
    else:
        print(f"unknown effect {args.effect!r}", file=sys.stderr)
        return 2
    return _reapply(strict=args.strict)


def cmd_set_rainbow(args) -> int:
    if args.state == "on":
        cfg.save_rainbow(True, args.speed)
    else:
        cfg.save_rainbow(False, args.speed)
    return _reapply(strict=args.strict)


def cmd_reset(args) -> int:
    """Back to the theme: clear the pin and the rainbow flag (the effect, speed and transition
    stay) and forget the hand-picked colour, then apply the theme colour."""
    cfg.clear_pin()
    cfg.clear_rainbow()
    state = cfg.load_state()
    if state.get("picked"):
        state["picked"] = False
        cfg.save_state(state)
    return _reapply(strict=args.strict)


def cmd_choices(args) -> int:
    """The names the widget offers, from the library's own lists."""
    print(json.dumps({
        "effects": [m for m in lighting.MODES if m not in cfg.NO_COLOR_EFFECTS],
        "bars": [b for b in music.BAR_COLORS if b != "off"],
        "backgrounds": ["off", "theme", *[b for b in music.BACKGROUNDS if b != "off"]],
    }))
    return 0


def cmd_palette(args) -> int:
    colors = tomllib.loads((cfg.THEME_DIR / "colors.toml").read_text(encoding="utf-8"))
    config = cfg.load_config()
    target, accent, _ = resolve_target(config)
    for source, led in theme_palette(config, colors, (hexstr(accent), hexstr(target))):
        print(source, led)
    return 0


def cmd_set_transition(args) -> int:
    cfg.save_transition(args.style)
    return 0


def cmd_unpin(args) -> int:
    cfg.clear_pin()
    return 0


def cmd_set_brightness(args) -> int:
    state = cfg.load_state()
    state["brightness"] = min(max(args.brightness, 1), 5)
    cfg.save_state(state)
    return _reapply(args.brightness, strict=args.strict)


def cmd_read(args) -> int:
    with open_keyboard(cfg.load_config()["device_prefer"]) as kb:
        entries = kb.read_table()
    print(f"device={kb.path} transport={kb.transport} slots={len(entries)}")
    for start in range(0, len(entries), 16):
        print(f"{start:3d}: " + " ".join(f"{s}:{r:02x}{g:02x}{b:02x}"
                                         for s, r, g, b in entries[start:start + 16]))
    return 0


def _read_keys(config):
    with open_keyboard(config["device_prefer"]) as kb:
        return _dominant(kb.read_table(), set(KEY_SLOTS))


def cmd_status(args) -> int:
    config, state = load_config(), cfg.load_state()
    try:
        target, accent, source = resolve_target(config)
    except Exception as exc:  # noqa: BLE001
        if args.json:
            print(json.dumps({"error": str(exc)}))
        else:
            print(f"theme error: {exc}", file=sys.stderr)
        return 1
    pin = cfg.load_pin()
    devices = sorted(present())
    if args.json:
        status = {
            "theme": cfg.theme_slug() or "unknown", "theme_dir": str(cfg.THEME_DIR),
            "pin": pin, "accent": hexstr(accent), "accent_source": source,
            "target": hexstr(target), "target_description": describe(target),
            "effect": config["effect"], "effect_source": config["effect_source"],
            "rainbow": config["rainbow"],
            "speed": config["speed"], "transition": config["transition"],
            "transition_time": config["transition_time"], "devices": devices,
            "config": {"direction": config["direction"], "prefer": config["device_prefer"],
                       "lcd_clock": config["lcd_clock"],
                       "theme_overrides": len(config["theme_overrides"])},
            "state": {k: state.get(k) for k in ("brightness", "transport", "target", "effect")},
        }
        if args.read_table:
            stored, share = _read_keys(config)
            status["keys"] = {"color": hexstr(stored) if stored else None, "share": share}
        print(json.dumps(status))
        return 0
    print(f"theme: {cfg.theme_slug() or 'unknown'} ({cfg.THEME_DIR})")
    if pin:
        print(f"pin: {pin['color']}{' exact' if pin['exact'] else ''} (overrides the theme)")
    print(f"accent: {hexstr(accent)} ({source})")
    print(f"target: {hexstr(target)} {describe(target)}")
    print(f"effect: {config['effect']} ({config['effect_source']})")
    print(f"rainbow: {'on' if config['rainbow'] else 'off'}")
    print(f"speed: {config['speed']}")
    print(f"transition: {config['transition']} {config['transition_time']:g}s")
    print(f"devices: {','.join(devices) or 'none'}")
    print(f"config: direction={config['direction']} prefer={config['device_prefer']} "
          f"lcd_clock={config['lcd_clock']} theme_overrides={len(config['theme_overrides'])}")
    print(f"state: brightness={state.get('brightness', '?')} transport={state.get('transport', '?')} "
          f"target={state.get('target', '?')} effect={state.get('effect', '?')}")
    if args.read_table:
        stored, share = _read_keys(config)
        print(f"keys now: {hexstr(stored) if stored else 'off'} ({share:.0%} of lit keys)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="f75ctl theme",
                                description="Follow the active Omarchy theme on an AULA F75 Max.")
    sub = p.add_subparsers(dest="command", required=True)
    strict = argparse.ArgumentParser(add_help=False)
    strict.add_argument("--strict", action="store_true",
                        help=f"exit {EXIT_SKIPPED} when nothing was applied because the keyboard "
                        "is missing or busy (default: 0, which the hook and service rely on)")
    a = sub.add_parser("apply", help="apply the current theme colour", parents=[strict])
    a.add_argument("theme", nargs="?", help="theme name for logging")
    a.add_argument("--dry-run", action="store_true", help="print the target colour only")
    a.add_argument("--color", help="use this colour instead of the theme accent")
    a.add_argument("--exact", action="store_true", help="with --color, use it as written")
    a.add_argument("--pin", action="store_true",
                   help="with --color, keep it across theme changes until `unpin`")
    a.add_argument("--unpin", action="store_true",
                   help="clear the pin after a successful apply (not with --pin)")
    a.add_argument("--brightness", type=int, help="force a brightness level 1-5")
    a.add_argument("--verify", action="store_true", help="read the keys back afterwards (wired)")
    a.set_defaults(func=cmd_apply)
    e = sub.add_parser("set-effect", help="show the accent as this effect and apply "
                       "(\"default\" returns to the config's effect)", parents=[strict])
    e.add_argument("effect", choices=["default", *[m for m in lighting.MODES
                                                   if m not in cfg.NO_COLOR_EFFECTS]])
    e.add_argument("--speed", type=int, choices=range(6), help="effect speed 0-5")
    e.set_defaults(func=cmd_set_effect)
    r = sub.add_parser("set-rainbow", help="turn the firmware's rainbow flag on or off for the "
                       "current effect, and apply", parents=[strict])
    r.add_argument("state", choices=["on", "off"])
    r.add_argument("--speed", type=int, choices=range(6), help="effect speed 0-5")
    r.set_defaults(func=cmd_set_rainbow)
    t = sub.add_parser("set-transition", help="how the keys change colour over the cable")
    t.add_argument("style", choices=transition.STYLES)
    t.set_defaults(func=cmd_set_transition)
    sub.add_parser("palette", help="the theme's colours as the keys would show them").set_defaults(
        func=cmd_palette)
    sub.add_parser("reset", help="clear the pin, the rainbow and a picked colour, apply the "
                   "theme colour", parents=[strict]).set_defaults(func=cmd_reset)
    c = sub.add_parser("choices", help="the effect, bar and background names (JSON)")
    c.add_argument("--json", action="store_true", help="accepted for clarity; always JSON")
    c.set_defaults(func=cmd_choices)
    sub.add_parser("unpin", help="clear the pinned colour (does not apply)").set_defaults(
        func=cmd_unpin)
    sub.add_parser("read", help="dump the live LED table (wired)").set_defaults(func=cmd_read)
    s = sub.add_parser("status", help="show theme, target and state")
    s.add_argument("--read-table", action="store_true", help="also read the keys (wired)")
    s.add_argument("--json", action="store_true", help="print one JSON object (for the bar widget)")
    s.set_defaults(func=cmd_status)
    b = sub.add_parser("set-brightness", help="set brightness 1-5 and reapply", parents=[strict])
    b.add_argument("brightness", type=int)
    b.set_defaults(func=cmd_set_brightness)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (NotFound, Busy, Rejected, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    except (ValueError, RuntimeError) as exc:      # includes tomllib.TOMLDecodeError
        print(f"f75ctl theme: {exc}", file=sys.stderr)
        return 1
