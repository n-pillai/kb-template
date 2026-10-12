---
title: An instruction binds only in a channel that loads — hook stdout loses to the always-loaded file
date: 2026-08-22
category: architecture-patterns
module: kb
problem_type: architecture_pattern
component: agent_instructions
severity: medium
applies_when:
  - "A recovery, exception or escape hatch is written into hook output, a doc, or any non-loaded channel"
  - "The same rule is stated in two places and one of them is CLAUDE.md or a command file"
  - "A command behaves differently depending on how the session was opened"
  - "A fix consists of strengthening the wording of an instruction that is already being ignored"
  - "Designing fail-closed behaviour for a resource that is normally absent at session start"
tags: [agent-instructions, claude-md, slash-commands, hooks, cloud-sessions, fail-closed, precedence, nondeterminism, mount]
---

# An instruction binds only in a channel that loads

## Context

On 2026-08-22 `/triage` failed in a cloud session with the personal-data mount reported unavailable.
The same command, in an earlier cloud session, had recovered the mount and worked. Same repo, same
account, same access — opposite outcomes.

Nothing was broken. In cloud, `$PERSONAL_DATA_DIR` is **never** pre-attached: `personal-data` must be
attached per session with `add_repo`, so the SessionStart clone in `mount-personal-data.sh` always
fails until that runs. An unset var on the first cloud turn is the **normal opening state**, and the
hook prints a seven-step recovery for it.

The recovery existed in exactly two channels — and neither was one that binds a slash-command turn:

| Channel | Says | Loaded when the first turn is a slash command? |
|---|---|---|
| `mount-personal-data.sh` stdout (SessionStart) | recover | In context, but competing |
| `docs/cloud-environment-setup.md` §5 | recover | **No** — never loaded at all |
| `CLAUDE.md` | *"STOP and say so"* | **Yes, always** |
| `.claude/commands/triage.md` | fail closed | **Yes, on invocation** |

Both channels *guaranteed* to load said stop, and neither mentioned that a recovery existed. So the
outcome depended on something nobody had modelled as a variable: **how the session was opened.** A
plain first message left room to act on the hook text; a slash command loaded a file whose own rules
said stop, and stopping won.

`grep -rn add_repo` over the repo's markdown made this visible in one line — every hit was in the
docs file, none in `CLAUDE.md`, none in any command.

## Guidance

**1. Put the exception in the same channel as the rule it qualifies.**

A rule and its escape hatch that live in different channels are not one rule with an exception; they
are two instructions, and the louder channel wins. If `CLAUDE.md` says STOP, the "unless you can
recover" clause must be in `CLAUDE.md` — not in a hook, not in a doc, not in a comment.

**2. Strengthening the wording in the losing channel is not a fix.**

An earlier commit (`f5d547f`) had already met this failure and responded by making the hook's own
output more emphatic — "run these steps NOW, before you answer the user's first message, whatever that
message is." That is the one channel structurally competing with `CLAUDE.md`, so more force there
could not settle it. **When an instruction is being ignored, ask which channel is beating it before
rewriting it.** Escalating tone inside a losing channel produces a rule that works sometimes, which
is worse than one that fails consistently — the intermittency reads as a flaky environment.

**3. Test the precedence question directly: `grep` for the escape hatch in the loaded files.**

```bash
grep -rn "add_repo" --include=*.md .        # every hit in docs/, none in CLAUDE.md
grep -rn "add_repo" .claude/commands/       # nothing
```

If the recovery for a fail-closed rule does not appear beside that rule, the rule is unconditional in
practice regardless of what the design intends.

**4. A rule stated as an absolute will be applied as one.**

"Fail closed: STOP and say so" is deliberately absolute, and that is correct where it applies. But it
was written for the desktop case (`setx` sets the var; absence is genuinely anomalous) and then
inherited by cloud, where absence is *routine*. **The same condition meant different things in the
two environments, and the rule named only one of them.** Split the rule when the condition's meaning
is environment-dependent, rather than trusting the reader to infer which case they are in.

**5. Duplication across channels is correct here — say so in the copies.**

The fix states the recovery in three places (`CLAUDE.md`, four command headers, the §5 doc). That is
intentional redundancy across loading contexts, not sloppiness. Each copy should say it is a copy and
name the others, or the next editor will "clean up" the duplication and reopen the hole.

## Why This Matters

Nondeterministic instruction-following is expensive to diagnose because it presents as environment
flakiness. Two identical-looking sessions diverged, and the first instinct was to look for a broken
clone, a revoked token, or a changed proxy — none of which existed. The real variable was invisible:
which files the harness happened to load before the agent decided.

This is a distinctively agent-shaped bug. In ordinary software, precedence between two conflicting
rules is decided by code you can read. Here it is decided by what is in the model's context and how
forcefully each part is phrased — so **"where does this instruction live?" is a design decision with
correctness consequences**, not documentation housekeeping.

It also compounds a rule already established workspace-wide: *rules that must survive a cloud session
have to be committed to the repo* (a cloud sandbox clones one repo and never sees the parent
`CLAUDE.md`). This adds the next refinement — committed is necessary but not sufficient.
`docs/cloud-environment-setup.md` is committed, travels perfectly, and still binds nothing, because
no session loads it. **Committed → travels. Loaded → binds. They are different properties.**

## When to Apply

- Writing any conditional exception to a fail-closed, refuse, or stop rule
- Adding a self-healing or recovery step for a resource that is normally absent at session start
- When a command works from one entry point and not another, with no code difference between them
- Before responding to a not-followed instruction by making it louder
- When a session's behaviour depends on whether the first turn was a slash command or a plain message
- Reviewing hook `stdout` intended as agent guidance — ask what always-loaded file contradicts it

## Examples

**The channel inventory that should be run for any agent-facing rule.** For each place the rule or
its exception appears, ask when it enters context:

| Channel | Enters context |
|---|---|
| Root `CLAUDE.md` (parent dir) | Desktop only — a cloud clone never sees it |
| Repo `CLAUDE.md` | Always, every session |
| `.claude/commands/<cmd>.md` | On invocation of that command |
| SessionStart hook stdout | Every session, but competes with the above |
| `docs/**` | Only if something reads it — assume never |
| Skill body | On skill invocation |
| Skill *description* | Always — which is why identifying specifics must never live there |

**The fix, in the shape the diagnosis implies.** The rule became two rules, each naming its
environment:

```markdown
- **Mount first, in a cloud/mobile session — then fail closed.** In cloud, `$PERSONAL_DATA_DIR` is
  **never** pre-attached ... An unset var there is therefore the **normal opening state, not a
  verdict.** Run the recovery ... **before answering the first message, whatever that message is** —
  including when it is a slash command.
- **Fail closed:** if `$PERSONAL_DATA_DIR` is unset or missing **and the recovery above has failed
  or does not apply** (desktop, where the var comes from `setx`), **STOP and say so.**
```

Plus a banner in `triage.md`, `distill.md`, `shelve.md` and `capture.md` — the four commands that
read the mount — because a command file is the *other* channel guaranteed to load on the turn that
matters.

## Related

- `controls-that-appear-installed-but-enforce-nothing-2026-08-04.md` — the same silence problem one
  layer down: there a guard was present and unwired; here an instruction was present and unloaded
- `docs/cloud-environment-setup.md` §5 — the `add_repo` recovery in full, and why there is no
  environment-level pre-attach
- `.claude/hooks/mount-personal-data.sh` — the seven steps, and the deliberate choice never to block
  a session
- `CLAUDE.md` → *Personal data (mounted, read-write)* — where the rule now lives, with the reason
