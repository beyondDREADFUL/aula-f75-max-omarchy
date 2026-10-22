#!/bin/bash
# Installs the controller, hooks, udev rule, systemd unit and bar plugin.
# Run as your normal user; sudo is used only for the udev rule and unit.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
[ "$(id -u)" -ne 0 ] || { echo "run as your normal user, not root" >&2; exit 1; }
user=$(id -un); group=$(id -gn)

install -Dm755 "$here/bin/omarchy-keyboard-accent" "$HOME/.local/bin/omarchy-keyboard-accent"
install -Dm755 "$here/bin/omarchy-keyboard-accent-queue" "$HOME/.local/bin/omarchy-keyboard-accent-queue"
for d in theme-set.d post-boot.d; do
    install -Dm755 "$here/hooks/keyboard-accent.sh" "$HOME/.config/omarchy/hooks/$d/keyboard-accent.sh"
done
cfg="$HOME/.config/omarchy/keyboard-accent/config.toml"
[ -e "$cfg" ] || install -Dm644 "$here/config.example.toml" "$cfg"
plug="$HOME/.config/omarchy/plugins/beyond.keyboard-accent"
mkdir -p "$plug" && cp -r "$here/plugin/." "$plug/" && chmod +x "$plug/bin/keyboard-accent"

getent group aula >/dev/null || sudo groupadd --system aula
id -nG "$user" | grep -qw aula || sudo usermod -aG aula "$user"
sudo install -Dm644 "$here/system/65-aula-f75-max.rules" /etc/udev/rules.d/65-aula-f75-max.rules
sed -e "s#@HOME@#$HOME#g" -e "s#@USER@#$user#" -e "s#@GROUP@#$group#" \
    "$here/system/aula-keyboard-accent.service.in" | sudo tee /etc/systemd/system/aula-keyboard-accent.service >/dev/null
sudo systemctl daemon-reload
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hidraw --action=change

echo "Done. Log out and back in once so the 'aula' group applies, then run:"
echo "  omarchy-keyboard-accent apply"
echo "Enable the bar widget with: omarchy plugin enable beyond.keyboard-accent && omarchy restart shell"
