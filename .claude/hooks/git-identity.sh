#!/bin/bash
# SessionStart hook — pin commit authorship to an approved no-reply identity.
#
# WHY THIS EXISTS
#   personal-data's CI gate once rejected a write/kb-triage-* branch because a
#   cloud /triage session authored the commit as the owner's REAL email. The
#   instruction to "commit as the owner" worked (the session did not use Claude's
#   identity, the cloud default) but it then reached for the address closest to
#   hand: Claude Code injects the real address into every session's system prompt
#   as `userEmail`. A rule kept outside the repo never reaches a cloud sandbox,
#   which clones this repo alone; this hook is committed, so it travels.
#
# WHY A HOOK AND NOT ONLY AN INSTRUCTION
#   `git config user.email` is per-clone and every cloud session is a fresh clone,
#   so the setting has to be re-applied every session. CI (check_authorship.py)
#   is the backstop; this is the part that stops the bad commit being written.
#
# IT ALSO TURNS THE LOCAL COMMIT CHECKS ON
#   scripts/hooks/pre-commit and commit-msg only run when git is told where they
#   live, via core.hooksPath -- per-clone config, never set in a cloud sandbox.
#   A repo-local core.hooksPath replaces the machine's global hooks in that clone;
#   scripts/hooks re-chains what they check (protected branch, .env, conventional
#   commits, co-author footers). The server-side integrity-gate stays the real wall.
#
# BOTH CLONES
#   The KB's write commands commit to personal-data, not to this repo, so the
#   personal-data clone is where authorship actually matters. Pin both.
#
# WHERE THE IDENTITY COMES FROM (first match wins)
#   1. KB_GIT_EMAIL / KB_GIT_NAME environment variables.
#   2. The first entry of "approved_authors" in this repo's .integrity-paths.json
#      (name defaults to the <username> part of a no-reply address).
#   If neither yields a real address (the shipped placeholder does not count),
#   it prints a one-line warning and leaves the identity alone (core.hooksPath
#   is still set).
#
# CONTRACT
#   - Idempotent: no-ops when the identity is already approved.
#   - Non-destructive: only overwrites an identity that the gate would reject.
#   - NEVER blocks the session (always exits 0).
set -uo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
CONFIG="$PROJECT_DIR/.integrity-paths.json"

# Human entries of approved_authors, one per line. github-actions[bot] is a CI
# author, never a local commit identity, so it is filtered out.
approved_list() {
  [ -f "$CONFIG" ] || return 0
  local py=""
  for c in python3 python py; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "" >/dev/null 2>&1; then py="$c"; break; fi
  done
  if [ -n "$py" ]; then
    "$py" -c 'import json,sys
for a in json.load(open(sys.argv[1])).get("approved_authors", []):
    print(a)' "$CONFIG" 2>/dev/null
  else
    tr -d '\n' < "$CONFIG" | sed -n 's/.*"approved_authors"[[:space:]]*:[[:space:]]*\[\([^]]*\)\].*/\1/p' \
      | tr ',' '\n' | sed 's/^[[:space:]]*"//; s/"[[:space:]]*$//'
  fi | grep -v 'github-actions' | grep -v '^YOUR-ID+YOUR-USER@' | grep -v '^$'
}

APPROVED="$(approved_list || true)"
EMAIL="${KB_GIT_EMAIL:-$(printf '%s\n' "$APPROVED" | head -n1)}"
if [ -z "$EMAIL" ]; then
  echo "[git-identity] WARNING: no identity configured (set KB_GIT_EMAIL/KB_GIT_NAME or replace the placeholder in .integrity-paths.json approved_authors) -- git identity left unchanged."
  NAME=""
elif [ -n "${KB_GIT_NAME:-}" ]; then
  NAME="$KB_GIT_NAME"
else
  NAME="${EMAIL%%@*}"
  NAME="${NAME#*+}"
fi

is_approved() {
  [ -n "$1" ] || return 1
  [ "$1" = "$EMAIL" ] && return 0
  printf '%s\n' "$APPROVED" | grep -qxF -- "$1"
}

# `git -C` rather than a `-d "$dir/.git"` test: $PERSONAL_DATA_DIR is a
# backslashed Windows path on the desktop, which bash's test handles poorly and
# git handles natively.
pin() {
  dir="$1"
  [ -n "$EMAIL" ] || return 0
  [ -n "$dir" ] || return 0
  git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || return 0

  current=$(git -C "$dir" config user.email 2>/dev/null || true)
  is_approved "$current" && return 0

  git -C "$dir" config user.email "$EMAIL" 2>/dev/null || return 0
  git -C "$dir" config user.name "$NAME" 2>/dev/null || return 0
  echo "[git-identity] $dir: identity was '${current:-unset}' -> pinned to $NAME <$EMAIL>"
}

# Point git at the repo's own hooks, in any clone that carries them. Presence is
# read from the committed tree (`cat-file -e`) for the same backslashed-path
# reason as above. Both files are required: pre-commit fails closed without
# .integrity-paths.json, so a clone holding the hooks but not the config would
# have every commit blocked rather than checked.
HOOKED=""
enable_hooks() {
  dir="$1"
  [ -n "$dir" ] || return 0
  git -C "$dir" rev-parse --git-dir >/dev/null 2>&1 || return 0
  git -C "$dir" cat-file -e HEAD:scripts/hooks/pre-commit 2>/dev/null || return 0
  git -C "$dir" cat-file -e HEAD:.integrity-paths.json 2>/dev/null || return 0

  # The personal-data candidates below often name the same clone twice.
  top=$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true)
  case "$HOOKED" in *"|$top|"*) return 0 ;; esac
  HOOKED="$HOOKED|$top|"

  if [ "$(git -C "$dir" config --local core.hooksPath 2>/dev/null || true)" != "scripts/hooks" ]; then
    git -C "$dir" config core.hooksPath scripts/hooks 2>/dev/null || {
      echo "[git-identity] $dir: could not set core.hooksPath -- local commit checks will NOT run this session"
      return 0
    }
  fi

  # git skips a non-executable hook with only a "hint" line. The index mode is
  # what a Linux clone gets, and unlike `test -x` it reads the same on Windows.
  for h in pre-commit commit-msg; do
    mode=$(git -C "$dir" ls-files -s -- "scripts/hooks/$h" 2>/dev/null | cut -d' ' -f1)
    if [ -n "$mode" ] && [ "$mode" != "100755" ]; then
      echo "[git-identity] WARNING: $dir scripts/hooks/$h is mode $mode, so git skips it on Linux. Fix: git update-index --chmod=+x scripts/hooks/$h"
    fi
  done
  echo "[git-identity] $dir: core.hooksPath -> scripts/hooks (local commit checks active)"
}

pin "$PROJECT_DIR"
enable_hooks "$PROJECT_DIR"

# mount-personal-data.sh runs first, but it exports PERSONAL_DATA_DIR via
# $CLAUDE_ENV_FILE, which is not retroactive to this hook run. So resolve the same
# candidates it does rather than trusting the var to be set yet. Duplicates are
# harmless — the second pass sees an approved identity and no-ops.
for candidate in \
  "${PERSONAL_DATA_DIR:-}" \
  "/workspace/personal-data" \
  "$(dirname "$PROJECT_DIR")/personal-data"
do
  pin "$candidate"
  enable_hooks "$candidate"
done

exit 0
