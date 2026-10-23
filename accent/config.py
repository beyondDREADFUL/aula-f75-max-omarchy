"""Paths, config file and persisted state."""
from __future__ import annotations

import json
import os
import sys
import tomllib
from datetime import datetime
from pathlib import Path

from aula_f75.lighting import MODES

HOME = Path.home()
THEME_DIR = HOME / ".local/state/omarchy/current/theme"
THEME_NAME_FILE = HOME / ".local/state/omarchy/current/theme.name"
CONFIG_FILE = HOME / ".config/omarchy/keyboard-accent/config.toml"
STATE_DIR = HOME / ".local/state/omarchy/keyboard-accent"
STATE_FILE = STATE_DIR / "state.json"
PIN_FILE = STATE_DIR / "pin.json"
LOG_FILE = STATE_DIR / "keyboard-accent.log"

DEFAULTS = {
    "color_mode": "theme",          # or "fixed"
    "fixed_color": "#F34820",
    "saturation_floor": 0.55,
    "saturation_gain": 0.5,
    "max_lightness": 0.54,
    "min_lightness": 0.46,
    "device_prefer": "auto",        # auto | wired | wireless
    "effect": "static",             # any lighting mode that takes a colour
    "default_brightness": 5,
    "speed": 3,
    "direction": 0,
    "lcd_clock": True,              # sync the LCD clock on every wired apply
    "theme_overrides": {},
}
# effects that ignore the colour and would hide the accent
NO_COLOR_EFFECTS = {"off", "custom"}


def log(message: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line)
        if LOG_FILE.stat().st_size > 256 * 1024:
            kept = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-1000:]
            LOG_FILE.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError:
        pass
    if os.environ.get("KEYBOARD_ACCENT_VERBOSE") or sys.stderr.isatty():
        print(line, end="", file=sys.stderr)


def load_config(path: Path = CONFIG_FILE) -> dict:
    """The config with defaults filled in. Errors are logged, never raised: a bad config
    must not break a theme switch. Keys from v1 that no longer apply are ignored."""
    config = dict(DEFAULTS)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as exc:  # noqa: BLE001
        log(f"config parse error: {exc}")
        return config
    color, device = data.get("color", {}), data.get("device", {})
    lighting, lcd = data.get("lighting", {}), data.get("lcd", {})
    try:
        for k in ("saturation_floor", "saturation_gain", "max_lightness", "min_lightness"):
            if k in color:
                config[k] = min(max(float(color[k]), 0.0), 1.0)
        config["min_lightness"] = min(config["min_lightness"], config["max_lightness"])
        if "mode" in color:
            config["color_mode"] = str(color["mode"])
        if "fixed_color" in color:
            config["fixed_color"] = str(color["fixed_color"])
        prefer = str(device.get("prefer", "auto")).strip().lower()
        config["device_prefer"] = prefer if prefer in ("auto", "wired", "wireless") else "auto"
        effect = str(lighting.get("effect", "static")).strip().lower()
        if effect not in MODES or effect in NO_COLOR_EFFECTS:
            log(f"invalid lighting.effect {effect!r}; using static")
            effect = "static"
        config["effect"] = effect
        if "default_brightness" in lighting:
            config["default_brightness"] = min(max(int(lighting["default_brightness"]), 1), 5)
        if "speed" in lighting:
            config["speed"] = min(max(int(lighting["speed"]), 0), 5)
        if "direction" in lighting:
            config["direction"] = 1 if int(lighting["direction"]) else 0
        if "clock" in lcd:
            config["lcd_clock"] = bool(lcd["clock"])
    except (TypeError, ValueError) as exc:
        log(f"config value error: {exc}; using defaults for the rest")
    overrides = data.get("theme_overrides", {})
    if isinstance(overrides, dict):
        config["theme_overrides"] = {str(k): str(v) for k, v in overrides.items()}
    return config


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_json(path: Path, data) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_state() -> dict:
    state = _read_json(STATE_FILE)
    return state if isinstance(state, dict) else {}


def save_state(state: dict) -> None:
    _write_json(STATE_FILE, state)


def load_pin() -> dict | None:
    """The pinned colour, if any: {"color": "#RRGGBB", "exact": bool}."""
    pin = _read_json(PIN_FILE)
    if isinstance(pin, dict) and isinstance(pin.get("color"), str):
        return {"color": pin["color"], "exact": bool(pin.get("exact"))}
    return None


def save_pin(color: str, exact: bool) -> None:
    _write_json(PIN_FILE, {"color": color, "exact": exact})


def clear_pin() -> None:
    PIN_FILE.unlink(missing_ok=True)


def theme_slug() -> str | None:
    try:
        return THEME_NAME_FILE.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def theme_accent() -> tuple[str, str]:
    """(colour string, key it came from) from the active theme's colors.toml."""
    data = tomllib.loads((THEME_DIR / "colors.toml").read_text(encoding="utf-8"))
    for key in ("accent", "blue", "magenta", "red"):
        if isinstance(data.get(key), str):
            return data[key], key
    raise RuntimeError("no usable accent colour in colors.toml")
