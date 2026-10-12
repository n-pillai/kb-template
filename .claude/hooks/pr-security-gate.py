#!/usr/bin/env python3
"""
PreToolUse hook: intercepts gh pr merge and gates it on two things.

  GATE 1 - CI checks are green   (added 2026-08-05)
  GATE 2 - security review confirmation for non-owner PRs

Exit 2 blocks the tool call and shows the message to Claude, which must then
confirm with the owner before re-running.

Author-aware: the hook queries GitHub for the PR's author and auto-passes gate 2
when it is the owner's own account. The owner is $KB_GITHUB_OWNER when set,
otherwise the owner half of the target repo's owner/name. This verifies against GitHub's authorship
record (ground truth) rather than Claude's assertion. External / unverifiable
PRs are blocked (fail-safe).

WHY GATE 1 EXISTS -- 2026-08-05
  GitHub cannot enforce this on these repos. Required status checks and branch
  protection need GitHub Pro for PRIVATE repos; this KB repo and personal-data
  are typically private on the free plan, so the API returns 403 for branch protection. CI there REPORTS, it does not ENFORCE --
  a red check does not stop `gh pr merge`.

  Two failures on 2026-08-04 made that concrete:
    - One PR merged with pr-text-scan RED. The scanner had correctly caught
      a real email address in the PR body; the merge went ahead without anyone
      reading the check. PR bodies cannot be un-published.
    - Three more PRs merged while EVERY workflow was dying at
      startup_failure (allowed_actions had been set to local_only, so
      actions/checkout@v4 was disallowed). Three merges, no gate, no signal.

  Both are the same shape: the only thing standing between a red or absent gate
  and a merge was someone remembering to look. This hook is the enforcement the
  free plan does not provide, placed where it can actually run.

  Pending counts as not-green. Merging before checks finish is the same bet with
  a shorter fuse.

  Zero checks configured is allowed through -- a repo with no CI is not the same
  as a repo whose CI is failing, and blocking there would make the hook unusable
  on repos that legitimately have no workflows.

Manual overrides (both are recorded in the command, which is the point):
  '# owner'            -- skip gate 2 when the author can't be verified
                          (e.g. gh not authenticated)
  '# checks-verified'  -- skip gate 1 when the check status can't be fetched,
                          or when merging a known-red check deliberately
  Needing both means gh is unavailable entirely; pass both.

RESOLVE THE REPO EXPLICITLY -- 2026-08-03
  The previous version ran `gh pr view <n>` with cwd set to the *shell's*
  working directory, ignoring any `cd` inside the command being intercepted.
  gh then resolved the PR number against whatever repo the shell happened to
  be sitting in. Demonstrated live: merging repo-A#54 while the shell was in
  repo B, the hook inspected repo-B#54 -- an unrelated PR -- and auto-passed
  on ITS author.

  That is a bypass, not just noise. PR numbers collide across repos, so an
  external contributor's PR could be auto-passed because a same-numbered PR in
  another repo happens to be the owner's. The External Contributor review rule in
  CLAUDE.md is exactly what that defeats.

  It also caused false blocks: when the shell cwd was not a git repo at all,
  `gh pr view` failed, the author came back None, and legitimate owner PRs were
  fail-safe blocked with no diagnostic -- which trains the operator to reach
  for the '# owner' override reflexively, defeating the gate from the other
  side. Observed on 4 of 5 merges in one session.

  Both are the same root cause: the target repo was inferred from ambient
  state instead of the command. It is now derived from the command itself --
  --repo if given, else the `cd` target -- resolved to owner/name, and passed
  to gh explicitly. If it cannot be determined unambiguously, the hook blocks
  and says why.

  NOTE: since 2026-08-05 '# owner' no longer short-circuits before repo
  resolution, because gate 1 needs the repo too. An unresolvable repo now
  blocks even with '# owner' -- which is correct: per the paragraph above, an
  unresolvable repo usually means the command targets a different repo than
  intended.
"""
import json
import os
import re
import shlex
import subprocess
import sys

