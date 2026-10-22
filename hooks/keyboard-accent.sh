#!/bin/bash
# Queue the AULA F75 Max sync asynchronously so theme switching is not
# blocked by HID settle times.  The queue script debounces bursts and
# applies the current theme after a short quiet period.
"$HOME/.local/bin/omarchy-keyboard-accent-queue" || true
