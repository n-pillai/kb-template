#!/usr/bin/env python3
"""L1 strict append-only enforcement hook.

Blocks commits that remove or otherwise unsafely modify lines in
append-only (L1) files, as declared in .integrity-paths.json -- e.g.:

  - exact paths listed in l1_exact
  - any *.md file under archives/
  - any *.md file under logs/

Any removed line (including a line that was edited, since that removes
the old line) is a violation. Deleting or renaming a protected file is
a violation. Adding lines / adding new files is always allowed.

Exception (2026-09-14): the `updated: YYYY-MM-DD` freshness stamp, its
front-matter fences, and a `Last updated:` header line may be replaced.
They are the file's own bookkeeping, refreshed on every legitimate write,
not history. See HEADER_EXEMPT_RE.

A commit message containing the literal token
    [allow-prune: monthly-archive]
bypasses these checks for that commit (used by the monthly archive
pruning flow).

Modes:
  1. Default (staged mode): evaluates `git diff --cached` against HEAD
     (or the empty tree if there is no HEAD yet). Optionally pass
     --commit-msg-file PATH to have the prospective commit message
     checked for the bypass token (this is how a commit-msg hook
     should invoke this script).
  2. --range BASE..HEAD: evaluates every non-merge commit in
     `git rev-list --no-merges BASE..HEAD` against its first parent,
     honoring the bypass token in that commit's own message
     (server-side / CI mode).

Exit 0 = clean. Exit 1 = violation, or any internal error (fails
SAFE: malformed input or a git failure blocks the commit).
Violations are printed to stderr, one per line, formatted as:
    [L1] <file>: <reason>
A clean run prints nothing, unless --verbose is given, in which case
a single summary line is printed to stderr.
"""

import argparse
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integrity_config  # noqa: E402

EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
BYPASS_TOKEN = "[allow-prune: monthly-archive]"

REASON_SUFFIX = (
    "commit blocked; use [allow-prune: monthly-archive] only for the "
    "monthly archive flow"
)


class GitError(RuntimeError):
    pass


