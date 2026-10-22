# AULA F75 Max — Omarchy Theme Sync Handbook

How the AULA F75 Max keyboard follows the Omarchy theme accent: architecture,
protocols, colour pipeline, installation, the bar widget, and troubleshooting.

- Platform: Arch-based Omarchy, Hyprland
- Keyboard: AULA F75 Max, two transports: wired USB and a 2.4 GHz dongle
- Controller: `~/.local/bin/omarchy-keyboard-accent`
- Bar widget: `~/.config/omarchy/plugins/beyond.keyboard-accent`
- Source: <https://github.com/beyondDREADFUL/omarchy-aula-f75-max-accent>
- Last verified: 2026-10-22, wired and wireless, on hardware

Measurements and file listings below come from the reference unit this was
developed on. Other F75 Max units and firmware revisions may differ in
calibration (§6.3) and device paths.

---

## 1. Status at a glance (reference unit)

| Item | Value |
|---|---|
| Active theme | `last-horizon` |
| Theme accent | `#B59790` → overridden to `#F34820` |
| Keys (direct zone) | `#F34820` |
| Underglow (effect zone) | `#A0471F` (firmware-calibrated) |
| Brightness | Level 5, preserved across applies |
| Transport | Wired `0C45:800A`, interface 03 |
| Wired `apply` time | **0.68 s** (1.00 s with `--verify`) |
| Wireless `apply` time | **0.19 s** (measured, no verify) |
| Overrides | 34 — one per installed theme |
| Daemons | None. Event-driven hooks and one-shot udev service only |

---

## 2. Architecture

Two independent USB devices with two unrelated protocols. The controller
detects whichever is present and uses the matching writer.

```
theme change ──> ~/.config/omarchy/hooks/theme-set.d/keyboard-accent.sh
login        ──> ~/.config/omarchy/hooks/post-boot.d/keyboard-accent.sh
                        │
                        ▼
        ~/.local/bin/omarchy-keyboard-accent-queue
        (writes request token, detaches one worker, 0.35 s debounce)
                        │
                        ▼
        ~/.local/bin/omarchy-keyboard-accent apply
                        │
        ┌───────────────┴───────────────┐
        ▼                               ▼
   wired 0C45:800A                 dongle 05AC:024F
   64-byte feature reports         32-byte OUTPUT reports
   per-key frame + static          static effect only
   reads table, infers brightness  stored brightness, no readback
```

The bar widget (§18) is a separate front end. It reads the theme and keyboard
state through a small helper and applies colours by calling the controller's
CLI; it never talks to the hardware itself.

Hotplug path: udev `add/change` and `remove` events set
`SYSTEMD_WANTS=aula-keyboard-accent.service`, which runs one `apply` as the
desktop user. No polling, nothing resident.

---

## 3. Hardware and transports

### 3.1 Wired keyboard

| Property | Value |
|---|---|
| USB ID | `0c45:800a` (SONiX / Microdia) |
| Interface | 03 (MI_03) |
| Usage page | `0xFF13` |
| Device node | `/dev/input/by-id/usb-SONiX_AULA_F75Max-if03-hidraw` |
| Report type | 64-byte **feature** reports |
| LED entries | 144 (9 pages × 64 bytes = 576 bytes) |
| Zone split | 83 effect/underglow + 61 direct/keys |

Only interface 03 is opened. The keyboard and consumer-control interfaces are
never touched.

### 3.2 2.4 GHz dongle

| Property | Value |
|---|---|
| USB ID | `05ac:024f` (masquerades as an Apple aluminium keyboard) |
| Command node | the hidraw node whose report descriptor has usage page `0xFF60` with a 32-byte output report |
| Report type | 32-byte **OUTPUT** report, report ID 0 |
| Linux write framing | 33 bytes: leading `0x00` report ID then the 32-byte packet |
| LED control | firmware static effect only, no per-key frame, no readback |
| This unit's node | `/dev/hidraw9` (can change across boots) |

On this machine the dongle exposes several hidraw nodes (keyboard, mouse,
consumer). Only the `0xFF60` node is a command channel; the rest are normal
input endpoints and are ignored. Detection reads the report descriptor, not
just the USB ID.

### 3.3 Do not confuse with `258A:010C`

That is a different 2.4 GHz keyboard family with a different packet layout.
Sending the `05AC:024F` protocol to it would produce garbage. Detection is by
USB ID plus descriptor, so it is never selected.

---

## 4. Files

