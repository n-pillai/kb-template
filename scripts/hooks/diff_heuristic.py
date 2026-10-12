#!/usr/bin/env python3
"""L2 diff-heuristic git hook.

Blocks lossy rewrites of L2-protected knowledge files by comparing the OLD
and NEW full content of each protected file and flagging:

  1. Removed-line ratio > 20% (multiset diff on normalized lines).
  2. A "### " section heading present in OLD but absent in NEW.
  3. Deletion or rename of a protected file (path disappears from the new
     side while it existed on the old side).

Bypass: a commit message containing "[allow-rewrite: weekly]" or
"[allow-rewrite: monthly]" makes all L2 checks pass for that commit.

Modes
-----
Default (staged):
    Compares the HEAD version of each L2 file against the staged (index)
    version. If HEAD has no such path, OLD is treated as empty (pass).
    Optional --commit-msg-file PATH supplies the pending commit message so
    the bypass tokens can be honored (e.g. from a commit-msg hook).

--range BASE..HEAD:
    Walks every non-merge commit in `git rev-list --no-merges BASE..HEAD`
    and compares each commit's first-parent version of a file against the
    commit's own version, honoring that commit's own message for bypass
    tokens.

Fails safe: any internal error, git failure, or undecodable file content
exits 1 with an explanation on stderr.

Output: violations are printed to stderr, one per line, as:
    [L2] <file>: <reason>
Exit 0 = clean, 1 = violation(s) found or an internal error occurred.
"""

import argparse
import subprocess
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integrity_config  # noqa: E402

# L2 paths come from <repo-root>/.integrity-paths.json rather than being
# hardcoded here, so this script can run unchanged in every repo using the
# integrity layer rather than forking per repo. Fail-safe: a missing or malformed
# config raises rather than falling back to a default list, because a default
# from another repo would silently protect nothing here.
def _l2_files():
    return integrity_config.load()["l2_files"]


def _l2_prefixes():
    # Optional config key (2026-08-08): directories whose EVERY file gets the
    # L2 rules -- for growing directories (personal-data's private/kb/entries/)
    # that the exact-path l2_files list cannot cover without per-file config
    # churn. integrity_config normalizes the key, so absent == [] == no-op and
    # repos not using it are unaffected.
    return integrity_config.load()["l2_prefixes"]


def ls_tree_paths(rev, prefix):
    """Paths under `prefix` at `rev`; [] when the rev or prefix is absent.

    Enumerated at the OLD revision deliberately: L2's rules need the old
    content (removed-line ratio, dropped sections, deletion), and a file that
    is new under the prefix has nothing to lose yet.
    """
    rc, out, _err = run_git(["ls-tree", "-r", "--name-only", rev, "--", prefix])
    if rc != 0:
        return []
    return [p for p in out.decode("utf-8", "replace").splitlines() if p]


def _l2_paths_at(rev):
    """The full L2 path set for one comparison: exact files + prefix members."""
    paths = list(_l2_files())
    for prefix in _l2_prefixes():
        for p in ls_tree_paths(rev, prefix):
            if p not in paths:
                paths.append(p)
    return paths

BYPASS_TOKENS = ("[allow-rewrite: weekly]", "[allow-rewrite: monthly]")
BYPASS_HINT = (
    "bypass with a commit message containing "
    "[allow-rewrite: weekly] or [allow-rewrite: monthly]"
)
REMOVED_RATIO_THRESHOLD = 0.20


