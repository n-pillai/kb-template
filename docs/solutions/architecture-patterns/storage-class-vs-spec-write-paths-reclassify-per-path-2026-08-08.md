---
title: When a storage class contradicts the spec's own write paths, reclassify per-path in config — a shared-code bypass token weakens every consumer
date: 2026-08-08
category: architecture-patterns
module: integrity-layer
problem_type: design_conflict
resolution_type: config_reclassification
severity: high
tags: [append-only, l1, l2, integrity-layer, vendored, per-path-config, bypass-token]
---

# When a storage class contradicts the spec's write paths, reclassify per-path — not with a token

## Problem

The corroboration audit found the migration had placed `private/kb/entries/` under **L1 strict
append-only** while the KB spec still promised three write paths into those same files: the
`signal_tier` mirror rule (re-tier counted-leg entries on theme promotion), in-place
corrections, and Phase-3 field appends (`cited_in:`/`projects:` — YAML line edits). None had a
legal write path; the only bypass token was scoped to monthly archiving. The rules had held
so far only because tiers happened to be set correctly at creation — **an unimplementable rule
that looks enforced is worse than a missing one**, because nothing surfaces the gap until a
write is needed.

## The decision space, and why the shape of the fix mattered

- **Align the spec to the storage** (signal_tier becomes tier-at-distill; THEMES.md sole
  authority): zero code, but forecloses in-place corrections and complicates Phase-3 appends —
  rejected by the owner, who wanted the original design (clean records, in-place fixes).
- **A bypass token in the shared hook** (`[allow-edit: ...]`): rejected on a structural
  ground — the integrity hooks are vendored **byte-identical** across six repos (hash-checked;
  a per-repo fork defeats the drift model), so a token added for one repo's entries is honored
  by *every* consumer's gate over *its* L1 files (other repos' learning logs and post logs).
  A token is also self-granted authorization: the gate cannot distinguish the owner's intent
  from an agent typing the magic string.
- **Per-path reclassification (chosen):** protection class was *already* per-repo config
  (`.integrity-paths.json`, required-no-default). The gap was mechanical — L2 supported only
  exact files — so the canonical layer gained an optional `l2_prefixes` key (normalized to
  empty; a consumer not using it is behaviorally byte-identical), and personal-data moved
  `entries/` from `l1_prefixes` to `l2_prefixes`. One repo's guarantees changed; nobody
  else's moved.

## What made the change safe

- **Additive-optional shared code**: unlike a token, an unused config key weakens nothing.
- Verified before shipping: the existing 11-scenario hook suite against the new code, plus
  five live staged-mode scenarios (small edit passes; bulk deletion, dropped sections, and
  file deletion still block; absent key is a no-op).
- **End-to-end proof through the real topology**: the audit's three re-tier edits rode a
  `write/kb-audit-*` branch and were auto-merged by the bot on a green gate — the first legal
  in-place entry edits since migration.
- The retired no-touch guarantee was converted into a **detective control** (the Janitor
  modified-entry check) plus a binding edit discipline in the spec — losses named, not
  papered over.

## Prevention

- When migrating data into a protection class, **sweep the owning spec for write paths into
  that data first** — every rule that edits a file is a claim the class must support.
- In a vendored byte-identical fleet, ask of any proposed change: *does its mere existence
  change behavior for consumers that don't opt in?* Tokens do; optional config keys don't.
- The audit habit that caught this: verify a documented rule by asking **"what commit would
  enforcing it produce, and would the gate pass that commit?"** — not whether the rule sounds
  enforced.