| Path | Role |
|---|---|
| `~/.local/bin/omarchy-keyboard-accent` | Controller: detection, colour pipeline, both protocols, verification |
| `~/.local/bin/omarchy-keyboard-accent-queue` | Single-flight debounced dispatcher used by hooks |
| `~/.config/omarchy/keyboard-accent/config.toml` | Configuration, including 34 theme overrides |
| `~/.config/omarchy/hooks/theme-set.d/keyboard-accent.sh` | Theme-change hook |
| `~/.config/omarchy/hooks/post-boot.d/keyboard-accent.sh` | Login hook |
| `~/.local/state/omarchy/keyboard-accent/state.json` | Brightness, transport, target, zone maps, cached frame |
| `~/.local/state/omarchy/keyboard-accent/keyboard-accent.log` | Apply history, one line per attempt |
| `~/.local/state/omarchy/keyboard-accent/{lock,worker.lock,request,applied}` | Locking and queue tokens |
| `/etc/udev/rules.d/65-aula-f75-max.rules` | Access rules and hotplug triggers |
| `/etc/systemd/system/aula-keyboard-accent.service` | One-shot apply service |
| `~/.config/omarchy/plugins/beyond.keyboard-accent/` | Bar widget: `KeyboardAccent.qml`, `bin/keyboard-accent` helper, `manifest.json` |

The repository's `install.sh` installs all of the above (§13.3). No daemon, no
vendor software running.

---

## 5. Execution flow

### 5.1 Hook and queue

`omarchy-theme-set` runs the theme-set hook synchronously. The hook calls
`omarchy-keyboard-accent-queue`, which:

1. writes a nanosecond token to `request`,
2. tries `flock -n` on `worker.lock`,
3. if it wins, detaches a worker that sleeps **0.35 s** (debounce), then runs
   `apply` for the *current* theme,
4. if it loses, returns immediately — the running worker will pick up the
   newest token.

Rapid theme previewing therefore cannot queue a backlog of stale HID writes.
The hook itself returns in milliseconds.

### 5.2 Wired apply — fast path

Used when zone maps are known, the cached frame is valid, and
`match_direct_zone = false` (the default).

1. Acquire `lock` (15 s timeout, `flock`).
2. Resolve theme accent → override → target colour; read stored brightness.
3. **Read page 0 only** (`04 18`, `04 F5` with count 1, `04 02`): carries
   effect entries 1–13, enough to infer the live brightness level. ~0.12 s.
4. Build the frame from `table_cache` (the last full frame this script
   wrote), replace the 61 direct entries with `scale_rgb(target, brightness)`.
5. Write all 9 pages with `04 20` and commit (`04 02`). **Keys change here**,
   ~0.4 s in.
6. Run `set_static` (`04 13` + data packet + `04 F0`): sets mode, colour and
   brightness for the effect group, and rewrites its calibrated bytes.
   **Underglow changes here**, ~0.65 s in.
7. Save state, including the frame that was just written.
8. Optionally verify (`--verify`), which reads all 9 pages and compares.

Why this order is safe: a probe wrote pure green to every direct entry, then
ran `set_static`; the green survived and only the effect entries changed.
`set_static` owns the effect zone,
the direct frame owns the key zone, and the two do not overwrite each other.

Why cached effect bytes are harmless: every one of the 144 entries is covered
by one of the two index maps, the direct entries are rewritten from the
current target, and the effect entries are rewritten by `set_static`. A stale
cached effect byte cannot survive a successful apply.

### 5.3 Wired apply — fallback path

Used on first run, lost state, invalid cache, `match_direct_zone = true`, or a
failed page-0 read. This is the original conservative order:

1. Full 9-page table read (also used to bootstrap the zone split if unknown).
2. Infer brightness from the effect group.
3. `set_static` (effect group).
4. Full table read to capture the calibrated effect bytes.
5. `write_direct` with direct entries replaced, effect entries preserved.

~2.8 s without verify, ~3.6 s with it.

### 5.4 Wireless apply

1. Acquire lock, resolve target, read stored brightness (no readback exists).
2. `os.write(fd, b"\x00" + packet)` — 33 bytes including report ID 0.
3. Commit packet (`[0]=0x0F`), wait ~50 ms.
4. Static packet (`05 10 00 01 …`), colour bytes according to
   `wireless_color_order`, checksum in `[31]`.
5. Save state with `transport=wireless`, `mode=wireless-static`.

### 5.5 Locking and failure isolation

- One `flock` around the whole apply; a second invocation exits quietly.
- A protocol error (missed ack) is retried up to 3 times, 0.5 s apart, each
  attempt reopening the device and re-taking the lock. Other exceptions are
  logged and the process exits 1; hooks use `|| true`, so a keyboard problem
  can never break theme switching.
- State is written atomically (`state.json.tmp` → `os.replace`, mode 0600).

---

## 6. Colour pipeline

### 6.1 Resolution order

1. `apply --color HEX` — explicit one-off colour; goes through the transform
   unless `--exact` is given, which uses the colour as written
   (`accent_source` becomes `override-exact`). The widget's "Exact colour"
   switch maps to this.
