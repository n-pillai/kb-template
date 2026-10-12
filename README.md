# kb-template — a Signal Ledger knowledge base for Claude Code

A personal knowledge base that runs inside [Claude Code](https://claude.com/claude-code): you drop
in what you read, listen to and watch, and it keeps only what matters to your work — distilled,
tied to a project or a thesis you're tracking, and tiered by how well it's corroborated.

This is the **template** (public) edition of a running personal deployment. The machinery is all
here; the content is not. Your entries, themes and projects live in a **separate private repo**
that this one reads through `PERSONAL_DATA_DIR`, so nothing you learn is ever committed here.

## Why it isn't a bookmark pile

Every source runs through the **Signal Ledger contract** before it is filed:

1. **Distill, don't summarize** — what it means *for your work*, in 3–5 bullets.
2. **Lead with "so what"** — tie it to an active project or a tracked theme, or it isn't signal.
3. **Log negative signal** — "not useful because X" is a valid entry.
4. **Track corroboration** — one source is *parking*, a second independent one is *watch*, a third
   is *confirmed*. Independent means a distinct author **and** outlet.

Things worth keeping that don't tie to anything go on a **library** shelf as plain pointers, out of
the signal counts, and can be promoted later.

## The loop

```
/triage <link>  →  read / listen  →  /distill  →  themes move, concept pages proposed  →  /digest
```

| Command | What it does | Writes to (private repo) |
|---|---|---|
| `/triage` | Front door: queue it, shelve it, or drop it; ranks podcasts | `_inbox/`, `library/` |
| `/capture` | Raw drop into the queue, no triage | `_inbox/queue/` |
| `/shelve` | Keep a pointer with no project tie | `library/` |
| `/distill` | Run the Signal Ledger: entry + theme movement; *proposes* concept-page changes | `entries/`, `THEMES.md`, `INDEX.md`, `_inbox/proposals/` |
| `/digest` | Daily summary: new entries, theme movement, what awaits your approval | — |
| `/healthcheck` | Monthly audit: hygiene + "is this still compounding?" | — (proposes only) |
| `/wrap` | End-of-session check that nothing was left unmerged | — |

Ask in plain language to read it back: *"What do I know about X?"* → the concept page →
*"show me the sources"* → the entries → the original link.

## Setup

1. **Use this template** to create your copy, and create a second, **private** repo for your
   content (the default name is `personal-data`).
2. Copy `example-data/kb/` into the private repo at `private/kb/`. Edit `projects.md` to list your
   real projects and clear out the example entry, card and theme.
3. Point the machinery at it: `export PERSONAL_DATA_DIR=/path/to/personal-data`. For cloud sessions,
   set `KB_DATA_REPO=<owner>/personal-data` and follow the steps the session-start hook prints
   (also in [`docs/cloud-environment-setup.md`](docs/cloud-environment-setup.md)).
4. Set your commit identity to a GitHub **no-reply** address: put it in `.integrity-paths.json` →
   `approved_authors` and export `KB_GIT_NAME` / `KB_GIT_EMAIL`.
5. Optional: create `~/.kb/pii-denylist.txt` (one term per line — names, places, employers) so the
   commit-time PII scan blocks them; set the `KB_PII_DENYLIST` secret to do the same in CI.
6. Open the repo in Claude Code and run `/triage <a link you read this week>`.

| Setting | Where | What it does |
|---|---|---|
| `PERSONAL_DATA_DIR` | env | Path to your private content repo. Required. |
| `KB_DATA_REPO` | env | `owner/repo` of the private repo, for cloud sessions (default: `<this repo's owner>/personal-data`). |
| `KB_GIT_EMAIL`, `KB_GIT_NAME` | env | Commit identity pinned at session start (else the first entry in `approved_authors`). |
| `KB_GITHUB_OWNER` | env | Your GitHub user, for the PR merge gate (default: the target repo's owner). |
| `KB_PII_DENYLIST` / `KB_PII_DENYLIST_FILE` | env or Actions secret | Extra terms the PII scan blocks. |
| `KB_REQUIRE_PRIVATE` | Actions variable | Set to `true` to make CI fail if the repo is ever public (use it on a private fork). |

## Guard rails included

- **Content never lands here.** Commands read and write only under `$PERSONAL_DATA_DIR`, and fail
  closed when it isn't set — they stop rather than guess.
- **Two commit tiers.** Entries commit automatically; concept pages are only ever *proposed* for
  your approval, because the concept graph is where careless merges do the most damage.
- **Write-branch gate.** Writes to the private repo go through `write/kb-*` branches; a hook blocks
  pushes to anything else.
- **PII scans.** A pre-commit scan (`scripts/hooks/pii_scan.py`) plus `pii-public-scan.yml` and
  `pr-text-scan.yml` in CI.
- **Lossless fetching.** Sources are fetched raw with the vendored `fetch-docs` skill before any
  summarizer touches them, so exact numbers and names survive into the evidence.

## Layout

```
CLAUDE.md               the operating contract Claude Code loads every session
.claude/commands/       the seven commands
.claude/hooks/          session-start mount + identity, write-branch and merge gates
.claude/skills/         fetch-docs (vendored, MIT — see NOTICE)
scripts/hooks/          pre-commit / commit-msg checks: PII, append-only, authorship
.github/workflows/      integrity gate, PII and PR-text scans
docs/design.md          the design, short form
docs/solutions/         lessons learned building it — the most reusable part
evals/                  how to check that /distill distills rather than summarizes
example-data/kb/        a starter private-data folder
tags.md                 the governed tag vocabulary (an example set)
```

Not included: the parts of the original that connect to other personal agents. One of those
patterns is written up in [`docs/agent-proposed-projects.md`](docs/agent-proposed-projects.md).

## License

MIT — see `LICENSE`. Third-party attributions in `NOTICE`.
