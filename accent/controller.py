"""The omarchy-keyboard-accent command: apply the theme accent and report state.

Wired apply: read page 0 of the LED table (keys Esc-F12) to learn the brightness the user
set with the keyboard's own keys, then one effect command in the target colour, then the
LCD clock. The dongle has no read-back, so it reuses the stored brightness.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime

from aula_f75 import lighting, transition
from aula_f75.device import Busy, NotFound, Rejected, open_keyboard, present
from aula_f75.layout import KEY_SLOTS
from aula_f75.lcd import clock_payload

from . import config as cfg
from .color import describe, hexstr, parse_color, vivid

STATE_VERSION = 2
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


def load_config() -> dict:
    """The config with the widget's effect and speed applied."""
    config = cfg.load_config()
    chosen = cfg.effect_override()
    config["effect_source"] = "widget" if "effect" in chosen else "config"
    config.update(chosen)
    return config


def theme_palette(config: dict, colors: dict, first=None) -> list[tuple[str, str]]:
    """[(theme colour, LED colour)] for the theme's accent and named colours, each through
    the automatic choice, without repeating a theme or LED colour. `first` (the theme's actual
    target, which a [theme_overrides] entry can set) replaces the accent's entry."""
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
        if source not in seen and target not in seen:
            seen.update((source, target))
            out.append((source, target))
    return out


