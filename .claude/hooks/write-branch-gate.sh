#!/bin/bash
# PreToolUse (Bash) hook — refuse a push into `personal-data` on a branch the
# auto-merge bot will never look at.
#
# WHAT IT PREVENTS
#   personal-data's auto-merge.yml triggers on `push` to `write/**` (and
#   `sync/auto`). It is the thing that runs the integrity checks and merges.
#   A push to any OTHER branch name is not rejected anywhere: it succeeds,
#   any other workflow that runs on it can pass (e.g. one that triggers on
#   `"**"`), and the work then sits on a branch nobody merges. Nothing errors.
#   The only symptom is that `main` never moves.
#
#   That happened once (2026-08-27). The Claude Code Remote harness pins each cloud
#   session to one generated branch — `claude/<slug>-<session-id>` — and applies
#   it to EVERY attached repo, because it is a platform default written before
#   any repo's CLAUDE.md is read. A full /triage + /distill ran, five commits
#   landed on a `claude/...` branch, every gate went green, and nothing merged. Recovering it needed a human to notice `main` was stale.
#
# WHY A HOOK AND NOT AN INSTRUCTION — THE WHOLE POINT
#   The rule already existed, in CLAUDE.md, in plain language. It lost to the
#   session-level instruction block, which is louder (it is injected per session,
#   names a specific branch, and says "NEVER push to a different branch"). This
#   repo has already written that lesson down twice:
#     docs/solutions/architecture-patterns/instructions-bind-only-in-the-channel-that-loads-2026-08-22.md
#     docs/solutions/architecture-patterns/controls-that-appear-installed-but-enforce-nothing-2026-08-04.md
#   Strengthening the wording a third time would be the same move that already
#   failed twice. A PreToolUse hook is not an instruction — the harness runs it
#   and honours its exit code no matter what any prompt says. That is the only
#   layer at this level that a session cannot talk itself out of.
#
# WHY NOT A GIT pre-push HOOK
#   `core.hooksPath` is per-clone config that cloud sandboxes never set, so git
#   hooks do not run in exactly the environment that produces this bug. Same
#   reasoning as git-identity.sh.
#
# SCOPE — personal-data ONLY
#   This gate applies to the personal-data clone and nothing else. This repo is an
#   ordinary feature-branch repo where `claude/**` is correct and expected; the
#   write/ topology is personal-data's alone. The repo is identified by its
#   `origin` URL, not by path, so it works on the desktop (a backslashed Windows
#   path) and in cloud (/workspace or a sibling symlink) without special-casing.
#
# FAILURE POSTURE
#   Blocks (exit 2) only when it is CERTAIN: the push targets personal-data and
#   the resolved branch is not write/** or sync/auto. If it cannot parse the
#   command, cannot resolve the repo, or has no python, it exits 0 and stays
#   quiet unless the command looked like a personal-data push — in which case it
#   warns. A hook that blocks unrelated work gets uninstalled, and uninstalled is
#   worse than backstopped: /wrap check 1 and the operator both still catch it.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$DIR/write-branch-gate.py"

input=$(cat)

# Cheap bail-out first: the overwhelming majority of Bash calls are not pushes,
# and this hook runs on every one of them.
case "$input" in
  *"git"*"push"*) ;;
  *) exit 0 ;;
esac

# Each candidate is EXECUTED, not just found on PATH: Windows ships a python3.exe
# App Execution Alias that resolves and then refuses to run (exit 49). Selecting
# on presence alone would pick it. Same trap documented in merge-gate.sh.
PY=""
for candidate in python3 python py; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "" >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done

if [ -z "$PY" ] || [ ! -f "$GATE" ]; then
  echo "[write-branch-gate] NOT ENFORCED: no python interpreter found." >&2
  echo "[write-branch-gate] If this push targets personal-data, the branch MUST be write/<producer>-<cmd>-<timestamp> or auto-merge will ignore it." >&2
  exit 0
fi

printf '%s' "$input" | "$PY" "$GATE"
exit $?
