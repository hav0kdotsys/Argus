#!/usr/bin/env bash
# argus/install.sh - put the ARGUS overlay into $ARGUS_HOME (default ~/.argus). Linux, macOS, WSL.
#
# Idempotent and cheap, so the `argus` launcher runs it on every start:
#   - skins/*.yaml and plugins/** are LINKED (a `git pull` of ARGUS updates them in place),
#   - config.yaml is SEEDED only when there is none (yours is never overwritten),
#   - the folder for MIRA's skills exists (filled by argus/sync-mira-skills.sh).
# `--quiet` prints nothing unless something was installed for the first time.
set -euo pipefail

quiet=0
[ "${1:-}" = "--quiet" ] && quiet=1
say() { [ "$quiet" = 1 ] || printf '%s\n' "$*"; }

argus_dir="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
home="${ARGUS_HOME:-$HOME/.argus}"
mkdir -p "$home/skins" "$home/plugins" "$home/mira-skills"

link() {   # link <source> <target>: a symlink, replaced only when it points somewhere else
    local src="$1" dst="$2"
    if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then return; fi
    if [ -e "$dst" ] && [ ! -L "$dst" ]; then
        say "argus: leaving $dst alone (a real file, not ARGUS's link)"
        return
    fi
    ln -sfn "$src" "$dst"
    printf 'argus: linked %s\n' "${dst#$home/}"
}

for f in "$argus_dir"/skins/*.yaml; do
    [ -e "$f" ] && link "$f" "$home/skins/$(basename "$f")"
done

# Plugins keep Hermes' own layout: plugins/<name>/ (general) and plugins/model-providers/<name>/.
if [ -d "$argus_dir/plugins" ]; then
    for p in "$argus_dir"/plugins/*/; do
        [ -d "$p" ] || continue
        name="$(basename "$p")"
        if [ "$name" = "model-providers" ]; then
            mkdir -p "$home/plugins/model-providers"
            for mp in "$p"*/; do [ -d "$mp" ] && link "${mp%/}" "$home/plugins/model-providers/$(basename "$mp")"; done
        else
            link "${p%/}" "$home/plugins/$name"
        fi
    done
fi

if [ ! -e "$home/config.yaml" ]; then
    cp "$argus_dir/config/config.yaml" "$home/config.yaml"
    printf 'argus: wrote a starting %s/config.yaml (yours from now on)\n' "$home"
fi
if [ ! -e "$home/.env" ]; then
    ( umask 077; : > "$home/.env" )
    printf 'argus: created %s/.env for provider keys (mode 600)\n' "$home"
fi