2. `[color] mode = "fixed"` — `fixed_color` replaces the theme accent, and is
   then put through the **same transform** as step 1. `min_saturation` and
   `max_lightness` therefore still apply in this mode.
3. Otherwise the active theme's `accent` from
   `~/.local/state/omarchy/current/theme/colors.toml`, also transformed.
4. Exception: if the theme slug has a `[theme_overrides]` entry, that hex is
   used **verbatim** and the transform is skipped (`accent_source` becomes
   `theme_override:<slug>`). This is the only path that bypasses
   `min_saturation`/`max_lightness`.

### 6.2 HSL transform (`vivid`)

- Hue preserved; near-grey accents (saturation < 0.05) get hue `0.03`
  (warm coral) because colorsys would otherwise fall back to pure red.
- Saturation raised to `min_saturation` (0.90).
- Lightness clamped to `[0.35, 0.54]` — the diffuser reads lighter than the
  monitor swatch.
- The result is the *target*; keys use it directly (scaled by brightness),
  the underglow gets firmware calibration on top.

### 6.3 Firmware calibration (underglow only)

Measured on this unit:

```
CHANNEL_GAIN      = (0.6575, 0.9911, 0.9885)      # R, G, B
BRIGHTNESS_SCALE  = (0.1805, 0.3750, 0.6598, 0.7848, 1.0000)  # levels 1–5
```

The live effect group at level 5 reports `#F34820` as **`#A0471F`**. These
gains are a fitted approximation of the firmware's arithmetic, not an exact
reproduction of it: applying them with `round()` predicts `#A04720` (blue is
32 × 0.9885 = 31.632, which rounds to 32), while the keyboard reports 31.
Measured across five colours the model stays within **±1 per channel**:

| Target | Live effect | Model | Delta |
|---|---|---|---|
| `#F34820` | `#A0471F` | `#A04720` | `[0, 0, -1]` |
| `#E6E1D8` | `#98DFD6` | `#97DFD6` | `[1, 0, 0]` |
| `#2064F3` | `#1463F1` | `#1563F0` | `[-1, 0, 1]` |
| `#1CF84B` | `#12F64A` | `#12F64A` | `[0, 0, 0]` |
| `#F3D420` | `#A0D21F` | `#A0D220` | `[0, 0, -1]` |

So the firmware's own quantization can differ from `round()` by a couple of
LSB, and its exact rule is not modelled. This is why verification compares the
dominant effect colour with a tolerance of 18 (summed channel deltas) rather
than expecting an exact match; a 1-LSB difference is invisible.

Red is attenuated by roughly a third, which means near-neutral or warm colours
shift toward green/cyan in the underglow, while keys stay exactly as written.
At normal viewing this is not noticeable (verified with the `white` override:
keys `#E6E1D8`, underglow `#98DFD6`). With `--exact` and pure white the keys
show `#FFFFFF` and the underglow `#A8FDFD`, a visibly cool tint that cannot be
corrected from software.

### 6.4 Per-theme overrides

All 34 installed themes are pinned, so retuning `min_saturation` /
`max_lightness` later cannot change an existing theme's colour. To fall back
to the automatic transform for a theme, delete its line.

**Bundled themes** (`/usr/share/omarchy/themes`):

| Theme | Colour | Note |
|---|---|---|
| `catppuccin` | `#1E70F5` | |
| `catppuccin-latte` | `#8839EF` | brand mauve, kept from earlier config |
| `ethereal` | `#202CF3` | |
| `everforest` | `#20F3D7` | |
| `flexoki-light` | `#0A5CBC` | |
| `gruvbox` | `#E8891A` | hand-tuned: amber identity, not the mint transform |
| `hackerman` | `#1CF84B` | |
| `kanagawa` | `#F3D420` | confirmed on hardware |
| `last-horizon` | `#F34820` | confirmed on hardware |
| `lumon` | `#20A8F3` | |
| `lupine` | `#2059F3` | |
| `matte-black` | `#E78E0C` | |
| `miasma` | `#A1C30A` | |
| `nord` | `#88C0D0` | brand frost colour, kept from earlier config |
| `osaka-jade` | `#0BD97B` | |
| `retro-82` | `#F77E1C` | |
| `ristretto` | `#F34F20` | |
| `rose-pine` | `#E58FA8` | hand-tuned: rose identity, not electric cyan |
| `solitude` | `#6E93C4` | hand-tuned: muted blue, not electric cyan |
| `tokyo-night` | `#2064F3` | |
| `vantablack` | `#8FA6B8` | hand-tuned: cool steel for a neutral theme |
| `white` | `#E6E1D8` | hand-tuned: warm white, confirming underglow is acceptable |

**User themes** (`~/.config/omarchy/themes`):

