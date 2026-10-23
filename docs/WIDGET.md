# Keyboard Accent

Omarchy bar widget for the AULA F75 Max accent colour, built on
`omarchy-keyboard-accent`.

- The bar dot shows the keyboard's current colour. Filled means it matches the
  theme, ringed means a custom colour is set.
- Left-click opens the picker. Right-click returns to the theme colour.
- The picker shows the keyboard and theme colours side by side, presets drawn
  in the colour the keys will really show, a hex field with a live preview, a
  Keep this colour switch, and Apply / Reset to theme. Nothing changes on the
  keyboard until you press Apply.

## Colours are applied as written

A colour picked here is sent exactly as chosen
(`omarchy-keyboard-accent apply --exact --color HEX`). Theme accents that have
no override in the config still get the controller's automatic choice, which keeps
muted accents vivid and turns grey ones into a soft white.

The keyboard's firmware applies its own white balance to every colour, so what
the keys show matches the colour picked (docs/HANDBOOK.md §5).

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
