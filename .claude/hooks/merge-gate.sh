#!/bin/bash
# PreToolUse shim for pr-security-gate.py — makes the merge gate reach cloud and
# mobile sessions.
#
# WHY A SHIM AND NOT A DIRECT `python ...` COMMAND
#   The committed settings.json runs on every machine this repo is opened on.
#   Windows has `python`; the cloud/mobile sandbox has `python3` and may not have
#   `python` at all. A hardcoded interpreter works in exactly one of those and
#   fails silently in the other — and a security gate that silently does not run
#   is the failure this whole hook exists to prevent.
#
# WHY THE GATE IS COMMITTED HERE AT ALL
#   A gate kept in ~/.claude/ is machine-local: cloud and mobile sandboxes never
#   set it up, so `gh pr merge` there would be ungated entirely. On a PRIVATE
#   repo on the free plan GitHub cannot enforce required status checks either —
#   nothing would stand between a red or missing CI result and a merge.
#
# NO INTERPRETER = NOT GATED, AND IT SAYS SO
#   If neither interpreter exists we exit 0 rather than blocking. A hook that
#   fails every Bash call gets uninstalled, and uninstalled is worse than
#   ungated-with-a-warning. The warning is printed only for commands that
#   actually look like a merge, so it cannot become background noise. CI and
#   personal-data's auto-merge bot remain as server-side backstops.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$DIR/pr-security-gate.py"

# Hook input arrives on stdin and is consumed once, so buffer it before deciding.
input=$(cat)

# `command -v` is NOT sufficient on Windows. It ships a python3.exe App Execution
# Alias that is on PATH, resolves, and then refuses to run:
#   "Python was not found; run without arguments to install from the Microsoft
#    Store" — exit 49.
# Selecting on presence alone picked that alias and made every Bash call exit
# non-zero. So each candidate is EXECUTED before being chosen.
PY=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 \
     && "$candidate" -c "" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ] || [ ! -f "$GATE" ]; then
  case "$input" in
    *"gh pr merge"*)
      echo "[merge-gate] not enforced here: ${PY:+missing $GATE}${PY:-no python interpreter found}." >&2
      echo "[merge-gate] Read the PR's checks yourself before merging. CI still runs server-side." >&2
      ;;
  esac
  exit 0
fi

printf '%s' "$input" | "$PY" "$GATE"
exit $?
