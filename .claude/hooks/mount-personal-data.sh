#!/bin/bash
# SessionStart hook — mount the private `personal-data` repo in cloud/mobile sessions.
#
# WHY THIS EXISTS
#   This repo's content migrated to `personal-data` on 2026-08-02 and CLAUDE.md now
#   says FAIL CLOSED when $PERSONAL_DATA_DIR is absent. On the desktop the var comes
#   from `setx`. Cloud sandboxes clone only the session's repo and set nothing, so
#   every cloud/mobile session has been correctly telling itself to stop — a live
#   breakage, not a latent gap. This hook is the cloud half of the mount.
#
# WHY A HOOK AND NOT THE ENV SETUP SCRIPT
#   The setup script runs once and is then SNAPSHOTTED and reused for ~7 days
#   (docs: "Environment caching"). A snapshot of personal data is a stale task list
#   and a stale ledger — exactly what CONVENTION.md's "pull at session start" rule
#   exists to prevent. A SessionStart hook runs every session, including resumed
#   ones, and is committed so it travels with the repo. The setup script also cannot
#   set $PERSONAL_DATA_DIR for the session; $CLAUDE_ENV_FILE (below) can.
#
# NO TOKEN, DELIBERATELY
#   Cloud environments have no secrets store — env vars are readable by anyone using
#   the environment (docs: "Set environment variables"). Putting a PAT with read
#   access to the personal-data repo there would place a credential to the owner's
#   personal data in plaintext config. So this relies on the session's GitHub proxy
#   instead, and if the proxy refuses, it reports that rather than working around it.
#
# ✅ VERIFIED 2026-08-04 (cloud session, Claude Code 2.1.221) — §5's open question is
#   settled, and the answer is BOTH sides of the doc conflict, at different layers:
#     - Account POLICY does allow it (the GitHub App can see personal-data).
#     - Session PROXY does not. Unattached repos are not served: the clone falls
#       through to a credential prompt on the session's local git proxy and dies with
#         fatal: could not read Password for 'http://local_proxy@127.0.0.1:PORT':
#         terminal prompts disabled
#       (Not the 2026-07-22 "access not enabled" JSON stub — that stub was the API
#       path; smart-HTTP git fails this way instead. Both mean "out of scope".)
#   So a clone works if and only if personal-data is attached to THIS session.
#
#   WHAT THAT CHANGES: a bash hook cannot attach a repo — only the agent can, via the
#   `add_repo` tool. So a clone failure is NOT the dead end this hook used to report.
#   It is a one-step recovery, and the hook now prints that recipe (emit_recovery
#   below) instead of just "stop". Fail-closed still holds *until* the recovery runs.
#   No PAT, no restructuring — route 4 that docs §5 did not know about.
#
#   ⚠️ There is NO known environment-level way to pre-attach the repo (retracted
#   2026-08-04). An earlier version of this comment said to "attach personal-data as
#   a second source on the cloud environment" — that option does not exist: the
#   environment settings dialog has only name, network access, environment variables
#   and setup script, confirmed both in Anthropic's docs and in the UI. So
#   the per-session recovery below is the mechanism, not a fallback to something
#   better. See §5 of docs/cloud-environment-setup.md.
#
# CONTRACT
#   - Cloud only; desktop is a no-op (the desktop var comes from setx).
#   - Idempotent: clones if absent, pulls if present.
#   - NEVER blocks the session (always exits 0). A hook that hard-fails a session is
#     a hook that gets removed. Fail-closed is enforced where it belongs — in
#     CLAUDE.md, by the agent — and this hook's job is to make the state UNMISSABLE
#     in context either way.
#
# WHICH REPO
#   KB_DATA_REPO=<owner>/<repo> names the private data repo. Unset, it defaults to
#   <owner>/personal-data, where <owner> is read from this repo's `origin` URL.
set -uo pipefail

