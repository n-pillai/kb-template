# Cloud environment setup (claude.ai/code)

Two separate concerns live here:

- **§0–§5 — mounting `personal-data`.** Required for the KB to function at all in a cloud or
  mobile session. **Verified working 2026-08-04** — the clone needs the repo *attached* to the
  session, see §5. Where the repo is not attached, the hook prints a one-step `add_repo` recovery.
  (An earlier note here claimed a web-UI action made this silent — that was wrong and is retracted
  in §5; no environment-level repo attachment appears to exist.)
- **§1–§4 (render) — provisioning `agent-browser`** for the tier-2 `fetch-docs --render` step.
  A capability upgrade; without it the fetch ladder degrades safely to WebFetch.

---

## 0. Mounting `personal-data` (REQUIRED — cloud/mobile is broken without it)

Since the 2026-08-02 migration this repo holds only *machinery*. All KB content lives in the
private `personal-data` repo at `$PERSONAL_DATA_DIR/private/kb/`, and `CLAUDE.md` says **fail
closed** — stop, don't fabricate — when that variable is unset. On the desktop it comes from
`setx`. **A cloud sandbox clones only the session's repo and sets nothing**, so every cloud and
mobile session correctly refuses to do anything. That is a live breakage, not a latent gap.

### The mechanism: a committed SessionStart hook

`.claude/hooks/mount-personal-data.sh`, registered in `.claude/settings.json`. It is cloud-only
(`CLAUDE_CODE_REMOTE` guard, desktop no-op), clones `<owner>/personal-data` to the session's
managed target `/workspace/personal-data` and symlinks the **sibling of the checked-out repo** at it
(mirroring the desktop layout, so it can never be committed into a build repo — see §5 for why the
real clone has to live at the managed path), pulls if already present, sets
`core.hooksPath scripts/hooks` in the clone per `CONVENTION.md`, and writes
`export PERSONAL_DATA_DIR=…` to **`$CLAUDE_ENV_FILE`** — the only supported way for a hook to set an
environment variable for the rest of the session.

If the clone is refused because the repo is not attached to the session, the hook prints a
**recovery recipe** (`add_repo` → clone → export → `register_repo_root`) rather than stopping at
"unavailable". Fail-closed still applies until that recovery completes.

**Why a hook and not the setup script (§1).** The setup script runs once and is then snapshotted
and reused for ~7 days. A snapshot of personal data is a stale task list and a stale ledger —
precisely what `CONVENTION.md`'s *"pull at session start"* rule exists to prevent. SessionStart
hooks run every session including resumed ones, are committed so they travel, and can set the env
var; setup scripts can do none of those three.

**No token, deliberately.** Cloud environments have **no secrets store** — environment variables
are readable by anyone using the environment (Anthropic's docs say so explicitly and the dialog
warns about it). A PAT with read access to `personal-data` is a credential to your personal
data; it does not belong in plaintext environment config. The hook relies on the session's GitHub
proxy instead, and if the proxy refuses, it reports that rather than working around it.

**Nothing to configure in the web UI for this section.** The hook is committed; it starts working
on the first cloud session after it merges to `main`.

## 5. ✅ VERIFIED (2026-08-04): a cloud session can clone a second private repo — *once it is attached*

This was the one open question in the mount, and the documentation appeared to contradict itself:

| Source | Claim |
|---|---|
| `claude-code-on-the-web` → GitHub authentication | *"a cloud session can access **any repository** the connecting GitHub account can see"* |
| `cloud-environments` → GitHub proxy | *"GitHub API and release-asset requests reach **only repositories attached to the session**"* |
| **§3 of this file, observed 2026-07-22** | *"the sandbox proxy rewrites github.com requests for repos **outside the session's authorized scope** into a JSON 'access not enabled' stub"* |

**Both are true, at different layers, and that is the whole answer.** The first is about account
*policy* — the GitHub App can indeed see `personal-data`, and nothing at the account level blocks
it. The second and third are about *proxy behaviour* — the session's local git proxy serves only
repos attached to **that session**, regardless of policy. Attachment, not permission, is the gate.

### What a blocked clone actually looks like

Observed in a cloud session on Claude Code 2.1.221, with only the KB repo attached:

```
$ git clone https://github.com/<owner>/personal-data.git /workspace/personal-data
Cloning into '/workspace/personal-data'...
fatal: could not read Password for 'http://local_proxy@127.0.0.1:41729': terminal prompts disabled
```

