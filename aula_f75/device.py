"""The keyboard over its two transports, behind one interface.

Cable (0c45:800a): 64-byte feature reports on interface 3, framed as
    04 18 | 04 <cmd> 00*6 <n> | n data packets | 04 02 | 04 f0 (apply)
Each packet is echoed; command packets come back with byte 3 set to 01 when accepted.
LCD images go as 4096-byte output reports on interface 2.

Dongle (05ac:024f, interface 3): 32-byte output reports [cmd, len, offset, data...,
checksum = sum of bytes 0-30], answered by input reports that can lag several messages.

Every opened keyboard holds an exclusive lock, so the accent controller, f75ctl and music
mode never interleave packets (interleaving corrupts transactions).
"""
from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

from . import hidraw, lighting
from .layout import KEYS, SLOTS
from .lcd import CHUNK

WIRED = (0x0C45, 0x800A)
DONGLE = (0x05AC, 0x024F)
CMD_IFACE, SCREEN_IFACE = 3, 2

PACKET_DELAY = 0.035   # vendor cmd_delaytime; the reply is read after it
FRAME_DELAY = 0.003    # per live-frame packet: without it acks come back 00/ff and the
                       # display freezes after a few seconds (Linux)
CHUNK_DELAY = 0.15     # the vendor app sends one LCD chunk about every 160 ms
TABLE_DELAY = 0.025    # between LED-table pages
FAST_DELAY = 0.004     # an effect sent at this pacing fits between two live frames (seen:
                       # no flash); the keyboard accepts it, though 04 f0 may not ack yet


class NotFound(RuntimeError):
    pass


class Busy(RuntimeError):
    pass


class Rejected(RuntimeError):
    pass


class Unsupported(RuntimeError):
    pass


def settings_block(sleep: int, debounce: int) -> bytes:
    """The 16-byte settings block: sleep timer code 0-3 (never, 1, 5, 30 min) and debounce
    level 1-5. Bytes 2-5 (Win lock, Alt+F4, Alt+Tab, Fn switch) are ignored by firmware 106,
    so they stay 0."""
    if sleep not in range(4):
        raise ValueError(f"sleep code {sleep} is not in 0-3")
    if debounce not in range(1, 6):
        raise ValueError(f"debounce {debounce} is not in 1-5")
    block = bytearray(16)
    block[1] = 0x01
    block[6] = sleep
    block[8] = debounce
    block[14:16] = b"\xaa\x55"
    return bytes(block)


def lock_path() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/aula-f75-{os.getuid()}"
    Path(base).mkdir(parents=True, exist_ok=True)
    return Path(base) / "aula-f75.lock"