| Theme | Colour | Note |
|---|---|---|
| `a-building-with-a-flag-on-the-roof-palette` | `#2081F3` | |
| `aether` | `#F34B20` | |
| `batman` | `#1754F3` | |
| `catppuccin-dark` | `#1E70F5` | |
| `felix` | `#FF5E14` | |
| `fireside` | `#F09A28` | hand-tuned: fire amber |
| `ign-batman-aether` | `#205FF3` | |
| `lavender` | `#8120F3` | |
| `nebula` | `#6E1BF3` | |
| `red-samurai-palette` | `#F71D28` | |
| `tokyoled` | `#2064F3` | |
| `tsukiyo` | `#20C0F3` | |

Notes:

- Overrides bypass the transform entirely, so they are not affected by
  `min_saturation` / `max_lightness`.
- Keys use the override scaled by brightness; the underglow still receives
  firmware calibration.
- `white` and `vantablack` are the only near-neutral entries. The firmware's
  red attenuation gives them a cooler underglow than their keys; `white`
  was checked on hardware and accepted, `vantablack` follows the same
  reasoning.
- Two pairs intentionally share a colour because they share an accent:
  `catppuccin`/`catppuccin-dark`, `tokyo-night`/`tokyoled`.

---

## 7. Wired protocol reference

All packets are 64-byte feature reports (report ID 0 prepended by the ioctl).
Commands are `04 <sub>`, and most are followed by an ack poll.

### 7.1 ACK convention

After a command, `GET_FEATURE` echoes the command in bytes `[1]` and `[2]` and
sets byte `[4] = 0x01` when ready. The controller polls up to 10 times at
`ACK_POLL` (20 ms inside the current pacing) and raises `ProtocolError` if no
matching ack arrives.

### 7.2 Commands in use

| Step | Packet | Purpose |
|---|---|---|
| Table access | `04 18` | enter table mode |
| Read pages | `04 F5 00 00 00 00 00 00 PP` | `PP` = number of pages to serve |
| Page fetch | `GET_FEATURE` | returns one 64-byte page; pages are sequential |
| Leave table | `04 02` | end table mode |
| Static effect | `04 13 00 … 01` | set effect parameters |
| Static data | `[0]=01 [1..3]=RGB [8]=00 [9]=brightness [10]=speed [11]=direction [14]=AA [15]=55` | colour/mode payload |
| Static commit | `04 F0` | apply the effect group |
| Direct begin | `04 20 … PP` | start a 9-page direct frame |
| Direct data | 9 × 64-byte pages | raw table, 4 bytes per LED |
| Refresh | 64 zero bytes | as SignalRGB does |
| Direct commit | `04 02` | end/finish the frame |

### 7.3 Timing constants

```
FEATURE_SETTLE = 0.010   # before every feature report
ACK_POLL       = 0.020   # between readiness polls
PAGE_SETTLE    = 0.025   # between table pages
```

These are settling gaps, not transfer time: each control transfer already
returns synchronously. The original values were 35/50/50 ms. They were
reduced after 20 consecutive `apply --verify` runs and 12 plain applies
produced no failures. If a future firmware drops frames, restore the older
values and re-validate with `--verify`.

### 7.4 Zone topology and page 0

The 144 entries are partitioned: 83 effect/underglow, 61 direct/keys. The
split was derived by applying the same colour at brightness 1 and 5 — effect
entries change, direct entries do not.

Page 0 (entries 0–15) contains direct entries 0/14/15 and effect entries
1–13. That is enough for brightness inference, which is why the fast path
does not need the full table.

Single-page reads were verified byte-identical to the first page of a full
read, twice in a row.

### 7.5 Verification

`apply --verify` reads the whole table afterwards and checks:

- dominant effect colour within **18** (sum of channel deltas) of
  `expected_effect(target, brightness)`;
- dominant direct colour within **6** of `scale_rgb(target, brightness)`.

A pass is logged as `verified=True`; a skipped check logs `verified=skipped`;
wireless logs `verified=n/a` because there is no readback.

---

## 8. Wireless protocol reference

### 8.1 Framing

`os.write(fd, b"\x00" + packet32)` — 33 bytes on Linux, report ID 0 followed
by the 32-byte output report. Writing 32 bytes alone was rejected by the
kernel; this was validated with a virtual UHID device before touching real
hardware.

### 8.2 Packets

Commit, then the static packet ~50 ms later (the firmware needs the gap):

```
commit: 0F ...
static: 05 10 00 01 [B] [G] [R] .. [11]=colourful [12]=brightness
        [13]=speed [14]=direction [17]=0xAA [18]=0x55
checksum: [31] = sum([0..30]) & 0xFF
```

### 8.3 Colour order

`wireless_color_order` defaults to `bgr` in the shipped defaults, matching
most reverse-engineering sources. **This unit needs `rgb`**: with `bgr`, an
orange target appeared blue, and switching the config to `rgb` produced the
correct orange. The config comment records this.

