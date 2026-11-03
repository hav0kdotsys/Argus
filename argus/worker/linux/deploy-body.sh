#!/bin/sh
# Her body's Linux build, from ~/mira-body, into ~/.local/share/mira-body, and its user unit. As HavoK (no sudo). It
# doesn't start her: ARGUS's worker does, when argus.yaml says body.enabled. Run it again after each new build.
set -eu
src="${MIRA_BODY_SRC:-$HOME/mira-body}"
dest="$HOME/.local/share/mira-body"
here="$(cd "$(dirname "$0")" && pwd)"
"$HOME/.dotnet/dotnet" build "$src/cross" -c Release -o "$src/out/cross" -nologo -v q
mkdir -p "$dest" "$HOME/.config/systemd/user"
cp -a "$src/out/cross/." "$dest/"
cp "$here/mira-body.service" "$HOME/.config/systemd/user/mira-body.service"
systemctl --user daemon-reload
if systemctl --user is-active --quiet mira-body.service; then systemctl --user restart mira-body.service; fi
echo "her body is at $dest; ARGUS's worker runs it when body.enabled is true"
