# AULA F75 Max on Omarchy: handbook

How the keyboard is controlled, what is known about its protocol and how sure we are,
and how the accent controller and `f75ctl` use it.

- Keyboard: AULA F75 Max, wired `0c45:800a` and 2.4 GHz dongle `05ac:024f`
- Platform: Omarchy on Arch (Hyprland), Linux hidraw
- Last verified: 2026-10-23, cable and dongle, on the reference keyboard

Every protocol statement is marked by how it was established:

| Mark | Meaning |
|---|---|
| **seen** | checked by eye on the keyboard |
| **read** | read back from the keyboard (LED table, acks, battery) |
| **sent** | the keyboard accepted it (ack) but the effect was not looked at |
| **assumed** | not checked; treat as a hypothesis |

Measurements come from one keyboard. Other units or firmware may differ, especially in
calibration (§5) and timing (§3.4).

---

## 1. Overview

```
theme change ──> hooks/theme-set.d ──┐
login        ──> hooks/post-boot.d ──┼─> omarchy-keyboard-accent-queue (debounce)
plug/unplug  ──> udev ─> systemd ────┘            │
                                                  ▼
bar widget ──> bin/keyboard-accent ──> omarchy-keyboard-accent apply   (accent/)
                                                  │
you ──> f75ctl light|keycolors|remap|music|... ───┤                    (aula_f75/cli.py)
                                                  ▼
                                        aula_f75 library, one lock
                                          │                 │
                                   cable 0c45:800a     dongle 05ac:024f
```

| Part | Role |
|---|---|
| `aula_f75/` | Protocol library, standard library only. `hidraw.py` (find nodes, ioctls), `device.py` (cable and dongle behind one interface, the lock), `layout.py`, `lighting.py`, `keymap.py`, `lcd.py`, `music.py`, `cli.py` (`f75ctl`) |
| `accent/` | Theme accent to keyboard: `color.py` (colour choice), `config.py` (config, state, pin, theme), `controller.py` (the `omarchy-keyboard-accent` command) |
| `bin/` | Thin entry points: `omarchy-keyboard-accent`, `omarchy-keyboard-accent-queue`, `f75ctl`, `keyboard-accent` (widget helper) |
| `KeyboardAccent.qml`, `manifest.json` | Bar widget (docs/WIDGET.md) |
| `hooks/`, `system/` | Omarchy hooks, udev rule, one-shot systemd unit |

Nothing runs in the background. The theme hook, login hook and udev events each start one
apply; `f75ctl music` runs only while you run it.

---

## 2. Hardware

### 2.1 Cable (`0c45:800a`)

| Interface | Usage page | Use |
|---|---|---|
| 0, 1 | keyboard, consumer | normal input, never opened |
| 2 | `0xFF68` | LCD image upload: 4096-byte output reports |
| 3 | `0xFF13` | commands: 64-byte feature reports |

### 2.2 Dongle (`05ac:024f`, masquerades as an Apple keyboard)

| Interface | Usage page | Use |
|---|---|---|
| 0-2, 4 | keyboard, mouse, consumer, `0xFF59` | input, never opened |
| 3 | `0xFF60` | commands: 32-byte output reports, input-report replies |

Nodes are found through sysfs: `HID_ID` in `device/uevent` and `bInterfaceNumber` of the
parent USB interface. No hidapi, no descriptor parsing.

### 2.3 The LED table and the 80 keys

The keyboard keeps one table of 144 slots, 4 bytes each: `[slot, R, G, B]` (9 pages of 64
bytes).

| Slots | What they are | How we know |
|---|---|---|
| the 80 slots in `layout.KEYS` (Esc = 1 ... Right = 102) | the only visible LEDs, one per key | **seen**: live frames on them light exactly those keys |
| 95, 110, 111 | written by effects, nothing lights up | **read** + **seen** (streamed red, blue, yellow: nothing visible anywhere) |
| the other 61 | empty: never written by effects, nothing lights up | **read** + **seen** |

There is no separate underglow on this keyboard. Slot numbers, HID usages and the 6 x 15
grid positions come from the vendor's `layouts/rgb-keyboard.xml`.

---

## 3. Cable protocol

### 3.1 Framing

All commands are 64-byte feature reports with report ID 0:

```
04 18                     begin            (04 19 for macros)
04 <cmd> 00*6 <n>         header: n = number of 64-byte data packets
<n data packets>
04 02                     end
04 f0                     apply (after lighting and keymap commands)
```

The keyboard echoes each packet as the next feature report. For `04 ..` packets it sets
byte 3 (after the report ID) to `01` when accepted (**read**). Data packets are echoed but
never flagged. The keyboard sometimes rejects a transaction right after a large write; one
retry after 0.5 s has always been enough.

### 3.2 Commands

