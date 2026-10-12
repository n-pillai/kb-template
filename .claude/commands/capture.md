---
description: Drop a source into the KB intake queue (no distillation yet)
---

> **Mount check (cloud/mobile first turn):** if `$PERSONAL_DATA_DIR` is unset, that is the normal
> opening state in a cloud session — **not** a reason to stop. Run the `add_repo` mount recovery
> from `.claude/hooks/mount-personal-data.sh` first, then continue this command. Fail closed only
> if the recovery itself fails. See CLAUDE.md → *Personal data lives outside this repo*.

Capture a source into `$PERSONAL_DATA_DIR/private/kb/_inbox/queue/` so it's queued for distillation. This does NOT distill or commit an entry — it just gets the source into the front door so nothing is lost.

## Steps

1. Parse the input ($ARGUMENTS): a link, a title, a pasted note, or "the thing I just mentioned." Capture whatever's there — partial is fine.
2. Write a queue file `$PERSONAL_DATA_DIR/private/kb/_inbox/queue/YYYY-MM-DD-short-slug.md` with:
   ```yaml
   ---
   captured: <today's date>
   channel: manual            # manual | automated
   source: <publication/author if known>
   url: <link if any>
   ---
   <raw note / why it might matter — verbatim, un-distilled>
   ```
3. **Dedup check** before writing: scan existing `$PERSONAL_DATA_DIR/private/kb/_inbox/queue/` and `$PERSONAL_DATA_DIR/private/kb/entries/` for the same URL (exact) or a near-identical title. If it's already captured or already an entry, say so and stop — don't duplicate.
4. Confirm: "Queued: <title>. Run `/distill` when you want it synthesized." Do NOT auto-distill — capture and distill are separate on purpose.

Capture is Tier-agnostic and never commits canonical files. It only writes to `$PERSONAL_DATA_DIR/private/kb/_inbox/queue/`.
