---
title: Content-review a source before discarding it — never route by format
date: 2026-06-21
category: workflow-issues
module: kb
problem_type: workflow_issue
component: triage_pipeline
severity: medium
applies_when:
  - "Triaging or curating a batch of inbound sources (newsletters, digests, roundups)"
  - "Tempted to drop an item by its type/format (\"it's just a digest\") without reading it"
  - "Running /triage or any bulk intake where the easy heuristic is sender/format"
tags: [triage, signal-ledger, curation, intake, format-vs-content, library-lane]
---

## Problem

When ingesting a 33-item email newsletter backlog, the first pass routed items by **format**: digests / roundups / Q&A threads (a community Q&A digest, a weekly podcast-recommendation roundup, a publication's digest, a markets column) were headed for the rejection log as "contentless digests." The owner caught it: *"Did you review for content, or are you discarding because it's a digest?"*

Routing by format is a false economy. A digest's *wrapper* is low-signal, but its *payload* often is not — the Q&A digest summarizes recommended podcasts and surfaces Q&A topics; the roundup names what it's recommending; the markets column carries real market-structure arguments. Dropping by type silently discards the exact surface area a wide reader wants kept.

## Solution

**Fetch and read the actual body before any disposition.** Disposition follows content, not container:

- Pull the real text (for email, the mail connector's thread fetch; bodies can exceed token limits, so save to disk and extract the plaintext — e.g. `jq -r '.messages[0].plaintextBody'`).
- Then apply the gate three-way: a work tie → queue/distill; no tie but worth knowing → `$PERSONAL_DATA_DIR/private/kb/library/` (the whole point of the library lane is to keep untied-but-worthwhile material); only genuinely contentless/duplicate/pure-promo → drop, with the **link preserved** in `rejected-log.md` so false-negatives are auditable.
- Reviewing the 33 by content turned ~25 presumed-drops into library cards and ~2 into entries; only ~6 were genuine drops.

To keep the main context clean on a large batch, delegate the body-reading to subagents (they can call the mail connector themselves) and act on their structured summaries.

## Why it matters

The library lane exists precisely so "no work tie" is **not** grounds to drop. Format-routing reintroduces the bug the library lane was built to fix — it just hides it behind a plausible-sounding heuristic. The cheap heuristic (sender/format) belongs at most to *ranking* cost (podcasts rank-then-listen); it must never substitute for the content read that decides keep-vs-drop.

## See also

- [[integrity-seams-mirror-the-gate-sync-the-catalog-2026-06-20]] — the other intake-integrity learning.
- CLAUDE.md → "The library (`$PERSONAL_DATA_DIR/private/kb/library/`) — the non-signal reference path"; the `/triage` skill's three-way gate.
