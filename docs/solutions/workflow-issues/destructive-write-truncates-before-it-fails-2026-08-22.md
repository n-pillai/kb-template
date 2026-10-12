---
title: A write that fails mid-flight has already destroyed the file — build the bytes before you open the target
date: 2026-08-22
category: workflow-issues
module: kb
problem_type: workflow_learning
component: tooling
severity: high
applies_when:
  - "Editing a large canonical file in place with a script (Python, Node, shell)"
  - "Any write where the content is assembled or encoded as it is written"
  - "Editing files under an integrity layer (L1 append-only / L2) where loss is the thing being guarded"
  - "A tool call fails and the next step assumes the target is untouched"
  - "Emoji, smart quotes, or any non-ASCII is being written from a generated script"
tags: [python, file-io, truncation, atomic-write, unicode, verification, canonical-files, integrity, data-loss]
---

# A write that fails mid-flight has already destroyed the file

## Context

While adding depth notes to `THEMES.md` — a 273KB canonical file in `personal-data`, the KB's
corroboration ledger — a Python edit script failed with:

```
UnicodeEncodeError: 'utf-8' codec can't encode characters in position 73035-73036: surrogates not allowed
```

The error is accurate and harmless-sounding: some escape sequences in the generated script were
surrogate halves (`"📌"`) rather than real codepoints (`"\U0001F4CC"`). Python parses those
as two lone surrogates, which UTF-8 cannot encode.

What the error does not say is that **the file was already gone.** The failing line was:

```python
io.open(p, "w", encoding="utf-8", newline="").write("\n".join(lines))
```

`open(..., "w")` truncates on open. The encode happens during `.write()` — *after* the target has
been emptied. So the traceback describes a failure to write, while the actual outcome was a
successful delete. `wc -c` returned `0`.

It then happened a **second time**, for a reason worth recording: the repair attempt was itself run
through a shell heredoc that mangled the escape sequences, so the "fixed" script was byte-identical
to the broken one. The script printed `patched`, changed nothing, and the rerun truncated the file
again. Both times the file was recoverable (`git checkout --`) because it was committed and
otherwise unmodified — which was luck about timing, not a property of the process.

## Guidance

**1. Encode before you open. The target is not touched until the bytes exist.**

```python
out = "\n".join(lines)
data = out.encode("utf-8")        # every failure that can happen, happens HERE
tmp = path + ".tmp"
with open(tmp, "wb") as fh:
    fh.write(data)
os.replace(tmp, path)             # atomic on the same filesystem
```

This converts "file destroyed, no output" into "file untouched, error printed" — the two outcomes
that a traceback cannot distinguish for you.

**2. Treat a failed write as a state change, not a no-op.**

The instinct after a traceback is to fix the script and rerun. That instinct assumes the failure was
inert. Check the target first — `wc -c`, `git status`, `git diff --stat` — *before* the next attempt,
because the second attempt often destroys the evidence of what the first one did. Here the check
happened only because the tool result mentioned the file was modified.

**3. Non-ASCII from a generated script is a live hazard, not a cosmetic one.**

Surrogate-pair escapes (`👍`) look like the emoji they represent and are not. Write the
actual character, or use the astral escape (`\U0001F44D`). Where a script is authored by generating
text into a shell, prefer writing the script to a **file** and executing it — a heredoc adds a layer
of quote and backslash mangling between what was intended and what runs, which is what turned one
incident into two.

**4. A script that reports success is not evidence the edit landed.**

The repair script printed `patched` while its `str.replace` calls matched nothing. Assert on the
substance, not the exit code: check that anchors were found (`assert anchor in s`), that the output
grew by roughly the expected amount, and that structural invariants survive (heading count, row
count, section count).

**5. Files under an integrity layer deserve the strictest version of this.**

`entries/` is L2 and `wiki/archive/` is L1 precisely because losing content is the failure mode being
designed against. A truncating write bypasses all of it — the integrity gate sees a commit, not a
crashed script, and a zero-byte file that was never committed is invisible to every check in the
fleet. The protection is upstream, in how the edit is performed.

## Why This Matters

Two independent guards existed and neither would have caught this. Git protects what is committed;
the integrity gate protects what is committed. The window between "script truncates the file" and
"someone notices" is unprotected by design, and in that window the file looks like a normal
uncommitted modification.

The deeper pattern is one this repo has now hit three times in one session, in three different
shapes: **the failure and the success produce indistinguishable local signals.** A guard that never
ran is as quiet as a guard that passed (`controls-that-appear-installed-but-enforce-nothing`). An
instruction in a channel that never loads reads the same as one that was considered and rejected
(`instructions-bind-only-in-the-channel-that-loads`). And a traceback about a failed write reads the
same whether the file is intact or empty. In every case the fix is the same move: **make the states
distinguishable before you need to tell them apart** — a third exit code, a rule in a loaded file, or
an encode step that runs before the truncate.

## When to Apply

- Any in-place edit of a file large enough that regenerating it by hand is not an option
- Scripts generating content with emoji, smart quotes, em-dashes, or any non-ASCII
- Immediately after any tool or script failure that touched a file — verify before retrying
- When editing canonical or integrity-protected content, where the loss is the thing being guarded
- When a script's output is a report of what it did rather than a diff you can read

## Examples

**The check that should follow any failed write, before the retry:**

```bash
wc -c path/to/file        # 0 is the answer you are looking for
git status -s             # ' M' on a file you thought was untouched
git checkout -- path      # restore, if it was committed and unmodified
```

**Verifying the restore rather than assuming it:**

```bash
git checkout -- private/kb/THEMES.md
wc -c private/kb/THEMES.md          # 272960
grep -c '^### ' private/kb/THEMES.md # 18 themes, matches pre-edit
```

**Asserting on substance after a successful run** — the edit above inserted five notes, so the
verification was that each landed in the section it was meant for, not that the script exited 0:

```bash
awk '/^### /{h=$2} /example-entry-slug/{print NR": "h}' THEMES.md
# 144: theme-a
# 182: theme-b
# 300: theme-c
# 347: theme-d
# 373: theme-e
```

## Related

- `../architecture-patterns/controls-that-appear-installed-but-enforce-nothing-2026-08-04.md` — the
  same indistinguishable-signals problem at the enforcement layer
- `../architecture-patterns/instructions-bind-only-in-the-channel-that-loads-2026-08-22.md` — the same
  problem at the instruction layer, from earlier the same day
- `CLAUDE.md` → *Personal data (mounted, read-write)* — the L1/L2 classes this bypasses, and why
  `entries/` being L2 is about legal *edits*, not tolerance for loss
