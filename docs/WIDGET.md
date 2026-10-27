# AULA F75 Max

Omarchy bar widget for the AULA F75 Max, built on `f75ctl theme` and
`f75ctl`, from Omarchy's own UI components.

- The bar shows a fixed keyboard icon in the bar's own colour, like the other icons. Left-click opens the panel,
  right-click returns the keyboard to the theme colour, and the scroll wheel changes
  the brightness one step per notch. The tooltip shows the colour, effect, brightness,
  connection and whether music is on.
- The icon dims when no keyboard is connected. With **Hide when disconnected**
  (Setup › Plugins, `hideWhenDisconnected`) it leaves the bar instead.
- **Every choice applies at once**, except the hex field, which waits for Apply.

## The panel

| Section | What it does |
|---|---|
| Header | connection (`CABLE` or `2.4G`, with the battery level over 2.4G) |
| Keyboard / Theme | one strip when the keys show the theme colour; Keyboard and Theme side by side otherwise; `PINNED` or `CUSTOM` when they differ |
| COLOUR | the theme's colours (accent, red, yellow, green, cyan, blue, magenta, each as the keys would show it, repeats left out) and a row of bright colours that starts with a rainbow swatch (toggles the firmware's rainbow, shown as "rainbow" in the Keyboard box); a hex field with a live preview and Apply; the **Keep through theme changes** switch with a small **Reset** button |
| LIGHT | brightness 1-5 (slider); the effect, picked from a dropdown; speed 0-5 for effects other than static; the transition (none, fade, wave, burst) used for the next colour change over the cable |
| MUSIC | the music visualiser switch (needs the USB cable), with two dropdowns: the bar colour and what shows behind the bars |

A colour picked here is sent exactly as shown (`apply --exact`). The swatches
already show what the keys get, and the keyboard's firmware applies its own white
balance (docs/HANDBOOK.md §5).

A colour lasts until the next theme change, when the theme hook sets the theme
colour again. **Keep through theme changes** shows whether the colour is pinned: switching it
on pins the colour the keys have now, so it survives theme changes, login and
reconnects; a colour picked while it is on replaces the pin. Switching it off releases it.

**Reset** (and right-click on the icon) clears a pin, a hand-picked colour and the
rainbow, and returns to the theme colour. The effect stays.

The effect and speed chosen here are remembered over the config's `[lighting]`
(`f75ctl theme set-effect NAME --speed N`). The rainbow swatch toggles the
firmware's rainbow flag on the current effect (`f75ctl theme set-rainbow on|off`); it does
not change the effect. It stays through brightness, speed, theme changes and choosing
another effect. Picking a colour or Reset turns it off and keeps the effect.

Music runs `f75ctl music` in the background; changing the bar colour or the background restarts it (the bars: green-yellow-red, rainbow, reverse-rainbow, gradient, spectrum-cycle or a solid colour; behind them: Dark, theme, spectrum-cycle or a solid colour; with the music off a choice is only remembered), and switching it off returns
the keyboard to the theme colour. With the theme-colour background, a theme change
moves the background to the new colour at once; the keys take the theme colour when
music stops.

## Keybindings

```bash
omarchy-shell beyond.aula-f75 toggle        # open or close the panel
omarchy-shell beyond.aula-f75 brighter      # or dimmer, or brightness 3
omarchy-shell beyond.aula-f75 music         # music on or off
omarchy-shell beyond.aula-f75 reset         # back to the theme colour
```

## How it stays current

No polling while the panel is closed. The widget refreshes when it loads, when the
panel opens, after each action, and a moment after the shell's theme accent changes
(long enough for the keyboard hook to finish). Plugging in or pulling out the cable or
dongle makes udev run `f75ctl theme apply`, which writes the connected transports to
`~/.local/state/omarchy/aula-f75/devices`; the widget watches that file. The battery is
read only when the panel opens over 2.4G.

The widget shows what was last sent, not changes made with the keyboard's own Fn keys
(colour, effect, speed): the keyboard doesn't report them, and reading the keys back is
slow and can't name an effect (docs/HANDBOOK.md §5.3). A brightness set with Fn+Up/Down
shows after the next apply over the cable.

## Files

- `AulaF75.qml`: the bar icon and the panel.
- `bin/aula-f75`: helper that wraps the controller and `f75ctl`. Every
  command prints one line of JSON: `status`, `palette`, `preview`, `apply`, `reset`,
  `rainbow`, `effect`, `transition`, `brightness`, `choices`, `battery`, `music start|stop`.
  It reads the controller through `f75ctl theme status --json`. The widget reads its
  effect, bar and background lists from `choices`, so they are defined in one place.
- When the keyboard is not connected or busy (for example while music runs), the helper
  says so (`keyboard not connected` or `keyboard busy`) and the widget shows that message
  instead of reporting success.
- `manifest.json`: plugin manifest.
