# Design — a Signal Ledger knowledge base

The short form of the design behind this template. `CLAUDE.md` is the operating contract Claude
follows; this file explains *why* it is shaped that way.

## 1. What it is

A private, synthesized reference layer for everything you read, listen to or watch — the system of
record for *what you've learned and why it matters to your work*.

It fuses two ideas:

- **Automated capture** (the strength of most content-curation pipelines): markdown + git as the
  store, frontmatter as the database, dedup, idempotent runs, cost tracking.
- **Governed synthesis** — the **Signal Ledger**: distill don't summarize, tie every source to
  active work, track corroboration over time.

Capture without synthesis just relocates the backlog. The design rule is: **automate the intake,
govern the synthesis, protect the concept graph.**

One brain in, many readers out. This repo is the single writer of the canonical files. Other agents
you run may read freely and may *refer* a source or *propose* a change; they never distill or commit.

## 2. Two relevance gates

| Gate | When | Question | Command |
|---|---|---|---|
| **Triage** | before you consume it | Is this worth my attention at all? | `/triage` |
| **Signal Ledger** | after you consume it | Does what I learned tie to my work? | `/distill` |

The Signal Ledger can only run on something you've already read. Triage exists because the
expensive step is the reading — or, for podcasts, the hours of listening.

**The triage bar scales with consumption cost.** Links get a generous filter (keep a maybe; sorting
later is cheap). Podcasts are ranked strictly on proxies — show, guest, title, description — into a
listen-list: **rank, then listen, then distill**, never transcribe-everything-then-distill.

**Triage is three-way, not keep/drop.** A source has two independent axes: a *work tie* (→ queue →
distill) and *learning value* (→ library shelf, kept). Only a source with neither — spam, noise,
duplicates — goes to the append-only rejection log. "No work tie" alone is never a drop.

## 3. The Signal Ledger

1. **Distill, don't summarize** — 3–5 bullets of what it means for your work.
2. **Lead with "so what"** — tie to a listed project (`active`/`parking`) or an active
   (watch/confirmed) theme. Investing and writing are work too: a source that advances a thesis you
   track is signal even with no build project. No tie → library, not entries.
3. **Log negative signal** — "not useful because X" calibrates future intake.
4. **Corroboration tiers** — 1 source *parking*, 2 independent *watch*, 3+ *confirmed*.
   Independent = distinct author **and** outlet. Shared authors, networks or origins are recorded
   as a caveat on the theme, so volume of mentions never passes for convergence. An absence is
   evidence about the speaker, not their organization.
5. **Write to the right place** — entry, theme tracker, catalog; concept pages only by proposal.

A good entry can be argued with by someone who hasn't read the source.

## 4. Two commit tiers

- **Tier A — entries auto-commit.** Each is self-contained and easy to revert. "Auto" means no
  approval prompt, not unattended: it still lands through a branch.
- **Tier B — the concept graph is proposed.** Concept pages accumulate across many sources; that is
  where a careless merge does the most damage, so every change is staged and approved in a batch
  ("this touches these pages — approve / edit / skip?").

## 5. Reading it back

- **Push:** `/digest` — new since yesterday (one line each: source · thesis · so-what · tier),
  theme movement, and proposals awaiting your nod.
- **Pull:** three levels of zoom — concept (`wiki/`) → evidence (`entries/`) → source (link or
  transcript timestamp). "What do I know about X?" returns the concept page, not a re-scan.

## 6. The library

A second front door for things worth knowing with no current tie. Cards are deliberately
un-distilled pointers (*what it is* / *why I might want it later*), outside the signal counts.
When a tie emerges, `/distill` promotes a card into a full entry and removes it. A card reaches the
concept graph only through an entry and then the Tier-B gate. `/healthcheck` sweeps the shelf
monthly so it stays a staging shelf, not a graveyard.

## 7. Content and machinery are separate repos

The machinery (this repo) can be shared; the content cannot. Content lives in a private repo at
`$PERSONAL_DATA_DIR/private/kb/`:

```
entries/      one .md per source (Tier A)
library/      non-signal pointers
wiki/         one .md per concept (Tier B); wiki/archive/ for retired pages
_inbox/       triage/ (listen-list, rejected-log) · queue/ (awaiting distill) · proposals/ (Tier B)
THEMES.md     corroboration tracker
INDEX.md      catalog of entries + concepts
projects.md   the governed project lens
```

Every command fails closed when `$PERSONAL_DATA_DIR` is missing — it stops instead of falling back
to in-repo paths or reconstructing content from memory.

## 8. Lifecycle

- **`projects.md` is the lens** that `/triage`, `/distill` and `/healthcheck` all read. Each project
  has a slug, one line, and a status: `active` · `parking` · `dormant`.
- **Project status drives KB lifecycle.** A new project makes shelved cards candidates for
  promotion. A project going `dormant` makes themes and concept pages whose only ties are dormant
  candidates for archiving. Detection is automated; every mutation is proposed in `/healthcheck`.
- **Retirement is archival, never deletion.** Entries are permanent — a dated record of what you
  read and what it meant then. Themes move to a dormant section. Concept pages move to
  `wiki/archive/` with a tombstone at the old path, so links never break.

## 9. Maintenance lenses (`/healthcheck`)

One monthly command, two report sections, both propose-only:

- **Janitor (hygiene)** — stale themes, duplicate concepts to merge, orphaned entries, dead links,
  secondhand evidence (a number credited to whoever repeated it instead of who produced it),
  accumulated fetch cache.
- **Doctor (health of the thinking)** — confirmation bias, theme balance, negative-signal ratio, and
  **is it compounding?**

## 10. The primary risk is the habit

For a single-user KB the existential risk isn't mangling — it's that you stop opening it. The
"distill, don't summarize" gate is both the design's strength and its highest-friction step. So the
Doctor watches a falsification tripwire: if intake falls while reading holds, or time-per-distill
climbs, loosen the gate (batch distillation; capture now, distill weekly). The explicit failure
signal is ~3 months where the library grows but entries and confirmed themes don't.

## 11. Security notes for automating intake

If you add unattended fetching:

- **Fetched content is untrusted input** flowing into an agent that commits. Quarantine it in the
  queue; commit a distilled entry only after a structural check (known fields only; no embedded
  instructions, raw HTML, paths or git commands).
- **PII scan before commit** — a hit goes to your review, not to `main`.
- **Scope credentials** (read-only mail scopes, keys in the OS credential store, never in the repo).
- **Make field-scoping a mechanism, not a convention**: proposals from other agents are structured
  (target file, field, append-only op, value) and validated before they are applied.

## Credits

The Signal Ledger rules are adapted from PJ Hoberman's Signal Ledger. The capture side draws on Sandhya
Simhan's "Automated Content Curation" teardown (GitHub Actions cron, Deepgram transcription,
markdown/git store).