### 8.4 Limitations

- No per-key frame is documented, and none was found by testing. The whole
  LED set takes the single accent in static mode.
- No brightness readback. The stored state level is reused; raising or
  lowering with the keyboard's own keys while on the dongle is not detected
  (the wired path does detect it).
- Brightness is preserved at the last applied level, not reset.

---

## 9. Brightness

### 9.1 Model

```
effect_value = round(target[channel] * CHANNEL_GAIN[channel] * BRIGHTNESS_SCALE[level - 1])
key_value    = round(target[channel] * BRIGHTNESS_SCALE[level - 1])
```

At level 5 the key value is the raw target. The direct frame itself has no
brightness byte, so keys are scaled in software; the static command does
carry one, so the firmware scales the effect group. The effect line is the
fitted model from §6.3, accurate to about ±1 per channel, not the firmware's
exact arithmetic.

### 9.2 Inference

1. Read the live table (fast path: page 0 only).
2. Take the dominant effect colour; require at least 80% of sampled effect
   entries to agree, otherwise fall back to stored brightness.
3. Predict the effect colour for levels 1–5 from the *previous* target and
   pick the closest.
4. Accept only if the error is ≤ 12; otherwise keep the stored level.

This is what preserves a brightness change made with the keyboard's own
keys. Test on 2026-10-22: state said 5, keyboard was forced to 3 behind the
controller's back, the next `apply` inferred 3, wrote `#A03015` for the keys
and reported `verified=True`.

### 9.3 `set-brightness N`

Persists a level and reapplies the current colour at that level. It updates
`brightness` in state, so later applies keep it.

---

## 10. Performance

Measured on 2026-10-22, wired, brightness 5, same theme.

| Stage | Before | After |
|---|---|---|
| Fast path `apply` (no verify) | 3.56 s | **0.68 s** |
| `apply --verify` | 3.57 s | **1.00 s** |
| Keys update | ~2.0 s in | **~0.4 s in** |
| Underglow update | ~0.5 s in | ~0.65 s in |
| Full table read | 0.71 s | 0.32 s |
| Page-0 read | — | 0.12 s |

Where the remaining 0.68 s goes: page-0 read ~0.12 s, direct frame ~0.27 s,
static effect ~0.19 s, process start and state I/O the rest.

The wireless path measured **0.19 s**: two packets, no readback, so none
of the wired optimisations touch it.

Safety checks run before adopting the pacing changes:

- 20 × `apply --verify` → 20/20 `verified=True`.
- 12 × plain `apply` → no failures.
- Six colours across the spectrum (`#F34820`, `#00A0FF`, `#8839EF`,
  `#88C0D0`, `#F3D420`, `#B59790`) → all `verified=True`.
- Corrupted cache → full fallback, verified, cache repopulated, next apply
  fast again.
- Theme switch to `kanagawa` and back, confirmed visually on the keyboard.


---

## 11. Configuration reference

`~/.config/omarchy/keyboard-accent/config.toml`:

| Key | Value | Meaning |
|---|---|---|
| `color.mode` | `theme` | follow the active theme (`fixed` uses `fixed_color`) |
| `color.fixed_color` | `#F34820` | replaces the accent when `mode = "fixed"`; still transformed |
| `color.min_saturation` | `0.90` | saturation floor for the transform |
| `color.max_lightness` | `0.54` | upper lightness clamp |
| `color.min_lightness` | `0.35` | lower lightness clamp |
| `device.path` | `auto` | auto-detect wired or dongle; or set a by-id path |
| `device.prefer` | `auto` | when both are present: `auto`/`wired` picks wired; use `wireless` while charging |
| `lighting.default_brightness` | `5` | only used before a live level is known |
| `lighting.speed` | `3` | static-mode speed (ignored by static) |
| `lighting.wireless_color_order` | `rgb` | verified for this unit; `bgr` for most sources |
| `lighting.match_direct_zone` | `false` | `true` matches keys to the calibrated underglow |
| `theme_overrides` | 34 entries | see §6.4 |

`match_direct_zone = true` forces the fallback path on wired (it needs the
calibrated effect bytes) and makes keys slightly less red but more uniform.

---

## 12. Command reference

```bash
# apply the current theme accent
omarchy-keyboard-accent apply

# apply and read the table back (adds ~0.3 s now)
omarchy-keyboard-accent apply --verify

# show what would be applied, without touching the keyboard
omarchy-keyboard-accent apply --dry-run

# one-off colour (runs the saturation/lightness transform)
omarchy-keyboard-accent apply --color '#00A0FF' --verify

# one-off colour exactly as written, no transform (white stays white)
omarchy-keyboard-accent apply --exact --color '#FFFFFF'

# force a brightness level for this apply (persists it)
omarchy-keyboard-accent apply --brightness 3

# debounced async apply, as used by the hooks
omarchy-keyboard-accent-queue

# theme, target, transport, cached state
omarchy-keyboard-accent status

# also read the live table and inferred brightness
omarchy-keyboard-accent status --read-table

# dump all 144 live entries
omarchy-keyboard-accent read

# persist a brightness level
omarchy-keyboard-accent set-brightness 5
```