# Owner login for gate 2. Empty means "the owner of the target repo".
OWNER_OVERRIDE = os.environ.get("KB_GITHUB_OWNER", "").strip()
GH_TIMEOUT = 15

# Directory the target repo was resolved from, when there is one. Used only
# for the no-selector case in gh_pr_json; see its docstring.
REPO_DIR = None

# Check-run conclusions that mean "do not merge". STARTUP_FAILURE is the one
# from the 2026-08-04 incident: the workflow never ran at all.
FAILING_CONCLUSIONS = {
    "FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE",
}
PASSING_CONCLUSIONS = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def mark_unquoted_newlines(command):
    """Replace unquoted newlines with '; ' so tokenize() preserves them as a
    command boundary.

    FOUND 2026-09-06: shlex's whitespace_split treats '\\n' exactly like a
    space -- a Bash tool call batching several shell lines into one command
    string (which it routinely does) loses every line break before tokenize()
    ever sees it, so nothing downstream can tell where one logical command
    ends and the next begins. Three `gh pr merge` lines in one command string
    reported the FIRST invocation's PR number paired with the THIRD
    invocation's --repo flag, and the 2nd/3rd invocations were not recognized
    as invocations at all (find_merge_indices requires the token before "gh"
    to be a real command boundary, and nothing was there).

    Naive, quote-aware only (single/double quotes; no backslash-escape
    tracking) -- good enough for recognizing `gh pr merge` invocations, not a
    general shell parser. A newline inside a quoted string (a multi-line PR
    body passed inline, say) is correctly left alone."""
    out = []
    quote = None
    for ch in command:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "\n":
            out.append(" ; ")
        else:
            out.append(ch)
    return "".join(out)


def tokenize(command):
    """Split a shell command into tokens, tolerating quoted Windows paths.

    posix=False keeps backslashes intact (C:\\Users\\... must survive); the
    quote characters it leaves behind are stripped afterwards."""
    command = mark_unquoted_newlines(command)
    try:
        tokens = shlex.split(command, posix=False)
    except ValueError:
        tokens = command.split()
    return [t.strip("\"'") for t in tokens]


# Tokens after which a new command can begin. Used to require that a matched
# `gh pr merge` sits at a command position rather than inside prose.
COMMAND_BOUNDARIES = {"&&", "||", ";", "|", "&", "(", "{", "!", "then", "do", "else"}

