# omarchy-aula-f75-max-accent

Makes the **AULA F75 Max** keyboard's lighting follow your [Omarchy](https://omarchy.org) theme accent, over the USB cable and the 2.4 GHz dongle, with an optional bar widget to see and change the colour. Also includes `f75ctl`, a command line for everything else the vendor app does: lighting effects, per-key colours, remaps and macros, the LCD clock and images, and a music visualiser.

![Bar widget popup](docs/popup.png)

https://github.com/user-attachments/assets/88de778c-60dc-4bb4-acfe-c5b5afe39300

**This only works with the AULA F75 Max** (wired `0c45:800a`, dongle `05ac:024f`). Other keyboards use different protocols.

## What's in it

| Path | Installs to | Purpose |
|---|---|---|
| `aula_f75/` | `~/.local/share/omarchy-keyboard-accent` | Protocol library (Python standard library only), shared by everything below |
| `accent/`, `bin/omarchy-keyboard-accent` | same, and `~/.local/bin` | Reads the theme accent and sets the keyboard |
| `bin/omarchy-keyboard-accent-queue` | `~/.local/bin` | Debounced, single-flight dispatch so theme switching never blocks |
| `bin/f75ctl` | `~/.local/bin` | Command line for effects, per-key colours, keymaps, macros, LCD, music |
| `hooks/keyboard-accent.sh` | `~/.config/omarchy/hooks/{theme-set.d,post-boot.d}` | Runs the queue on theme change and at login |
| `system/65-aula-f75-max.rules` | `/etc/udev/rules.d` | Access to the keyboard's command and LCD interfaces; applies on plug/unplug |
| `system/aula-keyboard-accent.service.in` | `/etc/systemd/system` | One-shot apply started by udev |
| `config.example.toml` | `~/.config/omarchy/keyboard-accent/config.toml` | Effect, colour choice, per-theme colours. Not overwritten if it exists |
| `manifest.json`, `KeyboardAccent.qml`, `bin/keyboard-accent` | `~/.config/omarchy/plugins/beyond.keyboard-accent` | Bar widget (needs `jq`). See [docs/WIDGET.md](docs/WIDGET.md) |
| `docs/HANDBOOK.md` | | Protocol reference, design, troubleshooting |

Event-driven: no daemon and no polling. Every program takes one shared lock on the keyboard, so they never interleave packets.

## Install

```bash
git clone https://github.com/beyondDREADFUL/omarchy-aula-f75-max-accent
cd omarchy-aula-f75-max-accent
./install.sh
```

`./install.sh --dry-run` prints the root commands without running them. It asks for sudo for the udev rule, the systemd unit and the `aula` group. Log out and back in once so the group applies, then:

```bash
omarchy-keyboard-accent apply
omarchy plugin enable beyond.keyboard-accent && omarchy restart shell
```

## Upgrading from v1

Run `./install.sh` again: v2 installs its libraries to `~/.local/share/omarchy-keyboard-accent`. Your `config.toml` keeps working; `underglow_correction`, `match_direct_zone` and `wireless_color_order` are ignored now (see `config.example.toml` for the new `[lighting]` and `[lcd]` keys). Theme colours from `[theme_overrides]` are unchanged; accents without an override can look slightly different, because v1 lowered green and blue to correct an underglow that doesn't exist ([docs/HANDBOOK.md](docs/HANDBOOK.md) §14).

## Uninstall

```bash
./uninstall.sh            # removes everything but keeps your config and saved state
./uninstall.sh --purge    # also removes the config and state
./uninstall.sh --dry-run  # show what would be removed
```

The `aula` group is left in place (`sudo groupdel aula` removes it). Run `omarchy restart shell` afterwards to drop the bar widget.

## Use

```bash
omarchy-keyboard-accent status
omarchy-keyboard-accent apply --color '#FF0000'          # until the next theme change
omarchy-keyboard-accent apply --exact --color '#FFFFFF'  # use the colour as written
omarchy-keyboard-accent apply --pin --color '#FF0000'    # keep it across theme changes
omarchy-keyboard-accent unpin && omarchy-keyboard-accent apply   # back to the theme colour
```

Set `effect = "breath"` (or any of the 19 effects) under `[lighting]` in the config to show the accent as an animation instead of a static colour.

The widget: left-click opens the picker, right-click resets to the theme. "Keep this colour" pins a colour through theme changes; the effect buttons and the music switch apply at once. `omarchy-shell beyond.keyboard-accent toggle` opens it from a keybinding.

```bash
f75ctl light breath -c 00ffff                 # any effect, colour, -b brightness, -s speed
f75ctl demo                                   # step through all 19 effects
f75ctl keycolors esc=ff0000 w=00ff00 --default 202020
f75ctl remap capslock=esc f1=a,b,c f2=ctrl+c  # remaps and macros, one layer per command
f75ctl reset-keymap
f75ctl gif cat.gif                            # LCD image or animation (needs pillow)
f75ctl music --background 202020              # spectrum bars; Ctrl+C returns to the theme
f75ctl battery                                # 2.4 GHz only
```

`f75ctl --dry-run ...` prints the packets instead of sending them. `music` uses [cava](https://github.com/karlstav/cava) when installed, else needs `numpy` and `soundcard`.

## Requirements

- An AULA F75 Max and Omarchy. Tested on Omarchy 4.0.6 (Arch, Hyprland); other versions are untested.
- `python3` 3.11+ and `jq` (widget). Optional: `cava` (music), `python-pillow` (LCD images), or `numpy` + `soundcard` (music without cava).
- `install.sh` needs root once for a udev rule, a systemd one-shot unit and the `aula` group.

## What works where

| Feature | USB cable | 2.4 GHz dongle |
|---|---|---|
| Theme accent, effects, brightness kept | yes | yes (brightness from the last apply) |
| Per-key colours | yes | yes |
| Remaps and macros, base layer | yes | yes |
| Fn layer | yes | no |
| LCD clock and images | yes | no |
| Music visualiser | yes | no |
| Battery level | no | yes |

## Tests

```sh
python3 -m unittest discover tests
```

Covers the packet builders against bytes verified on the keyboard, the calibration model against read-back values, and the colour choice. `omarchy-keyboard-accent apply --verify` checks the keys on the hardware.

## License

MIT, see [LICENSE](LICENSE).
