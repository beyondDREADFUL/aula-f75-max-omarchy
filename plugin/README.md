# Keyboard Accent

Omarchy bar widget for the AULA F75 Max accent colour, built on
`omarchy-keyboard-accent`.

- The bar dot shows the keyboard's current colour. Filled means it matches the
  theme, ringed means a custom colour is set.
- Left-click opens the picker. Right-click returns to the theme colour.
- The picker shows the keyboard and theme colours side by side, presets drawn
  in the colour the keys will really show, a hex field with a live preview, and
  an Exact colour switch.

## Exact colour

By default a picked colour goes through the controller's saturation and
lightness limits, the same ones theme accents get. That keeps accents vivid but
tints neutrals: white becomes gold. Turn on Exact colour to send the colour as
written (`omarchy-keyboard-accent apply --exact --color HEX`).

The underglow is calibrated by the keyboard firmware separately and cannot be
set exactly. Pure white keys come with a cyan-tinted underglow.

A custom colour lasts until the next theme change, when the theme hook sets the
keyboard back to the theme colour. Turn on **Keep this colour** to pin it
instead: it then survives theme changes, login and reconnects until you press
Reset to theme (or right-click the dot). Open the picker from a keybinding with
`omarchy-shell beyond.keyboard-accent toggle`.

## How it stays current

No polling. The widget refreshes when it loads, when the picker opens, after
each action, and a moment after the shell's theme accent changes (long enough
for the keyboard hook to finish).

## Files

- `KeyboardAccent.qml` — the bar widget and picker.
- `bin/keyboard-accent` — helper that wraps the controller. Every command
  prints one line of JSON: `status`, `targets`, `preview`, `apply`, `reset`.
- `manifest.json` — plugin manifest.
