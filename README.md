# omarchy-aula-f75-max-accent

Makes the **AULA F75 Max** keyboard's lighting follow your [Omarchy](https://omarchy.org) theme accent, on the wired USB connection and on the 2.4 GHz dongle. Includes an optional bar widget to see and change the colour.

![Bar widget popup](docs/popup.png)

https://github.com/user-attachments/assets/88de778c-60dc-4bb4-acfe-c5b5afe39300

**This only works with the AULA F75 Max.** It talks to the keyboard's own HID protocol (wired `0c45:800a`, dongle `05ac:024f`). Other keyboards use different protocols, so they would need a different controller. The bar widget is a thin front end over the controller's CLI.

## What's in it

| Path | Installs to | Purpose |
|---|---|---|
| `bin/omarchy-keyboard-accent` | `~/.local/bin` | Controller (Python 3, no dependencies). Reads the theme accent and writes it to the keyboard. |
| `bin/omarchy-keyboard-accent-queue` | `~/.local/bin` | Debounced, single-flight dispatch so theme switching never blocks. |
| `hooks/keyboard-accent.sh` | `~/.config/omarchy/hooks/{theme-set.d,post-boot.d}` | Runs the queue on theme change and at login. |
| `system/65-aula-f75-max.rules` | `/etc/udev/rules.d` | Grants access to the keyboard's HID node and triggers an apply on plug/unplug. |
| `system/aula-keyboard-accent.service.in` | `/etc/systemd/system` | One-shot apply service started by udev. |
| `config.example.toml` | `~/.config/omarchy/keyboard-accent/config.toml` | Saturation and lightness limits, per-theme overrides. Not overwritten if it exists. |
| `manifest.json`, `KeyboardAccent.qml`, `bin/keyboard-accent` | `~/.config/omarchy/plugins/beyond.keyboard-accent` | Bar widget (needs `jq` and the controller above). See [docs/WIDGET.md](docs/WIDGET.md). |
| `docs/HANDBOOK.md` | | Protocol notes, design, troubleshooting. |
| `install.sh`, `uninstall.sh` | | Install and remove everything above. Both take `--dry-run`. |
| `CHANGELOG.md` | | What changed and when. |

Event-driven, no daemon and no polling.

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

The bar widget can also be added on its own with `omarchy plugin add https://github.com/beyondDREADFUL/omarchy-aula-f75-max-accent --enable`, but it only drives the controller: run `./install.sh` from the cloned folder (`~/.config/omarchy/plugins/beyond.keyboard-accent`) first, or it will show nothing.

## Uninstall

```bash
./uninstall.sh            # removes everything but keeps your config and saved state
./uninstall.sh --purge    # also removes the config and state
./uninstall.sh --dry-run  # show what would be removed
```

It removes the scripts, hooks, plugin, udev rule and systemd unit. The `aula` group is left in place (`sudo groupdel aula` removes it). Run `omarchy restart shell` afterwards to drop the bar widget.

## Use

```bash
omarchy-keyboard-accent status
omarchy-keyboard-accent apply --color '#FF0000'          # until next theme change
omarchy-keyboard-accent apply --exact --color '#FFFFFF'  # use the colour as written
omarchy-keyboard-accent apply --pin --color '#FF0000'    # keep it across theme changes
omarchy-keyboard-accent unpin && omarchy-keyboard-accent apply   # back to the theme colour
```

The widget: left-click opens the picker, right-click resets to the theme. Switch on "Keep this colour" to pin a colour through theme changes. `omarchy-shell beyond.keyboard-accent toggle` opens it from a keybinding.

## Requirements

- An AULA F75 Max (wired USB or the 2.4 GHz dongle) and Omarchy.
- `python3` (controller), `jq` (widget helper), `sudo` once for `install.sh`.
- `install.sh` needs root for three things: a udev rule, a systemd one-shot unit, and adding you to a system group `aula` so the keyboard's HID node is writable without root. `./install.sh --dry-run` prints them; `./uninstall.sh` removes them (the group stays).
- It never overwrites an existing `~/.config/omarchy/keyboard-accent/config.toml`.

## License

MIT, see [LICENSE](LICENSE).

## Tests

```sh
python3 -m unittest discover tests
```

Covers colour parsing and the automatic colour choice. Hardware behaviour is checked with `apply --verify`.

## Limits

- The underglow is calibrated by the firmware, so exact colours (white in particular) can't be reproduced there.
- The dongle has no readback and supports a single static colour.
- Tested on one machine (Arch, Omarchy, Hyprland). Treat it as a starting point.
