---
title: A present-but-inert control is indistinguishable from a working one — test the refusing case, never the passing case
date: 2026-08-04
category: architecture-patterns
module: workspace-wide
problem_type: architecture_pattern
component: development_workflow
severity: high
applies_when:
  - "A guard, gate, hook or scanner is installed and assumed to be running"
  - "CI is green and that greenness is being treated as evidence a check ran"
  - "Verifying that a safeguard works after building or moving it"
  - "A repo is private on the GitHub free plan, where required status checks are unavailable"
  - "Auditing whether a safeguard needs to propagate to sibling repos"
tags: [enforcement, ci, hooks, verification, silent-failure, false-green, pretooluse, branch-protection, drift, negative-testing]
---

# A present-but-inert control is indistinguishable from a working one

## Context

On 2026-08-04 a cloud `/triage` session had a commit rejected by `check_authorship.py`. Chasing that
one rejection surfaced **five independent enforcement failures in a single day**, none of which had
announced themselves. Every one had been in place for hours or months, looked installed, and enforced
nothing.

| What looked fine | What was actually true |
|---|---|
| The KB repo's CI ran on every PR | `allowed_actions` was `local_only`, so `actions/checkout@v4` was disallowed and **every workflow died at `startup_failure`**. Three PRs merged with no gate at all. |
| `pr-body-scan.py` was installed in `~/.claude/hooks/` | It was **never registered** in `~/.claude/settings.json`. The outbound PII gate had never run — which is how a real email address reached a PR body. |
| A merge gate could ask "are the checks green?" | Workflows that fail to *start* **never create a check run**, so they are absent from `statusCheckRollup` entirely. A green-checks test passes a repo whose CI is dead. |
| CI enforced merge safety | These repos are **private on the free plan**, so branch protection and required status checks return `403`. CI *reports*; it never *enforces*. |
| A sibling workspace configuration repo had CI | `.gitignore`'s `*/` rule (which keeps nested project repos out) also caught `.github/`. That repo **could not have workflows at all**. |

The common shape: **the passing case and the absent case produce identical observable output.** A
working guard on a clean input is silent. A guard that never ran is also silent. Nothing in the
success path distinguishes them, so every one of these survived repeated green runs.

## Guidance

**1. Verify a control by making it refuse, not by watching it allow.**

A successful merge, a green pipeline, a commit that went through — none of these are evidence a guard
ran. Construct the input the guard is supposed to reject and confirm it is rejected. That is the only
observation where "working" and "absent" differ.

```bash
# Worthless as verification — a working gate and no gate both produce this
gh pr merge 123 --merge          # succeeded, checks were green

# Actual verification — only a working gate produces a refusal
gh pr merge 96 --merge           # PR with a RED check; expect the block message
```

**2. When a check has two possible reasons to be quiet, give it a third exit code.**

Collapsing "could not run" into "clean" is what makes a dead check invisible. Separate them and fail
loudly on the third:

```
0  clean
1  finding — real and actionable
2  the check could not run (auth, network, missing config)
```

Exit 2 must fail the job. A credential expiring a year from now should produce a loud red failure
naming the token, not a quiet green.

**3. Distinguish "installed" from "registered" from "running".**

Copying a hook file is visible; wiring it up is not. Assert on the wiring, not the file's existence —
and prefer asserting on observed *behaviour* over either.

**4. Ask what a control depends on that nothing checks.**

Each failure above had a silent dependency: a repo setting, a settings.json entry, an API surface
that omits failed-to-start runs, a plan tier, a `.gitignore` line. None appeared in any inventory.

**5. Where the platform cannot enforce, put the enforcement where it can run — then test *that*.**

Private repos on the free plan cannot have required status checks. The gate has to live client-side
(a `PreToolUse` hook) or server-side in a bot. Both are real; both need the refusing-case test,
because both fail silently too.

## Why This Matters

**A green check that never asked its question is worse than no check**, because it consumes the trust
a real check would have earned. Every additional silent pass erodes what a green pipeline means.

The consequences here were not theoretical. `pr-body-scan.py` being unregistered is the direct reason
a real email address was published to a PR body — PR bodies cannot be un-published, and an edit
leaves the original in the timeline. The scanner that would have blocked it was sitting on disk,
correct and complete, wired to nothing.

The same insight already exists in a sibling repo's learnings from a different angle: a write-up on
vendored copies drifting upstream (2026-08-02) found that a hash manifest answers *"was
this edited here?"* and never *"is this current?"* — and reports **7 of 7 matching** beside a stale
file. That doc also observed that its own limitation was written down accurately in the morning and
bit the same day. **Documenting a gap does not close it.** Both docs converge on the same rule: if
the failure mode is silence, the test must be one that produces noise.

