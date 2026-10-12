---
title: A lossy channel corrupts the identifiers your integrity checks key on — and the corruption reads as valid data
date: 2026-08-26
category: architecture-patterns
module: kb
problem_type: architecture_pattern
component: signal_ledger_intake
severity: high
applies_when:
  - "Content arrives through a transformation you do not control (ASR, OCR, translation, a summarizer, a scraper)"
  - "A downstream correctness rule is computed by matching strings that came through that channel"
  - "The corrupted value is of the same type as the correct one, so nothing looks malformed"
  - "A pipeline treats 'the source text' as one artifact when it is really metadata plus a machine-generated body"
  - "Deduplication, identity, or independence tests run on names rather than on stable IDs"
tags: [signal-ledger, intake, transcripts, asr, proper-nouns, provenance, corroboration-independence, dedup, silent-failure, metadata-vs-body, two-layer-source]
---

## Context

`/distill` treats a fetched transcript page as *the source*. It is not one thing. A page from an
ASR host has **two layers with different provenance**: metadata (`<title>`, `og:` tags, the
show · episode · duration header) written by a human or a CMS, and a transcript **body** produced by
speech recognition. The Signal Ledger read both as equally authoritative.

Speech recognition degrades gracefully on ordinary prose and catastrophically on **proper nouns** —
the tokens with no language-model prior to fall back on. On 2026-08-26 a podcast transcript rendered
the company under discussion (call it *Company A*) eight different ways — near-miss spellings and
unrelated real words — **and twice as *Company B*** — a real company, unrelated, uninvolved in the
conversation — at the two highest-stakes moments in the episode, including a bull case for a
$200 billion valuation.

The dangerous property is not the error rate. It is that **the corrupted value is well-formed**.
A garbled spelling looks like a typo and gets caught. *"Company B is a $200 billion company"* is grammatical,
plausible, attributable, and false. Nothing downstream can distinguish it from signal.

## Guidance

**1. Find out which of your correctness rules key on strings from the lossy channel.** This is the
whole move. In this repo the answer was worse than expected:

| Rule | Keys on | Failure when the key is corrupted |
|---|---|---|
| Corroboration independence (*distinct author AND outlet*) | two proper nouns | **false independence verdict** — a same-outlet source counted as a new leg, promoting a theme on one voice |
| Dedup at `/triage` | URL, else title | re-triage of an already-distilled source |
| Listen-list auto-trim | URL, else **show + episode title** | trim silently stops matching; consumed episodes linger as stale pre-consumption state |
| Backlinks and entity search | names | quiet misses, which look like absence of evidence |

Independence is the severe one: it is the mechanism that decides what the KB *believes*, and it is
computed on exactly the two strings the channel is worst at.

**2. Normalize before the first rule runs, not before quoting.** The instinct is to treat this as a
citation-hygiene problem and clean names on the way into an entry. Too late — by then the tier
judgment has already been made. Normalization belongs immediately after fetch and **before** any
step that compares, counts, or classifies.

**3. Prefer the layer with human provenance, and say so explicitly.** "Verbatim from the source" is
ambiguous the moment a source has two layers, and ambiguity resolves toward whichever layer the
reader happens to be looking at. State the precedence: **metadata wins over body.**

**4. Let your own store arbitrate.** An entity the system already tracks has a canonical spelling
locally. Checking a name against `INDEX.md` / `THEMES.md` is cheaper than an external lookup and
catches the case that matters most — a source naming someone already counted on a theme.

**5. Mark what you cannot resolve; never infer it.** A plausible name attached to a real
organization (*"Person X, the founder of Company C"*) is the worst outcome, because it looks
checkable and therefore does not get checked. `(unverified)` is a cheap, honest terminal state.

## Why This Matters

The KB already had two provenance riders, and this is the third — but it is the first about
**transport** rather than **attribution**:

- **v1.6.5 (secondhand evidence)** — one primary reaching the KB through two intermediaries is one
  source. *Stops double-counting.*
- **v1.6.7 (absence)** — one speaker's silence must not stand in for an organization.
  *Stops over-attribution.*
- **v1.6.8 (this)** — the primary said the right thing and the channel mangled it.
  *Stops corruption in transit.*

The first two are about reasoning correctly over what a source said. This one is about not being
sure what the source said at all — a lower layer, and it undercuts both of the others, since a
secondhand-evidence audit or an absence audit run over corrupted names inherits the corruption.

The generalizable claim: **any system that computes correctness by matching strings is only as
sound as the noisiest channel those strings arrive through** — and a lossy channel that emits
well-formed wrong values is far more dangerous than one that emits obvious garbage, because garbage
fails loudly and plausibility fails silently.

## When to Apply

- Adding any new intake path that involves ASR, OCR, translation, or an LLM summarizer.
- Any time an identity, dedup, or independence rule is specified as matching on a **name** rather
  than a stable identifier. Ask where that name came from.
- When a system's "source" is a fetched page — check whether it is really two artifacts.
- When a match-based mechanism appears to be working but the thing it should be catching keeps
  slipping through. Suspect the key before suspecting the logic.

## Examples

**The near-miss.** The 2026-08-26 distill of that source would have asserted a $200B
bull case for Company B. It was caught only because the reader was already tracking the company name
across the episode and noticed the substitution was too well-formed to be a typo. Nothing in the
pipeline would have flagged it.

**The prior instance nobody logged.** `/triage` already had the shape of this rule — "record the
episode title as published, verbatim, never a paraphrase," written after a plausible-sounding
paraphrased title broke auto-trim. That was the same failure (a well-formed wrong key silently
disabling a match-based mechanism) diagnosed one instance at a time. The paraphrase case and the ASR
case are one pattern; only the corrupting agent differs.

**Where it was fixed:** `/distill` step 2 (normalize before reading for meaning, ahead of the tier
judgment at step 5); `/triage` (metadata beats body when recording listen-list rows);
`/healthcheck` Janitor §1.10 (standing audit — metadata agreement, hapax entities, unresolved
markers, with corrupted author/outlet prioritized because a tier move may have leaned on it) and
Doctor §2.6 (*named, or verified?*).

## Related

- `docs/solutions/architecture-patterns/auto-cleanup-invariant-covers-every-exit-2026-06-28.md` —
  the other listen-list failure: an invariant enforced on one exit path. Same store, and both
  failures are silent-until-audited.
- `docs/solutions/workflow-issues/content-review-before-discard-in-triage-2026-06-21.md` — the
  intake-stage judgment sibling.
- Spec §2.2 (the Signal Ledger contract, rule 4 — corroboration tier) and the v1.6.5 / v1.6.7 / v1.6.8 provenance riders.
