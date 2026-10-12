---
title: A branch prefix that is secretly a trigger fails open — the wrong name strands work with every gate green
date: 2026-08-27
category: architecture-patterns
module: kb
problem_type: silent_failure
component: personal_data_write_topology
severity: high
applies_when:
  - "A branch/path/tag naming convention is also the trigger condition for automation (CI filter, webhook, bot)"
  - "An outer layer (platform harness, CI template, framework default) picks a name your repo's convention also wants to pick"
  - "The wrong value produces no error anywhere — the automation simply never fires"
  - "A rule is stated only in CLAUDE.md or docs and competes with a per-session instruction block"
  - "Reviewing whether 'all checks green' actually means 'the pipeline ran'"
tags: [write-topology, auto-merge, branch-naming, trigger-vs-convention, silent-failure, cloud-sessions, harness-defaults, precedence, fail-open, pretooluse-hook, enforcement-not-instruction]
---

# A branch prefix that is secretly a trigger fails open

## Context

On 2026-08-27 a cloud session ran a full `/triage` → `/distill` → Tier-B pass on a podcast episode.
Five commits landed in `personal-data`, `integrity-gate` ran and passed on every push, and the
session reported success accurately at each step. Nothing merged. `main` had not moved, and the
only way to find out was a human asking "is there a PR to merge?" — the answer was no, and there
never would have been one.

The commits were on `claude/transcribe-triage-49zrdu`. `personal-data`'s `auto-merge.yml` triggers
on `push` to `write/**` and `sync/auto`. Those are the only two prefixes in the repository that
cause a PR to be opened and merged.

## Root cause — two independent faults, and the second is what made it silent

**1. The `write/` prefix is load-bearing and does not look it.** `CLAUDE.md` described it the way
you would describe a naming convention: *"WRITES go via a branch: `write/kb-<cmd>-<timestamp>`."*
Read as a convention, a differently-named branch is untidy. Read correctly — it is the **trigger
condition for the entire merge apparatus** — a differently-named branch is inert. Nothing in the
wording distinguished those two readings, and the distinction is the whole behaviour.

**2. Every guard that could have caught it was scoped to the branch that was already correct.**
This is the part worth internalising:

| Control | Trigger | On `claude/**` |
|---|---|---|
| `integrity-gate.yml` | `push: "**"` | **runs, and passes** |
| `auto-merge.yml` | `push: write/**`, `sync/auto` | never fires |
| `pr-text-scan.yml` | `pull_request` | never fires (no PR exists) |
| `pii-alert.yml` | `push: main` | never fires |

The one control that *did* run is the one that says the content is fine. So the Actions list was
solid green, which is worse than a red X: it actively signalled health. A workflow that never
fires is **absent** from that list rather than failing in it — the same trap this repo already
recorded in `personal-data` on 2026-08-22, when `pr-text-scan` sat dark for two weeks behind a
bot-opened PR while everything looked green.

**Why the session chose the wrong name.** The Claude Code Remote harness injects a "Git Development
Branch Requirements" block naming one generated branch — `claude/<slug>-<session-id>` — and applies
it to **every attached repo uniformly**. It is a platform default computed before any repo's
`CLAUDE.md` is read, so it cannot know that one of those repos keys its automation to a prefix. The
block is also emphatic ("NEVER push to a different branch without explicit permission"), so the
session correctly treated it as binding and correctly noted that both candidates were non-`main`,
which is the invariant that actually protects the data.

## Why the obvious fix was the wrong one

The rule already existed, in `CLAUDE.md`, in plain language. It lost to a per-session block that is
louder: injected fresh each session, naming a specific branch, phrased as a prohibition. Rewriting
the `CLAUDE.md` sentence more forcefully is the same move that already failed — twice, counting
[[instructions-bind-only-in-the-channel-that-loads-2026-08-22]], where the mount recovery lost to
the same class of competition. An instruction cannot reliably win against another instruction with
better placement, and "state it more firmly" has now been tried and observed to fail.

## Fix (2026-08-27) — enforcement, then instruction, then detection

