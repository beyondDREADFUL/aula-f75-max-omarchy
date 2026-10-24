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

# Stop the music visualiser if the widget started it.
pid=$(cat "$HOME/.local/state/omarchy/aula-f75/music.pid" 2>/dev/null || true)
[ -n "$pid" ] && grep -q f75ctl "/proc/$pid/cmdline" 2>/dev/null && run kill -TERM "$pid"

run rm -f "$HOME/.local/bin/f75ctl" "$HOME/.local/bin/f75ctl-theme-queue"
run rm -rf "$HOME/.local/share/aula-f75"
run rm -f "$HOME"/.config/omarchy/hooks/{theme-set.d,post-boot.d}/aula-f75.sh
# Let Omarchy drop the widget from the bar layout, then clean up the folder.
if command -v omarchy >/dev/null; then
    run omarchy plugin remove beyond.aula-f75 --yes || true
fi
run rm -rf "$HOME/.config/omarchy/plugins/beyond.aula-f75"
# The bar group's member list can still name the widget.
shell_json="$HOME/.config/omarchy/shell.json"
if grep -q 'beyond\.aula-f75' "$shell_json" 2>/dev/null; then
    run sed -i -e 's/, beyond\.aula-f75//' -e 's/beyond\.aula-f75, //' "$shell_json"
fi

root rm -f /etc/udev/rules.d/65-aula-f75-max.rules /etc/systemd/system/aula-f75.service
root systemctl daemon-reload
root udevadm control --reload

if $purge; then
    run rm -rf "$HOME"/.config/omarchy/plugins/.beyond.aula-f75.bak.*
    run rm -rf "$HOME/.config/omarchy/aula-f75" "$HOME/.local/state/omarchy/aula-f75"
else
    echo "Kept your config (~/.config/omarchy/aula-f75) and state. Use --purge to remove them too."
fi

echo "Removed. Restart the shell to drop the bar widget: omarchy restart shell"
echo "The 'aula' group was left in place; remove it with: sudo groupdel aula"
}
main "$@"
exit $?
