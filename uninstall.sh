#!/bin/bash
# Removes everything install.sh installed. Your config and saved state are kept
# unless you pass --purge. The 'aula' group is left in place.
# Pass --dry-run to print what would be removed without removing it.
set -eu
# Everything is inside main so bash reads the whole script before it runs; this
# matters when the repo is itself the installed plugin folder and gets deleted.
main() {
dry=false; purge=false
for arg in "$@"; do
    case "$arg" in
    --dry-run) dry=true ;;
    --purge) purge=true ;;
    *) echo "usage: uninstall.sh [--dry-run] [--purge]" >&2; exit 2 ;;
    esac
done
[ "$(id -u)" -ne 0 ] || { echo "run as your normal user, not root" >&2; exit 1; }

run() { if $dry; then echo "+ $*"; else "$@"; fi; }
root() { if $dry; then echo "+ sudo $*"; else sudo "$@"; fi; }

run rm -f "$HOME/.local/bin/omarchy-keyboard-accent" "$HOME/.local/bin/omarchy-keyboard-accent-queue"
run rm -f "$HOME/.config/omarchy/hooks/theme-set.d/keyboard-accent.sh" \
          "$HOME/.config/omarchy/hooks/post-boot.d/keyboard-accent.sh"
# Let Omarchy drop the widget from the bar layout, then clean up the folder.
if command -v omarchy >/dev/null; then
    run omarchy plugin remove beyond.keyboard-accent --yes || true
fi
run rm -rf "$HOME/.config/omarchy/plugins/beyond.keyboard-accent"
# The bar group's member list can still name the widget.
shell_json="$HOME/.config/omarchy/shell.json"
if grep -q 'beyond\.keyboard-accent' "$shell_json" 2>/dev/null; then
    run sed -i -e 's/, beyond\.keyboard-accent//' -e 's/beyond\.keyboard-accent, //' "$shell_json"
fi

root rm -f /etc/udev/rules.d/65-aula-f75-max.rules /etc/systemd/system/aula-keyboard-accent.service
root systemctl daemon-reload
root udevadm control --reload

if $purge; then
    run rm -rf "$HOME"/.config/omarchy/plugins/.beyond.keyboard-accent.bak.*
    run rm -rf "$HOME/.config/omarchy/keyboard-accent" "$HOME/.local/state/omarchy/keyboard-accent"
else
    echo "Kept your config (~/.config/omarchy/keyboard-accent) and state. Use --purge to remove them too."
fi

echo "Removed. Restart the shell to drop the bar widget: omarchy restart shell"
echo "The 'aula' group was left in place; remove it with: sudo groupdel aula"
}
main "$@"
exit $?