1. **`.claude/hooks/write-branch-gate.sh` + `.py` (PreToolUse `Bash`) — the actual guarantee.**
   Inspects every Bash call; when the command is a `git push` whose target clone's `origin` URL
   contains `personal-data` and the resolved ref is not `write/**` or `sync/auto`, it exits **2**,
   which blocks the tool call and returns the reason to the model. A PreToolUse hook is not an
   instruction — the harness executes it and honours its exit code regardless of what any prompt
   says — so it is the only layer at this level a session cannot talk itself out of. Deliberately
   **not** a git `pre-push` hook: `core.hooksPath` is per-clone config that cloud sandboxes never
   set, so git hooks are absent from exactly the environment that produces the bug (the same
   reasoning that made `git-identity.sh` a SessionStart hook).
   Scoped by `origin` URL, not path, so it distinguishes `personal-data` from the KB repo on both a
   Windows desktop path and a cloud symlink. Resolves `cd X && git push`, `git -C X push`, bare
   `git push`, and `HEAD:refs/heads/X` refspecs; fails closed if it cannot determine the branch,
   and stays silent on every non-push call.
2. **`CLAUDE.md` says both halves.** The `write/` bullet now states that the prefix *is the
   trigger*, that a wrong name fails silently with green checks, and — critically — what to do when
   a session instruction pins a different branch: follow it for the KB repo, use `write/kb-…` for
   `personal-data` anyway, and say so. Naming the competing channel is what
   [[instructions-bind-only-in-the-channel-that-loads-2026-08-22]] concluded, applied here.
3. **`/wrap` check 1 widened.** It flagged surviving `write/*` refs — a *stalled* merge — and so
   was blind to the more serious case. It now flags **every** non-`main` remote ref and reads the
   two shapes differently: `write/*` means a stalled or red gate; any other prefix means the branch
   will never be picked up at all.

## The reusable rule

**When a naming convention is also a trigger condition, say so where the name is chosen, and
enforce it mechanically — because the failure mode is silence, not error.** Three tests:

- **Is this name load-bearing?** If some automation filters on it, the convention is an interface.
  Document it as *"this prefix is what causes X to run"*, never as *"we name branches like this."*
- **Does the wrong value fail loudly?** A trigger filter fails **open**: the automation does not
  complain, it is simply absent. Ask what the observable difference is between "ran and passed" and
  "never ran" — if it is only that a downstream state didn't change, you have no detection.
- **Green means "the checks that fired, passed."** It never means "the pipeline ran." When
  auditing, enumerate the controls that *should* have fired and confirm each one did, rather than
  reading the summary. A missing run is invisible in a list of runs.

And the precedence rule, now confirmed a second time: **an outer layer will keep picking names
inside your namespace** — harness defaults, CI templates, framework scaffolds — and it cannot know
your conventions. Where the collision is costly, the resolution belongs in a layer that executes
(a hook, a CI guard), not in a layer that asks. Instruction sets the default; enforcement holds the
line when a louder instruction arrives.

## Related

- [[instructions-bind-only-in-the-channel-that-loads-2026-08-22]] — the precedence half. That one is
  about *which channel loads*; this one is about *what to do once you accept that the louder channel
  will sometimes win*: stop competing on wording and move the rule into an executing layer.
- [[controls-that-appear-installed-but-enforce-nothing-2026-08-04]] — the sibling failure. There a
  control was present but inert; here the control was correctly scoped and the *work* moved outside
  its scope. Both present as green.
- [[integrity-seams-mirror-the-gate-sync-the-catalog-2026-06-20]] — partial coverage of a
  multi-branch seam that drifts instead of erroring.

## Open — the layer this fix does not reach

The hook is client-side. It protects sessions that run in a checkout of **this** repo with its
`.claude/settings.json` active; it does nothing for a push made from a different working copy, from
another repo's session, or by hand. The unbypassable version is **server-side**: a step in
`personal-data`'s `integrity-gate.yml` that fails when a push touches `private/` on a branch outside
`write/**` | `sync/auto` | `main`. That is ~15 lines and closes the case completely, but it gates
every write to the repo, so a wrong condition blocks all KB writes — it deserves its own change,
tested deliberately, rather than being appended to this one.
