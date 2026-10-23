# Changelog

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
