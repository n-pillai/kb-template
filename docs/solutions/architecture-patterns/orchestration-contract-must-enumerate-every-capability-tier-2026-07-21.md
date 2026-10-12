---
title: An orchestration contract must enumerate every tier a capability offers — naming a subset silently disables the rest
date: 2026-07-21
category: architecture-patterns
module: kb
problem_type: silent_capability_bypass
component: intake_fetch_ladder
severity: medium
applies_when:
  - "A skill/tool/dependency offers a multi-tier capability (e.g. fetch: plain -> render -> summarize)"
  - "A higher-level contract (CLAUDE.md, a command, a router) decides when each tier fires"
  - "The contract names only some tiers, or has an escape clause ('if X is available') that goes unverified"
tags: [signal-ledger, intake, fetch-docs, fallback-ladder, agent-browser, render, silent-bypass, cover-all-tiers, orchestration-contract, mirror-the-mechanism]
---

## Problem

The KB's intake fetch chain kept failing with "curl and web fetch both failed" on JS-rendered (SPA) pages. The vendored `fetch-docs` skill actually ships a **three-tier fetch**: plain `curl` → `--render` (drives a headless `agent-browser` that runs the page's JS and captures the real DOM) → give up. And `agent-browser` **was installed** (v0.27, confirmed by `fetch-docs --check`), so `--render` worked. Yet the failures kept recurring on exactly the pages `--render` exists for.

## Root cause

The KB's *operational contract* — the "Source fetching" section of `CLAUDE.md` plus the `/triage` / `/distill` / `/shelve` commands — described the fallback as **`fetch-docs` (plain) → WebFetch**, omitting the `--render` tier entirely. It even routed the trigger case backwards: "use WebFetch when fetch-docs fails … *or a JS-rendered SPA shell*" sent SPA pages straight to WebFetch, which *also* can't run JS. `distill.md` carried an escape clause — "a JS-rendered SPA shell **with no `--render` available**" — that was never checked against reality (`--render` *was* available), so it rationalized the skip.

The capability existed and worked; the layer that decides *when to invoke it* never named it, so it was **silently dead**. Nothing errored — the chain just fell through to a weaker tier that "works" everywhere except the hard case, so the gap was invisible until SPA pages recurred often enough to notice.

## Fix (PR #70)

Rewrite the fallback as an explicit **4-tier escalation ladder**, with `CLAUDE.md` as the single source of truth and the three commands pointing to it:

1. `fetch-docs` (plain curl) → 2. **`fetch-docs --render`** (empty SPA shell; agent-browser installed) → 3. WebFetch (last automated resort) → 4. **manual paste / OCR** (auth-walled / subscriber / bot-blocked — unreachable by any automated tier).

Removed the "with no `--render` available" loophole, named tier 2 explicitly as the fix for the recurring error, and added tier 4 for the genuinely-unfetchable case (the failure mode `--render` *can't* solve, because it forwards no login).

## The reusable rule

When a tool offers a multi-tier capability, the **orchestration contract must enumerate every tier** — the layer that decides *when* each tier fires is the real interface, and a contract that names a subset silently disables the rest, no matter that the capability is installed and working. Two tells:

1. **An escape clause tied to an unverified precondition** ("if X is available") is a silent-skip waiting to happen — verify the precondition (here: `fetch-docs --check` / `command -v agent-browser`) or drop the clause.
2. **A fallback that "works" everywhere but the hard case** hides the gap, because the failure only shows on the inputs the skipped tier existed for.

Design check: "for each capability the dependency advertises, does my contract actually reach for it, and under what *verified* condition?"

This is a sibling of [[auto-cleanup-invariant-covers-every-exit-2026-06-28]] and [[integrity-seams-mirror-the-gate-sync-the-catalog-2026-06-20]]: all three are **partial coverage of a multi-branch seam that doesn't error, just degrades** — that one covers every *exit*, the integrity one mirrors the whole *gate*, this one enumerates every *tier*. Same shape, different seam.
