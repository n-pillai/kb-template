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

## Start here

About 30 minutes, once. You'll make **two** GitHub repos: your copy of this template (the
machinery) and a **private** one for your content. Claude Code reads and writes the private one;
nothing you learn is ever saved in this one.

### Step 1 — Install three things

| What | Get it | Check it worked (type in a terminal) |
|---|---|---|
| Claude Code | [claude.com/claude-code](https://claude.com/claude-code) | `claude --version` |
| Git | [git-scm.com/downloads](https://git-scm.com/downloads) (on Windows this also installs **Git Bash** — use it for the commands below) | `git --version` |
| Python 3 | [python.org/downloads](https://www.python.org/downloads/) | `python3 --version` (Windows: `python --version`) |

### Step 2 — Find your GitHub "no-reply" email address

Every save is recorded under an email address, and your real one should never end up in your
history. GitHub gives you a private stand-in:

1. Open [github.com/settings/emails](https://github.com/settings/emails).
2. Tick **Keep my email addresses private**.
3. Copy the address shown under it. It looks like `12345678+yourname@users.noreply.github.com`.
4. Tell git to use it (paste your address in place of the example):
   ```
   git config --global user.email "12345678+yourname@users.noreply.github.com"
   git config --global user.name "yourname"
   ```

### Step 3 — Make your two repos

1. **The machinery:** on this repo's GitHub page click **Use this template** → **Create a new
   repository**. Name it (say, `kb`). Public or private both work.
2. **Your content:** click **+** (top right of GitHub) → **New repository**. Name it
   `personal-data`, choose **Private**, and tick **Add a README file**. Click **Create repository**.
   (Another name works too, but then add `"KB_DATA_REPO": "yourname/<that name>"` to the settings
   file in step 5, so the safety checks know which repo is yours.)
3. Download both into the same folder on your computer (replace `yourname`):
   ```
   cd ~/Documents
   git clone https://github.com/yourname/kb
   git clone https://github.com/yourname/personal-data
   ```

### Step 4 — Fill your private repo

From inside your `kb` folder, run the setup script and point it at the private repo:

```
cd ~/Documents/kb
bash scripts/setup-private-repo.sh ../personal-data
```

It adds an empty knowledge base (`private/kb/`), the safety checks, and a GitHub workflow called
**auto-merge** that saves your work. Then:

1. Open your `personal-data` repo on GitHub and click the **Actions** tab. A run called
   **auto-merge** turns green within a minute or two.
2. Click the **Code** tab: there's now a `private` folder. That means saving works.
3. Update your copy: `git -C ../personal-data pull`

If the script stops with a message, it says what to fix; fix it and run it again.

### Step 5 — Tell Claude Code where your content lives

In your `kb` folder, create the file `.claude/settings.local.json` with this in it, using the full
path to **your** `personal-data` folder and your no-reply address:

```json
{
  "env": {
    "PERSONAL_DATA_DIR": "/Users/yourname/Documents/personal-data",
    "KB_GIT_EMAIL": "12345678+yourname@users.noreply.github.com",
    "KB_GIT_NAME": "yourname"
  }
}
```

On Windows, write the path with forward slashes, like `C:/Users/yourname/Documents/personal-data`.
This file stays on your computer — it is never uploaded.

### Step 6 — First run

1. Open the `kb` folder in Claude Code (in a terminal: `cd ~/Documents/kb` then `claude`).
2. The welcome text should include `mount: present`. If it says `mount: ABSENT`, recheck the path
   in step 5 and restart Claude Code.
3. Tell it what you're working on, in plain words, for example:
   *"Replace the example projects in projects.md with: my gardening blog, and finding a product
   role."* Projects are what makes something worth keeping, so this comes first.
4. Give it something you read this week: `/triage https://…`

**What success looks like:** Claude tells you whether the link was **queued** (ties to your
work), **shelved** in the library (worth keeping, no tie), or **dropped** (and why). It saves the
result, and a new green **auto-merge** run appears in your private repo's Actions tab. After
you've read it, `/distill` turns it into an entry.

End each session with `/wrap`. It checks nothing was left unsaved.

### Using it from claude.ai or your phone (optional)

Cloud sessions can't see your computer, so the private repo has to be attached to each session.
Set `KB_DATA_REPO=yourname/personal-data` in the cloud environment's settings. The session prints
the steps it needs at the start; [`docs/cloud-environment-setup.md`](docs/cloud-environment-setup.md)
has the details.

### Words you'll see

| Term | Means |
|---|---|
| **Signal Ledger** | The rules every source goes through before it's kept (above). |
| **parking / watch / confirmed** | How well a theme is backed up: 1, 2, or 3+ independent sources. |
| **Tier A / Tier B** | Entries are saved automatically (A); concept pages wait for your OK (B). |
| **L1 / L2** | Protection levels: L1 files can only grow; L2 files can be edited but not gutted or deleted. |
| **write branch** | `write/kb-…` — how each save travels to your private repo before auto-merge merges it. |

## Reference: settings

| Setting | Where | What it does |
|---|---|---|
| `PERSONAL_DATA_DIR` | `.claude/settings.local.json` → `env` | Path to your private content repo. Required. |
| `KB_GIT_EMAIL`, `KB_GIT_NAME` | same | The identity every commit uses (your no-reply address). |
| `KB_DATA_REPO` | `.claude/settings.local.json` → `env`, and the cloud environment's variables | `owner/repo` of the private repo. Needed if it isn't named `personal-data`: the write-branch guard and the cloud mount both use it (default: `<this repo's owner>/personal-data`). |
| `KB_GITHUB_OWNER` | env | Your GitHub user, for the PR merge gate (default: the target repo's owner). |
| `KB_PII_DENYLIST` | Actions secret on the private repo | Extra words (names, places, employers — one per line) the PII scan blocks. Locally: `~/.kb/pii-denylist.txt`. |
| `KB_REQUIRE_PRIVATE` | Actions variable | Set to `true` on a repo that must never be public; its checks then fail if it is. |

To have this repo's own checks recognise you too, replace the placeholder in `.integrity-paths.json`
→ `approved_authors` with your no-reply address.

## Guard rails included

- **Content never lands here.** Commands read and write only under `$PERSONAL_DATA_DIR`, and fail
  closed when it isn't set — they stop rather than guess.
- **Two commit tiers.** Entries commit automatically; concept pages are only ever *proposed* for
  your approval, because the concept graph is where careless merges do the most damage.
- **Write-branch gate.** Writes to the private repo go through `write/kb-*` branches; a hook blocks
  pushes to anything else, and the private repo's `auto-merge.yml` runs the integrity checks
  (append-only, lossy-rewrite, PII, authorship) before it merges.
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
scripts/setup-private-repo.sh   one-time setup of your private repo
.github/workflows/      integrity gate, PII and PR-text scans
docs/design.md          the design, short form
docs/solutions/         lessons learned building it — the most reusable part
evals/                  how to check that /distill distills rather than summarizes
example-data/kb/        the starter private-data folder, with one example of each file
example-data/private-repo-files/   auto-merge.yml + integrity config the setup script installs
tags.md                 the governed tag vocabulary (an example set)
```

Not included: the parts of the original that connect to other personal agents. One of those
patterns is written up in [`docs/agent-proposed-projects.md`](docs/agent-proposed-projects.md).

## License

MIT — see `LICENSE`. Third-party attributions in `NOTICE`.
