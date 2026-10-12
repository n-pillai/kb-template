# Pattern: another agent proposes project changes

> **Not included in this template.** This is part of the author's own setup, where a separate
> chief-of-staff agent owns the project list. It is described here, not shipped, because it
> depends on that other agent. In the template, you edit `projects.md` by hand.

## The problem

`projects.md` is the lens the Signal Ledger ties every entry to. If you already run an agent that
tracks your projects (a task manager, a chief-of-staff agent), keeping a second list by hand means
two lists that drift. But letting that agent edit the KB's files directly makes it a second writer
of a file the KB owns.

## The pattern: the other agent proposes, the KB applies

1. **The other agent writes one proposal file per change** into
   `$PERSONAL_DATA_DIR/private/kb/_inbox/proposals/`, named `<UTC yyyymmddTHHMMSSZ>-<agent>-project-status.md`:

   ```yaml
   ---
   from: <agent>
   type: project-status
   sent: 2026-10-04T04:15:19Z
   slug: example-project
   status: active        # active | parking | dormant
   ---
   One line: what the project is.
   One line: why the status is what it is.
   ```

   The agent does its own mapping from its pipeline to a status. The KB receives the status; it does
   not read the other agent's files.

2. **A `/projects` command applies them**, oldest first:
   - new slug → added under its status section;
   - existing slug → status changed, line moved to the matching section;
   - `dormant` → moved to *Dormant projects*, **never deleted** (old entries still reference it).

   Applied proposals are deleted in the same commit, on a `write/kb-projects-<timestamp>` branch.

3. **Applied without asking — with two exceptions.** Which projects exist is the other agent's fact
   to state, not a KB judgment, so there is no approval prompt. But:
   - a proposed slug that **looks like a duplicate** of an existing one is left in place and asked
     about (two slugs for one project split its entries);
   - a proposal the command **can't read** (wrong type, missing slug, unknown status) is left in
     place and reported. A proposal is never silently dropped.

4. **Checked where the lens is read.** `/distill` and `/triage` run the procedure first, before the
   tie check, so they never judge against a stale list. `/digest` and `/wrap` report how many are
   waiting.

5. **Hand edits stop.** Once this is on, change a project in the other agent, not in
   `projects.md` — a hand edit is overwritten by the next proposal for that slug.

## Why this shape

- **One writer per file.** The other agent never edits KB files; the KB never edits the other
  agent's. The inbox folder is the only shared surface, and it is add-only for the sender.
- **No inferred diffs.** An earlier version synced by diffing the two lists and asking about every
  difference. A proposal is the owner of the fact stating the change outright, so there is nothing
  to infer and nothing to approve.
- **What the status change triggers is still gated.** A project going dormant makes its themes and
  concept pages *candidates* for archiving; `/projects` reports that and `/healthcheck` proposes
  it. Nothing is archived without your approval.
