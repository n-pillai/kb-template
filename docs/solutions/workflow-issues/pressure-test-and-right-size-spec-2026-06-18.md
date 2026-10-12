---
title: Pressure-test and right-size a spec before building more machinery
date: 2026-06-18
category: workflow-issues
module: kb
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "Iterating on a design spec for a single-user or personal system"
  - "Tempted to add lifecycle/automation/governance machinery before the core loop is proven"
  - "Adopting a new rule or definition that affects already-recorded data"
  - "Reviewing a design doc (not just code) before implementation"
tags: [ce-doc-review, spec-design, right-sizing, scope-control, personal-systems, pressure-test, signal-ledger]
---

# Pressure-test and right-size a spec before building more machinery

## Context

The KB is a spec-driven personal knowledge base — markdown + git + agent manifests, **not** an app codebase. Over a working session the spec kept accreting machinery (a §8 "lifecycle & maintenance" layer: three propose-only agents, a project-status cascade, archival retirement with tombstone-link rewriting) — much of it written and reviewed in the *same* session. The open question was the right one to ask out loud: is this design sound, or over-built for a one-person system? Running `ce-doc-review` (6 personas) as a pressure-test answered it and reshaped the spec.

## Guidance

1. **Pressure-test the design doc, not just the code.** For spec / markdown / agent-manifest systems, the highest-leverage review is `ce-doc-review` on the *spec itself* (coherence · feasibility · product-lens · security-lens · scope-guardian · adversarial). It surfaces over-build, contradictions, and unstated assumptions before any of it is built. The value spine for these systems is upstream review + capture, not code review.

2. **Right-size the spec to the phase that's actually running.** It's fine to keep design-ahead detail on the page — but **label the phase seam explicitly and give it a concrete build trigger** ("build the GC layer when `$PERSONAL_DATA_DIR/private/kb/wiki/` > ~20 pages OR the first project goes dormant"). A spec that *claims* a system it doesn't have reads as a current guarantee and inflates the perceived weight of a tool that must feel light to get used at all.

3. **For a single-user system, the load-bearing risk is behavioral, not structural.** What kills a personal tool is "you stop using it." The highest-friction step is often *both* the core value and the top abandonment risk (here: the distillation discipline). Name that tension in the spec and add a **falsification tripwire** (e.g. intake-per-week vs. reading volume) — don't let success metrics be all engagement proxies that can't detect abandonment.

4. **When you adopt a new rule/definition, apply it retroactively to live data.** A rule change isn't done until you backfill existing records — and the backfill may surface a contradiction that forces an honest correction. If the system is append-only with provenance, correcting *down* (e.g. demoting a tier) loses nothing: it just stops claiming confidence it never had.

5. **Capture the problem before solutioning.** When a new requirement surfaces, write the **problem statement** first — including the structural insight — and stop. Park the design questions for the plan. Resist designing the solution in the same breath; the captured framing is what a later brainstorm/plan builds on.

## Why This Matters

The single most-flagged finding in the pressure-test was machinery added *the same session it was reviewed*. Without an adversarial review, momentum keeps you building forward; the review is what tells you the real risk is **adoption, not the absence of a maintenance bureaucracy**. Each practice trades a little ceremony for not over-fitting a system to imagined future states — which, for a tool that lives or dies on a daily habit, is the difference between compounding and abandonment.

## When to Apply

- Iterating on a design spec for a single-user or personal system.
- Tempted to add lifecycle / automation / governance machinery before the core loop is proven in real use.
- Adopting a new rule or definition that affects already-recorded data.
- Reviewing a design doc (not just code) before implementation.

## Examples

- **Over-build caught.** 3 of 6 personas independently flagged the §8 lifecycle layer (three agents + cascade + tombstone rewrites) as premature for a KB with 3 wiki pages and 0 dormant projects. Resolution: *kept* the detail but relabeled it Phase-2/3 design-ahead **with a build trigger** — right-sized without losing the thinking (it stays in git history regardless).
- **Rule reaching back into data.** Adopting "independent source = distinct author AND outlet" and backfilling a `corroboration_caveat` field exposed that a WATCH theme rested on two same-author (single-person) sources = *one* independent source → re-tiered to PARKING, and the dependent entry's tier dropped with it. Provenance preserved; nothing deleted. The backfill *is* what surfaced the contradiction.
- **Behavioral risk named.** Added a "primary risk = the habit" section + a falsification tripwire to the spec's success metrics, instead of leaving adoption as an unstated assumption.
- **Problem-before-solution.** Captured an intake / relevance-triage problem statement — including the structural insight that there are **two relevance gates** (pre-consumption *triage* vs. post-consumption *signal*), and that podcasts invert to *rank-then-listen-then-distill* — without committing a solution.

## Related

- Design: `docs/design.md` (descends from spec v1.4). The build plan and intake problem statement are not included in this template.
- Method: `ce-doc-review` (the pressure-test), `ce-compound` (this capture). Fits the broader rule that for spec/markdown/agent-manifest builds the CE value is the upstream + capture spine, not the code reviewers.