Note this is **not** the 2026-07-22 "access not enabled" JSON stub. That stub is the **API** path;
**smart-HTTP git** falls through to a credential prompt on the local proxy instead and dies on
`terminal prompts disabled`. Same meaning — out of session scope — two different signatures, so
match on both when detecting it (the hook does).

### The fix: attach the repo, then clone

> As of 2026-08-22 this recovery is also stated in **`CLAUDE.md` → *Personal data (mounted,
> read-write)*** and in each intake command's header banner. That duplication is deliberate: this
> doc is never loaded into a session's context, so a session whose first turn is a slash command
> used to see only the "STOP" half of the rule and stop. Keep the two in sync.

A bash hook **cannot** attach a repo — only the agent can, via the `add_repo` tool. That makes a
blocked clone a *recoverable* state, not the design dead-end §5 previously assumed. Verified
working end to end:

1. `add_repo {owner: "<owner>", repo: "personal-data", access: "read"}` → repo enters session scope
   immediately (the system prompt's Repository Scope list does **not** update; that is expected).
2. `git clone https://github.com/<owner>/personal-data /workspace/personal-data` → succeeds.
   One clone, inline, generous timeout: the proxy caps concurrent git ops per repo at 2, and a
   second concurrent clone 429s both.
   ⚠️ **Full depth, not `--depth 1`.** The verification run used a shallow clone, which is fine
   for a read-only look but wrong as the standing recipe: `personal-data` is a **write** target.
   Writes go via `write/<repo>-<cmd>-<ts>` branches, and both the local L1 append-only hook
   (`core.hooksPath scripts/hooks`, set in step 4) and `git merge-base` need real history. A
   shallow clone breaks them on the first cloud write, not at clone time — so it would have
   looked fine here and failed later.
3. `export PERSONAL_DATA_DIR=/workspace/personal-data` → `ls $PERSONAL_DATA_DIR/private/kb/entries`
   listed the entries.

**This is route 4, and it beats all three fallbacks below** — no PAT, no restructuring, no
downgrade to read-only. Those are kept at the bottom for the record only.

**Why `/workspace/personal-data` and not the sibling path.** `register_repo_root` — the call that
loads `personal-data`'s `CLAUDE.md`/`CONVENTION.md` into context — accepts **only** the session's
managed clone target and rejects anything else:

```
register_repo_root: directory "/home/user/personal-data" does not match the managed
session's clone target "/workspace/personal-data"
```

So the hook clones to `/workspace/personal-data` and symlinks the sibling path
(`<parent>/personal-data`) at it. Both resolve; the desktop layout promise — `personal-data` sits
*beside* the build repo, never inside it, so it can never be committed into one — still holds.

### Two further findings from the same session

- **`$CLAUDE_ENV_FILE` IS supported** on 2.1.221 (it is set for `SessionStart`, `Setup`,
  `CwdChanged` and `FileChanged` hooks). It is deliberately absent from the **Bash tool**
  environment, so `echo $CLAUDE_ENV_FILE` in a Bash call printing empty is *not* evidence the
  feature is missing. Do not diagnose it that way.
- **The env file is sourced as a bash prelude, so it needs `export`.** The hook previously wrote a
  bare `PERSONAL_DATA_DIR=…`, which sets a shell variable that `$PERSONAL_DATA_DIR` expands from but
  that child processes (git, node, scripts) never see. Fixed to `export PERSONAL_DATA_DIR=…`.
- **A hook-set var is not retroactive.** In the session where recovery runs, prefix Bash calls with
  `PERSONAL_DATA_DIR=…` or `export` it; the env file applies from the next command onward.

### Is there a durable fix? — ⚠️ NOT FOUND, and an earlier claim here was wrong

**This section previously said: "Attach `personal-data` as a second source on the cloud
environment." That instruction is wrong — retracted 2026-08-04.** It was carried over from the
cloud session's investigation and adopted without verification. Checked against the UI and the
docs:

- The owner opened the Default environment's settings and there is **no option to add a source.**
- Anthropic's `cloud-environments` doc lists the dialog's fields exhaustively — *"the name, network
  access level, environment variables, and setup script."* No repository or sources field exists.
- A web search suggested a per-session **"+ button next to the repo pill"**, but fetching **both**
  articles it cited found no such text. Unverified; do not rely on it.

So there is **no confirmed environment-level way to pre-attach a second repo**, and the per-session
`add_repo` recovery above is the mechanism that actually works.

That is less bad than it sounds. The hook prints the recipe into SessionStart context *only when
the clone is refused*, so the agent is told precisely when it matters rather than having to
remember. The cost is one round trip per session, not a broken mount.

**Still worth checking when convenient** (5 seconds, at session-start rather than in environment
settings): when picking the repo for a new cloud session, is there any control for adding a second
one? If yes, that is the durable fix and this section should be rewritten around it. If no, the
per-session recovery is the answer and this open question can be closed.

⚠️ **Process note.** This is the second wrong claim in this file traceable to adopting a
conclusion without independently checking it — the first being the `--depth 1` recipe corrected in
§5. Cloud-session findings about *observed behaviour* (the proxy error, `register_repo_root`
rejecting paths, the `export` requirement) proved reliable, because they were things that session
actually ran. Its claims about *UI that it could not see* did not. Weight them differently.

### Verify (one cloud session, once)

Open the KB repo in a cloud session.

⚠️ **You will see a blank window. That is not a failure.** The SessionStart output goes to *Claude's*
context, not to your screen — Claude reads the mount diagnostic and the recovery recipe; you see
nothing. Verified 2026-08-04: a session that had clearly received the full diagnostic showed the user
an empty window until they typed something.

Two consequences that were previously stated wrongly here:

- **Nothing happens until you send a message.** A session with no user turn takes no action, so the
  mount recovery cannot run "at session start". The earliest it can run is while answering your first
  message — which is why `mount-personal-data.sh` instructs the agent to do the recovery *before*
  answering, whatever that first message is, rather than reporting the state and waiting.
- **A status report about the mount is a bug, not information.** From the user's side it is
  indistinguishable from the session doing nothing with their first request.

Then:

```bash
echo "$PERSONAL_DATA_DIR"                      # expect: /workspace/personal-data
ls "$PERSONAL_DATA_DIR/private/kb/entries" | head
git config user.email                          # expect: your no-reply address (KB_GIT_EMAIL)
git -C "$PERSONAL_DATA_DIR" config user.email  # expect: the same
```

The **fourth** line is the one that matters most. The personal-data clone is created by hand during
recovery, *after* `git-identity.sh` has already run and found nothing to pin — so recovery step 5
re-runs it. If that line returns `noreply@anthropic.com` or anything else, step 5 was skipped and the
first write branch will be rejected by `check_authorship.py`.

Then run `/distill` on a queued item and confirm it reads and writes under
`$PERSONAL_DATA_DIR/private/kb/`.

| Result | Meaning | Next |
|---|---|---|
| Hook prints `mounted at …`, `ls` lists entries | `personal-data` is attached to the session | Working as intended |
| Hook prints `NOT MOUNTED YET` with the recovery recipe | Repo not attached to this session | Run the `add_repo` recovery above. Expect this every session — there is no known environment-level pre-attach (see the retraction above) |
| Hook prints `NOT MOUNTED` (no recipe) | A real failure — network, disk, deleted repo | Read the printed git error; the recipe would not help |
| Hook prints `mounted`, but a command still fails closed | `$CLAUDE_ENV_FILE` unsupported in that Claude Code version | The hook says so and prints the manual `export` |

### Fallback routes (superseded — kept for the record)

`add_repo` (route 4 above) makes these unnecessary. Do **not** reach for a PAT in environment
variables — that is the option the no-secrets-store warning exists to prevent, and the data at stake
is the reason.

1. **GitHub MCP** — connector traffic goes through Anthropic's servers, not the session network, so
   it is not subject to the repo-scope proxy. Still a candidate mechanism for client-agent access,
   but no longer needed as the way in.
2. **Restructure so the session attaches to `personal-data`** — inverting which repo is the session
   root. Unnecessary now that a second repo can simply be attached.
3. **Accept desktop-only for KB writes.** Weakest, and no longer warranted.

---

## 6. What enforces in cloud (and what does not)

*(Added 2026-08-08. Every claim carries its evidence; a control documented without a verifiable invocation is treated as
not running.)*

The leak-safety story a cloud session can rely on, by layer:

### Server-side — reaches every environment, including cloud and mobile

These run on GitHub's side of the push, so no sandbox property can disable them. They are the
reason a cloud session is allowed to write at all:

- **personal-data `integrity-gate`** (`personal-data/.github/workflows/integrity-gate.yml`) —
  L1 append-only, L2 lossy-rewrite heuristic, PII scan over content **and commit messages**,
  commit-authorship check against `approved_authors`. Proven to catch real violations from
  live sessions: the 2026-08-04 real-email commit (rejected) and the 2026-08-07 first run
  of a sync job (contact PII in a synced list, blocked before merge).
- **`pr-text-scan`** (same repo + this one) — outbound PR title/body scan.
- **Auto-merge bot** (`personal-data/.github/workflows/auto-merge.yml`) — merges `write/**`
  PRs **only on a green gate**, with `--delete-branch`, so a session's write branches are
  closed out without any session-side cleanup.
- **Private-repo CI assertion** — fails if personal-data is ever not private.

### Committed hooks (`.claude/settings.json` + `.claude/hooks/`) — travel with the repo

- **SessionStart chain** (mount → identity pin → cloud CA import → orientation banner):
  **proven to fire in cloud** — the mount + identity hooks have run in live cloud sessions
  since 2026-08-05 (the identity pin exists *because* a cloud session mis-authored a commit).
- **PreToolUse merge gate** (`merge-gate.sh`): fires on desktop, but **unverified in cloud**
  — no cloud session has run since it was committed. See the probe below. Until it is
  verified, treat the hook layer as desktop-only defence and rely on the server-side layer.

### Machine-local — does NOT reach cloud; never assume it

- `core.hooksPath` git hooks (conventional-commit format, direct-`main` block, `.env` block)
  — per-clone config a sandbox never sets. Hold to the conventions manually in cloud.
- `~/.claude` hooks (`pr-security-gate.py`, `pr-body-scan.py`) — home-machine only.

### The one open probe — run from a CLOUD or MOBILE session (pending)

Does a cloud sandbox fire `PreToolUse` hooks registered in committed `settings.json`? Safe to
test — the PR does not exist, so nothing can merge under any outcome:

```
gh pr merge 999999 --repo <owner>/<kb-repo> --merge
```

| Outcome | What you see |
|---|---|
| **Gate fired** | `MERGE GATE - CI checks are not green.` … `Could not fetch check status: GraphQL: Could not resolve to a PullRequest…` — the command never reaches `gh` |
| **Gate absent** | `gh`'s own error passes straight through: `Could not resolve to a PullRequest with the number of 999999` |

⚠️ A **desktop run answers the wrong question**: the machine-local `pr-security-gate.py` wins
there (verified 2026-08-05), so a desktop pass proves only the local hook. Bonus signal in
cloud: the error banner names the script — the only candidate in a sandbox is the committed
`merge-gate.sh`, so seeing the banner at all proves committed config was honoured. **After
running, record the dated result here.** Worst case if absent: cloud merges are ungated by the
hook layer — the server-side gates above still stand.

**First attempt — 2026-08-08, mobile session: the verbatim response settled it, and the
answer restructures the question.** The session **never executed the Bash command at all**: it
answered via the GitHub MCP connector (`GET /repos/<owner>/<kb-repo>/pulls/999999 → 404`,
"gh isn't available in this cloud sandbox — no gh/hub CLI... GitHub work here goes through the
GitHub MCP tools"). Three conclusions:

1. **The PreToolUse question is still open but is now second-order.** The hook was never
   exercised — no Bash call happened, so nothing could intercept anything. If it still wants
   answering, the probe must *force* the transport: instruct the session to run the literal
   command **in its shell tool** (not "merge this PR", which it will route to MCP) and paste
   raw output. Gate text (`MERGE GATE` / `[merge-gate]` / `pr-security-gate`) → hook fires;
   bare `bash: gh: command not found` only → it does not.
2. **The finding that matters more: in that sandbox the merge path IS the MCP connector**,
   and no Bash `PreToolUse` hook intercepts MCP tool calls in any environment. Even a
   perfectly-firing merge gate would sit beside the road actually travelled. The hook layer is
   desktop defence; for cloud/mobile, the server-side gates above are the whole story — which
   is what they were built for (D1: "the server-side gate is the only enforcement cloud
   writers have").
3. Confirmed also: the session independently applied the merge-not-squash rule from this
   repo's committed CLAUDE.md — committed instructions do reach cloud sessions.

### Write-branch lifecycle — verified clean 2026-08-08

The bot's merge uses `--delete-branch`, and `git branch -r` on a freshly-pruned mount clone
showed **only `origin/main`** — zero dangling `write/*` refs, including the previous day's
`write/*` traffic from another writer (personal-data PRs #37–#39). Renewed per session by `/wrap`'s
check 1, not assumed from this observation.

---

# Provisioning `--render` (agent-browser)

The KB intake fetch ladder (`CLAUDE.md` → *Source fetching*) has a tier-2 `fetch-docs --render` that drives **`agent-browser`** — a native Rust CLI that downloads its own headless Chrome (Chrome for Testing) — to render JavaScript-heavy pages. On the **desktop** it's installed and works. In the **claude.ai/code cloud sandbox** it is **not present by default** and must be provisioned once — otherwise the ladder degrades to WebFetch (tier 3), which is safe but can't render SPA pages.

> **Verified in a live cloud session 2026-07-22** — the original three-step script needs two amendments in practice: the Chrome-for-Testing download is blocked by the sandbox egress policy, and the sandbox's TLS-inspecting proxy needs its CA trusted in Chromium's NSS store. Provisioning is therefore split in two: the **setup script (§1)** installs the CLI and points it at the sandbox's **pre-installed Playwright Chromium** (`/opt/pw-browsers/chromium`) instead of downloading Chrome, and the **committed `SessionStart` hook** (`.claude/hooks/session-start.sh`) imports the Anthropic proxy CAs each session — the CA bundle doesn't exist yet at snapshot time, so the import can't live in the setup script (see the note under §1). End-to-end result: `fetch-docs --check` → `agent-browser: OK`, and `fetch-docs <url> --render` captured a 310 KB JS-rendered DOM.

`agent-browser` is a *runtime dependency* — **not committed, does not travel with the repo** (same class as `yt-dlp` per the workspace portability rule). The cloud setup script is configured **only in the claude.ai/code web UI**, not in version control, so the steps below are a one-time manual action, documented here so they're repeatable.

## 1. Setup script (paste into the web UI)

claude.ai/code → cloud environment (cloud icon) → **Add/edit environment** → **Setup script** field. It runs **once as root** on Ubuntu 24.04, before Claude Code launches; the resulting filesystem is snapshotted and reused by later sessions. It re-runs (and the snapshot rebuilds) when you edit the script, change the environment's network settings, or after ~7 days.

```bash
#!/bin/bash
set -euo pipefail

# 1) Install the agent-browser CLI (native Rust binary — zero npm deps, no bundled browser)
npm install -g agent-browser

# 2) System libraries a headless Chrome needs. The sandbox ships chromedriver but not a
#    guaranteed set of Chrome shared libs; this installs them (idempotent, runs as root).
npx --yes playwright install-deps chromium || true

# 3) Point agent-browser at the sandbox's PRE-INSTALLED Playwright Chromium.
#    (`agent-browser install` would download Chrome for Testing from Google's CDN,
#    which the egress gateway blocks — verified 2026-07-22: "tunnel error: unsuccessful".
#    The sandbox already ships Chromium at /opt/pw-browsers/chromium; use it instead.)
mkdir -p /root/.agent-browser
cat > /root/.agent-browser/config.json <<'EOF'
{
  "executablePath": "/opt/pw-browsers/chromium"
}
EOF

# 4) certutil, for the per-session CA import (see the note below — the import
#    itself CANNOT run here; only its tooling can be pre-installed).
apt-get install -y libnss3-tools

# 5) Surface status in the setup log
agent-browser --version && echo "agent-browser provisioned OK"
```

**Why the CA import isn't in the setup script (confirmed 2026-07-22):** Chromium on Linux trusts the NSS store (`~/.pki/nssdb`), not the system CA store, so the sandbox's TLS-inspection CAs must be imported there or every proxied HTTPS page fails `ERR_CERT_AUTHORITY_INVALID` in agent-browser. But the CA bundle (`/root/.ccr/ca-bundle.crt`) is written by the **session** proxy and does not exist yet at setup-script (snapshot) time — the import failed there in practice. It therefore runs per-session via the **committed `SessionStart` hook** `.claude/hooks/session-start.sh` (registered in `.claude/settings.json`): cloud-only (`$CLAUDE_CODE_REMOTE` guard, desktop no-op), idempotent (skips when the certs are already present), and soft-failing (on any failure it logs and exits 0, so the ladder just degrades to WebFetch — it can never block a session). Nothing to remember: the hook fires automatically on every cloud session once merged to `main`. It also self-heals two setup-script gaps — installs `libnss3-tools` if step 4 was skipped, and rewrites the `executablePath` config if the snapshot lost it.

## 2. Network access

The default **Trusted** network level allows npm / PyPI / GitHub / Docker Hub. Two findings from the 2026-07-22 verification session:

- **Chrome-for-Testing CDN is blocked** under the default policy (`googlechromelabs.github.io` → "tunnel error"), which is why §1 uses the pre-installed Chromium instead of `agent-browser install`. If you'd rather have agent-browser's own Chrome, set **Network access** to **Custom** and add `storage.googleapis.com`, `edgedl.me.gvt1.com`, `googlechromelabs.github.io` — but the pre-installed-Chromium route needs no policy change and is the recommended default.
- **General-web intake is still policy-bound.** The same egress policy that blocks the CDN also 403s arbitrary hosts (e.g. `example.com`). A provisioned browser doesn't widen egress — it only adds JS rendering for hosts the policy already allows. For KB intake of arbitrary URLs in the cloud, the environment's network access must allow those hosts; otherwise route that intake to the desktop as before. **§2.1 is the operational version of this bullet** — how to recognise it in under a minute and what the ladder should do about it.

## 2.1 Ladder amendment: host-level policy denial — the failure mode the ladder has no rung for

**The ladder's tiers 1–3 all assume the *page* is the obstacle** — an empty SPA shell, an auth wall, a timeout. Each tier is a different way of getting a page to give up its content. **A host-level network-policy denial is not a page problem, and it defeats all three identically and instantly.** The session's egress gateway refuses the `CONNECT` before any HTTP request exists, so there is no page to render, no wall to authenticate past, and nothing a different client can do differently.

Left unrecognised it costs a full ladder walk and then *reads like a dead link* — which is the expensive part, because a dead link and a policy denial call for opposite responses (drop it vs. route it to the desktop).

### The signature

Observed on one podcast host (`blocked-host.example` below) in two independent cloud sessions, 2026-08-04 and 2026-08-05:

| Tier | Command | Result |
|---|---|---|
| 1 | `fetch-docs <url>` | `curl: (56) CONNECT tunnel failed, response 403` |
| 2 | `fetch-docs <url> --render` | `agent-browser: ✗ Navigation failed: net::ERR_TUNNEL_CONNECTION_FAILED` |
| 3 | WebFetch | `HTTP 403 Forbidden` |

The confirming diagnostic — **run this instead of escalating**:

```bash
curl -sS "$HTTPS_PROXY/__agentproxy/status"
```

```json
"recentRelayFailures": [
  { "kind": "connect_rejected",
    "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
    "host": "blocked-host.example:443" }
]
```

`connect_rejected` on the host you just tried is conclusive. Note the proxy is the **only** component that names the cause — every tier above it reports a generic transport failure, which is exactly why the ladder walks past it.

### The rule: a 403-at-CONNECT short-circuits tiers 2–3

**On tier 1 returning `CONNECT tunnel failed, response 403`, stop escalating. Check the proxy status; on `connect_rejected`, go straight to tier 4** (manual paste / OCR, or route the intake to the desktop). Do not run `--render`, do not run WebFetch.

**Why tier 2 in particular is not an escape hatch — this was the open question, and it is now tested rather than inferred.** The 2026-08-04 session recorded tier 2 as *"n/a — the host never connects, so a headless browser buys nothing,"* which was sound reasoning but not a result: `agent-browser` wasn't confirmed present in that sandbox. The 2026-08-05 session had it provisioned (SessionStart reported `--render is live`) and **actually ran it**: `ERR_TUNNEL_CONNECTION_FAILED`. → **`agent-browser` shares the sandbox's proxy and inherits its policy denials.** `--render` escapes a *client-side rendering* problem, never a *network-policy* one. This is the same finding as §2's bullet ("a provisioned browser doesn't widen egress") arriving from the other direction, and it generalises: **no tier of the ladder can widen egress, because they are all clients behind the same gateway.**

### Distinguishing it from the failures it resembles

| Looks like | Tell it apart by |
|---|---|
| **Dead link / wrong URL** | A sibling page on the same host also fails (`/e/2026-07-29` was live and indexed, yet equally unreachable). A dead link fails for *one* path; a policy denial fails for *every* path on the host. |
| **Auth wall (tier 4's normal trigger)** | An auth wall returns a real page — a login form, a paywall teaser. A policy denial returns **no HTTP response at all**; the failure is at `CONNECT`. |
| **Empty SPA shell (tier 2's trigger)** | A shell is a *successful* fetch of unhelpful content. Here nothing is fetched. |

The destination is tier 4 either way for auth walls and policy denials — but the *reason* differs, and the record should say which, because a policy denial is fixable at the environment level (§2: set Network access to **Custom** and allow the host) while an auth wall never is.

### Consequence for triage records

`/triage` legitimately ranks on unverified metadata — it **predicts and never counts**, so search-snippet metadata is an acceptable input to a rank. `/distill` is not: a summary is never evidence. So when this failure mode forces a blind triage, the listen-list row **must carry an explicit unverified-metadata warning** naming every specific — including the title — as unconfirmed, and directing `/distill` to work from the real source.

## 3. Verify (in a cloud session, once)

Open the repo in a cloud session and run:

```bash
agent-browser --version
bash .claude/skills/fetch-docs/scripts/fetch-docs.sh --check          # expect: agent-browser: OK
bash .claude/skills/fetch-docs/scripts/fetch-docs.sh "<a JS-rendered docs URL>" --render
```

If `--check` reports `agent-browser: OK` and the `--render` fetch returns real content (not an empty `<div id="root">` shell), tier 2 is live in the cloud. **2026-07-22 result: both passed** — `--check` reported OK and a `--render` fetch of a JS-rendered github.com page captured a 310 KB rendered DOM.

### ✅ Mobile shares the cloud environment (verified 2026-08-05)

**Phone sessions get the same provisioned environment as claude.ai/code — confirmed by
running `agent-browser --version` in a mobile session and getting a version number back.**

This was an open question, and the pessimistic answer was the plausible one: if mobile had been a
separate or barer environment, the web-UI setup script and network-access policy would not have
reached it, and mobile intake would have been permanently stuck on WebFetch / manual paste. It is
not. One environment config covers web **and** mobile.

Consequences:

- **Provision once, get both.** The §1 setup script and any §2 network-access change apply to phone
  sessions too. There is no separate mobile provisioning step, and none should be invented.
- **Tier 2 is live on mobile**, so `--render` is available for SPA pages there.
- **§2.1 applies identically on mobile** — same gateway, same policy, so a 403-at-`CONNECT` short-
  circuits to tier 4 there for the same reason.
- The mount recovery in §0 behaves the same way: mobile is a cloud sandbox, so `personal-data` needs
  the per-session `add_repo` attach exactly as on web.

Two quirks observed in that session, for future debugging:

- **GitHub URLs are session-scoped.** The sandbox proxy rewrites github.com requests for repos outside the session's authorized scope into a JSON "access not enabled" stub — a tiny (~400 B) rendered file from a github.com URL means proxy scoping, not a browser failure.
- **Some hosts reset headless Chrome specifically.** `claude.com` properties (e.g. `code.claude.com`) consistently `ERR_CONNECTION_RESET` in the headless browser while `curl`/`openssl` through the same proxy succeed — likely upstream bot-management rejecting the headless-Chrome TLS fingerprint (disabling QUIC, post-quantum key agreement, and ECH didn't help). For such hosts the ladder falls through to WebFetch/manual paste as designed; it's a per-host upstream behavior, not a provisioning gap.

## 4. If it can't be made to work

~~Anthropic's docs confirm `chromedriver` in the sandbox but **do not confirm a Chrome binary or its shared libs**, so provisioning may not succeed.~~ **Resolved 2026-07-22:** the sandbox ships a full Playwright Chromium (v141 at `/opt/pw-browsers/chromium`), and the §1 script provisions successfully against it. The degradation path still stands as the safety net: **unprovisioned, the ladder falls to WebFetch (tier 3) → manual paste/OCR (tier 4)** — the same safe behavior as any environment without `agent-browser`. And even provisioned, hosts outside the environment's network policy (see §2) still need the desktop route — **§2.1** is how to recognise that case fast and why `--render` never rescues it.

## Why this can't just be committed

Per the Claude Code web docs, setup scripts and network settings live **only in the cloud environment config (web UI)** — there's no repo-committable equivalent for system-dependency provisioning. (A `SessionStart` hook *is* committable, but it runs on **every** session, local included, and re-installing a browser each session is the wrong tool — setup scripts run once and cache.) So this file is the durable record; the action is yours to apply once in the web UI.
