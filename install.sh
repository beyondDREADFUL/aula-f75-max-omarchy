#!/bin/bash
# Installs f75ctl, the theme hooks, udev rule, systemd unit and bar plugin. Also moves an
# install made under the old names (omarchy-keyboard-accent, beyond.keyboard-accent).
# Run as your normal user; sudo is used only for the udev rule and unit.
# Pass --dry-run to print every command that changes something instead of running it.
set -eu
dry=false
[ "${1:-}" = "--dry-run" ] && dry=true
here=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" -ne 0 ] || { echo "run as your normal user, not root" >&2; exit 1; }
user=$(id -un); group=$(id -gn)
# the unit runs as this user with this home: take it from the user database, not $HOME,
# and only accept characters that are safe in a unit file and a sed replacement
home=$(getent passwd "$user" | cut -d: -f6)
case "$home" in
/*) ;;
*) echo "could not find the home directory of $user" >&2; exit 1 ;;
esac
case "$home" in
*[!A-Za-z0-9._/-]*) echo "home directory '$home' has characters the systemd unit can't take safely (allowed: A-Z a-z 0-9 . _ / -)" >&2; exit 1 ;;
esac
[ "$HOME" = "$home" ] || { echo "\$HOME ($HOME) is not your home directory ($home); run from a normal login shell" >&2; exit 1; }

run() { if $dry; then echo "+ $*"; else "$@"; fi; }
root() {
    if $dry; then echo "+ sudo $*"; else sudo "$@"; fi
}
# python 3.11+ is required (tomllib); stop before installing anything that can't run
/usr/bin/python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null \
    || { echo "python 3.11 or newer is required: sudo pacman -S python" >&2; exit 1; }
command -v jq >/dev/null || echo "warning: jq not found; the bar widget needs it: sudo pacman -S jq" >&2

# ---- move an install made under the old names ----
# config (theme colours) and state (pin, effect, brightness) keep their contents
for kind in .config .local/state; do
    old="$HOME/$kind/omarchy/keyboard-accent" new="$HOME/$kind/omarchy/aula-f75"
    if [ -d "$old" ] && [ ! -e "$new" ]; then
        run mv "$old" "$new"
        $dry || echo "moved ${old/#$HOME/\~} to ${new/#$HOME/\~}"
    fi
done
[ -e "$HOME/.local/state/omarchy/aula-f75/keyboard-accent.log" ] \
    && run mv "$HOME/.local/state/omarchy/aula-f75/keyboard-accent.log" "$HOME/.local/state/omarchy/aula-f75/theme.log"
run rm -f "$HOME/.local/bin/omarchy-keyboard-accent" "$HOME/.local/bin/omarchy-keyboard-accent-queue"
run rm -rf "$HOME/.local/share/omarchy-keyboard-accent"
run rm -f "$HOME"/.config/omarchy/hooks/{theme-set.d,post-boot.d}/keyboard-accent.sh
# the widget keeps its place in the bar: swap its id in the layout, then drop the old folder
shell_json="$HOME/.config/omarchy/shell.json"
if grep -q 'beyond\.keyboard-accent' "$shell_json" 2>/dev/null; then
    run sed -i 's/beyond\.keyboard-accent/beyond.aula-f75/g' "$shell_json"
    $dry || echo "the bar widget is now beyond.aula-f75, in the same place"
fi
old_plug="$HOME/.config/omarchy/plugins/beyond.keyboard-accent"
if [ -d "$old_plug" ] && [ "$(cd "$old_plug" && pwd -P)" != "$(cd "$here" && pwd -P)" ]; then
    run rm -rf "$old_plug"
fi

# ---- install ----
# the libraries the commands import; replaced as a whole so removed modules don't linger
lib="$HOME/.local/share/aula-f75"
run rm -rf "$lib/aula_f75" "$lib/theme"
run mkdir -p "$lib"
run cp -r "$here/aula_f75" "$here/theme" "$lib/"
run find "$lib" -name __pycache__ -prune -exec rm -rf {} +
run install -Dm755 "$here/bin/f75ctl" "$HOME/.local/bin/f75ctl"
run install -Dm755 "$here/bin/f75ctl-theme-queue" "$HOME/.local/bin/f75ctl-theme-queue"
for d in theme-set.d post-boot.d; do
    run install -Dm755 "$here/hooks/aula-f75.sh" "$HOME/.config/omarchy/hooks/$d/aula-f75.sh"
done
cfg="$HOME/.config/omarchy/aula-f75/config.toml"
[ -e "$cfg" ] || run install -Dm644 "$here/config.example.toml" "$cfg"
plug="$HOME/.config/omarchy/plugins/beyond.aula-f75"
if [ "$(cd "$plug" 2>/dev/null && pwd -P)" != "$(cd "$here" && pwd -P)" ]; then
    run mkdir -p "$plug/bin"
    run cp "$here/manifest.json" "$here/AulaF75.qml" "$plug/"
    run cp "$here/bin/aula-f75" "$plug/bin/"
fi
run chmod +x "$plug/bin/aula-f75"
# state and the keyboard lock; the service may write only here, so it must exist
run mkdir -p -m 700 "$HOME/.local/state/omarchy/aula-f75"

getent group aula >/dev/null || root groupadd --system aula
id -nG "$user" | grep -qw aula || root usermod -aG aula "$user"
root install -Dm644 "$here/system/65-aula-f75-max.rules" /etc/udev/rules.d/65-aula-f75-max.rules
unit=$(sed -e "s#@HOME@#$home#g" -e "s#@USER@#$user#" -e "s#@GROUP@#$group#" \
    "$here/system/aula-f75.service.in")
if $dry; then
    echo "+ write /etc/systemd/system/aula-f75.service:"
    printf '%s\n' "$unit" | sed 's/^/    /'
else
    printf '%s\n' "$unit" | sudo tee /etc/systemd/system/aula-f75.service >/dev/null
fi
[ -e /etc/systemd/system/aula-keyboard-accent.service ] \
    && root rm -f /etc/systemd/system/aula-keyboard-accent.service
root systemctl daemon-reload
root udevadm control --reload
root udevadm trigger --subsystem-match=hidraw --action=change

# ---- bar widget ----
# Enable it once; a shell restart shows it, so only a fresh enable triggers one.
if command -v omarchy >/dev/null && command -v jq >/dev/null; then
    enabled=$(omarchy plugin list --json 2>/dev/null \
        | jq -r '.[] | select(.id == "beyond.aula-f75") | .enabled' || true)
    if [ "$enabled" != "true" ]; then
        run omarchy plugin enable beyond.aula-f75
        run omarchy restart shell
    fi
else
    echo "Bar widget not enabled: install Omarchy's omarchy command and jq, then re-run ./install.sh"
fi

echo "Done. Log out and back in once so the 'aula' group applies, then run:"
echo "  f75ctl theme apply"

# optional features: say what is missing, install nothing
missing=()
command -v cava >/dev/null || missing+=("  music visualiser needs cava:   sudo pacman -S cava")
/usr/bin/python3 -c 'import PIL' 2>/dev/null || missing+=("  LCD images (f75ctl gif) need pillow:   sudo pacman -S python-pillow")
if [ ${#missing[@]} -gt 0 ]; then
    echo
    echo "Optional, not installed:"
    printf '%s\n' "${missing[@]}"
fi
