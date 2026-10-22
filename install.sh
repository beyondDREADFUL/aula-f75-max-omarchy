#!/bin/bash
# Installs the controller, hooks, udev rule, systemd unit and bar plugin.
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
for tool in python3 jq; do
    command -v "$tool" >/dev/null || echo "warning: $tool not found (the controller needs python3, the widget needs jq)" >&2
done

install -Dm755 "$here/bin/omarchy-keyboard-accent" "$HOME/.local/bin/omarchy-keyboard-accent"
install -Dm755 "$here/bin/omarchy-keyboard-accent-queue" "$HOME/.local/bin/omarchy-keyboard-accent-queue"
for d in theme-set.d post-boot.d; do
    install -Dm755 "$here/hooks/keyboard-accent.sh" "$HOME/.config/omarchy/hooks/$d/keyboard-accent.sh"
done
cfg="$HOME/.config/omarchy/keyboard-accent/config.toml"
[ -e "$cfg" ] || install -Dm644 "$here/config.example.toml" "$cfg"
plug="$HOME/.config/omarchy/plugins/beyond.keyboard-accent"
mkdir -p "$plug" && cp -r "$here/plugin/." "$plug/" && chmod +x "$plug/bin/keyboard-accent"

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