def cmd_apply(args) -> int:
    config = load_config()
    state = cfg.load_state()
    theme = cfg.theme_slug() or args.theme or state.get("theme") or "unknown"
    color, exact = args.color, args.exact
    try:
        if color and args.pin and not args.dry_run:
            parse_color(color)
            cfg.save_pin(color, exact)
        elif not color and (pin := cfg.load_pin()):
            color, exact = pin["color"], pin["exact"]
        target, accent, source = resolve_target(config, color, exact)
    except (ValueError, OSError, RuntimeError) as exc:
        cfg.log(f"apply failed: {exc}")
        return 1
    summary = (f"theme={theme} accent={hexstr(accent)} ({source}) target={hexstr(target)} "
               f"{describe(target)}")
    if args.dry_run:
        print(summary)
        return 0
    try:
        kb = open_keyboard(config["device_prefer"])
    except NotFound as exc:
        cfg.log(f"{summary} result=skipped ({exc})")
        return 0
    except Busy:
        # music mode or f75ctl holds the keyboard; they hand back with `apply` when done
        cfg.log(f"{summary} result=deferred (keyboard busy)")
        return 0
    last = state.get("target_rgb")
    last = tuple(last) if isinstance(last, list) and len(last) == 3 else None
    stored = min(max(int(state.get("brightness", config["default_brightness"])), 1), 5)
    verified = "n/a"
    try:
        with kb:
            if args.brightness is not None:
                brightness = min(max(args.brightness, 1), 5)
            elif kb.transport == "wired" and state.get("effect", "static") == "static":
                # only a static colour can be read back: an animated effect shows the keys
                # dimmed part of the time, which would read as a lower level
                brightness = live_brightness(kb, last, stored)
            else:
                brightness = stored
            effect = lighting.Effect(config["effect"], target, brightness, config["speed"],
                                     config["direction"])
            # animate only from one static colour to another: an animated effect has no
            # single colour to start from, and the dongle can't show live frames
            if (kb.transport == "wired" and last and last != target and not args.dry_run
                    and config["effect"] == "static" and state.get("effect", "static") == "static"):
                transition.run(kb, last, target, effect, config["transition"],
                               config["transition_time"])
            else:
                kb.light(effect)
            if kb.transport == "wired":
                if config["lcd_clock"]:
                    kb.set_clock(clock_payload())
                verified = "skipped"
                if args.verify and config["effect"] == "static":
                    verified = str(verify(kb, target, brightness))
    except (Rejected, OSError) as exc:
        cfg.log(f"{summary} transport={kb.transport} result=failed ({exc})")
        return 1
    cfg.save_state({
        "version": STATE_VERSION, "theme": theme, "accent": hexstr(accent),
        "accent_source": source, "target": hexstr(target), "target_rgb": list(target),
        "brightness": brightness, "effect": config["effect"], "transport": kb.transport,
        "device_path": kb.path, "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    cfg.log(f"{summary} brightness={brightness} effect={config['effect']} "
            f"transport={kb.transport} verified={verified} result=ok")
    return 0 if verified != "False" else 1


def cmd_set_effect(args) -> int:
    if args.effect == "default":
        cfg.save_effect(None)
    elif args.effect in lighting.MODES and args.effect not in cfg.NO_COLOR_EFFECTS:
        cfg.save_effect(args.effect, args.speed)
    else:
        print(f"unknown effect {args.effect!r}", file=sys.stderr)
        return 2
    args.color, args.exact, args.pin, args.dry_run, args.verify, args.theme, args.brightness = (
        None, False, False, False, False, None, None)
    return cmd_apply(args)


def cmd_palette(args) -> int:
    import tomllib
    colors = tomllib.loads((cfg.THEME_DIR / "colors.toml").read_text(encoding="utf-8"))
    config = cfg.load_config()
    target, accent, _ = resolve_target(config)
    for source, target in theme_palette(config, colors, (hexstr(accent), hexstr(target))):
        print(source, target)
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
    args.color, args.exact, args.pin, args.dry_run, args.verify, args.theme = (
        None, False, False, False, False, None)
    return cmd_apply(args)


def cmd_read(args) -> int:
    with open_keyboard(cfg.load_config()["device_prefer"]) as kb:
        entries = kb.read_table()
    print(f"device={kb.path} transport={kb.transport} slots={len(entries)}")
    for start in range(0, len(entries), 16):
        print(f"{start:3d}: " + " ".join(f"{s}:{r:02x}{g:02x}{b:02x}"
                                         for s, r, g, b in entries[start:start + 16]))
    return 0


def cmd_status(args) -> int:
    config, state = load_config(), cfg.load_state()
    try:
        target, accent, source = resolve_target(config)
    except Exception as exc:  # noqa: BLE001
        print(f"theme error: {exc}", file=sys.stderr)
        return 1
    pin = cfg.load_pin()
    print(f"theme: {cfg.theme_slug() or 'unknown'} ({cfg.THEME_DIR})")
    if pin:
        print(f"pin: {pin['color']}{' exact' if pin['exact'] else ''} (overrides the theme)")
    print(f"accent: {hexstr(accent)} ({source})")
    print(f"target: {hexstr(target)} {describe(target)}")
    print(f"effect: {config['effect']} ({config['effect_source']})")
    print(f"speed: {config['speed']}")
    print(f"transition: {config['transition']} {config['transition_time']:g}s")
    print(f"devices: {','.join(sorted(present())) or 'none'}")
    print(f"config: direction={config['direction']} prefer={config['device_prefer']} "
          f"lcd_clock={config['lcd_clock']} theme_overrides={len(config['theme_overrides'])}")
    print(f"state: brightness={state.get('brightness', '?')} transport={state.get('transport', '?')} "
          f"target={state.get('target', '?')} effect={state.get('effect', '?')}")
    if args.read_table:
        with open_keyboard(config["device_prefer"]) as kb:
            stored, share = _dominant(kb.read_table(), set(KEY_SLOTS))
        print(f"keys now: {hexstr(stored) if stored else 'off'} ({share:.0%} of lit keys)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="omarchy-keyboard-accent",
                                description="Follow the active Omarchy theme on an AULA F75 Max.")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("apply", help="apply the current theme colour")
    a.add_argument("theme", nargs="?", help="theme name for logging")
    a.add_argument("--dry-run", action="store_true", help="print the target colour only")
    a.add_argument("--color", help="use this colour instead of the theme accent")
    a.add_argument("--exact", action="store_true", help="with --color, use it as written")
    a.add_argument("--pin", action="store_true",
                   help="with --color, keep it across theme changes until `unpin`")
    a.add_argument("--brightness", type=int, help="force a brightness level 1-5")
    a.add_argument("--verify", action="store_true", help="read the keys back afterwards (wired)")
    a.set_defaults(func=cmd_apply)
    e = sub.add_parser("set-effect", help="show the accent as this effect and apply "
                       "(\"default\" returns to the config's effect)")
    e.add_argument("effect", choices=["default", *[m for m in lighting.MODES
                                                   if m not in cfg.NO_COLOR_EFFECTS]])
    e.add_argument("--speed", type=int, choices=range(6), help="effect speed 0-5")
    e.set_defaults(func=cmd_set_effect)
    t = sub.add_parser("set-transition", help="how the keys change colour over the cable")
    t.add_argument("style", choices=transition.STYLES)
    t.set_defaults(func=cmd_set_transition)
    sub.add_parser("palette", help="the theme's colours as the keys would show them").set_defaults(
        func=cmd_palette)
    sub.add_parser("unpin", help="clear the pinned colour (does not apply)").set_defaults(
        func=cmd_unpin)
    sub.add_parser("read", help="dump the live LED table (wired)").set_defaults(func=cmd_read)
    s = sub.add_parser("status", help="show theme, target and state")
    s.add_argument("--read-table", action="store_true", help="also read the keys (wired)")
    s.set_defaults(func=cmd_status)
    b = sub.add_parser("set-brightness", help="set brightness 1-5 and reapply")
    b.add_argument("brightness", type=int)
    b.set_defaults(func=cmd_set_brightness)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (NotFound, Busy, Rejected) as exc:
        print(exc, file=sys.stderr)
        return 1
