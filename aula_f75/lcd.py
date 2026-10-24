"""The 128x128 LCD: clock and images. Cable only (the vendor app has neither over 2.4 GHz)."""
from __future__ import annotations

import datetime

SIZE = 128
CHUNK = 4096
MAX_FRAMES = 255


def clock_payload(t: datetime.datetime | None = None) -> bytes:
    """0x28 payload: 00 01 5a YY MM DD hh mm ss 00 weekday (Sunday = 0)."""
    t = t or datetime.datetime.now()
    return bytes([0, 1, 0x5A, t.year % 100, t.month, t.day, t.hour, t.minute, t.second, 0,
                  t.isoweekday() % 7])


def image_blob(path: str) -> tuple[bytes, int]:
    """Load a GIF/PNG/JPG (needs pillow) -> (upload blob, frame count). The blob is a
    256-byte header [frames, delay per frame in 2 ms units, ff pad] plus 128x128 RGB565
    little-endian frames, padded with ff to whole 4096-byte chunks."""
    from PIL import Image, ImageOps, ImageSequence
    frames, delays = [], []
    for f in ImageSequence.Iterator(Image.open(path)):
        frames.append(ImageOps.fit(f.convert("RGB"), (SIZE, SIZE)))
        # checked: 250 ms frames play at 250 ms, so the longest frame is 510 ms
        delays.append(max(1, min(255, f.info.get("duration", 100) // 2)))
        if len(frames) == MAX_FRAMES:
            break
    head = bytearray(b"\xff" * 256)
    head[0] = len(frames)
    head[1:1 + len(delays)] = bytes(delays)
    body = bytearray()
    for f in frames:
        px = f.tobytes()
        for k in range(0, len(px), 3):
            r, g, b = px[k], px[k + 1], px[k + 2]
            body += (((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)).to_bytes(2, "little")
    blob = bytes(head + body)
    return blob + b"\xff" * (-len(blob) % CHUNK), len(frames)
