"""Linux hidraw access: find the keyboard's nodes in sysfs and exchange reports.

Feature reports go through the HIDIOC[SG]FEATURE ioctls, output reports through write(),
input reports through read(). Report ID 0 is always prepended, as the kernel expects for
these unnumbered reports.
"""
from __future__ import annotations

import fcntl
import os
import select
from dataclasses import dataclass
from pathlib import Path

SYSFS = Path("/sys/class/hidraw")


def _ioc(nr: int, size: int) -> int:
    # _IOC(_IOC_READ | _IOC_WRITE, 'H', nr, size)
    return (3 << 30) | (size << 16) | (ord("H") << 8) | nr


@dataclass(frozen=True)
class Node:
    path: str             # /dev/hidrawN
    vendor: int
    product: int
    interface: int        # USB bInterfaceNumber
    name: str = ""        # the USB device's product string ("" if it has none)
    usage_page: int | None = None   # the report descriptor's first usage page


def usage_page(descriptor: bytes) -> int | None:
    """The usage page the report descriptor opens with (its first Usage Page item, e.g.
    06 60 ff = 0xFF60), or None if the first item is something else."""
    if not descriptor:
        return None
    size = {0: 0, 1: 1, 2: 2, 3: 4}[descriptor[0] & 0x03]
    if descriptor[0] & 0xFC != 0x04 or len(descriptor) < 1 + size:
        return None
    return int.from_bytes(descriptor[1:1 + size], "little")


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def nodes() -> list[Node]:
    """Every hidraw node with its USB ids, interface number, product string and usage
    page."""
    found = []
    for entry in sorted(SYSFS.glob("hidraw*")):
        try:
            uevent = (entry / "device/uevent").read_text()
            hid_id = next(l.split("=", 1)[1] for l in uevent.splitlines()
                          if l.startswith("HID_ID="))
            _, vendor, product = (int(x, 16) for x in hid_id.split(":"))
            # the HID device sits under its USB interface, which knows its number
            interface = int((entry / "device/../bInterfaceNumber").read_text(), 16)
        except (OSError, StopIteration, ValueError):
            continue
        # the USB device (above the interface) carries the product string
        name = _read(entry / "device/../../product")
        try:
            page = usage_page((entry / "device/report_descriptor").read_bytes())
        except OSError:
            page = None
        found.append(Node(f"/dev/{entry.name}", vendor, product, interface, name, page))
    return found


def find(vendor: int, product: int, interface: int, name: str | None = None,
         page: int | None = None) -> str | None:
    """The first node with these ids and interface; name and page, when given, must also
    match its product string and usage page."""
    for node in nodes():
        if (node.vendor, node.product, node.interface) != (vendor, product, interface):
            continue
        if name is not None and node.name != name:
            continue
        if page is not None and node.usage_page != page:
            continue
        return node.path
    return None


class Device:
    """An open hidraw node."""

    def __init__(self, path: str):
        self.path = path
        self.fd = os.open(path, os.O_RDWR)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def set_feature(self, payload: bytes, size: int = 64) -> None:
        buf = bytes([0]) + bytes(payload).ljust(size, b"\0")
        fcntl.ioctl(self.fd, _ioc(0x06, len(buf)), buf)

    def get_feature(self, size: int = 64) -> bytes:
        """The keyboard's current feature report, without the report-ID byte."""
        buf = bytearray(size + 1)
        fcntl.ioctl(self.fd, _ioc(0x07, len(buf)), buf)
        return bytes(buf[1:])

    def write(self, payload: bytes) -> None:
        os.write(self.fd, bytes([0]) + bytes(payload))

    def read(self, size: int, timeout: float) -> bytes | None:
        """One input report, or None if none arrives within timeout seconds."""
        if not select.select([self.fd], [], [], timeout)[0]:
            return None
        return os.read(self.fd, size)