| Cmd | Data | What it does | Status |
|---|---|---|---|
| `13` | 1 packet: effect payload (§4.1) | set the lighting effect | **seen**, all 19 modes |
| `23` | 9 packets: 576-byte colour table (§4.2) | per-key colours, shown with mode `0x80` | **seen** |
| `11` | 9 packets: layer table (§6) | base-layer keymap | **seen** |
| `27` | same as `11` | Fn-layer keymap | **seen** |
| `15` | macro blob (§6.2), begin `04 19`, no `04 f0` | macro store | **seen** |
| `28` | `00 01 5a YY MM DD hh mm ss 00 wd` (Sunday = 0), no `04 f0` | LCD clock | **seen** |
| `72` | header byte 2 = frames, bytes 8-9 = chunk count (LE); no data packets | LCD image upload (§7) | **seen** |
| `20` | up to 8 packets of `[slot, R, G, B]`; no `04 18` / `04 f0` | live frame (§4.3) | **seen** |
| `F5` | header byte 8 = pages; then read that many feature reports | read the LED table | **read** |

A battery query (`04 ..` form of `20 01`) is answered with `ff`: the cable does not report
the battery (**read**).

### 3.3 Reading the LED table

`04 18`, `04 F5 00 00 00 00 00 00 <pages>`, then one feature read per page (25 ms apart),
then `04 02`. Page 0 holds slots 0-15, which includes Esc and F1-F12; that is enough to
learn the brightness (§5.2).

### 3.4 Timing on Linux

| Wait | Value | Why |
|---|---|---|
| after each command packet, before reading its echo | 35 ms | the vendor app's `cmd_delaytime`; faster was not needed |
| between table pages | 25 ms | **read** reliably |
| after each live-frame packet | 3 ms | without it the ack comes back `00`/`ff` instead of `01` and the display freezes after ~3 s; 3 ms gave 200/200 clean frames (**read**, **seen**) |
| between LCD chunks | 150 ms | the vendor app sends one about every 160 ms |

The Linux `ioctl` returns before the keyboard has processed a packet, which is why the
live-frame pause is needed on Linux and not on Windows.

---

## 4. Lighting

### 4.1 Effects (`13`, dongle `05`)

16-byte payload: `mode, R, G, B, 0*4, rainbow, brightness 0-5, speed 0-5, direction 0/1,
0, 0, aa, 55`. With no colour, effects run as rainbow (`ff0000` + rainbow flag), as the
vendor app sends them. Static and custom never set the rainbow flag.