# Command-modifying prefixes that can precede the real command without being
# a different command themselves -- `time gh pr merge ...` and
# `sudo gh pr merge ...` must still be recognized as merge invocations.
# `timeout N` and `VAR=val` (bare, or after `env`) are handled separately in
# skip_command_prefixes because they consume an extra token.
#
# FOUND 2026-09-06: `time gh pr merge 278 --repo <owner>/<repo> --merge`
# silently skipped the ENTIRE hook -- find_merge_index returned None because
# "time" is not in COMMAND_BOUNDARIES, so the token immediately before "gh"
# failed the boundary check. Every gate no-op'd on a live merge. It looked
# like a timeout; it was a parsing gap.
BARE_PREFIX_COMMANDS = {"time", "sudo", "nice", "ionice", "exec", "command", "nohup", "env"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def skip_command_prefixes(tokens, i):
    """Walk index i backward over recognized command-modifying prefixes to
    find the true start of the command `tokens[i]` ("gh") belongs to.

    Handles `time`/`sudo`/`nice`/... (bare), `timeout 30 ...` / `timeout -s
    TERM 30 ...` (consumes the numeric arg too), and `FOO=bar ...` / `env
    FOO=bar ...` (one or more env-assignment tokens). Returns the index that
    should be checked against COMMAND_BOUNDARIES."""
    while i > 0:
        prev = tokens[i - 1]
        if prev in BARE_PREFIX_COMMANDS:
            i -= 1
            continue
        if prev == "timeout" or (i >= 2 and tokens[i - 2] == "timeout" and prev.lstrip("-").isdigit()):
            i -= 1 if prev == "timeout" else 2
            continue
        if ENV_ASSIGNMENT.match(prev):
            i -= 1
            continue
        break
    return i


def find_merge_indices(tokens):
    """Indices of every 'merge' token that starts a `gh pr merge` INVOCATION
    at command position, in order. A Bash tool call routinely batches several
    shell lines into one `command` string (each logically a separate
    command); if more than one is `gh pr merge`, every one of them needs its
    own gate check -- returning only the first (as this used to) leaves every
    subsequent merge in the same batch completely ungated.

    Matching the three tokens in order matters: a bare tokens.index("merge")
    also matches a path component or a --merge flag.

    COMMAND POSITION IS REQUIRED -- 2026-08-05
      Matching the three words anywhere is a false positive generator, and a
      gate that blocks ordinary commands is a gate that gets uninstalled.

      Observed: a `gh pr create` whose commit message described what breaks
      without this hook -- the plain words "gh pr merge proceeds on red" -- was
      blocked. Two things combined. The PR body contained apostrophes
      ("doesn't", "isn't"), so shlex.split(posix=False) hit an unbalanced quote
      and raised; tokenize() then fell back to a naive whitespace split, which
      turns prose into bare tokens. "gh", "pr", "merge" duly appeared in a row.

      Requiring the preceding token to be a command boundary (or a recognized
      prefix command before one) fixes it: in that fallback the previous
      token was "->", not a separator.

      Trade-off, stated plainly: `sh -c "gh pr merge ..."` still does not
      match, because its previous token is -c, not a recognized prefix. That
      is a narrowing. It is the right side of the trade against blocking
      every PR that discusses merging."""
    indices = []
    for i in range(len(tokens) - 2):
        if tokens[i] == "gh" and tokens[i + 1] == "pr" and tokens[i + 2] == "merge":
            start = skip_command_prefixes(tokens, i)
            if start == 0 or tokens[start - 1] in COMMAND_BOUNDARIES:
                indices.append(i + 2)
    return indices


def parse_invocation(tokens, merge_index, end_index):
    """Return (selector, explicit_repo) from the gh pr merge invocation
    starting at merge_index, never reading past end_index.

    end_index MUST be the start of the next merge invocation in the same
    command string (or len(tokens) if this is the last one) -- 2026-09-06.
    Without a bound, three `gh pr merge` lines batched into one Bash call
    (newlines vanish under shlex, so nothing marks where one logical command
    ends and the next begins) let this function wander into the SECOND
    invocation's --repo flag while keeping the FIRST invocation's PR number,
    silently pairing PR #130 (repo A) with repo B's gate. Reproduced live:
    `gh pr merge 130 --repo repo-a --merge\\ngh pr merge 106 --repo
    repo-b --merge\\ngh pr merge 99 --repo repo-c --merge` in one
    Bash call reported "Target: repo-c PR 130"."""
    stop = {"|", "||", "&&", ";"}
    selector = None
    repo = None
    for j in range(merge_index + 1, min(end_index, len(tokens))):
        t = tokens[j]
        if t in stop or t.startswith("#"):
            break
        if t in ("--repo", "-R") and j + 1 < len(tokens):
            repo = tokens[j + 1]
        elif t.startswith("--repo="):
            repo = t.split("=", 1)[1]
        elif selector is None and (t.isdigit() or t.startswith("http")):
            selector = t  # PR number or URL; branch names fall through to gh
    return selector, repo


def cd_target(tokens, merge_index, start_index):
    """The last `cd <path>` appearing before the gh invocation, no earlier
    than start_index -- 2026-09-06: bounded the same way as parse_invocation,
    so a `cd` belonging to an EARLIER command in the same batch doesn't leak
    into a LATER invocation's repo resolution.

    This is the piece an older version missed. `cd X && gh pr merge N`
    targets the repo at X, not the shell's cwd."""
    path = None
    for j in range(start_index, merge_index):
        if tokens[j] == "cd" and j + 1 < len(tokens):
            candidate = tokens[j + 1]
            if candidate not in ("&&", ";", "||", "|"):
                path = candidate
    return path


def normalize_dir(path):
    """Map an MSYS / Git-Bash path to one a native Windows Python can stat.

    FOUND 2026-08-05, and it is a real bypass, not cosmetics.
      The shell here is Git Bash, so `cd /c/Users/.../repo && gh pr merge N` is
      an ordinary command. But this hook runs under native Windows Python, where
      os.path.isdir('/c/Users/...') is False. repo_of_dir therefore returned
      None for ANY bash-style cd target, and the caller fell through to
      repo_of_dir(hook_cwd) -- the ambient shell cwd.

      That is precisely the ambient-state resolution the 2026-08-03 rewrite
      removed, reintroduced through a path-format side door. Caught when the
      hook blocked a `cd <repo-B> && gh pr merge 150` and reported the
      target as repo-A#150.

      The 2026-08-03 test suite missed it because its cd-target case used a
      Windows-style path, which stats fine."""
    if not path:
        return path
    match = re.match(r"^/(?:cygdrive/)?([A-Za-z])(/.*)?$", path)
    if match:
        return "{}:{}".format(match.group(1).upper(), match.group(2) or "/")
    return path


def repo_of_dir(directory):
    """Resolve a directory to owner/name via gh, or None."""
    directory = normalize_dir(directory)
    if not directory or not os.path.isdir(directory):
        return None
    try:
        out = subprocess.run(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GH_TIMEOUT, cwd=directory,
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def gh_pr_json(selector, repo, field):
    """Run `gh pr view --json <field>` and return (parsed_dict, error_text).

    NO SELECTOR MEANS "the current branch's PR" -- 2026-08-05
      `gh pr view --repo X --json Y` with no PR selector is an error:
      "argument required when using the --repo flag". So a bare `gh pr merge`
      (merge whatever PR this branch has) could not be inspected at all, and
      the hook blocked it with a usage dump instead of a verdict.

      When there is no selector, drop --repo and run gh inside REPO_DIR
      instead, which is exactly how gh resolves a bare `gh pr view`. REPO_DIR
      is the directory the repo was resolved FROM, so this cannot silently
      retarget: if the repo came from an explicit --repo with no directory
      behind it, there is nothing to run in and the error is reported."""
    cmd = ["gh", "pr", "view"]
    cwd = None
    if selector:
        cmd += [selector, "--repo", repo]
    elif REPO_DIR:
        cwd = REPO_DIR
    else:
        return None, ("no PR selector given and no local directory to resolve "
                      "the current branch's PR from")
    cmd += ["--json", field]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GH_TIMEOUT, cwd=cwd,
        )
    except Exception as exc:
        return None, "gh invocation failed: {}".format(exc)
    if out.returncode != 0:
        return None, (out.stderr or out.stdout).strip()[:300]
    try:
        return json.loads(out.stdout), None
    except Exception as exc:
        return None, "could not parse gh output: {}".format(exc)


def pr_author(selector, repo):
    """Return (author_login, error_text). Exactly one is non-None."""
    data, error = gh_pr_json(selector, repo, "author")
    if error:
        return None, error
    login = ((data or {}).get("author") or {}).get("login")
    return (login, None) if login else (None, "gh returned no author field")


def workflow_runs_for_head(repo, selector):
    """Return (bad, pending, error) from the Actions runs API for the PR head.

    WHY THIS EXISTS, SEPARATELY FROM THE ROLLUP -- 2026-08-05
      A workflow that fails to START never creates a check run, so it is absent
      from statusCheckRollup entirely. Verified on a live PR: its rollup held
      only the two Socket Security checks, both SUCCESS, while integrity-gate
      and pr-text-scan had both died at startup_failure. A gate that only asks
      "are the checks green?" passes that PR.

      That is the dangerous shape: broken or disabled CI looks identical to CI
      that has nothing to say. So the runs API is consulted too -- it lists the
      runs themselves, including the ones that never produced a check."""
    data, error = gh_pr_json(selector, repo, "headRefOid")
    if error:
        return None, None, error
    sha = (data or {}).get("headRefOid")
    if not sha:
        return None, None, "gh returned no headRefOid"
    try:
        out = subprocess.run(
            ["gh", "api", "repos/{}/actions/runs?head_sha={}&per_page=100".format(repo, sha)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=GH_TIMEOUT,
        )
    except Exception as exc:
        return None, None, "gh api failed: {}".format(exc)
    if out.returncode != 0:
        return None, None, (out.stderr or out.stdout).strip()[:300]
    try:
        runs = json.loads(out.stdout).get("workflow_runs") or []
    except Exception as exc:
        return None, None, "could not parse runs: {}".format(exc)
    bad, pending = [], []
    for run in runs:
        name = run.get("name") or run.get("path") or "<unnamed run>"
        status = (run.get("status") or "").upper()
        conclusion = (run.get("conclusion") or "").upper()
        if status != "COMPLETED":
            pending.append("{} (run {})".format(name, status.lower() or "queued"))
        elif conclusion and conclusion not in PASSING_CONCLUSIONS:
            bad.append("{} (run {})".format(name, conclusion.lower()))
    return bad, pending, None


def pr_checks(selector, repo):
    """Return (bad, pending, error).

    bad/pending are lists of human-readable check names. An empty rollup yields
    ([], [], None) -- no CI configured is not a failure."""
    data, error = gh_pr_json(selector, repo, "statusCheckRollup")
    if error:
        return None, None, error
    rollup = (data or {}).get("statusCheckRollup") or []
    bad, pending = [], []
    for check in rollup:
        name = check.get("name") or check.get("context") or "<unnamed>"
        if check.get("__typename") == "StatusContext" or "state" in check:
            state = (check.get("state") or "").upper()
            if state in ("FAILURE", "ERROR"):
                bad.append("{} ({})".format(name, state.lower()))
            elif state == "PENDING":
                pending.append(name)
        else:
            status = (check.get("status") or "").upper()
            conclusion = (check.get("conclusion") or "").upper()
            if status and status != "COMPLETED":
                pending.append(name)
            elif conclusion and conclusion not in PASSING_CONCLUSIONS:
                bad.append("{} ({})".format(name, conclusion.lower()))

    # Second source of truth: runs that never became check runs (see above).
    run_bad, run_pending, run_error = workflow_runs_for_head(repo, selector)
    if run_error:
        return None, None, run_error
    seen = set(bad) | set(pending)
    bad += [r for r in run_bad if r not in seen]
    pending += [r for r in run_pending if r not in seen]
    return bad, pending, None


def block_checks(reason, detail_lines, repo, selector):
    sys.stderr.write(
        "MERGE GATE - CI checks are not green.\n\n"
        "  Target: {} PR {}\n".format(repo or "<repo unknown>", selector or "<current branch>")
        + "  {}\n\n".format(reason)
        + "".join("    - {}\n".format(d) for d in detail_lines)
        + "\nThese repos are PRIVATE on the free plan, so GitHub cannot enforce required\n"
        "status checks -- a red gate does not stop a merge. That is why this hook does.\n"
        "On 2026-08-04 a PR merged with pr-text-scan red (a real email address in\n"
        "the PR body, correctly caught), and #97-#99 merged while every workflow was\n"
        "dying at startup_failure.\n\n"
        "Do NOT re-run until you have read the failing check and either fixed it or\n"
        "established it is a false positive. Tell the owner what the check said.\n"
        "If the status genuinely cannot be fetched, or the red check is being accepted\n"
        "deliberately, append '# checks-verified' to the command -- and say why.\n"
    )
    sys.exit(2)


def block(reason, repo=None, selector=None):
    target = ""
    if repo or selector:
        target = "  Target: {} PR {}\n".format(repo or "<repo unknown>",
                                               selector or "<current branch>")
    sys.stderr.write(
        "SECURITY GATE - PR merge intercepted.\n\n"
        + target
        + "  {}\n\n".format(reason)
        + "Before proceeding, confirm the following checks were completed for this PR:\n\n"
        "  [1] /security-review was run on this PR diff\n"
        "  [2] Every hooks.json / settings.json / .claude-plugin/*.json change was\n"
        "      manually read and every 'command' field verified\n"
        "  [3] All description/name/summary text fields were checked for prompt injection\n"
        "      (look for 'ignore previous instructions', embedded commands, unusual directives)\n"
        "  [4] No new scripts or executables were added without explicit review\n\n"
        "If this is the owner's own PR but the author couldn't be verified: re-run with\n"
        "'# owner' appended -- but read the reason above first. A repo that cannot be\n"
        "resolved usually means the command is targeting a different repo than you think.\n"
        "If external contributor: confirm all 4 checks are complete before re-running.\n"
    )
    sys.exit(2)


try:
    data = json.load(sys.stdin)
except Exception:
    # Can't parse hook input — don't break unrelated tool calls.
    sys.exit(0)

command = data.get("tool_input", {}).get("command", "")
hook_cwd = data.get("cwd", "") or ""

if "gh pr merge" not in command:
    sys.exit(0)

tokens = tokenize(command)
merge_indices = find_merge_indices(tokens)
if not merge_indices:
    # The literal string was present but not as a `gh pr merge` invocation at
    # command position (e.g. inside a quoted PR body, or wrapped in an
    # unrecognized prefix command -- see skip_command_prefixes). Nothing is
    # being merged.
    sys.exit(0)

# GATE EVERY INVOCATION IN THE BATCH -- 2026-09-06
#   A single Bash tool call routinely carries several shell lines as one
#   `command` string; each is logically its own command. This used to check
#   only the FIRST `gh pr merge` found, so the second and third in a batch
#   ran completely ungated. Now every invocation found gets the full gate
#   sequence, bounded to its own token range so a later invocation's --repo
#   or PR number can never leak into an earlier one's (see parse_invocation's
#   docstring for the reproduced bug).
for n, merge_index in enumerate(merge_indices):
    start_index = merge_indices[n - 1] + 1 if n > 0 else 0
    end_index = merge_indices[n + 1] - 2 if n + 1 < len(merge_indices) else len(tokens)

    selector, explicit_repo = parse_invocation(tokens, merge_index, end_index)

    # Target repo from the COMMAND, never from ambient shell state.
    cd_dir = cd_target(tokens, merge_index, start_index)
    repo_from_cd = repo_of_dir(cd_dir)
    repo_from_cwd = repo_of_dir(hook_cwd)
    repo = explicit_repo or repo_from_cd or repo_from_cwd

    # Remember the directory the repo was resolved FROM, for the no-selector
    # case in gh_pr_json. Only when that directory is the SAME repo --
    # otherwise running gh there would silently inspect a different repo,
    # which is the 2026-08-03 bug. Reset every iteration: a REPO_DIR resolved
    # for an earlier invocation in the same batch must never leak into a
    # later one that has no directory of its own.
    REPO_DIR = None
    if repo_from_cd == repo:
        REPO_DIR = normalize_dir(cd_dir)
    elif repo_from_cwd == repo:
        REPO_DIR = normalize_dir(hook_cwd)

    if not repo:
        block(
            "Could not determine the target repository from the command "
            "(no --repo, no resolvable `cd` target, and the shell cwd is not a repo).",
            selector=selector,
        )

    # ---- GATE 1: CI checks ---------------------------------------------------
    # Runs before the author gate, and applies to owner PRs too -- the 2026-08-04
    # red-check merge was an owner PR with a red check, which is precisely the case that got
    # through.
    if "# checks-verified" not in command:
        bad, pending, checks_error = pr_checks(selector, repo)
        if checks_error:
            block_checks("Could not fetch check status: {}".format(checks_error),
                         [], repo, selector)
        if bad:
            block_checks("{} check(s) are failing:".format(len(bad)), bad, repo, selector)
        if pending:
            block_checks("{} check(s) have not finished:".format(len(pending)),
                         pending, repo, selector)

    # ---- GATE 2: authorship / security review ---------------------------------
    if "# owner" in command:
        continue

    owner = OWNER_OVERRIDE or repo.split("/", 1)[0]
    author, error = pr_author(selector, repo)
    if author and author.lower() == owner.lower():
        continue

    if author:
        block("Detected PR author: {} (not owner {}).".format(author, owner), repo, selector)
    block("Could not verify PR author: {}".format(error), repo, selector)

sys.exit(0)
