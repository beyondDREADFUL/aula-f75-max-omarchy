# Changelog

## 2026-10-26 (settings, resets, Right Alt)
- Right Alt is the key right of Space. It was mapped as Right Ctrl (`rctrl`, usage 0xE4),
  and the Fn and Right Alt grid columns were swapped. A dongle `reset-keymap` turned the
  key into Right Ctrl. The key is now `ralt` (usage 0xE6) at grid position (5, 9), Fn at
  (5, 10). There is no Right Ctrl key.
- New `f75ctl settings --sleep never|1|5|30 --debounce 1-5`: the sleep timer and key
  debounce. The keyboard can't report them, so both are written each time, and the sleep
  timer applies on 2.4G.
- New `f75ctl reset-keyboard --yes` (clears the remaps, keeps the lighting) and
  `f75ctl factory-reset --yes` (also clears the lighting and settings). Both need the 2.4G
  dongle and refuse to run without `--yes`.
- Where these come from: reverse engineering the vendor program, checked on the keyboard
  (firmware 106). The settings and reset commands were verified over the 2.4G dongle; the
  settings write also over the cable.

## 2026-10-25 (fixes from a code review)
- A keyboard that can't be opened (for example no access before the `aula` group applies)
  no longer ends `f75ctl` or `f75ctl theme` with a traceback: apply logs
  `result=failed (...)` in `theme.log` and exits 1, the other commands print the error.
- Unknown key names print without extra quotes: `f75ctl: unknown key 'foo'`.
- The verbose-log variable is now `AULA_F75_VERBOSE` (was `KEYBOARD_ACCENT_VERBOSE`).
- The widget reads the battery after the status it opens with, so the first open after
  switching from the cable to the dongle shows the battery level.

## 2026-10-24 (rename)
- The project is now **aula-f75-max-omarchy** (repository renamed). Everything follows the
  name `aula-f75`: `omarchy-keyboard-accent ...` is `f75ctl theme ...`, the hook queue is
  `f75ctl-theme-queue`, the widget is `beyond.aula-f75` ("AULA F75 Max", `AulaF75.qml`,
  helper `bin/aula-f75`), the libraries live in `~/.local/share/aula-f75`, config and
  state in `~/.config/omarchy/aula-f75` and `~/.local/state/omarchy/aula-f75`, the service
  is `aula-f75.service`, and the Python package is `theme/`.
- `install.sh` moves an existing install: config and state (theme colours, pin, effect),
  the widget's place in the bar, and removes the old commands, hooks, plugin and service.

## 2026-10-24 (v2, music follows the theme)
- With the widget's theme-colour background, a theme change while music runs moves the
  background to the new theme colour within a frame, instead of waiting for music to stop.
  `apply` sends the visualiser SIGHUP and returns at once (no 15 s wait for the lock); the
  visualiser reloads the colour between frames. New `f75ctl music --background theme`.
- The theme-colour background is no longer dimmed to 30 %; it shows at full brightness.

