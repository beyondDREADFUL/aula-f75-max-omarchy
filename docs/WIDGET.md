# Keyboard Accent

Omarchy bar widget for the AULA F75 Max, built on `omarchy-keyboard-accent` and
`f75ctl`, from Omarchy's own UI components.

- The bar shows a fixed keyboard icon in the bar's own colour, like the other icons. Left-click opens the panel,
  right-click returns the keyboard to the theme colour. The tooltip shows the
  colour, effect, brightness, connection and whether music is on.
- **Every choice applies at once**, except the hex field, which waits for Apply.

## The panel

| Section | What it does |
|---|---|
| Header | connection (`CABLE` or `2.4G`, with the battery level over 2.4G) |
| Keyboard / Theme | the colour the keys have and the theme's colour, side by side; `PINNED` or `CUSTOM` when they differ |
| COLOUR | the theme's colours (accent, red, yellow, green, cyan, blue, magenta, each as the keys would show it, repeats left out) and a row of bright colours; a hex field with a live preview and Apply; **Keep this colour**; Reset to theme |
| LIGHT | brightness 1-5; the effect, picked from a list that folds out inside the panel; speed 0-5 for effects other than static; the transition (none, fade, wave, burst) used for the next colour change over the cable |
| MUSIC | the music visualiser switch (needs the USB cable), with a dark or theme-colour background behind the bars |

A colour picked here is sent exactly as shown (`apply --exact`). The swatches
already show what the keys get, and the keyboard's firmware applies its own white
balance (docs/HANDBOOK.md §5).

A colour lasts until the next theme change, when the theme hook sets the theme
colour again. **Keep this colour** shows whether the colour is pinned: switching it
on pins the colour the keys have now, so it survives theme changes, login and
reconnects; a colour picked while it is on replaces the pin. Switching it off, or
Reset to theme, releases it.

The effect and speed chosen here are remembered over the config's `[lighting]`
(`omarchy-keyboard-accent set-effect NAME --speed N`). Music runs `f75ctl music` in
the background; switching the background restarts it, and switching it off returns
the keyboard to the theme colour. A theme change while music runs is applied when it
stops.

## Keybindings

```bash
omarchy-shell beyond.keyboard-accent toggle        # open or close the panel
omarchy-shell beyond.keyboard-accent brighter      # or dimmer, or brightness 3
omarchy-shell beyond.keyboard-accent music         # music on or off
omarchy-shell beyond.keyboard-accent reset         # back to the theme colour
```

## How it stays current

No polling. The widget refreshes when it loads, when the panel opens, after each
action, and a moment after the shell's theme accent changes (long enough for the
keyboard hook to finish). The battery is read only when the panel opens over 2.4G.

The widget shows what was last sent, not changes made with the keyboard's own Fn keys
(colour, effect, speed): the keyboard doesn't report them, and reading the keys back is
slow and can't name an effect (docs/HANDBOOK.md §5.3). A brightness set with Fn+Up/Down
shows after the next apply over the cable.

## Files

- `KeyboardAccent.qml`: the bar icon and the panel.
- `bin/keyboard-accent`: helper that wraps the controller and `f75ctl`. Every
  command prints one line of JSON: `status`, `palette`, `targets`, `preview`,
  `apply`, `reset`, `effect`, `brightness`, `battery`, `music start|stop`.
- `manifest.json`: plugin manifest.
