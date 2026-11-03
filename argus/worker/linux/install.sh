#!/bin/sh
# ARGUS's worker as root on this machine (laphvk or debhvk). Run with sudo from this folder:
#   sudo ./install.sh laphvk     (her body on: the worker runs it in HavoK's session, the old QML body stands down)
#   sudo ./install.sh debhvk     (headless: no body, no companion)
# It installs a root-owned copy of the worker, /etc/argus/argus.yaml (kept if it's already there), the system unit, and
# lets HavoK's own systemd manager linger so her units can be started from root. Rollback: set body.enabled: false in
# /etc/argus/argus.yaml (the old body comes back within 30 s), or `systemctl disable --now argus` to stop ARGUS's worker.
set -eu
[ "$(id -u)" -eq 0 ] || { echo "run it with sudo"; exit 1; }
host="${1:?which machine: laphvk or debhvk}"
user="${SUDO_USER:-havok}"
here="$(cd "$(dirname "$0")" && pwd)"
install -d -m 0755 /usr/local/lib/argus /etc/argus
install -m 0644 "$here/../argus_worker.py" /usr/local/lib/argus/argus_worker.py
if [ ! -e /etc/argus/argus.yaml ]; then
    install -m 0644 "$here/../argus.$host.yaml" /etc/argus/argus.yaml
    sed -i "s/^user: .*/user: $user/" /etc/argus/argus.yaml
fi
/usr/bin/python3 /usr/local/lib/argus/argus_worker.py check --config /etc/argus/argus.yaml
install -m 0644 "$here/argus.service" /etc/systemd/system/argus.service
loginctl enable-linger "$user"
# The old QML body no longer starts on its own at login: the worker starts it only while body.enabled is false.
if [ "$host" = laphvk ]; then systemctl --user -M "$user@" disable mira-pet.service 2>/dev/null || true; fi
systemctl daemon-reload
systemctl enable --now argus.service
sleep 3
systemctl --no-pager --lines 5 status argus.service || true