## When to Apply

- After building, moving, or vendoring any guard — the move is exactly when wiring gets lost
- Before trusting a green CI run as evidence that a specific check executed
- When a safeguard's canonical copy lives somewhere that does not travel (`~/.claude/`, machine-local
  git config, a repo setting)
- When auditing whether a control needs to propagate to sibling repos — check the *rule* as well as
  the *mechanism*; a repo can have the hook and not the documented rule it enforces
- Whenever a check has a credential, a plan tier, or a platform setting as an unstated dependency

## Examples

**Verifying an alarm by breaking something on purpose.** Both cross-repo drift jobs were verified
this way rather than by watching them pass:

```bash
git checkout -b test/drift-alarm
printf '\n# deliberate perturbation\n' >> scripts/hooks/pii_scan.py
git commit -am "test: prove the drift alarm fires" && git push -u origin test/drift-alarm
gh workflow run vendored-drift.yml --ref test/drift-alarm
# -> issue opened naming all three consumers.  Re-run on clean master -> auto-closed.
git push origin --delete test/drift-alarm
```

`pii_scan.py` was chosen deliberately: it is the exact file that drifted unnoticed on 2026-08-02, so
the test demonstrated the alarm that would have caught the original incident.

**A false-green that a rollup check would have passed.** PR #99's `statusCheckRollup` contained only
two Socket checks, both `SUCCESS`, while `integrity-gate` and `pr-text-scan` had both died at
`startup_failure`. The fix was to consult a second source that lists runs which never became checks:

```bash
gh api "repos/$REPO/actions/runs?head_sha=$SHA&per_page=100"
```

> ⚠️ **That two-source check has a third blind spot, found 2026-08-22.** Both sources here assume the
> workflow *started* and then died. A workflow that never **fires** produces no run at all, so it is
> absent from the runs API too — and both sources come back clean. This is not hypothetical: GitHub
> does not trigger workflow runs from `GITHUB_TOKEN` events, so a `pull_request`-only workflow never
> fires on a bot-opened PR. In `personal-data`, where `auto-merge` opens every `write/**` PR,
> `pr-text-scan` was dark from 2026-08-09 to 2026-08-22 and **neither** prescribed source showed it.
> Verified against a bot PR from inside that window:
>
> ```bash
> SHA=$(gh pr view 88 --json headRefOid --jq .headRefOid)
> gh api "repos/<owner>/personal-data/commits/$SHA/check-runs" --jq '.check_runs[].name'
> #   Socket Security: Project Report / Pull Request Alerts / auto-merge / integrity-gate
> gh api "repos/<owner>/personal-data/actions/runs?head_sha=$SHA" --jq '.workflow_runs[].name'
> #   auto-merge / integrity-gate
> ```
>
> **The check that does cover it is run *recency*, not run presence:** `gh run list --workflow
> <name>.yml --limit 1` — is the most recent run actually recent? (Full analysis lives in a sibling repo's learning: *pull-request-triggered guards are inert
> on bot write paths*, 2026-08-22.)

**A control caught failing on its own PR.** The merge gate blocked its own pull request and reported
the target as the *wrong repo* — `cd /c/Users/...` is a valid Git Bash path but `os.path.isdir()`
under native Windows Python returns `False`, so the resolver silently fell back to ambient shell cwd.
That is the same ambient-state bypass an earlier fix had removed, returning through a path-format side
door. The prior test suite missed it because its `cd` case happened to use a Windows-style path.

**A false positive is a security bug, not an annoyance.** The same gate then blocked an ordinary
`gh pr create` whose commit message merely *described* what breaks without the gate. Apostrophes in
the PR body made `shlex` raise; tokenisation fell back to a naive whitespace split; prose became
tokens. A gate that blocks ordinary work gets uninstalled, and uninstalled is strictly worse than
noisy.

## Related

- *Vendored copies drift upstream, not locally* (sibling repo, 2026-08-02) — the same lesson from
  the drift angle: a self-referential check reports green beside a stale file
- `docs/cloud-environment-setup.md` — cloud/mobile sandboxes never set `~/.claude/` or
  `core.hooksPath`, so client-side gates do not exist there
- A machine-setup check hook (workspace-level) — reports controls that are present but
  unregistered, written after this session found one
- A PR merge-gate hook (workspace-level) — including why pending counts as not-green and why it
  reads two sources of check state