def run_git(args):
    """Run git and return (returncode, stdout_bytes, stderr_text)."""
    proc = subprocess.run(
        ["git"] + args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stdout, proc.stderr.decode("utf-8", "replace")


def git_show(rev_path):
    """Return decoded text content of `git show <rev_path>`, or None if the
    path does not exist at that revision (or the revision itself does not
    exist yet, e.g. no HEAD / no parent commit)."""
    rc, out, _err = run_git(["show", rev_path])
    if rc != 0:
        return None
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as e:
        raise RuntimeError(f"could not decode {rev_path!r} as UTF-8: {e}")


def normalize(text):
    """Split into lines, stripping a trailing '\\r' from every line so CRLF
    churn does not trip the heuristic. Drops the single phantom empty
    element produced when the text ends with a trailing newline."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line[:-1] if line.endswith("\r") else line for line in lines]


def fmt_violation(path, reason, context=None):
    ctx = f" (commit {context[:8]})" if context else ""
    return f"[L2] {path}: {reason}{ctx} — {BYPASS_HINT}"


def check_file(old_content, new_content, path, violations, context=None):
    """Evaluate the three L2 violation rules for one file and append any
    findings (as formatted strings) to `violations`."""
    if new_content is None:
        if old_content is not None:
            violations.append(fmt_violation(path, "file deleted or renamed", context))
        return

    old_lines = normalize(old_content) if old_content is not None else []
    new_lines = normalize(new_content)
    old_total = len(old_lines)

    # Rule 1: removed-line ratio. Old file empty (or new file) -> pass.
    if old_total > 0:
        removed = sum((Counter(old_lines) - Counter(new_lines)).values())
        ratio = removed / old_total
        if ratio > REMOVED_RATIO_THRESHOLD:
            pct = round(ratio * 100)
            violations.append(
                fmt_violation(
                    path,
                    f"{pct}% of lines removed (>20% threshold)",
                    context,
                )
            )

    # Rule 2: dropped "### " section heading (exact normalized string).
    new_line_set = set(new_lines)
    seen = set()
    for line in old_lines:
        if line.startswith("### ") and line not in seen:
            seen.add(line)
            if line not in new_line_set:
                violations.append(
                    fmt_violation(path, f"dropped section {line!r}", context)
                )


def read_commit_message(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def has_bypass_token(message):
    return any(tok in message for tok in BYPASS_TOKENS)


def handle_staged(commit_msg_file, violations):
    if commit_msg_file:
        message = read_commit_message(commit_msg_file)
        if has_bypass_token(message):
            return  # bypass: all L2 checks pass for this commit

    for path in _l2_paths_at("HEAD"):
        old_content = git_show(f"HEAD:{path}")
        new_content = git_show(f":{path}")
        check_file(old_content, new_content, path, violations)


def handle_range(range_spec, violations):
    parts = range_spec.split("..")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise RuntimeError(f"invalid --range spec {range_spec!r} (expected BASE..HEAD)")
    base, head = parts

    rc, out, err = run_git(["rev-list", "--no-merges", "--reverse", f"{base}..{head}"])
    if rc != 0:
        raise RuntimeError(f"git rev-list failed for {range_spec!r}: {err.strip()}")
    shas = out.decode("utf-8", "replace").split()

    for sha in shas:
        rc, out2, err2 = run_git(["log", "-1", "--format=%B", sha])
        if rc != 0:
            raise RuntimeError(f"git log failed for {sha}: {err2.strip()}")
        message = out2.decode("utf-8", "replace")
        if has_bypass_token(message):
            continue  # bypass: all L2 checks pass for this commit

        for path in _l2_paths_at(f"{sha}^"):
            old_content = git_show(f"{sha}^:{path}")
            new_content = git_show(f"{sha}:{path}")
            check_file(old_content, new_content, path, violations, context=sha)


def main(argv=None):
    parser = argparse.ArgumentParser(description="L2 diff-heuristic git hook.")
    parser.add_argument(
        "--range",
        dest="range_spec",
        default=None,
        help="BASE..HEAD — check every non-merge commit in this range",
    )
    parser.add_argument(
        "--commit-msg-file",
        dest="commit_msg_file",
        default=None,
        help="path to the pending commit message (default/staged mode only)",
    )
    args = parser.parse_args(argv)

    try:
        rc, _out, err = run_git(["rev-parse", "--is-inside-work-tree"])
        if rc != 0:
            print(f"[L2] internal error: not inside a git repository: {err.strip()}", file=sys.stderr)
            return 1

        violations = []
        if args.range_spec:
            handle_range(args.range_spec, violations)
        else:
            handle_staged(args.commit_msg_file, violations)

        if violations:
            for v in violations:
                print(v, file=sys.stderr)
            return 1
        return 0
    except Exception as e:  # fail safe
        print(f"[L2] internal error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
