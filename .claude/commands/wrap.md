---
description: Cloud-safe session close — verify write branches merged, nothing dangling, in-flight intake named. Report-only; never mutates state.
---

Run the session wrap: a cloud-safe close report, scoped to
this repo and its personal-data write topology. **Every check is read-only** — report and
propose; never push, merge, delete, or commit on the operator's behalf.

Fail closed on the mount exactly as the pipeline does: if `$PERSONAL_DATA_DIR` is unset or
missing, run checks 3–4 only and report the mount as ABSENT — do not guess at its state.

## Checks — each reported ✅ / ⚠️ with a proposed fix on ⚠️

1. **personal-data write lifecycle.** `git -C "$PERSONAL_DATA_DIR" fetch --prune`, then
   `git -C "$PERSONAL_DATA_DIR" branch -r`. Expected: only `origin/main`. **Flag every ref that
   is not `origin/main`, and read the two failure shapes differently — a surviving `write/*`
   ref is a *stalled* merge; any other prefix is a *stranded* one:**
   - **`write/*` survives** — `auto-merge.yml` has not closed it out: a check failed, the
     branch conflicts with `main`, or the run is still going. Propose: open the private repo's
     **Actions** tab and read that branch's `auto-merge` run. Do NOT merge it from the session;
     the workflow merging only after its checks pass is the control.
   - 🔴 **any other prefix survives (`claude/*`, `feat/*`, …)** — **worse, and silent.**
     `auto-merge.yml` triggers only on `write/**`, so this branch will *never* be picked up:
     no merge, no error, and nothing red in the Actions list. Work sits there indefinitely. Propose: re-point the
     commits onto `write/kb-<cmd>-<timestamp>` and push that (`git branch write/kb-…  <sha>`),
     then delete the stray ref once merged. This is the classic stranding — a cloud session
     harness pins `claude/<slug>-<session-id>` for every attached repo, and
     `.claude/hooks/write-branch-gate.sh` now blocks those pushes at source; this check is the
     backstop for a push that predates the hook or was made where it could not run.
2. **Mount clone state.** The mount must be on `main`, working tree clean, and not ahead of
   `origin/main`. Dirty or ahead = writes that bypassed the `write/kb-*` branch topology —
   flag loudly and propose moving the changes onto a `write/kb-<cmd>-<timestamp>` branch;
   never commit or push them directly.
3. **This repo.** Working tree clean; current branch pushed; if `gh` is available, list open
   PRs on this repo and flag any authored this session as unmerged. When `gh` is unavailable
   or unauthenticated, skip with a note ("PR check skipped — gh unavailable") — degrade,
   never block the wrap.
4. **In-flight intake.** Count files (excluding `.gitkeep`) in
   `$PERSONAL_DATA_DIR/private/kb/_inbox/queue/` and note the top of
   `$PERSONAL_DATA_DIR/private/kb/_inbox/triage/listen-list.md` if present. Parked items are
   fine — the point is that the close report NAMES them so nothing is silently stranded.

## Output

A short block:

```
== session wrap ==
write lifecycle: ✅ no dangling write/* branches
mount clone:     ✅ main, clean, in sync
this repo:       ✅ clean, pushed / ⚠️ ...
in-flight:       queue 2 | listen-list top: <item> — parked, named
→ ✅ nothing stranded  /  ⚠️ N item(s) need attention
```

Keep it to the block plus one line per ⚠️ proposal. This is a close report, not an audit —
`/healthcheck` owns the deep monthly pass.
