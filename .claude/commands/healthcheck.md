---
description: Monthly KB audit — two lenses (Janitor hygiene + Doctor health). Propose-only, read-only.
---

The Signal Ledger monthly health check (see `docs/design.md`). **One command, two report sections.** Read-only over canonical files; it **proposes**, it never writes or deletes. Run monthly. This is the bet-protecting check: a synthesis brain with falling intake is worse than a bookmark pile, so this watches for that.

Load the lens first: `$PERSONAL_DATA_DIR/private/kb/projects.md` (active/parking/dormant), `$PERSONAL_DATA_DIR/private/kb/THEMES.md` (tiers + caveats), `$PERSONAL_DATA_DIR/private/kb/INDEX.md`, `$PERSONAL_DATA_DIR/private/kb/entries/`, `$PERSONAL_DATA_DIR/private/kb/library/`, `$PERSONAL_DATA_DIR/private/kb/wiki/`.

---

## Section 1 — 🧹 Janitor (hygiene)

File/graph cleanliness. Emits **proposals**, never auto-applies.

1. **Library sweep (Phase-1 manual Librarian).** Re-read every `$PERSONAL_DATA_DIR/private/kb/library/` card's "why I might want it later" hook against the *current* `$PERSONAL_DATA_DIR/private/kb/projects.md` + `$PERSONAL_DATA_DIR/private/kb/THEMES.md`. A card whose latent hook now ties to an **active/parking project or a watch/confirmed theme** → propose promoting it: *"`<card>` now ties to `<project/theme>` — run `/distill $PERSONAL_DATA_DIR/private/kb/library/<card>` to promote?"* (This is the manual stand-in until the Librarian agent ships.)
2. **Stale themes.** `watch`/`parking` themes with no new corroboration in ~6+ weeks → flag *confirm-or-drop*. Note any `parking` theme still one independent source short (name the missing-source type).
3. **Dead links & orphans.** `entries`/`library` URLs that 404 (spot-check); `$PERSONAL_DATA_DIR/private/kb/wiki/` pages with no backing `$PERSONAL_DATA_DIR/private/kb/entries/`; `$PERSONAL_DATA_DIR/private/kb/entries/` whose `projects:`/`themes:` point at slugs no longer in `$PERSONAL_DATA_DIR/private/kb/projects.md`/`$PERSONAL_DATA_DIR/private/kb/THEMES.md`.
4. **Governance drift.** Tags used that aren't in `tags.md`; `projects:` slugs not in `$PERSONAL_DATA_DIR/private/kb/projects.md`; entries that slipped in with no project AND no theme tie.
5. **Corroboration-tier integrity.** Verify each theme in `$PERSONAL_DATA_DIR/private/kb/THEMES.md` has **exactly one** `corroboration_caveat` and that every backing source's independent-vs-depth label still holds (distinct author AND outlet; same-author or same-network = depth, not a count). Check that each entry's `signal_tier` matches its **primary theme's current tier** (a theme promotion that didn't re-tier its counted legs is the common drift) and that `$PERSONAL_DATA_DIR/private/kb/INDEX.md`'s Tier column agrees with the entry frontmatter. Propose fixes; don't apply. *(Until the agents ship, this is the manual home for the corroboration-independence audit.)*
6. **Secondhand-evidence audit (borrowed & contested stats).** Entries inherit numbers from sources that are themselves only *citing* someone else — a vendor newsletter quoting a study, a podcast quoting a report. The number arrives wearing the primary's authority with none of its scrutiny. Sweep `$PERSONAL_DATA_DIR/private/kb/entries/` for load-bearing stats and check three things:
   - **Attribution depth.** Is the stat credited to the **primary** (the study/report that produced it) or to the **intermediary** who repeated it? An entry crediting a consultancy for a number that is a university lab's is misattributed → propose the fix.
   - **Echo-vs-corroboration (the one that touches tiers).** If the same underlying stat reaches the KB through ≥2 *different* intermediaries, that is **one primary echoing**, not two independent legs — the distinct-author-AND-outlet rule applies to the **evidence**, not just the byline. Cross-check the affected theme's `corroboration_caveat` and propose a line naming the shared primary.
   - **Stacked interest.** Flag any borrowed stat where **both** the intermediary and the primary have a commercial stake in the conclusion (the intermediary sells the remedy; so does the study's sponsor). That's the highest-risk shape — two layers of interested framing behind one number that reads as neutral.

   Propose one of: attribute to the primary · add a contested-evidence caveat · or demote the claim from **evidence** to **discourse artifact** (record *that* a number is widely cited without asserting it's true). *Worked example: a research report's "95% of pilots never produce measurable impact," arriving via a consultancy newsletter that sells the remedy, from a report that itself endorses its sponsor's product as the fix — and whose own figures imply ~75%, not 95%.*
7. **Modified-entry review (the detective check).** `entries/` admits in-place
   edits, bound by the edit discipline (corrections or
   governed field appends, never re-summarization). List every commit since the last healthcheck
   that **modified an existing entry**:
   `git -C "$PERSONAL_DATA_DIR" log --since="<last healthcheck>" --diff-filter=M --oneline -- private/kb/entries/`
   For each, read the diff and confirm it is a correction/append rather than a rewrite that could
   distort evidence (the laundering failure modes are the checklist: dropped hedges,
   self-reports upgraded to measurements, migrated attributions). Nothing found → report "no entry
   modifications." A violation → propose `git revert` of that commit. *(This check is what converts
   the retired no-touch guarantee into a detectable event.)*
8. **Fetch-cache sweep (`/tmp/fetch-docs-*`).** The intake fetcher (vendored `fetch-docs` skill) caches raw pages in `/tmp/fetch-docs-*`, and MSYS `/tmp` is **not auto-cleaned on Windows** — they accumulate until swept. Report the count + total size (`ls /tmp/fetch-docs-* 2>/dev/null | wc -l` · `du -ch /tmp/fetch-docs-* 2>/dev/null | tail -1`), then **propose the sweep**: *"N cached fetches, ~X MB — sweep with `rm /tmp/fetch-docs-*`?"* On your nod, run it directly — these are regenerable 24h-cache scratch files **outside the canonical KB**, so the sweep is the one Janitor proposal that executes on approval rather than flowing through a PR. Nothing found → report "fetch cache clean." *(Manual stand-in until the sweep is automated with the Phase-2/3 agents.)*
9. **Absence-derived claims audit.** Some of the KB's sharpest rulings rest on what a
   source *didn't* say — a notable absence, logged deliberately. Those are legitimate, and they are
   also the ones that rot silently, because nothing about a missing sentence gets re-examined when a
   later source arrives. Sweep for them:
   `grep -rniE "names no|describes no|no budget|no cap|never (mentions|treats|reaches)|absent|does not (mention|describe)" "$PERSONAL_DATA_DIR/private/kb/THEMES.md" "$PERSONAL_DATA_DIR/private/kb/wiki/"`
   For each hit, ask **who the claim is about**: if it is scoped to the speaker (*“Speaker A names no budget”*)
   it stands; if it has drifted into a claim about the **organization** (*“the company does no token
   accounting”*) and only one voice from that org has ever been distilled, propose **rescoping it to the
   speaker** and note the open check. Where a second voice from the same org *has* since been distilled,
   propose reconciling the two.
   ⚠️ Absences that moved a **theme statement or scope note** are the priority; absences recorded as
   entry-level colour are low-stakes.
10. **Transcript proper-noun audit.** Entries distilled from machine transcription
    carry a class of error nothing else in this audit catches: the *argument* is primary but every
    *proper noun* is secondary, and a corrupted name reads as valid prose. Build the affected set —
    `grep -rlE "usetranscribe\.io|youtube\.com/watch|auto-generated captions" "$PERSONAL_DATA_DIR/private/kb/entries/"`
    — and for each entry test three things:
    - **Metadata agreement.** Do the entry's `title:` and `source:` match the page's own `<title>` /
      `og:title`? Re-fetch and read only the head; it is cheap. A mismatch means the entry was
      written off the ASR body rather than the metadata.
    - **Hapax entities (the sharp one).** Any company, person or product named in such an entry that
      appears **nowhere else in the KB and nowhere in the source metadata** is the suspect class —
      that is precisely the shape of a silent substitution. Cross-check each against `INDEX.md` and
      `THEMES.md`, where the KB's own spelling is canonical.
    - **Unresolved names still marked.** Anything carrying `(unverified)` from an earlier pass: has a
      later source settled it? Resolve or restate the gap; never quietly drop the marker.
    ⚠️ **Priority order is the same as §1.9's:** a corrupted **author or outlet** is urgent, because
    the distinct-author-AND-outlet independence test is computed on those two strings and a wrong one
    can have produced a **false independence verdict** — re-check any tier move that leaned on it.
    A corrupted name in entry-body colour is low-stakes. Propose in-place corrections (legal under
    the L2 edit discipline — a correction, not a re-summarization).
11. **Method-note promotion sweep.** The KB records its own process findings *inside
    the artifact that provoked them* — an entry, a theme note, the rejection log — which is the one
    place nothing ever re-reads. A finding filed there is **correct and inert**. This check converts
    an unread recommendation into a tracked one, the same move §1.7 made for entry modifications.
    Sweep for the markers the KB actually uses:
    `grep -rniE "method note|method datapoint|should be a standing|worth logging as a pattern|worth a \`?/[a-z]+\`? amendment|worth a \`[a-z_]+\` term|the cheapest fix|standing \`?/healthcheck" "$PERSONAL_DATA_DIR/private/kb/entries/" "$PERSONAL_DATA_DIR/private/kb/THEMES.md" "$PERSONAL_DATA_DIR/private/kb/wiki/" "$PERSONAL_DATA_DIR/private/kb/_inbox/"`
    For each hit, ask **one** question — *does a rule implementing this exist?* — and grep the
    machinery for it (`.claude/commands/*.md`, `CLAUDE.md`, `docs/design.md` in this repo).
    Classify each: **promoted** (a rule exists — cite it) · **open** (no rule, still valid) ·
    **superseded** (overtaken by a later decision — say which).
    - ⚠️ **Age and recurrence are the signal, not the wording.** An open note older than one audit
      cycle is the finding; **the same note recorded independently in two or more artifacts is the
      strongest promote signal there is** — the KB re-derived it rather than recalling it. Report
      both numbers per open note (days since first recorded · times recorded).
    - ⚠️ **The finding and the fix live in different repositories** — notes accumulate in
      `personal-data`, rules live in this repo — so neither repo's own history shows the mismatch,
      and no single-repo review can catch it. That is why this check has to read across both.
    - **Propose one disposition per open note:** promote it to a named file, retire it with a
      reason, or keep it open **with its recurrence count recorded**, so the next audit sees a
      number going up rather than re-reading prose.
    📌 **Why this exists.** The transcript proper-noun failure (§1.10) was first diagnosed inside
    an entry, in terms nearly identical to the rule it eventually became — including the sentence
    *"it should be a standing check whenever a transcript is the evidence path"* — then
    re-diagnosed from scratch twice more, and only became a rule after a near-fabrication forced it.
    **Three independent diagnoses, zero recall.** Detection was never the problem.

## Section 2 — 🩺 Doctor (health of the thinking)

Not file hygiene — the health of *how* the KB is being used. Emits **observations**, not file moves.

1. **Abandonment tripwire (the load-bearing one).** Track **intake-per-week against reading volume** and **time-per-distill**. Failure signal: intake falling while reading holds, or per-distill time climbing, or **~3 consecutive months where `$PERSONAL_DATA_DIR/private/kb/library/` grows but `$PERSONAL_DATA_DIR/private/kb/entries/` and confirmed themes don't.** If tripped: recommend *loosening* the gate (batch distillation; capture-now-distill-weekly) before the habit breaks. State plainly whether the tripwire is currently clear or tripped.
2. **Is-it-compounding.** Is each pass faster than the last? Is "what do I know about X" actually replacing re-searching the web for things already read? If not, the KB is accumulating, not compounding — say so.
3. **Confirmation bias.** Are themes only accruing sources that agree? Flag any theme with zero dissenting/`negative` entries. Report the **negative-signal ratio** (negative entries / total). **Then ask the repetition question:** is a belief here held because it was *verified*, or because it was *repeated*? A stat met three times in three newsletters is one stat met three times — read the Janitor's secondhand-evidence findings (§1.6) for whether the KB's most-repeated claims trace back to a single contested primary.
4. **Theme balance.** Distribution across parking/watch/confirmed; anything stuck at parking too long; over-concentration in one area.

---

5. **Established, or merely unmentioned?** For the beliefs this KB is currently
   leaning on, separate *“I checked and it is so”* from *“nobody raised the alternative.”* The second
   feels identical to the first from inside — a claim nothing contradicts reads as settled. Name one
   belief per audit that is resting on silence rather than evidence, and say what would test it. (Sibling of Doctor §2.3's repeated-vs-verified question, one level down: that one asks why I believe a
   claim I've heard often; this one asks why I believe a claim I've never heard challenged.)

6. **Named, or verified?** Sibling of §2.3 (repeated vs verified) and §2.5
   (established vs unmentioned), one layer lower: those ask why I believe a *claim*; this asks
   whether I ever checked that an *entity* is what the source called it. Reading a name in a
   transcript feels identical to knowing the name — and if the name is wrong, everything built on
   it is confidently wrong while looking fully sourced. Name one entity per audit that the KB
   asserts and has never seen outside a single machine-transcribed source, and say what would
   confirm it.

7. **What have I learned twice?** Janitor §1.11 counts unpromoted method
   notes; this asks the uncomfortable version. Find one thing the KB worked out, wrote down, and
   then worked out again later without recognising it — the tell is two artifacts reaching the same
   conclusion from scratch, months apart, neither citing the other. Re-derivation feels like
   insight, which is why it never registers as waste: the second time is as satisfying as the
   first. Name one, and say what would have made the first note findable at the moment the second
   was being written. **If the answer is repeatedly "nothing" — the notes are fine and nobody
   re-reads them — the problem is the store, not the discipline.**

---

## Output

Two clearly-headed sections (Janitor proposals · Doctor observations), each tight: the finding + the one recommended action. Lead with the **abandonment tripwire status** — it's the bet the whole system rides on. Janitor proposals flow through the same "Awaiting your nod" approval as Tier-B concept changes; nothing is applied by this command.

**Phase note:** Phase 1 runs all checks **manually** here. The automated Librarian/Janitor/Doctor agents are Phase 2/3 — they run this same logic on a schedule and refer/propose instead of being invoked by hand.
