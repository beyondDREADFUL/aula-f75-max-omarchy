"""Colour parsing and the automatic choice of an LED colour for a theme accent.

The firmware's own calibration is a correct white balance (docs/HANDBOOK.md), so the
chosen colour is sent as is; nothing here compensates for the LEDs.
"""
from __future__ import annotations

import colorsys
import re

# Saturated accents (>= KEEP_SATURATION) are kept; muted ones keep their hue with
# saturation lifted to floor + gain * saturation, at most MAX_SATURATION. Near-grey accents
# (< NEUTRAL_BELOW) and pale, low-saturation ones such as cream become a soft white that
# keeps their hue, warm when the accent has none.
KEEP_SATURATION = 0.80
MAX_SATURATION = 0.95
NEUTRAL_BELOW = 0.12
ACHROMATIC_BELOW = 0.05
PALE_LIGHTNESS = 0.75
PALE_SATURATION = 0.50
SOFT_WHITE_LIGHTNESS = 0.88
SOFT_WHITE_SATURATION = 0.22
WARM_HUE = 40 / 360

RGB = tuple[int, int, int]


def hexstr(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def parse_color(value: str) -> RGB:
    """Parse #RGB, #RRGGBB, RRGGBB, 0xRRGGBB, or rgb()/rgba()."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("empty colour")
    text = value.strip()
    m = re.fullmatch(r"rgba?\(([^)]*)\)", text, re.IGNORECASE)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        if len(parts) < 3:
            raise ValueError(f"bad rgb() colour: {value!r}")
        try:
            rgb = [int(float(p)) for p in parts[:3]]
        except ValueError as exc:
            raise ValueError(f"bad rgb() colour: {value!r}") from exc
        return tuple(max(0, min(255, c)) for c in rgb)  # type: ignore[return-value]
    text = text.lower().removeprefix("#").removeprefix("0x")
    if len(text) == 3 and all(c in "0123456789abcdef" for c in text):
        text = "".join(c * 2 for c in text)
    if len(text) != 6 or any(c not in "0123456789abcdef" for c in text):
        raise ValueError(f"unsupported colour: {value!r}")
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def vivid(rgb: RGB, config: dict) -> RGB:
    """Turn a theme accent into a colour that reads well on the key LEDs."""
    hue, lightness, saturation = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    if saturation < NEUTRAL_BELOW or (lightness > PALE_LIGHTNESS and saturation < PALE_SATURATION):
        if saturation < ACHROMATIC_BELOW:
            hue = WARM_HUE          # no meaningful hue; colorsys would fall back to red
        lightness, saturation = SOFT_WHITE_LIGHTNESS, SOFT_WHITE_SATURATION
    else:
        if saturation < KEEP_SATURATION:
            saturation = min(MAX_SATURATION,
                             config["saturation_floor"] + config["saturation_gain"] * saturation)
        lightness = min(max(lightness, config["min_lightness"]), config["max_lightness"])
    out = colorsys.hls_to_rgb(hue, lightness, saturation)
    return tuple(max(0, min(255, round(c * 255))) for c in out)  # type: ignore[return-value]


def describe(rgb: RGB) -> str:
    """H/L/S and chroma, for logs and dry runs."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return f"H={h * 360:.1f} L={l:.3f} S={s:.3f} chroma={max(rgb) - min(rgb)}"