def _lock(timeout: float) -> int:
    fd = os.open(lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise Busy("another program is using the keyboard")
            time.sleep(0.05)


class Keyboard:
    """Common interface. Methods a transport can't do raise Unsupported."""
    transport = ""

    def __init__(self, path: str, lock_fd: int):
        self.dev = hidraw.Device(path)
        self.path = path
        self._lock_fd = lock_fd

    def close(self) -> None:
        self.dev.close()
        if self._lock_fd >= 0:
            os.close(self._lock_fd)        # releases the lock
            self._lock_fd = -1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _no(self, what):
        raise Unsupported(f"{what} is not available over the {self.transport} connection")

    def light(self, effect: lighting.Effect, fast: bool = False) -> None: self._no("lighting")
    def key_colors(self, table: bytes, brightness: int = 5) -> None: self._no("per-key colour")
    def write_layer(self, table: bytes, fn_layer: bool = False) -> None: self._no("remapping")
    def write_macros(self, blob: bytes) -> None: self._no("macros")
    def set_clock(self, payload: bytes) -> None: self._no("the LCD clock")
    def upload_image(self, blob: bytes, frames: int, progress=None) -> None: self._no("the LCD")
    def frame(self, colors: dict[int, tuple[int, int, int]]) -> None: self._no("live frames")
    def read_table(self) -> list[tuple[int, int, int, int]]: self._no("LED read-back")
    def battery(self) -> int: self._no("the battery level")
    def settings(self, sleep: int, debounce: int) -> None: self._no("keyboard settings")
    def reset(self, factory: bool = False) -> None: self._no("reset")


class Wired(Keyboard):
    transport = "wired"

    def _send(self, payload, check=True) -> bytes:
        self.dev.set_feature(payload)
        time.sleep(PACKET_DELAY)
        reply = self.dev.get_feature()
        if check and (reply[:2] != bytes(payload[:2]) or reply[3] != 1):
            raise Rejected(f"keyboard rejected {bytes(payload[:2]).hex(' ')} "
                           f"(reply {reply[:8].hex(' ')})")
        return reply

    def transaction(self, cmd: int, data: bytes = b"", apply: bool = True, begin: int = 0x18):
        # the keyboard occasionally rejects a transaction right after a large write
        for attempt in (1, 2):
            try:
                n = (len(data) + 63) // 64
                self._send([0x04, begin])
                self._send([0x04, cmd, 0, 0, 0, 0, 0, 0, n])
                for i in range(n):
                    self._send(data[i * 64:(i + 1) * 64], check=False)
                self._send([0x04, 0x02])
                if apply:
                    self._send([0x04, 0xF0])
                return
            except Rejected:
                if attempt == 2:
                    raise
                time.sleep(0.5)

    def light(self, effect, fast=False):
        """fast: live-frame pacing, for use during a transition (see transition.py)."""
        if not fast:
            self.transaction(0x13, effect.payload())
            return
        for n, p in enumerate([[0x04, 0x18], [0x04, 0x13, 0, 0, 0, 0, 0, 0, 1],
                               effect.payload(), [0x04, 0x02], [0x04, 0xF0]]):
            self.dev.set_feature(p)
            time.sleep(FAST_DELAY)
            if n in (0, 1, 3):
                reply = self.dev.get_feature()
                if reply[:2] != bytes(p[:2]) or reply[3] != 1:
                    raise Rejected(f"keyboard rejected {bytes(p[:2]).hex(' ')} (reply "
                                   f"{reply[:8].hex(' ')})")

    def key_colors(self, table, brightness=5):
        self.transaction(0x23, table)
        self.light(lighting.Effect("custom", (0, 0, 0), brightness, 0))

    def write_layer(self, table, fn_layer=False):
        self.transaction(0x27 if fn_layer else 0x11, table)

    def write_macros(self, blob):
        self.transaction(0x15, blob, apply=False, begin=0x19)

    def set_clock(self, payload):
        self.transaction(0x28, payload, apply=False)

    def settings(self, sleep, debounce):
        # the data packet is not read back: the keyboard then rejects the end packet
        block = settings_block(sleep, debounce)
        data = bytearray(64)
        data[0:14] = block[0:14]
        data[62:64] = block[14:16]
        for attempt in (1, 2):
            try:
                self._send([0x04, 0x18])
                self._send([0x04, 0x17, 0x01, 0, 0, 0, 0, 0, 1])
                time.sleep(PACKET_DELAY)
                self.dev.set_feature(bytes(data))
                time.sleep(PACKET_DELAY)
                # the end reply carries the sum of the data packet and the packet count
                reply = self._send([0x04, 0x02])
                if reply[4] != (sum(data) & 0xFF) or reply[5] != 1:
                    raise Rejected(f"keyboard did not take the settings (reply "
                                   f"{reply[:6].hex(' ')})")
                return
            except Rejected:
                if attempt == 2:
                    raise
                time.sleep(0.5)

    def upload_image(self, blob, frames, progress=None):
        chunks = len(blob) // CHUNK
        path = hidraw.find(*WIRED, SCREEN_IFACE)
        if not path:
            raise NotFound(f"screen interface {SCREEN_IFACE} not found")
        self._send([0x04, 0x18])
        self._send([0x04, 0x72, frames, 0, 0, 0, 0, 0, chunks & 0xFF, chunks >> 8])
        screen = hidraw.Device(path)
        try:
            for i in range(chunks):
                screen.write(blob[i * CHUNK:(i + 1) * CHUNK])
                if progress:
                    progress(i + 1, chunks)
                time.sleep(CHUNK_DELAY)
        finally:
            screen.close()
        self._send([0x04, 0x02])

    def frame(self, colors):
        """One live frame: {slot: rgb}, stored raw (see lighting.calibrate). It shows only
        while frames keep arriving; the effect returns when they stop. The host must read
        the ack after the header and after 04 02 or the keyboard stops taking frames."""
        blob = bytearray(512)
        for k, (slot, rgb) in enumerate(sorted(colors.items())[:128]):
            blob[k * 4:k * 4 + 4] = bytes([slot, *rgb])
        pkts = ([[0x04, 0x20, 0, 0, 0, 0, 0, 0, 8]] + [blob[i:i + 64] for i in range(0, 512, 64)]
                + [[0x04, 0x02]])
        for n, p in enumerate(pkts):
            self.dev.set_feature(p)
            time.sleep(FRAME_DELAY)
            if n in (0, len(pkts) - 1):
                try:
                    self.dev.get_feature()
                except OSError:      # occasional EPIPE; costs only this frame
                    time.sleep(0.02)

    def read_table(self, pages: int = SLOTS * 4 // 64):
        """The live LED table as [(slot, r, g, b)], first `pages` 64-byte pages (16 slots
        each)."""
        self._send([0x04, 0x18])
        self._send([0x04, 0xF5, 0, 0, 0, 0, 0, 0, pages])
        raw = bytearray()
        for _ in range(pages):
            time.sleep(TABLE_DELAY)
            raw += self.dev.get_feature()
        self._send([0x04, 0x02])
        return [tuple(raw[i:i + 4]) for i in range(0, len(raw), 4)]


class Dongle(Keyboard):
    transport = "wireless"

    def _send(self, cmd, offset, data, length=None):
        msg = bytearray(32)
        msg[0:3] = bytes([cmd, len(data) if length is None else length, offset])
        msg[3:3 + len(data)] = data
        msg[31] = sum(msg[:31]) & 0xFF
        self.dev.write(msg)
        # acks come back over the radio and lag a few messages behind: check status only
        reply = self.dev.read(33, 0.1)
        if reply and reply[0] == 0x03 and reply[3]:
            raise Rejected(f"keyboard rejected key {reply[2]} (reply {reply[:4].hex(' ')})")
        time.sleep(0.02)

    def _send_chunks(self, cmd, buf, total):
        """buf as 28-byte chunks [cmd, len, chunk number, data]; the last chunk's len covers
        only up to total, but (like the vendor app) all 28 bytes are sent."""
        for n in range((total + 27) // 28):
            self._send(cmd, n, buf[n * 28:(n + 1) * 28], length=min(28, total - n * 28))

    def light(self, effect, fast=False):
        self._send(0x05, 0, effect.payload())

    def key_colors(self, table, brightness=5):
        self._send_chunks(0x14, table, len(table))
        self.light(lighting.Effect("custom", (0, 0, 0), brightness, 0))

    def write_layer(self, table, fn_layer=False):
        if fn_layer:
            self._no("the Fn layer")
        # one key at a time; an all-zero entry means "default", which the dongle takes as
        # the key's own usage (as the vendor app does to restore a key)
        for slot, usage in KEYS.values():
            entry = table[slot * 4:slot * 4 + 4]
            if any(entry):
                self._send(0x03, slot, entry)
            elif usage is not None:          # Fn has no usage to restore
                self._send(0x03, slot, bytes([2, 0, usage, 0]))

    def write_macros(self, blob):
        # same blob as the cable; size = used bytes plus one spare chunk, padded to whole
        # 28-byte chunks with aa 55 at the very end
        used = len(blob[:-2].rstrip(b"\0"))
        total = used + 28
        buf = bytearray((total + 27) // 28 * 28)
        buf[:used] = blob[:used]
        buf[-2:] = b"\xaa\x55"
        self._send_chunks(0x09, bytes(buf), total)

    def settings(self, sleep, debounce):
        self._send(0x07, 0, settings_block(sleep, debounce))

    def reset(self, factory=False):
        # 1F clears the remaps; 0F also clears the lighting and the settings
        self._send(0x0F if factory else 0x1F, 0, b"")

    def battery(self):
        while self.dev.read(33, 0.05):
            pass
        self.dev.write(bytes([0x20, 0x01]).ljust(32, b"\0"))
        deadline = time.time() + 1.5
        while time.time() < deadline:
            r = self.dev.read(33, 0.3)
            if r and r[0] == 0x20 and r[1] == 0x01:
                if not 0 < r[3] <= 100:
                    raise Rejected("keyboard did not report a level; is it switched to 2.4G?")
                return r[3]
        raise Rejected("no answer from the dongle; is the keyboard on and in 2.4G mode?")


def present() -> dict[str, str]:
    """{"wired": path, "wireless": path} for the transports that are plugged in."""
    found = {}
    if path := hidraw.find(*WIRED, CMD_IFACE):
        found["wired"] = path
    if path := hidraw.find(*DONGLE, CMD_IFACE):
        found["wireless"] = path
    return found


def open_keyboard(prefer: str = "auto", lock_timeout: float = 15.0) -> Keyboard:
    """The keyboard over the cable if it is enumerated (as the hardware itself prefers),
    else over the dongle; prefer="wireless" or "wired" picks one when both are present,
    e.g. "wireless" when the cable is only charging. Waits up to lock_timeout for the lock."""
    found = present()
    order = ["wireless", "wired"] if prefer == "wireless" else ["wired", "wireless"]
    if prefer in ("wired", "wireless") and prefer in found:
        order = [prefer]
    for transport in order:
        if transport in found:
            fd = _lock(lock_timeout)
            try:
                cls = Wired if transport == "wired" else Dongle
                return cls(found[transport], fd)
            except Exception:
                os.close(fd)
                raise
    raise NotFound("keyboard not found: plug in the cable or the 2.4G dongle")