# Desktop / local sessions: PERSONAL_DATA_DIR comes from setx. Nothing to do.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
REPO="${KB_DATA_REPO:-}"
if [ -z "$REPO" ]; then
  origin=$(git -C "$PROJECT_DIR" remote get-url origin 2>/dev/null || true)
  owner=$(printf '%s' "$origin" | sed -nE 's#^.*(github\.com[:/]+|/git/)([^/]+)/[^/]+/?$#\2#p')
  [ -n "$owner" ] && REPO="$owner/personal-data"
fi
if [ -z "$REPO" ] || [ "${REPO#*/}" = "$REPO" ]; then
  echo "[personal-data] NOT MOUNTED — set KB_DATA_REPO=<owner>/personal-data in the cloud environment (could not derive it from origin)."
  echo "  FAIL CLOSED: do not read in-repo fallback paths or reconstruct content from memory."
  exit 0
fi

# WHERE THE CLONE GOES, and why it is not simply the sibling path any more.
#   `register_repo_root` — the call that loads personal-data's CLAUDE.md and
#   CONVENTION.md into context — accepts ONLY the session's managed clone target,
#   /workspace/<repo>, and rejects any other path outright. So the real clone lives
#   there, and the sibling path becomes a symlink to it. That keeps the desktop
#   layout promise (personal-data resolves BESIDE the build repo, never inside it,
#   so it can never be committed into one) while staying registrable.
MANAGED_TARGET="/workspace/personal-data"
SIBLING_TARGET="$(dirname "$PROJECT_DIR")/personal-data"
TARGET="$MANAGED_TARGET"

# Link the sibling path at the managed clone, unless something real is already there.
link_sibling() {
  [ "$SIBLING_TARGET" = "$MANAGED_TARGET" ] && return 0
  [ -e "$SIBLING_TARGET" ] && [ ! -L "$SIBLING_TARGET" ] && return 0
  ln -sfn "$MANAGED_TARGET" "$SIBLING_TARGET" 2>/dev/null || true
}

emit_unmounted() {
  cat <<EOF
[personal-data] NOT MOUNTED — $1

  FAIL CLOSED. Per CLAUDE.md, do not read in-repo fallback paths, do not
  reconstruct content from memory, and do not fabricate entries, themes or
  task state. Tell the user the mount is unavailable and stop.

  Diagnostic (for docs/cloud-environment-setup.md §5):
$2
EOF
}

