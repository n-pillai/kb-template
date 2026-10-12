#!/usr/bin/env python3
"""Commit-authorship check — server-side, because nothing else can do it.

The rule: commit as the owner when working collaboratively; Claude's identity
is for genuinely independent action only. That rule was ignored at scale, and
not through disobedience -- the instruction asserted "git config is already set
to the owner's credentials", which is true on the home machine and FALSE in
every cloud sandbox, where git config is provisioned fresh with Claude's
identity. It told sessions not to check, so they did not.

The correlation was exact: repos worked only from the home machine carried
ZERO Claude-authored commits; repos also worked from cloud carried 25-45%.

WHY THIS LIVES IN CI, NOT IN pre-commit
  A local hook cannot catch this. `core.hooksPath` is per-clone configuration
  that cloud sandboxes never set, so the very environment producing the wrong
  authorship is the one where local hooks do not run. The server-side
  gate is the ONLY enforcement cloud writers have. Putting this in pre-commit
  would guard exactly the machine that never had the problem.

BYPASS
  A commit message containing [claude-authored] exempts that commit. The rule
  permits Claude's identity for independent action, so the exception has to
  exist -- but it is now a deliberate act recorded in the message rather than a
  silent default. Same shape as the L1/L2 bypass tokens.

Approved identities come from .integrity-paths.json ("approved_authors"), so
this script stays byte-identical across repos and only config differs.

Exit 0 = all authors approved. Exit 1 = violation, or any internal error
(fail-safe: an error must never pass authorship silently).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integrity_config  # noqa: E402

BYPASS_TOKEN = "[claude-authored]"


def run_git(args, cwd=None):
    return subprocess.run(
        ["git"] + args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--range", required=True, metavar="BASE..HEAD")
    ap.add_argument("--repo", default=None)
    args = ap.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        cfg = integrity_config.load(args.repo)
        approved = cfg.get("approved_authors")
        if not approved:
            print("[author] .integrity-paths.json has no 'approved_authors' — "
                  "cannot verify authorship (fail-safe)", file=sys.stderr)
            return 1
        approved = {a.lower() for a in approved}

        # --no-merges: a merge commit's authorship is created by the merging
        # party (often the auto-merge bot) and is not a writer's choice.
        listing = run_git(["rev-list", "--no-merges", args.range], cwd=args.repo)
        if listing.returncode != 0:
            print(f"[author] git rev-list failed: {listing.stderr.strip()}", file=sys.stderr)
            return 1

        violations = []
        for sha in listing.stdout.split():
            info = run_git(["log", "-1", "--format=%ae%n%an%n%B", sha], cwd=args.repo)
            if info.returncode != 0:
                print(f"[author] git log failed for {sha}: {info.stderr.strip()}",
                      file=sys.stderr)
                return 1
            parts = info.stdout.split("\n", 2)
            email = parts[0].strip().lower()
            name = parts[1].strip() if len(parts) > 1 else ""
            body = parts[2] if len(parts) > 2 else ""
            if email in approved:
                continue
            if BYPASS_TOKEN in body:
                print(f"[author] {sha[:8]}: {name} <{email}> — exempt via {BYPASS_TOKEN}")
                continue
            violations.append((sha[:8], name, email))
    except Exception as exc:
        print(f"[author] error: {exc}", file=sys.stderr)
        return 1

    if not violations:
        print("[author] all commit authors approved")
        return 0

    for sha, name, email in violations:
        print(f"[author] {sha}: unapproved author {name} <{email}>", file=sys.stderr)

    print(
        "\n[author] Commits must be authored as the owner. Cloud sandboxes provision\n"
        "[author] fresh git config with Claude's identity, so VERIFY before the\n"
        "[author] first commit in any session — do not assume it is set:\n"
        "[author]\n"
        "[author]   git config user.email\n"
        "[author]   git config user.name\n"
        "[author]\n"
        "[author] To fix for this clone, use an approved no-reply identity from\n"
        "[author] .integrity-paths.json (or set KB_GIT_EMAIL and re-run\n"
        "[author] .claude/hooks/git-identity.sh), then amend or rebase the commits above.\n"
        "[author]\n"
        f"[author] If the work was genuinely independent, add {BYPASS_TOKEN} to the\n"
        "[author] commit message. Authoring at the owner's direction is collaborative,\n"
        "[author] not independent.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
