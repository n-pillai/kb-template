---
title: An auto-cleanup invariant must be enforced on every exit path, not just the one built first
date: 2026-06-28
category: architecture-patterns
module: kb
problem_type: asymmetry_bug
component: listen_list_lifecycle
severity: medium
applies_when:
  - "A state store has an invariant maintained by a cleanup step (trim/remove/archive on transition out)"
  - "That state has more than one exit path (e.g. /distill vs /shelve, success vs cancel, promote vs drop)"
  - "The cleanup was added to one exit when a feature shipped, and the other exits predate or postdate it"
tags: [signal-ledger, listen-list, two-gate-model, lifecycle-invariant, auto-trim, asymmetry-bug, cover-all-exits, mirror-the-gate]
---

## Problem

The listen-list (`$PERSONAL_DATA_DIR/private/kb/_inbox/triage/listen-list.md`) is **pre-consumption** state with one invariant: a consumed episode must never linger on it. v1.6.1 enforced this by having `/distill` auto-trim the row when a work-tied episode was distilled. But the listen-list has a first-class **`$PERSONAL_DATA_DIR/private/kb/library/learning` lane** whose *designed* exit is `/shelve`, not `/distill` — and `/shelve` had no trim. So every learning-lane episode that was consumed and shelved stayed on the list forever as stale pre-consumption state. The invariant held for one exit and silently leaked on the other.

## Root cause

The cleanup was attached to the **command that happened to introduce the feature** (`/distill`), not to the **state transition it actually protects** ("an episode leaves pre-consumption state"). That transition has *two* normal exits — distill (work-tied) and shelve ($PERSONAL_DATA_DIR/private/kb/library/learning) — plus a manual drop. Implementing the trim on only the first exit built is an asymmetry that's invisible until the *other* exit's path is exercised, because nothing errors — the row just accumulates.

## Fix (PR #60, spec v1.6.4)

Make `/shelve` trim symmetrically with `/distill`: same match logic (URL, else show + title), same idempotent no-op when nothing matches, same commit. Rename the off-list section `Consumed (off-list)` so it covers both dispositions (`distilled → [[entry]]` / `shelved → [[library-card]]`). The manual drop (listened-but-neither-distilled-nor-shelved) stays an explicit documented edge case.

## The reusable rule

When a state's invariant is maintained by a cleanup step, **the cleanup belongs to the transition, not to one command** — enumerate every exit path out of that state and enforce the invariant on all of them. A good check at design time: "what are *all* the ways something leaves this state, and does each one maintain the invariant?" Bonus tell: if the state has *lanes* or *categories* (here, work-tied vs. $PERSONAL_DATA_DIR/private/kb/library/learning), each lane usually has its own exit — and the lane added later is the one whose exit gets forgotten.

This is a sibling of [[integrity-seams-mirror-the-gate-sync-the-catalog-2026-06-20]]: that one says "mirror the *whole* gate's decision logic"; this one says "mirror the *whole* lifecycle's cleanup across every exit." Both are the same failure shape — partial coverage of a multi-branch seam that doesn't error, just drifts.