Modes (names from the vendor's language file, **seen** with `f75ctl demo`):
`off 00, static 01, single-on 02, single-off 03, glittering 04, falling 05, colourful 06,
breath 07, spectrum 08, outward 09, scrolling 0A, rolling 0B, rotating 0C, explode 0D,
launch 0E, ripples 0F, flowing 10, pulsating 11, tilt 12, shuttle 13, custom 80`.

Which effects use the single colour has not been checked for every mode (**assumed**
for most).

### 4.2 Per-key colours (`23` + mode `0x80`)

The 576-byte table is `[slot, R, G, B]` at offset `slot x 4` for each key slot, `aa 55` in
the last two bytes. Then an effect command with mode `0x80` shows it. Over the dongle the
same table goes as command `14` (§8).

### 4.3 Live frames (`20`)

What is known (**seen** unless noted):

- A frame patches the slots it names in the LED table, raw (uncalibrated, §5). Entries are
  addressed by their slot byte, not their position in the frame: an entry for slot 94
  placed first lit Space, not Esc.
- **It only shows while frames keep arriving.** One frame shows nothing; a stream shows,
  and the running effect returns when the stream stops.
- The host must read the feature-report ack after the header and after `04 02`, or the
  keyboard stops taking frames after one or two.
- Frame size and order do not matter: 9 pages sorted by slot and 8 packets in grid order
  both work.
- Patched slots keep their values in the table after the stream stops and reappear in the
  next stream until an effect command rewrites them (**read**).

The music visualiser (§9) is the only user of live frames.

---

## 5. Colour calibration

### 5.1 The firmware's white balance

Effects and per-key colours are stored scaled per channel and by brightness; both store
identical values (**read**):

| Requested | Level 5 | Level 3 |
|---|---|---|
| `ff0000` | `a80000` | `6e0000` |
| `ffffff` | `a8fdfd` | `6ea6a6` |
| `f34820` | `a0471f` | `692f14` |
| `0000ff` | `0000fd` | `0000a6` |

Model (`lighting.calibrate`), within about 1 per channel of every measurement:

```
stored = round(colour x GAIN x BRIGHTNESS[level])
GAIN       = (0.6575, 0.9911, 0.9885)            R, G, B
BRIGHTNESS = (0.1805, 0.3750, 0.6598, 0.7848, 1.0)   levels 1-5
```

Side by side, raw white from a live frame looks warm and the calibrated white looks
neutral (**seen**). **The red gain is a correct white balance**, so:

- effects and per-key colours are sent as the intended colour, with no correction;
- live frames bypass it, so the music visualiser runs every colour through `calibrate()`
  to look the same as an effect.

### 5.2 Brightness read-back

Over the cable the apply reads page 0 of the table, takes the colour most key slots show
(at least 80 % must agree), and finds the level at which the last applied colour is stored
as that value (within 12). This keeps a level set with the keyboard's own keys
(**read**: set 3, next apply kept 3). If the keys are not uniform (an animated effect),
or nothing fits, the stored level is used. The dongle has no read-back; it reuses the
stored level.

---

## 6. Keymaps and macros

### 6.1 Layers (`11` base, `27` Fn; dongle `03`)

144 entries of 4 bytes, indexed by LED slot: `[2, 0, usage, 0]` remaps a key, `[6, macro
slot, 0, 0]` binds a macro, all zero keeps the default. **Writing a layer replaces all of
it**, so every remap and macro for a layer goes in one command (`f75ctl remap capslock=esc
f1=a,b,c`). The Fn layer can only be written over the cable.

### 6.2 Macros (`15`; dongle `09`)

```
100 slots of [offset u16, 0, 0]          first macro at offset 400
per macro: [word count u16, 0*6]         8-byte header
per event: [0, 0, usage, b0 press | 30 release] [delay ms u16, 00, 50]
aa 55 at the end; sized to whole 64-byte packets plus one
```

A step like `ctrl+c` presses its keys in order and releases them in reverse (**seen**:
`shift+h,i` types "Hi", `ctrl+a` selects all). The macro store seems to be shared by both
layers, so writing macros for one layer probably replaces those bound on the other
(**assumed**).

---

## 7. LCD (cable only)

- Clock: command `28` (§3.2). The accent controller sets it on every wired apply.
- Image: command `72`, then the image as 4096-byte output reports on interface 2, then
  `04 02`. The image is a 256-byte header `[frame count, delay per frame in 2 ms units,
  ff...]` plus 128 x 128 RGB565 little-endian frames, padded with `ff` to whole chunks
  (**seen**: a 40-frame GIF at 250 ms per frame plays at 250 ms; 321 chunks in 69 s).
- The vendor app sets neither over the dongle, and neither does this.

---

## 8. Dongle protocol

Every message is a 32-byte output report: `[cmd, len, offset, data..., checksum]` with
byte 31 = sum of bytes 0-30 & `ff`. On Linux it is written as 33 bytes with report ID 0
first. There is no begin/end framing and no commit packet (**seen**: everything below
works without the `0F` packet v1 sent first).

| Cmd | Offset | Data | Status |
|---|---|---|---|
| `05` | 0 | the 16-byte effect payload (§4.1), colour as R, G, B | **seen** |
| `14` | chunk number | the 576-byte colour table in 28-byte chunks; then `05` with mode `80` | **seen** |
| `03` | key slot | one 4-byte layer entry; to restore a key send `[2, 0, own usage, 0]` | **seen** |
| `09` | chunk number | the macro blob, trimmed to used bytes plus one spare chunk, `aa 55` at the end | **seen** |
| `20 01` | | battery query, answered `20 01 00 <percent>` | **read** |

Acks for `03` (`[03, 04, slot, status]`) arrive several messages late, so only a non-zero
status is treated as an error. The last chunk's `len` covers only the used bytes, but all
28 are sent, like the vendor app.

---

## 9. Music visualiser (`f75ctl music`)

15 columns of bars, one per grid column, streamed as live frames at up to 20 fps
(**seen**: 19.6-20.0 fps).

- Levels from **cava** when installed (raw 8-bit output, 15 mono bars; only the newest frame
  is used so it never lags), else a numpy FFT of the system audio via `soundcard`, which
  reads exactly the audio produced since its last read (reading a fixed amount fell ~20 s
  behind over 30 s).
- Backgrounds: solid colours, a hue cycle, or `ambilight`: the screen colour from a 5 %
  `grim` screenshot in a background thread, weighted toward saturated pixels and eased
  25 % per frame.
- Holds the keyboard lock while running; a theme change meanwhile waits up to 15 s, then is
  deferred, and `music` applies the theme accent when it stops (`--after theme`, default).

---

## 10. The accent controller

### 10.1 Apply

1. Resolve the colour: `--color` (as written with `--exact`), else a pin, else `fixed`
   mode, else a `[theme_overrides]` entry (as written), else the theme accent through the
   automatic choice (§10.2).
2. Take the keyboard lock (wait up to 15 s; if busy, log `deferred` and stop).
3. Cable: read page 0 for the brightness (§5.2), send one effect command, set the LCD
   clock. Dongle: one `05` message with the stored brightness.
4. Save state and log one line.

About 0.57 s over the cable including the clock, 0.1 s over the dongle (**read**).
`--verify` reads the table and checks the keys against `calibrate(target, level)` within 18.

### 10.2 Automatic colour choice

Saturated accents (saturation >= 0.80) are kept; muted ones keep their hue with saturation
`saturation_floor + saturation_gain x s` (at most 0.95); grey and pale accents become a
soft white that keeps their hue (warm if none); lightness is held in
`min_lightness`-`max_lightness`. Nothing compensates for the LEDs (§5.1).

### 10.3 Files

| Path | Content |
|---|---|
| `~/.config/omarchy/keyboard-accent/config.toml` | config (`config.example.toml` documents every key); never overwritten by install |
| `~/.local/state/omarchy/keyboard-accent/state.json` | last apply: theme, accent, source, target, brightness, effect, transport |
| `.../pin.json` | pinned colour, if any |
| `.../keyboard-accent.log` | one line per apply |
| `$XDG_RUNTIME_DIR/aula-f75.lock` | the keyboard lock |

---

## 11. Commands

```bash
omarchy-keyboard-accent apply [--color HEX [--exact] [--pin]] [--brightness N] [--verify] [--dry-run]
omarchy-keyboard-accent unpin | status [--read-table] | read | set-brightness N

f75ctl light <mode> [-c RRGGBB] [-b 0-5] [-s 0-5] [-d 0|1]
f75ctl demo | keycolors esc=ff0000 ... [--default RRGGBB]
f75ctl remap capslock=esc f1=a,b,c f2=ctrl+c [--fn-layer] | macro ... | reset-keymap [--fn-layer]
f75ctl clock | gif FILE | battery | keys
f75ctl music [--source auto|cava|builtin] [--color ...] [--background ...|ambilight] [--test]
f75ctl --dry-run ...       print cable packets, send nothing
f75ctl --dongle ...        use the dongle when the cable is also plugged in
```

`gif` and the ambilight background need pillow; the built-in analyser needs numpy and
soundcard. Everything else needs only Python 3.11+.

---

## 12. Install, access and verification

`install.sh` copies `aula_f75/` and `accent/` to `~/.local/share/omarchy-keyboard-accent/`,
the commands to `~/.local/bin`, the hooks and the widget; with sudo it adds the `aula`
group, the udev rule (cable interfaces 2 and 3, dongle interface 3) and the one-shot unit.
`uninstall.sh` removes all of it (`--purge` also config and state).

Checks:

```bash
python3 -m unittest discover tests          # packets, calibration, colour choice
omarchy-keyboard-accent apply --verify      # cable: keys match the expected stored colour
f75ctl --dry-run light static -c 00ff00     # see the packets
f75ctl music --test --seconds 5             # bars must move the whole time
```

---

## 13. Troubleshooting

| Symptom | Check |
|---|---|
| nothing happens on theme change | `tail ~/.local/state/omarchy/keyboard-accent/keyboard-accent.log`; `result=deferred` means another program held the keyboard |
| `keyboard not found` | `lsusb | grep -iE '0c45:800a|05ac:024f'`; the cable must carry data |
| permission denied | `id | grep aula` (log in again after install); `ls -l /dev/hidraw*` |
| `keyboard rejected 04 ..` | close any other program using the keyboard (the vendor app on Windows polls constantly) |
| music bars freeze | the live-frame pause (§3.4) may need raising on other hardware |
| colour differs cable vs dongle | both should match; report it, since the dongle colour order was only checked on one unit |
| wrong colour for a new theme | add a line under `[theme_overrides]` |

---

## 14. Corrections to v1

v1 (2026-10-21/22) was built on a wrong model of the LED table. Corrected in v2:

| v1 said | Actually |
|---|---|
| 83 "effect/underglow" slots + 61 "direct/key" slots | the 80 keys are among the 83; the 61 are empty; there is no separate underglow (§2.3) |
| keys show the colour exactly, the underglow is calibrated | keys are calibrated, and the calibration is a correct white balance (§5.1) |
| `underglow_correction` lowers green and blue | it shifted the keys; removed |
| the direct per-key frame paints the keys | it wrote to empty slots; as a live frame it only shows while streamed (§4.3) |
| "per-key wave not visible" | same cause: written to empty slots, and not streamed |
| dongle: static colour only, no per-key | per-key colours, remaps and macros work (§8) |
| dongle needs a `0F` commit first | not needed |
| apply = page-0 read + direct frame + static + cache | page-0 read + one effect command |

v1's experiments with cross-fades between theme colours (about 10 steps per second before
the keyboard merges updates) still stand as an observation about effect commands; they
were not repeated.
