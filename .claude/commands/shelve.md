---
description: File a source on the non-signal reference shelf ($PERSONAL_DATA_DIR/private/kb/library/) — kept for later, no distillation
---

> **Mount check (cloud/mobile first turn):** if `$PERSONAL_DATA_DIR` is unset, that is the normal
> opening state in a cloud session — **not** a reason to stop. Run the `add_repo` mount recovery
> from `.claude/hooks/mount-personal-data.sh` first, then continue this command. Fail closed only
> if the recovery itself fails. See CLAUDE.md → *Personal data (mounted, read-write)*.

Put a source on the **library shelf** (`$PERSONAL_DATA_DIR/private/kb/library/`) — the non-signal reference path. Use this when something is worth knowing but has **no current tie** to a listed project (`active` or `parking` — see `projects.md`), so it doesn't belong in the Signal Ledger. This does NOT distill, does NOT run the ledger, and never touches `$PERSONAL_DATA_DIR/private/kb/THEMES.md` or the signal catalog. It just keeps a pointer so nothing is lost.

`/shelve` is the second front door (the first is `/capture` → distill). The test: *"Do I have a 'so what' tie to a named project?"* → no, or only a weak/speculative one → shelve it. Yes → `/capture` + `/distill` instead.

## Steps

1. Parse the input ($ARGUMENTS): a link, a title, or a note. If it's a URL, you may fetch it to fill in title/source via the **escalation ladder** (CLAUDE.md → *Source fetching*): `fetch-docs` (default) → **`--render`** on an empty SPA shell (needs `agent-browser`) → WebFetch → **manual paste/OCR** for auth-walled pages. Never pass `--slug`/`--md`. Read only enough of the fetched file to get title/source/type — keep the card a *pointer* — do NOT distill or extract load-bearing specifics, and never fabricate quotes/numbers for a source you couldn't read.
2. **Dedup check** before writing: scan existing `$PERSONAL_DATA_DIR/private/kb/library/`, `$PERSONAL_DATA_DIR/private/kb/entries/`, and `$PERSONAL_DATA_DIR/private/kb/_inbox/queue/` for the same URL or a near-identical title. If it already exists anywhere, say so and stop.
3. Write a card `$PERSONAL_DATA_DIR/private/kb/library/YYYY-MM-DD-short-slug.md`:
   ```yaml
   ---
   shelved: <today's date>
   title: <source title>
   type: essay | article | podcast | book | post | ...
   source: <author / publication>
   url: <link if any>
   topics: [free-text]          # ungoverned — the library isn't signal, so tags stay loose
   writer: owner                # provenance: kb | owner | <agent-name>
   ---

   **What it is** — one line.

   **Why I might want it later** — one line: the latent hook (a *candidate* future tie), not a committed "so what."
   ```
4. **Update `$PERSONAL_DATA_DIR/private/kb/INDEX.md`** — add a row to the **Library** section only. Do NOT touch the entries catalog or the themes summary.
5. **Listen-list auto-trim** — if the shelved source matches a row in `$PERSONAL_DATA_DIR/private/kb/_inbox/triage/listen-list.md` (match on URL, else show + episode title), **remove that ranked row and append a line to the "Consumed (off-list)" section** noting the disposition (`shelved → [[library-card-slug]]`), in the same commit. **Idempotent:** if no row matches (the source never came from the listen-list, or it's already trimmed), do nothing — don't error. This mirrors `/distill`'s trim (step 9): the *library/learning* lane's exit cleans the listen-list the same way the work-tied lane does, so a consumed episode never lingers in pre-consumption state.
6. **Commit** — card + `$PERSONAL_DATA_DIR/private/kb/INDEX.md` + any listen-list trim on the feature branch (low risk, append-only, like Tier A). No `$PERSONAL_DATA_DIR/private/kb/wiki/`, no `$PERSONAL_DATA_DIR/private/kb/THEMES.md`.
7. Confirm: "Shelved: <title> in `$PERSONAL_DATA_DIR/private/kb/library/`. Run `/distill $PERSONAL_DATA_DIR/private/kb/library/<file>` if a project tie ever emerges."

The library is a staging shelf, not a graveyard: when a tie appears, `/distill $PERSONAL_DATA_DIR/private/kb/library/<file>` promotes the card into a full `$PERSONAL_DATA_DIR/private/kb/entries/` entry and removes it from the shelf.
