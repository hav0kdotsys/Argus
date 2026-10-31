#!/usr/bin/env bash
# argus/sync-mira-skills.sh - copy MIRA's skills from debhvk into $ARGUS_HOME/mira-skills (read-only for ARGUS).
#
# MIRA's skills are agentskills.io SKILL.md folders, which Hermes reads natively; config.yaml lists this folder
# under skills.external_dirs, so ARGUS uses them and writes any skill it creates into $ARGUS_HOME/skills instead.
# A mirror, not a merge: a skill deleted on debhvk disappears here on the next sync. Needs the `debhvk` ssh alias.
#   argus/sync-mira-skills.sh            (or let a timer run it)
set -euo pipefail
home="${ARGUS_HOME:-$HOME/.argus}"
src="${MIRA_SKILLS_SRC:-debhvk:/srv/authentik-prod/production/mira/skills/}"
mkdir -p "$home/mira-skills"
rsync -a --delete --exclude '.*' --exclude '*.bak*' "$src" "$home/mira-skills/"
n=$(find "$home/mira-skills" -name SKILL.md | wc -l)
printf 'argus: %s MIRA skills in %s\n' "$n" "$home/mira-skills"