Example outputs:

```
$ omarchy-keyboard-accent apply --dry-run
theme=last-horizon accent=#F34820 (theme_override:last-horizon) target=#F34820 H=11.4 L=0.539 S=0.898 chroma=211

$ omarchy-keyboard-accent status
theme: last-horizon (~/.local/state/omarchy/current/theme)
accent: #F34820 (theme_override:last-horizon)
target: #F34820 H=11.4 L=0.539 S=0.898 chroma=211
config: min_saturation=0.90 max_lightness=0.54 match_direct_zone=False wireless_color_order=rgb theme_overrides=34
device: auto (prefer=auto)
state: brightness=5 transport=wired path=/dev/input/by-id/usb-SONiX_AULA_F75Max-if03-hidraw effect=83 direct=61 target=#F34820 mode=static+direct
```

---

## 13. Access, udev and systemd

### 13.1 Group and nodes

- Dedicated group `aula` contains your user (`install.sh` creates it).
- Rule sets `GROUP="aula"`, `MODE="0660"`, plus `TAG+="uaccess"`.
- Wired: matches `0c45:800a` **and** `ID_USB_INTERFACE_NUM == "03"`.
- Dongle: matches `05ac:024f`; the controller then picks the `0xFF60` node
  from the report descriptor.
- `remove` events re-trigger the service so the surviving transport gets the
  theme (e.g. unplugging the cable while on the dongle).

Deliberately avoided: `MODE="0666"`, broad `hidraw*` matching,
`RUN+="su …"`, and any long-running helper in udev.

### 13.2 Service

```ini
[Unit]
Description=Apply Omarchy theme accent to AULA F75 Max
After=local-fs.target
ConditionPathExists=~/.local/bin/omarchy-keyboard-accent

[Service]
Type=oneshot
User=<you>
Group=<your group>
SupplementaryGroups=aula
Environment=HOME=<your home>
WorkingDirectory=<your home>
ExecStart=<your home>/.local/bin/omarchy-keyboard-accent apply
```

The repository ships this as `system/aula-keyboard-accent.service.in`;
`install.sh` fills in the user, group and home directory. The unit is not
portable as written because systemd does not expand `~`.

Started by udev via `SYSTEMD_WANTS`, not enabled at boot. Typical run is
well under a second; `systemctl status aula-keyboard-accent.service` shows the
last run.

### 13.3 Installer

`install.sh` in the repository root installs the controller and queue script,
both hooks, the plugin, the udev rule and the systemd unit (user, group and
home filled in), creates the `aula` group and adds you to it, then reloads
systemd and udev. Run it as your normal user; it uses `sudo` only for the
system files. It never overwrites an existing
`~/.config/omarchy/keyboard-accent/config.toml`, so reinstalling cannot undo
your overrides or the colour-order fix. Log out and back in once so the group
applies to the desktop session.

---

## 14. Verification recipes

```bash
# 1. resolution only
omarchy-keyboard-accent apply --dry-run

# 2. write and check both zones
omarchy-keyboard-accent apply --verify
tail -1 ~/.local/state/omarchy/keyboard-accent/keyboard-accent.log

# 3. live table (expect #f34820 keys, #a0471f underglow at level 5)
omarchy-keyboard-accent read

# 4. theme change end to end
omarchy-theme-set kanagawa; sleep 2
tail -1 ~/.local/state/omarchy/keyboard-accent/keyboard-accent.log
omarchy-theme-set last-horizon

# 5. brightness preservation
#    set a level behind the controller's back, then apply and check the log
#    (see §9.2; a Python one-liner importing the module is enough)

# 6. wireless
lsusb | grep -i 05ac:024f
omarchy-keyboard-accent status        # transport should be wireless
omarchy-keyboard-accent apply
tail -1 ~/.local/state/omarchy/keyboard-accent/keyboard-accent.log
# expect transport=wireless, mode=wireless-static, verified=n/a
```

Wireless has no readback, so the only real check is visual: the accent should
match the theme. If red and blue are swapped, set
`lighting.wireless_color_order = "rgb"` (already the case here).

---

## 15. Troubleshooting

### Keyboard does not change with the theme

1. `omarchy-keyboard-accent status` — is a device listed?
2. `systemctl status aula-keyboard-accent.service` and
   `tail ~/.local/state/omarchy/keyboard-accent/keyboard-accent.log`.
3. Run `omarchy-keyboard-accent apply` manually; the error line explains the
   failure (permission, no ack, device not found).
