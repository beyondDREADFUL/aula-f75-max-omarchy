# v2 phase 0: hardware findings

Measured 2026-10-23 on the reference AULA F75 Max over the USB cable (Linux,
hidraw). "Seen" means confirmed by eye on the keyboard; "read" means read back
from the LED table with `04 F5`. These replace the v1 handbook where they
disagree.

## The LED table

The keyboard keeps one 144-slot table (9 pages x 64 bytes, 4 bytes per slot:
`index, R, G, B`), readable with `04 18`, `04 F5 .. 09`, 9 feature reads, `04 02`.

| Slots | What they are | Evidence |
|---|---|---|
| The 80 key indices from the vendor layout (`layout.py`) | The only visible LEDs | read: written by `04 13`; seen: live frames on them light the keys |
| 95, 110, 111 | Written by `04 13`, but nothing lights up | read + seen (streamed red/blue/yellow: nothing visible) |
| The other 61 (0, 14-18, 32-36, ...) | Empty: never written by `04 13`, nothing lights up | read + seen |

**v1 was wrong here.** It called the 83 slots touched by `04 13` the
"effect/underglow" zone and the 61 empty slots the "direct/key" zone. In fact
the keys are in its effect zone, there is no separate underglow, and its
`write_direct` step writes only empty slots. Everything built on that split
(`write_direct`, `bootstrap_zones`, `table_cache`, `match_direct_zone`, the
direct check in `--verify`, "keys exact, underglow calibrated") has no visible
effect or describes something that does not exist.

## How each command changes the table and the display

| Command | Table | Display |
|---|---|---|
| `04 13` effect (static or any mode) | rewrites the same 83 slots with calibrated values | shows the effect |
| `04 23` + mode `0x80` (custom per-key) | stores the same calibrated values as static | shows the per-key colours (verified earlier with f75ctl) |
| `04 20` live frame | patches only the slots named in the frame, raw (uncalibrated) | **only while frames keep arriving**; the effect returns when the stream stops (seen: one frame shows nothing, a 3 s stream shows, then reverts) |

- Live-frame entries are addressed by their index byte, not by their position
  in the frame (seen: an entry with index 94 placed first lit Space, not Esc).
- Patches survive in the table after the stream stops and reappear in the next
  stream until `04 13` rewrites the slot. Stale patches explain the "F3 and
  Space" seen in an early test.
- Both the 9-page index-sorted frame (v1) and the 8-packet row-major frame
  (f75ctl) work, when streamed and when the host reads the ack after the header
  and after `04 02`. Frame size and order do not matter.

## Colour calibration

The firmware scales stored values per channel; static and custom store the
same numbers:

| Requested | Brightness 5 | Brightness 3 |
|---|---|---|
| `ff0000` | `a80000` | `6e0000` |
| `ffffff` | `a8fdfd` | `6ea6a6` |
| `f34820` | `a0471f` | `692f14` |
| `0000ff` | `0000fd` | `0000a6` |

Seen side by side, raw white from a live frame (`ffffff`) looks warm and the
calibrated static white (`a8fdfd`) looks neutral. So the firmware's red gain
(about 0.66) is a correct white balance:

- Effects and custom per-key colours can be sent as the intended colour.
- Live frames bypass it, so music mode and any other live output must apply
  the same gains itself to match.
- v1's `underglow_correction` (lowering green and blue to "fix" the underglow)
  compensated for a white balance that was already right; it shifts the keys.

## Dongle

The `0F` commit packet that v1 sends before the dongle's lighting packet is not
needed: f75ctl set effects, per-key colours, remaps and macros over the dongle
without it (seen). Per-key colours over the dongle work (command `14`), which
v1's handbook says is impossible.

## Consequences for v2

- Wired apply = one `04 13` (or `04 23` + `0x80` for per-key), no direct
  frame, no zone bootstrap, no table cache. Brightness inference can still use
  the table read, on key slots only.
- One calibration model (`gain = (0.66, 0.99, 0.99)` x brightness curve)
  shared by verification and by live-frame output.
- Drop `underglow_correction` and re-derive the theme colour choice on the
  keys themselves.