def run_git(args, cwd):
    """Run a git command, returning CompletedProcess. Raises GitError on
    non-zero exit for commands where that indicates a real failure (the
    caller decides whether a given non-zero exit is meaningful)."""
    # Decode explicitly as UTF-8. text=True alone uses the platform default codec (cp1252
    # on Windows), so an em-dash or curly quote anywhere in a staged diff raised
    # UnicodeDecodeError inside subprocess's reader thread. The blanket fail-safe handler
    # then exited 1, blocking the commit with an error naming neither the file nor the
    # cause. The same fix was applied to pii_scan.py; this call site and diff_heuristic.py
    # were missed, which only moved the opaque block from pre-commit to commit-msg.
    result = subprocess.run(
        ["git", "-c", "core.quotePath=false"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result


def get_repo_root():
    result = run_git(["rev-parse", "--show-toplevel"], cwd=None)
    if result.returncode != 0:
        raise GitError(
            "could not determine git repo root: "
            + (result.stderr.strip() or "not a git repository")
        )
    return result.stdout.strip()


def get_staged_base(repo_root):
    """Return HEAD if it exists, else the empty tree hash."""
    result = run_git(["rev-parse", "--verify", "-q", "HEAD"], cwd=repo_root)
    if result.returncode == 0:
        return "HEAD"
    return EMPTY_TREE


def is_protected(path, cfg=None):
    """True if `path` is L1-protected under this repo's .integrity-paths.json.

    The list used to be hardcoded here. It moved to per-repo config so the same
    script can run unchanged in every repo using the integrity layer, rather
    than forking per repo. See scripts/hooks/integrity_config.py.
    """
    if cfg is None:
        cfg = integrity_config.load()
    return integrity_config.is_l1(path, cfg)


def get_name_status(repo_root, base, target, staged):
    cmd = ["diff"]
    if staged:
        cmd.append("--cached")
    cmd += ["--name-status", "-M", base]
    if not staged:
        cmd.append(target)
    result = run_git(cmd, cwd=repo_root)
    if result.returncode != 0:
        raise GitError("git diff --name-status failed: " + result.stderr.strip())
    lines = [l for l in result.stdout.split("\n") if l.strip() != ""]
    return lines


def get_numstat(repo_root, base, target, path, staged):
    """Return ('binary', 'binary') for a binary file, else (added, deleted)
    as ints for the given path."""
    cmd = ["diff"]
    if staged:
        cmd.append("--cached")
    cmd += ["--numstat", "-M", base]
    if not staged:
        cmd.append(target)
    cmd += ["--", path]
    result = run_git(cmd, cwd=repo_root)
    if result.returncode != 0:
        raise GitError("git diff --numstat failed: " + result.stderr.strip())
    lines = [l for l in result.stdout.split("\n") if l.strip() != ""]
    if not lines:
        return (0, 0)
    fields = lines[0].split("\t")
    if len(fields) < 2:
        # Unexpected output shape -- fail safe.
        return ("binary", "binary")
    added_s, deleted_s = fields[0], fields[1]
    if added_s == "-" or deleted_s == "-":
        return ("binary", "binary")
    try:
        return (int(added_s), int(deleted_s))
    except ValueError:
        return ("binary", "binary")


def fmt(path, reason):
    return "[L1] {}: {}".format(path, reason)


# Lines whose REPLACEMENT is the file's designed behaviour, not a loss of history:
#   - the `updated: YYYY-MM-DD` freshness stamp (read by freshness checks;
#     every legitimate write must refresh it -- found 2026-09-14 when L1
#     refused every legitimate write to a stamped append-only file)
#   - the front-matter fences around that stamp
#   - the `Last updated:` header line the hand-maintained files carry
# Everything else in an L1 file is history and stays absolute.
HEADER_EXEMPT_RE = re.compile(
    r"^(?:updated:\s*\d{4}-\d{2}-\d{2}\s*|---\s*|\*{0,2}Last updated:.*)$"
)


def is_header_line(line):
    return bool(HEADER_EXEMPT_RE.match(line.rstrip("\r\n")))


def get_removed_lines(repo_root, base, target, path, staged):
    """The '-' lines of a zero-context unified diff for `path`, without the
    leading '-'. Used only after numstat reported deletions, to decide whether
    any of them is a real removal."""
    cmd = ["diff"]
    if staged:
        cmd.append("--cached")
    cmd += ["-U0", "-M", base]
    if not staged:
        cmd.append(target)
    cmd += ["--", path]
    result = run_git(cmd, cwd=repo_root)
    if result.returncode != 0:
        raise GitError("git diff -U0 failed: " + result.stderr.strip())
    out = []
    for line in result.stdout.split("\n"):
        if line.startswith("-") and not line.startswith("---"):
            out.append(line[1:])
    return out


def check_diff(repo_root, base, target, staged):
    """Return a list of formatted violation strings for the diff between
    base and target (or base and the index, when staged)."""
    violations = []
    entries = get_name_status(repo_root, base, target, staged)
    for entry in entries:
        fields = entry.split("\t")
        status = fields[0]
        code = status[0]

        if code in ("R", "C"):
            old_path, new_path = fields[1], fields[2]
        else:
            path = fields[1]

        if code == "A":
            if is_protected(path):
                added, _deleted = get_numstat(repo_root, base, target, path, staged)
                if added == "binary":
                    violations.append(
                        fmt(
                            path,
                            "binary file change cannot be verified as "
                            "append-only -- " + REASON_SUFFIX,
                        )
                    )
            continue

        if code == "D":
            if is_protected(path):
                violations.append(
                    fmt(
                        path,
                        "file deleted -- append-only files cannot be "
                        "removed; " + REASON_SUFFIX,
                    )
                )
            continue

        if code == "M":
            if is_protected(path):
                added, deleted = get_numstat(repo_root, base, target, path, staged)
                if added == "binary":
                    violations.append(
                        fmt(
                            path,
                            "binary file change cannot be verified as "
                            "append-only -- " + REASON_SUFFIX,
                        )
                    )
                elif deleted > 0:
                    # A freshness stamp or header line changing is not history
                    # being lost -- see HEADER_EXEMPT_RE. Count only the rest.
                    removed = get_removed_lines(repo_root, base, target, path, staged)
                    real = [l for l in removed if not is_header_line(l)]
                    if real:
                        violations.append(
                            fmt(
                                path,
                                "removed {} line(s) from append-only file -- "
                                "{}".format(len(real), REASON_SUFFIX),
                            )
                        )
            continue

        if code == "R":
            if is_protected(old_path):
                violations.append(
                    fmt(
                        old_path,
                        "file renamed -- append-only files cannot be "
                        "renamed; " + REASON_SUFFIX,
                    )
                )
            continue

        if code == "C":
            if is_protected(new_path):
                added, _deleted = get_numstat(
                    repo_root, base, target, new_path, staged
                )
                if added == "binary":
                    violations.append(
                        fmt(
                            new_path,
                            "binary file change cannot be verified as "
                            "append-only -- " + REASON_SUFFIX,
                        )
                    )
            continue

        # Anything else (type change, unmerged, unknown status codes) --
        # fail safe.
        target_path = new_path if code in ("R", "C") else path
        if is_protected(target_path):
            violations.append(
                fmt(
                    target_path,
                    "unsupported change type '{}' -- {}".format(
                        status, REASON_SUFFIX
                    ),
                )
            )

    return violations


def has_bypass_token(message):
    return BYPASS_TOKEN in message


def read_commit_message(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def get_first_parent(repo_root, commit):
    result = run_git(["rev-parse", commit + "^"], cwd=repo_root)
    if result.returncode == 0:
        return result.stdout.strip()
    return EMPTY_TREE


def get_commits_no_merge(repo_root, base, target):
    result = run_git(
        ["rev-list", "--no-merges", "{}..{}".format(base, target)], cwd=repo_root
    )
    if result.returncode != 0:
        raise GitError("git rev-list failed: " + result.stderr.strip())
    return [c for c in result.stdout.split("\n") if c.strip() != ""]


def get_commit_message(repo_root, commit):
    result = run_git(["log", "-1", "--format=%B", commit], cwd=repo_root)
    if result.returncode != 0:
        raise GitError("git log failed: " + result.stderr.strip())
    return result.stdout


def run_staged_mode(repo_root, commit_msg_file, verbose):
    bypass = False
    if commit_msg_file:
        message = read_commit_message(commit_msg_file)
        bypass = has_bypass_token(message)

    if bypass:
        if verbose:
            sys.stderr.write(
                "[L1] bypass token present -- skipping append-only checks\n"
            )
        return []

    base = get_staged_base(repo_root)
    return check_diff(repo_root, base, None, staged=True)


def run_range_mode(repo_root, range_arg, verbose):
    parts = range_arg.split("..")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise GitError(
            "invalid --range value {!r}; expected BASE..HEAD".format(range_arg)
        )
    base, target = parts[0], parts[1]

    violations = []
    for commit in get_commits_no_merge(repo_root, base, target):
        message = get_commit_message(repo_root, commit)
        if has_bypass_token(message):
            if verbose:
                sys.stderr.write(
                    "[L1] {}: bypass token present -- skipping\n".format(commit)
                )
            continue
        parent = get_first_parent(repo_root, commit)
        violations.extend(check_diff(repo_root, parent, commit, staged=False))
    return violations


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Block commits that remove lines from append-only (L1) files."
    )
    parser.add_argument(
        "--commit-msg-file",
        help="Path to the prospective commit message (staged mode only).",
    )
    parser.add_argument(
        "--range",
        help="BASE..HEAD -- evaluate each non-merge commit in the range "
        "against its first parent (server-side / CI mode).",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print a summary line on a clean run."
    )
    args = parser.parse_args(argv)

    try:
        repo_root = get_repo_root()
        if args.range:
            violations = run_range_mode(repo_root, args.range, args.verbose)
        else:
            violations = run_staged_mode(
                repo_root, args.commit_msg_file, args.verbose
            )
    except GitError as exc:
        sys.stderr.write("[L1] error: {}\n".format(exc))
        sys.exit(1)
    except OSError as exc:
        sys.stderr.write("[L1] error: {}\n".format(exc))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 -- fail safe on any surprise
        sys.stderr.write("[L1] internal error: {}\n".format(exc))
        sys.exit(1)

    if violations:
        for v in violations:
            sys.stderr.write(v + "\n")
        sys.exit(1)

    if args.verbose:
        sys.stderr.write("[L1] clean -- no append-only violations\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
