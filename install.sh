#!/bin/bash
# Installs the controller, f75ctl, hooks, udev rule, systemd unit and bar plugin.
# Run as your normal user; sudo is used only for the udev rule and unit.
# Pass --dry-run to print the root commands instead of running them.
set -eu
dry=false
[ "${1:-}" = "--dry-run" ] && dry=true
here=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" -ne 0 ] || { echo "run as your normal user, not root" >&2; exit 1; }
user=$(id -un); group=$(id -gn)

root() {
    if $dry; then echo "+ sudo $*"; else sudo "$@"; fi
}
# python 3.11+ is required (tomllib); stop before installing anything that can't run
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null \
    || { echo "python 3.11 or newer is required: sudo pacman -S python" >&2; exit 1; }
command -v jq >/dev/null || echo "warning: jq not found; the bar widget needs it: sudo pacman -S jq" >&2

# the libraries the commands import; replaced as a whole so removed modules don't linger
lib="$HOME/.local/share/omarchy-keyboard-accent"
rm -rf "$lib/aula_f75" "$lib/accent"
mkdir -p "$lib"
cp -r "$here/aula_f75" "$here/accent" "$lib/"
find "$lib" -name __pycache__ -prune -exec rm -rf {} +
install -Dm755 "$here/bin/omarchy-keyboard-accent" "$HOME/.local/bin/omarchy-keyboard-accent"
install -Dm755 "$here/bin/f75ctl" "$HOME/.local/bin/f75ctl"
install -Dm755 "$here/bin/omarchy-keyboard-accent-queue" "$HOME/.local/bin/omarchy-keyboard-accent-queue"
for d in theme-set.d post-boot.d; do
    install -Dm755 "$here/hooks/keyboard-accent.sh" "$HOME/.config/omarchy/hooks/$d/keyboard-accent.sh"
done
cfg="$HOME/.config/omarchy/keyboard-accent/config.toml"
[ -e "$cfg" ] || install -Dm644 "$here/config.example.toml" "$cfg"
plug="$HOME/.config/omarchy/plugins/beyond.keyboard-accent"
if [ "$(cd "$plug" 2>/dev/null && pwd -P)" != "$(cd "$here" && pwd -P)" ]; then
    mkdir -p "$plug/bin"
    cp "$here/manifest.json" "$here/KeyboardAccent.qml" "$plug/"
    cp "$here/bin/keyboard-accent" "$plug/bin/"
fi
chmod +x "$plug/bin/keyboard-accent"

getent group aula >/dev/null || root groupadd --system aula
id -nG "$user" | grep -qw aula || root usermod -aG aula "$user"
root install -Dm644 "$here/system/65-aula-f75-max.rules" /etc/udev/rules.d/65-aula-f75-max.rules
unit=$(sed -e "s#@HOME@#$HOME#g" -e "s#@USER@#$user#" -e "s#@GROUP@#$group#" \
    "$here/system/aula-keyboard-accent.service.in")
if $dry; then
    echo "+ write /etc/systemd/system/aula-keyboard-accent.service:"
    printf '%s\n' "$unit" | sed 's/^/    /'
else
    printf '%s\n' "$unit" | sudo tee /etc/systemd/system/aula-keyboard-accent.service >/dev/null
fi
root systemctl daemon-reload
root udevadm control --reload
root udevadm trigger --subsystem-match=hidraw --action=change

echo "Done. Log out and back in once so the 'aula' group applies, then run:"
echo "  omarchy-keyboard-accent apply"
echo "Enable the bar widget with: omarchy plugin enable beyond.keyboard-accent && omarchy restart shell"

# optional features: say what is missing, install nothing
missing=()
command -v cava >/dev/null || missing+=("  music visualiser needs cava:   sudo pacman -S cava")
python3 -c 'import PIL' 2>/dev/null || missing+=("  LCD images (f75ctl gif) need pillow:   sudo pacman -S python-pillow")
if [ ${#missing[@]} -gt 0 ]; then
    echo
    echo "Optional, not installed:"
    printf '%s\n' "${missing[@]}"
fi
