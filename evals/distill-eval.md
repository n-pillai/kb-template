# distill-eval — evaluating the `/distill` transformation

**What we evaluate:** the `/distill` step — *queue item / library card → `$PERSONAL_DATA_DIR/private/kb/entries/` file (+ `$PERSONAL_DATA_DIR/private/kb/THEMES.md` move + `$PERSONAL_DATA_DIR/private/kb/wiki/` proposal)*.

**The eval question:** *"Is this the distillation the owner would have written, and is the corroboration call correct?"* — an **LLM-judge-aligned-to-the-owner** problem. The Signal Ledger's five rules (CLAUDE.md) are the failure taxonomy, already written in prose; this file turns them into checks.

Status: **v0 sketch** (2026-07-01). Not yet wired to any runner — Phase 1 is manual grading against the golden set.

---

## Layer 1 — code-graded (deterministic, run on every `/distill`)

Cheap `if/else` assertions. No model needed; these should never fail on a good entry.

| # | Check | Rule enforced |
|---|-------|---------------|
| C1 | Frontmatter parses; all required keys present (`date, title, type, source, url, tags, signal_tier, projects, themes, writer, cited_in`) | Entry format |
| C2 | `signal_tier` ∈ {parking, watch, confirmed, negative} | Tier vocab |
| C3 | Every `tags:` value exists in `tags.md` | Governed tags |
| C4 | Every `projects:` slug exists in `$PERSONAL_DATA_DIR/private/kb/projects.md`; every `themes:` slug in `$PERSONAL_DATA_DIR/private/kb/THEMES.md` | Governed vocab |
| C5 | `projects` ∪ `themes` non-empty **OR** `signal_tier: negative` | Rule #2 — the "so what" tie |
| C6 | `signal_tier` == current tier of the entry's **primary counted-leg theme** (else `parking` if depth-only/project-only; `negative` overrides) | THEMES.md mirroring rule |
| C7 | All four body sections present: **Thesis / So what / Key evidence / What stuck** | Entry format |
| C8 | Filename matches `YYYY-MM-DD-slug.md`; `writer:` set | Provenance |
| C9 | No `$PERSONAL_DATA_DIR/private/kb/wiki/` file created/modified in the same Tier-A commit as the entry | Tier-B gating |

## Layer 2 — LLM-as-judge (judgment calls code can't make)

One rubric per dimension. **Binary verdict + one-line reason.** Judge must be aligned before use (see below).

| # | Dimension | Pass question |
|---|-----------|---------------|
| J1 | **Distillation-not-summary** | Is the **Thesis** an *arguable claim* someone who hadn't read the source could dispute — not the topic restated? (Rule #1) |
| J2 | **Tie is real** | Does the **So what** genuinely connect to the named project/theme, or is the slug cosmetic? (Rule #2) |
| J3 | **Corroboration integrity** ⭐ | Does any `$PERSONAL_DATA_DIR/private/kb/THEMES.md` move count a **non-independent** source (same author OR same outlet/network/origin) as a leg? Highest-damage error. (Rule #4) |
| J4 | **Evidence faithfulness** | Is every number/quote in **Key evidence** traceable to the source, no fabrication? |
| J5 | **Negative-signal handling** | If the source wasn't useful, is that logged as `signal_tier: negative` with the reason, rather than force-fit? (Rule #3) |

J3 is the one to weight hardest — the entire value of the ledger over a bookmark pile is that a bad independence call doesn't slip through.

## The golden set (this is the real work — "validate the validators")

The judge is only trustworthy if it agrees with the owner on examples they've already ruled on.

**The anchor set itself — which entries, and the owner's rulings on them — is data, not machinery:
it lives at `$PERSONAL_DATA_DIR/private/kb/evals/golden.md`** (moved 2026-08-07 so this repo
carries no entry slugs or rulings). Reference fixtures by ID: gold-positive **GP-1..GP-3**
(GP-1 is the hard both-ways J3 case), gold-negative **GN-1** (J1 must fail it), **GN-2** (J3),
**GN-3** (J4).

*(Fixtures to live under `$PERSONAL_DATA_DIR/private/kb/evals/golden/` when built — in the
mount, never here, so this repo doesn't re-acquire a data tree.)*

## Judge-alignment plan (before trusting J1–J5)

Method (Hamel Husain and Shreya Shankar's error-analysis-first eval practice):

1. **Benevolent dictator = the owner.** One trusted grader hand-labels the golden set (the ground truth) — not a committee. The eval encodes *their* taste by design.
2. Run each judge rubric over the same set.
3. **Build the confusion matrix per dimension — do NOT trust raw agreement %.** A judge that "agrees 90% of the time" is worthless when the failure is rare (10% failure rate → 90% agreement by always saying "pass"). Look at the off-diagonal — **false positives and false negatives separately** — and drive *both* toward zero. Use EvalGen's published vocabulary: a judge's alignment = **coverage** (fails the entries you graded bad) + a low **false-failure-rate** (doesn't fail the ones you graded good). Generate *several* candidate judge prompts per dimension and keep the most-aligned — don't hand-write one and trust it.
4. Where the judge disagrees, revise the *rubric wording* (not the labels) and re-run. Expect **criteria drift** (the EvalGen term): you can't fix the rubric upfront — what "arguable thesis" means sharpens only as we grade.
5. **Only build a judge for the pesky failures.** In practice a real product needs only ~4–7 judges; most failures are just missing instructions → fix the `/distill` prompt/contract, don't add an eval. If a failure mode disappears once the contract is clearer, delete its judge. And if the eval catches something wrong, *fix the entry/contract* — don't curate an eval museum.

## How & when this runs

Today (**v0**) it runs **manually / not at all** — this file is a design, not a runner. There is no wiring yet; nothing executes on its own. The proposed rollout, matching the KB's command-based, manual-first architecture (like `/triage` and `/distill`):

- **Layer 1 (code checks C1–C9) — cheap, deterministic, frequent.** No model calls, so it can run on *every* `/distill` and/or as a lightweight check when `$PERSONAL_DATA_DIR/private/kb/entries/` changes. This is the automatable half; it catches schema/governed-vocab/tier-mirror regressions the moment they happen. (Phase 2 could make it a pre-commit/CI check; not needed for v0.)
- **Layer 2 (judge checks J1–J5 + confusion matrix) — expensive, run on cadence or on-demand.** LLM calls against the golden set, too costly per-commit. Run it (a) **on-demand when the `/distill` contract changes** (the trigger that matters — does the change still align to your labels?), and (b) **periodically on a sample of recent entries**, folded into the existing monthly `/healthcheck` **Doctor** lens (it already does read-only health observations — "is `/distill` still matching the owner's judgment?" fits there). This mirrors the recommended cadence: heavy setup once, then ~30 min/week on samples.

**Proposed runner: a `/eval` command** (Phase 1.5) — `/eval [entry|--golden]` runs Layer 1 inline and, with `--golden`, runs the judges against `evals/golden/` and prints the confusion matrix per dimension. Reuses the KB's slash-command machinery instead of standing up CI. **Not built yet — flagged for your go-ahead** (paired with the held golden fixtures; the runner and the fixtures are the same next step).

## Open questions
- Do we eval `/triage` too (predicted-relevance calibration vs. the rejection log)? Likely next after `/distill`.
- Sample size for the golden set — start ~6, grow as real `/distill` failures surface (error analysis feeds the golden set); per published eval guidance, bias toward *volume of distribution-representative* examples over a few pristine ones.
