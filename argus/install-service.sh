#!/usr/bin/env bash
# argus/install-service.sh - run the ARGUS core server (`argus serve`) as a systemd USER service on Linux.
#
# The server is what the Desktop app (and, from phase 3, `argus --attach` in the TUI) connect to. It binds
# loopback only (127.0.0.1:9119); reach it from elsewhere through an SSH tunnel or with an auth provider set
# (Hermes refuses a public bind without one). Re-run after moving the checkout. --remove takes it out again.
set -euo pipefail
unit_dir="$HOME/.config/systemd/user"
unit="$unit_dir/argus.service"
launcher="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)/bin/argus"
port="${ARGUS_PORT:-9119}"

if [ "${1:-}" = "--remove" ]; then
    systemctl --user disable --now argus.service 2>/dev/null || true
    rm -f "$unit"; systemctl --user daemon-reload
    echo "argus: service removed"; exit 0
fi

mkdir -p "$unit_dir"
cat > "$unit" <<EOF
[Unit]
Description=ARGUS core server (argus serve on 127.0.0.1:$port)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=ARGUS_HOME=%h/.argus
ExecStart=$launcher serve --host 127.0.0.1 --port $port
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now argus.service
echo "argus: service installed - systemctl --user status argus ; journalctl --user -u argus -f"
