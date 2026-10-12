---
title: Two integrity seams — mirror the whole gate, and sync the catalog at the tier the artifact lands
date: 2026-06-20
category: architecture-patterns
module: kb
problem_type: design_seam
component: intake_and_catalog
severity: medium
applies_when:
  - "Building a filter/gate that mirrors an existing gate's decision logic"
  - "Two artifacts reference each other but are written/committed at different tiers or times"
  - "Adding a command that routes inputs into a multi-store system (queue / library / drop)"
  - "A catalog/index is supposed to stay in sync with a gated, separately-committed asset"
tags: [signal-ledger, triage, two-gate-model, tier-a-tier-b, catalog-sync, index-drift, design-seam, mirror-the-gate]
---

# Two integrity seams — mirror the whole gate, and sync the catalog at the tier the artifact lands

## Context

Building the Phase-1.5 intake surface for the KB surfaced two distinct integrity bugs, both about **seams between components that look independent but aren't**. One was caught in a demo rehearsal; the other by `/healthcheck`. Both are the kind of thing that passes review and only bites later.

## Guidance

1. **A gate that mirrors another must mirror its FULL decision space — not a subset.** `/triage` (gate 1, pre-consumption) was built to mirror the Signal Ledger (gate 2), but only copied two of its three outcomes — *signal* (keep) and *drop* — and silently dropped the **library** axis. Result: a source with no work tie but real learning value (an investing-classics podcast episode) got **dropped** instead of shelved. The Signal Ledger is three-way (signal / library / drop); the front-door mirror must be three-way too. When you copy a decision model into a new place, enumerate the *original's* full set of outcomes and port every one — a missing branch doesn't error, it silently discards.

2. **When two artifacts commit at different tiers, pin their reconciliation to the LATER tier.** `$PERSONAL_DATA_DIR/private/kb/INDEX.md`'s Concepts catalog drifted: it listed 2 of 3 concept pages. Root cause — `/distill` updated INDEX at **Tier A** (entry auto-commit, at distill time), but concept pages (`$PERSONAL_DATA_DIR/private/kb/wiki/`) land at **Tier B** (approved and committed *later, separately*). The Tier-A INDEX update literally *cannot* add a row for a page that doesn't exist yet, and nothing reconciled the catalog when the Tier-B page arrived. Fix: move the catalog-row update into the **Tier-B** commit (alongside the page it describes). The general rule: if artifact A's catalog entry depends on artifact B, update the catalog **where/when B lands**, not where A lands.

3. **Cost-asymmetric inputs need a "predict-before-consume" lane, and that prediction is the same lens used downstream.** Podcasts can't run the post-consumption gate until consumed, and consuming is the expensive step — so they rank on proxies *before* listening, keyed to the **same** projects/themes lens the Signal Ledger validates against. One lens, two jobs (triage ranker + signal validator). When a stage is expensive, move the cheap relevance-prediction ahead of it rather than paying the cost to find out.

## Why This Matters

Both bugs are silent. The missing gate branch doesn't throw — it deletes things you wanted (and worse, the cost-scaling logic made it *more* aggressive about dropping exactly the rich, long content most worth keeping). The catalog drift doesn't throw — it just quietly makes "what do I know about X" incomplete, undermining the one thing the KB exists to do. Neither shows up in a quick read of the command; both show up only when you exercise the system end-to-end (a rehearsal) or audit it (`/healthcheck`). That's the argument for rehearsing the full loop and running the health audit *before* trusting a freshly-built command.

## When to Apply

- Adding a gate/filter that reuses another gate's logic — port its **whole** decision space.
- Any catalog/index that must track a separately-committed (gated, approved-later) asset — sync at the asset's tier.
- Routing inputs into a multi-store system — make sure every store is reachable, including the "keep but don't promote" lane.

## Examples

- **Mirror-the-gate.** `/triage` shipped two-way (tie → queue / no tie → drop); rehearsal showed that episode dropped. Fixed to three-way (work tie → queue · library-worth → `$PERSONAL_DATA_DIR/private/kb/library/` or lower listen-list rows · neither → rejection log). "No work tie" alone is no longer a drop. (PR: triage-library-lane.)
- **Sync-at-the-later-tier.** The `example-theme` concept page (Tier B, via a `propose(wiki)` commit) was never added to INDEX's Concepts table because the Tier-A distill commit ran before the page existed. Fixed `/distill` so the Concepts row is written in the Tier-B commit. (PR: stale-index-concepts.)

## Related

- Commands: `.claude/commands/triage.md`, `.claude/commands/distill.md` · spec (§2.1.0 two-gate model, §2.2 Signal Ledger, the Tier-A/Tier-B split).
- Method note: both were caught by *exercising* the system (demo rehearsal + `/healthcheck`), not by review — fits the rule that for spec/markdown/agent-manifest builds the value spine is upstream review + running the loop, not code review.