4. Check the hook exists and is executable:
   `ls -l ~/.config/omarchy/hooks/theme-set.d/`.

### `device not found`

- Wired: cable must be data-capable; check
  `ls /dev/input/by-id | grep -i aula`.
- Dongle: check `lsusb | grep 05ac:024f` and that a `0xFF60` node exists.
- Both present: `prefer = "auto"` picks wired. Set `prefer = "wireless"` to
  charge over USB while staying on 2.4 GHz.

### Permission denied

- `id | grep aula`; group changes need a fresh login session for the desktop.
- The service also sets `SupplementaryGroups=aula`, so hotplug applies work
  even in a session that predates the group.

### Wireless colour is wrong / swapped

- Red and blue swapped → `wireless_color_order = "rgb"` (current), or `"bgr"`
  if a firmware update inverts it.
- Wrong theme entirely → check `accent_source` in `state.json`; a stale
  override would show `theme_override:<slug>`.

### Wired write works but `verified=False`

- Restore pacing: raise `FEATURE_SETTLE`, `ACK_POLL`, `PAGE_SETTLE` in the
  controller (the current values are 10/20/25 ms; slower values are more
  conservative).
- A single missed ack is already retried up to 3 times (§5.5); check the log
  for `apply attempt N failed` lines to see how often it happens.
- Re-test with `apply --verify` a few times.

### Brightness resets after a theme change

- Wired should infer it. If it does not, the effect group may not be uniform
  (dynamic effect running); inference falls back to the stored level.
- Wireless cannot infer; use `set-brightness N`.

### New theme has the wrong colour

- Add/remove a line in `[theme_overrides]`. Without a line the automatic
  transform applies.
- Check the slug with `ls ~/.local/state/omarchy/current/` after switching, or
  `basename` of the theme directory.

### Bar widget missing or stuck

- After installing or editing the plugin, run `omarchy restart shell`.
  Quickshell's hot reload of plugins is unreliable and can leave a plugin
  silently absent (no dot, no IPC target, nothing in the logs).
- `omarchy plugin validate` checks the manifest; `omarchy plugin list` shows
  whether it is enabled.
- The widget needs `jq`. Run `~/.config/omarchy/plugins/beyond.keyboard-accent/bin/keyboard-accent status`;
  it prints one line of JSON, with `"ok":false` and an error if something is
  wrong.
- It shows on the laptop bar only (`allowMultiple` is false).

### Reinstall wiped something?

- `install.sh` never touches `config.toml`. Config backups from earlier edits
  are `config.toml.bak.<timestamp>` next to the config.

---

## 16. Maintenance

- **Add a theme**: add `slug = "#RRGGBB"` under `[theme_overrides]`; pick the
  colour from the theme's accent or by hand.
- **Remove a theme**: delete its line; the transform takes over again.
- **Retune the look globally**: overrides are pinned, so change them
  individually; `min_saturation`/`max_lightness` only affect `--color`,
  `mode="fixed"`, and themes without an override.
- **Firmware update**: re-run `apply --verify`; if it fails, restore the
  conservative pacing and re-test. Protocol commands are unlikely to change,
  but pacing and calibration may.
- **Reinstall the rules**: run the installer; it is idempotent.
- **Backups**: keep a copy of the controller before editing it, for example
  under `~/.local/share/omarchy-keyboard-accent/`.
- **Plugin edits**: run `omarchy restart shell` afterwards (§15).

---

## 17. Design decisions and limitations

- **No daemon or polling.** Everything is event-driven: theme hook, login
  hook, udev add/change/remove. Idle cost is zero.
- **No vendor software.** Nothing holds the hidraw node between applies.
- **Two protocols, not one.** The dongle is not the wired keyboard behind a
  radio; it has its own output-report protocol with no per-key support.
- **Brightness is preserved, not reset.** Wired infers the live level; wireless
  reuses the stored one because there is no readback.
- **Keys before underglow on wired.** The fast path writes keys first; the
  underglow follows ~0.25 s later. This is the price of not reading the full
  table before every write.
- **Overrides are static by design.** They trade automatic adaptation for
  predictable, vetted colours. New themes need a new line.
- **Calibration is firmware-specific.** `CHANNEL_GAIN` and
  `BRIGHTNESS_SCALE` were measured on this unit (2026-10-21) and may differ on
  other F75 Max revisions.
- **Near-neutral colours shift in the underglow.** Red attenuation turns warm
  whites mint-ish and greys cool. Accepted after visual check; keys remain
  exactly as configured.
- **The fast path assumes the zone partition is complete** (83 + 61 = 144).
  If a future firmware exposes a different split, the controller falls back
  to the read-based order automatically.
- **Exact colour is opt-in.** The transform keeps accents vivid but tints
  neutrals (white becomes gold), so `--exact` skips it. Underglow is
  firmware-calibrated either way and cannot be set exactly.
