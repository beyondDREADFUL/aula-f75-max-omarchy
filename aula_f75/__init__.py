"""Control library for the AULA F75 Max keyboard (wired 0c45:800a, 2.4 GHz dongle 05ac:024f).

Pure standard library, Linux hidraw only. Protocol facts are in docs/HANDBOOK.md; every
command here was checked on the keyboard.

    from aula_f75 import open_keyboard, lighting
    with open_keyboard() as kb:
        kb.light(lighting.Effect("static", (255, 72, 32)))
"""
from .device import Keyboard, NotFound, Rejected, open_keyboard

__all__ = ["Keyboard", "NotFound", "Rejected", "open_keyboard"]
