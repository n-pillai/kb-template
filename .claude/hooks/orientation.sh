#!/bin/bash
# SessionStart hook -- pipeline orientation banner.
#
# Every session -- desktop, cloud, mobile -- opens knowing the pipeline instead
# of reconstructing it from the repo. Deliberately dependency-free: filesystem
# and nothing else (no gh, no network, no git), so it runs identically in an
# unauthenticated sandbox and can never slow or block a session start.
# Runs LAST in the SessionStart chain, after the mount + identity hooks, so the
# mount state it reports is the settled one. Always exits 0.
set -uo pipefail

echo "== kb: the synthesis brain =="
echo "intake:  /triage <link> (front door) | /capture <link> (raw drop) -> _inbox/queue | /shelve -> library"
echo "distill: /distill -> entry + INDEX/THEMES update; wiki changes are PROPOSED, never silent"
echo "writes:  land as write/kb-* branches in personal-data -- auto-merged AND branch-deleted on a green gate"
echo "close:   /wrap -- verify nothing stranded before ending the session"

pd="${PERSONAL_DATA_DIR:-}"
if [ -n "$pd" ] && [ -d "$pd/private/kb" ]; then
  count_files() {
    find "$1" -maxdepth 1 -type f ! -name '.gitkeep' 2>/dev/null | wc -l | tr -d '[:space:]'
  }
  q="$(count_files "$pd/private/kb/_inbox/queue")"
  t="$(count_files "$pd/private/kb/_inbox/triage")"
  l="$(count_files "$pd/private/kb/library")"
  echo "mount:   present -- queue: $q awaiting distill | triage state files: $t | library cards: $l"
else
  echo "mount:   ABSENT -- \$PERSONAL_DATA_DIR is unset or has no private/kb. FAIL CLOSED:"
  echo "         do not fall back to in-repo paths and do not reconstruct content from memory."
fi
exit 0