## 2026-10-24 (v2, Fn-key changes investigated)
- Documented what the keyboard reveals about changes made with its own Fn keys
  (docs/HANDBOOK.md §5.3): no report on any cable or dongle interface; over the cable the
  LED table shows the current colour and level of a static colour and whether an effect
  is animated, but not which effect or its speed. A widget that followed these changes was
  tried and left out (about 0.9 s per read, and animated effects can't be named). The
  Fn+Tab colours are listed there.

## 2026-10-24 (v2, transitions)
- Colour changes over the cable animate: a wave from left to right by default, or a fade or
  a burst from the middle (`[lighting] transition`, `transition_time`, or the widget). The
  new effect is set at live-frame pacing between the first frame and the animation, so
  neither end flashes; the keys still go dark for a moment as the animation starts.

## 2026-10-24 (v2, dependencies)
- Music needs cava now; the built-in numpy/soundcard analyser and `f75ctl music --source`
  are removed (`soundcard` isn't packaged for Arch, and cava is cheaper and smoother).
  Without cava, music stops with "music needs cava: sudo pacman -S cava".
- `install.sh` stops if Python is older than 3.11 and ends with the optional dependencies
  that are missing (cava, pillow); it installs none of them.

## 2026-10-23 (v2, widget redesign)
- The widget is rebuilt from Omarchy's own components and is shorter. Every choice applies
  at once (only the hex field waits for Apply). New: colours from the active theme next to
  the bright presets, brightness 1-5, effect speed, the connection and the 2.4G battery
  level in the header. Effects fold out inside the panel instead of a popup that the
  panel's edge cut off. Music is disabled with a note when only the dongle is connected.
- The bar shows a fixed keyboard icon in the bar's colour instead of a coloured dot; the tooltip carries
  the state.
- Keep this colour now pins the current colour when switched on and shows the pin state;
  before, any refresh (a brightness or effect change) switched it back off before a colour
  was picked. The music background shows the running one after a shell restart.
- Switching between animated effects no longer lowers the brightness: it is read back from
  the keys only when they showed a static colour (a breathing key read as a dimmer level).
- New keybinding targets: `brighter`, `dimmer`, `brightness N`.
- New controller commands: `palette`, `set-effect NAME --speed N`; `status` reports the
  speed and the connected transports.

## 2026-10-23 (v2, widget)
- The widget can switch the effect the accent is shown as, and start and stop the music
  visualiser (dark or the theme colour behind the bars). New `omarchy-keyboard-accent
  set-effect`.
- `f75ctl music --background` also takes a hex colour.
- Removed the ambilight background (the screen's colour behind the bars). It was unclear
  what it followed, an ordinary desktop turned it white, and it cost 44-74 % of a CPU core
  against about 4 % for music without it; the theme background covers what it was for.
- Stopping music no longer leaves the keyboard rejecting the theme apply: Ctrl+C and
  SIGTERM now stop between frames.
- Changing the music background in the widget while music runs restarts it with the new
  background (SIGUSR1 stops `f75ctl music` without handing back to the theme).
- `f75ctl music` over the dongle fails at once with "music needs the USB cable".

## 2026-10-23 (v2)
- Rebuilt on `aula_f75`, a protocol library with every command checked on the keyboard
  (cable and dongle). The controller, `f75ctl` and the music visualiser share it and one
  lock, so they never interleave packets; a theme change during `f75ctl music` is applied
  when the music stops.
- Corrected the model of the keyboard (docs/HANDBOOK.md §14): the keys are in the slots
  effects write, the 61 "direct" slots are empty, there is no separate underglow, and the
  firmware's red gain is a correct white balance. Removed the direct-frame write, the zone
  bootstrap, the table cache, `match_direct_zone` and `underglow_correction`. A wired apply
  is now one effect command (about 0.57 s including the LCD clock).
- New config: `[lighting] effect`, `speed`, `direction` (show the accent as any of the 19
  effects) and `[lcd] clock` (sync the LCD clock on every wired apply). v1 keys that no
  longer apply are ignored.
- New `f75ctl`: effects, per-key colours (also over the dongle), remaps and macros with
  key combos in one layer, LCD clock and images, music visualiser (cava or built-in,
  colour backgrounds), battery.
- udev rule: also grants the LCD image interface; the dongle rule matches its command
  interface only.
- Handbook rewritten from verified facts, each marked seen/read/sent/assumed.

## 2026-10-22 (plugin layout)
- The widget now sits at the repository root (`manifest.json`, `KeyboardAccent.qml`, `bin/keyboard-accent`) so `omarchy plugin add <repo url>` works and the repo can be listed on the Omarchy plugin marketplace. Added `license` to the manifest and a `preview.png`. `plugin/README.md` moved to `docs/WIDGET.md`. The widget now says "Controller missing: run install.sh (see README)" when `omarchy-keyboard-accent` is not installed.

## 2026-10-22 (tests)
- Added unit tests for colour parsing and the automatic colour choice (`python3 -m unittest discover tests`).

## 2026-10-22 (latest)
- The automatic colour choice now reproduces the hand-picked set for 29 of 34 themes: grey/pale accents become a soft white, muted accents get a saturation lift, and green/blue are rebalanced for the underglow. `[color]` gains `saturation_floor`, `saturation_gain`, `underglow_correction` (`min_saturation` removed; `min_lightness` is now 0.46). The example config ships overrides for the bundled Omarchy themes (plus Fireside) so the colours stay fixed; only Kanagawa and Fireside depend on the wallpaper.

## 2026-10-22 (later)
- Theme overrides reworked. They follow each theme's own accent so the keyboard matches the desktop, with warm and purple values corrected for the underglow's weak red so they no longer drift to green or blue. Exceptions where the accent cannot show on LEDs: Kanagawa (indigo from the wallpaper), Fireside (campfire orange) and the grey themes (soft whites).
- Investigated animated theme changes (cross-fade, per-key wave, firmware modes); not adopted. Findings are in the handbook (section 19).
- Pinned colours: `apply --pin --color HEX` keeps a colour across theme changes,
  login and reconnects until `unpin`. The widget has a Keep this colour switch.
- Fixed a brief flash of an old colour on the effect LEDs at every wired apply:
  the frame now carries the predicted effect colour instead of stale cached bytes.
- Widget popup no longer overflows when the hint text is showing.
- The popup now applies colours exactly as chosen (always `--exact`); the Exact colour switch and the adjustment hint are gone. Theme accents without an override are still adjusted.
- Popup choices (presets, THEME swatch) now only take effect when Apply is pressed. The hint and message lines have a fixed height, so the popup no longer resizes or flashes a stale preview.
- Clicking a preset now fills the hex field, so pressing Apply again repeats the colour you see instead of the stale field text.

## 2026-10-21
- Wired controller, hooks, queue, locking, brightness preservation,
  verification, logging, state.
- Dongle support added: USB/descriptor detection, 32-byte output protocol,
  static-only colour, persisted brightness.
- udev rules and one-shot service installed with a dedicated `aula` group.
- First real wireless apply; colour came out blue, fixed by switching
  `wireless_color_order` from `bgr` to `rgb` (verified on hardware).

## 2026-10-22
- Added `apply --exact` (colour as written, no transform) after white showed as
  light gold through the saturation floor.
- Bar widget added and the project published as a repository with an
  installer.
- Protocol errors retried (3 attempts, 0.5 s apart). Added after a theme
  change was dropped on a missed ack (`no ack for 4/24`, 11:26).
- Wired `apply` optimised from 3.56 s to 0.68 s:
  - verify made opt-in (`--verify`);
  - direct frame written before `set_static`, using a cached full frame;
  - page-0 read replaces the full 9-page read for brightness inference;
  - pacing constants reduced (10/20/25 ms) and validated.
- All 34 installed themes pinned in `[theme_overrides]`, with six hand-tuned
  (`white`, `vantablack`, `fireside`, `solitude`, `gruvbox`, `rose-pine`) and
  the earlier `nord` / `catppuccin-latte` brand colours kept.
- Verified: brightness inference on the fast path, cache fallback, 20/20
  verified applies, visual theme switch to `kanagawa` and `white`.