- **The widget polls nothing.** It refreshes on load, when the picker opens,
  after each action, and 2.5 s after the shell's accent changes.
- **`verified=n/a` on wireless** is expected, not an error.

---

## 18. Bar widget

Plugin `beyond.keyboard-accent` (`plugin/` in the repository). It adds a dot to
the bar showing the keyboard's current colour and a popup picker.

- **Dot**: filled when the keyboard matches the theme accent, ringed when a
  custom colour is set. Left-click opens the popup; right-click resets to the
  theme colour.
- **Popup**: keyboard and theme swatches (click THEME to reset), seven presets
  drawn in the colour the keys will really show, a hex field with live
  preview, an **Exact colour** switch, and Apply / Reset to theme.
- **Matching**: keyboard and theme count as matching when their summed
  per-channel difference is at most 3, because controller rounding can leave a
  colour a step or two off.
- **Custom colours** last until the next theme change, when the hook sets the
  theme colour again.
- **Helper** `bin/keyboard-accent` wraps the controller and prints one line of
  JSON per command: `status`, `targets [--exact] #HEX...` (dry run, what the
  keys would show), `preview`, `apply [--exact] #HEX`, `reset`. Errors are
  `{"ok":false,"error":...}`.
- **IPC**: `omarchy-shell beyond.keyboard-accent toggle` (also `open`, `close`,
  `refresh`, `reset`).
- **Enable**: `omarchy plugin enable beyond.keyboard-accent`, then
  `omarchy restart shell`.

---

## 19. Change log

### 2026-10-21
- Wired controller, hooks, queue, locking, brightness preservation,
  verification, logging, state.
- Dongle support added: USB/descriptor detection, 32-byte output protocol,
  static-only colour, persisted brightness.
- udev rules and one-shot service installed with a dedicated `aula` group.
- First real wireless apply; colour came out blue, fixed by switching
  `wireless_color_order` from `bgr` to `rgb` (verified on hardware).

### 2026-10-22
- Added `apply --exact` (colour as written, no transform) after white showed as
  light gold through the saturation floor.
- Bar widget added (§18) and the project published as a repository with an
  installer.
- Protocol errors retried (3 attempts, 0.5 s apart). Added after a theme
  change was dropped on a missed ack (`no ack for 4/24`, 11:26)..
- Wired `apply` optimised from 3.56 s to 0.68 s:
  - verify made opt-in (`--verify`);
  - direct frame written before `set_static`, using a cached full frame;
  - page-0 read replaces the full 9-page read for brightness inference;
  - pacing constants reduced (10/20/25 ms) and validated.
- All 34 installed themes pinned in `[theme_overrides]`, with six hand-tuned
  (`white`, `vantablack`, `fireside`, `solitude`, `gruvbox`, `rose-pine`) and
  the earlier `nord` / `catppuccin-latte` brand colours kept.
- Verified: 34/34 overrides resolve exactly; no missing or stale slugs.
- Verified: brightness inference on the fast path, cache fallback, 20/20
  verified applies, visual theme switch to `kanagawa` and `white`.

---

## Appendix A — state file

`~/.local/state/omarchy/keyboard-accent/state.json` (table cache shortened):

```json
{
  "version": 1,
  "theme": "last-horizon",
  "accent": "#F34820",
  "accent_source": "theme_override:last-horizon",
  "target": "#F34820",
  "target_rgb": [243, 72, 32],
  "brightness": 5,
  "effect_indices": [83 entries],
  "direct_indices": [61 entries],
  "match_direct_zone": false,
  "mode": "static+direct",
  "updated_at": "2026-10-22T11:31:42+02:00",
  "transport": "wired",
  "device_path": "/dev/input/by-id/usb-SONiX_AULA_F75Max-if03-hidraw",
  "table_cache": "<base64 of the 576-byte frame, 768 chars>"
}
```

- `effect_indices` / `direct_indices` are learned once; if both are missing
  the controller bootstraps them by probing brightness 1 and 5.
- `table_cache` exists only for the wired fast path and is validated on load
  (base64, exactly 576 bytes). A bad cache is ignored, not fatal.

## Appendix B — log format

```
2026-10-22 11:30:34 theme=last-horizon accent=#F34820 target=#F34820 H=11.4 L=0.539 S=0.898 chroma=211 brightness=5 transport=wired effect=83 direct=61 direct_rgb=#F34820 bootstrapped=False verified=True result=ok
```

- `transport` is `wired` or `wireless`.
- `verified` is `True`, `False`, `skipped` (no `--verify`), or `n/a` (dongle,
  no readback).
- Failures are logged as `apply failed: <reason>` with no result line.
- Wireless lines use `path=<hidraw>` and `mode=wireless-static` instead of
  the zone counts.