# The clone failed because personal-data is not attached to this session. That is
# recoverable in-session, so print the recipe rather than stopping at "unavailable".
emit_recovery() {
  cat <<EOF
[personal-data] NOT MOUNTED YET — $REPO is not attached to this session, so the
  session's git proxy refused the clone.

  Diagnostic (for docs/cloud-environment-setup.md §5):
$1

  RECOVERABLE — run these steps NOW, before you answer the user's first message,
  whatever that message is. Do not report this state back and wait for them to
  approve the recovery: they cannot see this text (SessionStart output goes to
  your context, not to their screen), so to them a status report looks like the
  session doing nothing. Run the steps, then answer what they actually asked,
  mentioning the mount only in one line — or not at all if it succeeded.
  Stop and tell them ONLY if a step genuinely fails.
    1. Call the \`add_repo\` tool with {owner: "${REPO%%/*}", repo: "${REPO#*/}",
       access: "read"}  (use "push" if this session will write to the KB).
    2. Clone ONCE, inline, with a generous timeout — FULL depth, not --depth 1:
         git clone https://github.com/$REPO $MANAGED_TARGET
       Do not parallelise it; the proxy caps concurrent git ops on a repo at 2.
       personal-data is a WRITE target: writes go via write/<repo>-<cmd>-<ts>
       branches, and both the local L1 append-only hook and git merge-base need
       real history. A shallow clone breaks them on the first write.
    3. ln -sfn $MANAGED_TARGET $SIBLING_TARGET
    4. git -C $MANAGED_TARGET config core.hooksPath scripts/hooks
    5. bash "$PROJECT_DIR/.claude/hooks/git-identity.sh"
       — REQUIRED, not optional. That hook already ran at SessionStart, found no
       personal-data clone (you had not made it yet) and silently skipped it. The
       clone you just created therefore still carries the sandbox's default git
       identity, and personal-data's CI authorship gate rejects the first write
       branch it produces. Re-running the hook pins it. It is idempotent.
    6. export PERSONAL_DATA_DIR=$MANAGED_TARGET
       — and prefix subsequent Bash calls with it, since a hook-set var is not
       retroactive to a session that already started.
    7. Call \`register_repo_root\` with {owner: "${REPO%%/*}", repo: "${REPO#*/}",
       directory: "$MANAGED_TARGET"} so its CLAUDE.md/CONVENTION.md load.

  UNTIL step 6 succeeds, FAIL CLOSED: do not read in-repo fallback paths, do not
  reconstruct content from memory, and do not fabricate entries, themes or tasks.

  This recovery runs per session, and that is expected — there is no known way to
  pre-attach the repo at the environment level (the settings dialog has only name,
  network access, environment variables and setup script). Do NOT ask the user to
  "attach it as a source"; that option does not exist. Just run the steps above.
EOF
}

if [ -d "$TARGET/.git" ]; then
  # Present from a resumed session or a warm snapshot — refresh it.
  # A stale clone is a stale ledger, which is the failure this guards against.
  if err=$(git -C "$TARGET" pull --ff-only 2>&1); then
    mounted=1
  else
    # Pull failed but the clone exists. Usable but possibly stale — say both.
    echo "[personal-data] mounted at $TARGET, but PULL FAILED — content may be stale."
    echo "  Treat task lists / ledgers as possibly out of date and say so before relying on them."
    echo "  git: $(echo "$err" | head -3 | sed 's/^/    /')"
    mounted=1
  fi
else
  mkdir -p "$(dirname "$TARGET")" 2>/dev/null || true
  if err=$(git clone --quiet "https://github.com/${REPO}.git" "$TARGET" 2>&1); then
    mounted=1
  else
    mounted=0
    # Distinguish "not attached to this session" (recoverable via add_repo) from a
    # genuine failure (network, disk, deleted repo), which the recipe would not fix.
    if echo "$err" | grep -qiE 'could not read (Password|Username)|local_proxy|terminal prompts disabled|Authentication failed|access not enabled|403'; then
      emit_recovery "$(echo "$err" | head -5 | sed 's/^/    /')"
    else
      emit_unmounted "could not clone ${REPO} into this sandbox." "$(echo "$err" | head -5 | sed 's/^/    /')"
    fi
  fi
fi

if [ "${mounted:-0}" != "1" ]; then
  exit 0
fi

link_sibling

# CONVENTION.md: the integrity hooks are per-clone config and must be set in every
# clone, on every machine. This clone is new every session, so set it every session.
git -C "$TARGET" config core.hooksPath scripts/hooks 2>/dev/null || true

# Persist PERSONAL_DATA_DIR for every subsequent Bash command in this session.
# This is the only supported way to set a session env var from a hook. The file is
# sourced as a bash prelude, so it must contain EXPORTS — a bare assignment would
# set a shell variable that $PERSONAL_DATA_DIR expands from but that child
# processes (git, node, scripts) would never see.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PERSONAL_DATA_DIR=$TARGET" >> "$CLAUDE_ENV_FILE"
  echo "[personal-data] mounted at $TARGET (PERSONAL_DATA_DIR exported for this session)"
  echo "  Sibling path $SIBLING_TARGET also resolves here."
  echo "  Call register_repo_root {owner: ${REPO%%/*}, repo: ${REPO#*/}, directory: $TARGET} to load its CLAUDE.md."
else
  # No env-file support in this Claude Code version: the clone is there but the
  # var is not, and a command reading $PERSONAL_DATA_DIR would still fail closed.
  # Surface the path so the session can be told explicitly.
  emit_unmounted "clone succeeded at $TARGET but \$CLAUDE_ENV_FILE is unset, so PERSONAL_DATA_DIR could not be set." \
                 "    Claude Code version predates CLAUDE_ENV_FILE support. Export it manually: export PERSONAL_DATA_DIR=$TARGET"
fi

exit 0
