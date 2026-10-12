#!/usr/bin/env python3
"""PII / secret pre-commit scanner.

Purpose: block git writes that introduce PII or other toxic content (emails,
phone numbers, SSNs, account/card numbers, court case numbers, and LOCAL-tier
proper nouns from the denylist) into the repo.

Scope: only ADDED lines are scanned (lines introduced by the change) — removed
lines and unchanged context are never flagged. Paths under
scripts/hooks/tests/ and anything under .git/ are never scanned (the former
holds intentionally-toxic synthetic fixtures plus the test scripts that embed
the same synthetic literals inline).
Binary content is skipped silently — these are text regexes; L1 (integrity)
is responsible for binary-file concerns, not this scanner.

Denylist: the denylist of LOCAL-tier proper nouns (people, places, private
project names) is NEVER committed to this repo in plaintext. Sources, checked
in priority order:
  1. env var KB_PII_DENYLIST       — newline-separated terms (how CI injects
                                      the value as a GitHub Actions secret)
  2. file at env KB_PII_DENYLIST_FILE
  3. ~/.kb/pii-denylist.txt        — desktop default, local file outside the repo
One term per line; '#' comments and blank lines are ignored. Matching is
case-insensitive and word-boundary-anchored. If no source is available at
all, a warning is printed to stderr and the scan continues with the regex
patterns only (denylist coverage is degraded, not fatal). On a denylist hit,
the matched term is printed MASKED (first character + "***") so CI logs never
re-leak the term itself.

CLI modes:
  (default)              scan added lines of `git diff --cached`
                          (falls back to the empty tree if there is no HEAD)
  --range BASE..HEAD      scan added lines of each non-merge commit's diff
                          against its first parent, for every commit in range
  --files PATH [PATH...]  scan the ENTIRE contents of the given files (every
                          line counts as "added") — e.g. a one-off scan
                          over existing source files
  --text-file PATH [--label NAME]
                          scan an arbitrary text file as one unit — commit
                          messages (commit-msg hook) and PR/issue bodies.
                          Reports under LABEL, not the path (see below).
  --message-range BASE..HEAD
                          scan the commit MESSAGE of every non-merge commit in
                          a range — the server-side counterpart, and the only
                          wall for anyone who bypassed or never installed the
                          local hook

Why message scanning exists (2026-08-02): file content was gated from
the start, but commit messages never were, and prose is where sensitive detail
actually lands — describing a redaction reproduces the thing being redacted.
Three instances in a single session: a sensitive name quoted in the message
that removed it, an identifier quoted in the message adding the pattern to
catch it, and the same identifier written into a comment in THIS FILE while
documenting that pattern. Only the last was caught by automation; the other two needed a human
to think of it.

⚠️ Do NOT scan a commit message with --files. A message lives at
.git/COMMIT_EDITMSG, and is_excluded() skips anything under .git/, so
`--files .git/COMMIT_EDITMSG` exits 0 having scanned nothing — a silent
fail-open with no output and no hint (verified 2026-08-02). --text-file exists
for exactly this: it reports under a LABEL rather than the path, so the
exclusion cannot suppress the scan.

Output: one line per hit on stderr:
    [PII] <file>:<line-no>: <PATTERN_NAME> — <short explanation>
Exit 0 = clean. Exit 1 = any hit, OR any internal error (fail safe — an error
in the scanner must never silently let content through).

NO BYPASS TOKEN EXISTS for this scanner (unlike the L1/L2 hooks, which have
one). `git commit --no-verify` bypasses local hooks entirely and is BANNED in
this repo by policy — it does not get a special exemption here. The
server-side gate (integrity-gate.yml) re-runs this same scanner on push/PR and is the
backstop for anyone who bypasses (or lacks) the local hook.

One scoped exception (2026-07-11): a line containing
"[pii-allow: phone]" or "[pii-allow: email]" is exempt from the PHONE or
EMAIL pattern respectively, on that line only — for public business contact
details (office numbers, org emails), which are GIT-tier operational data.
The markers are visible in every diff and honored identically by the server
gate. There is NO marker for SSN, ACCOUNT_NUMBER, COURT_CASE, or DENYLIST.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integrity_config  # noqa: E402

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# Formats this scanner must never analyse. It is a TEXT-pattern scanner; the
# internals of a PDF or an Office file are not text, line numbers inside them are
# meaningless, and any "match" is unreviewable.
#
# An extension check is needed because the byte heuristics DISAGREE between modes:
# git marks a file binary only if it finds NUL in the first 8000 bytes, while
# collect_files_mode checks the whole file. A PDF with a text header and
# compressed streams later is therefore BINARY to --files and TEXT to staged mode
# -- so the same file scanned clean one way and blocked the commit the other.
# Observed 2026-08-02 on a LinkedIn profile export. Extension is the only check
# that gives both modes the same answer.
BINARY_EXTENSIONS = (
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".odt", ".ods",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp",
    ".zip", ".gz", ".tar", ".7z", ".rar",
    ".mp3", ".mp4", ".wav", ".m4a", ".webm", ".mov",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".pyc", ".so", ".dll", ".exe", ".bin",
)

EXCLUDED_SUBSTRINGS = (
    # The whole hook-test tree: fixtures/ holds intentionally-toxic synthetic
    # data, and the test scripts embed the same synthetic literals inline.
    # Both are reviewed code/fixtures, not knowledge data.
    "scripts/hooks/tests/",
)

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

# --- Named patterns -----------------------------------------------------
# Each entry: (NAME, [compiled regexes], explanation). A line hits NAME if
# ANY of its regexes match; only one hit is reported per (line, NAME) pair
# even if multiple sub-patterns match.

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Domains whose entire purpose is to NOT identify a person. A
# users.noreply.github.com address is what you use so your real address stays
# private; flagging it as PII is backwards, and it forces awkward workarounds --
# .integrity-paths.json has to list approved commit authors, JSON has no
# comments, so the allow-marker cannot be applied there at all.
#
# This is narrower than it looks: only these exact domains are exempt, and a
# real address at any other domain still trips. Added 2026-08-02.
NOREPLY_EMAIL_DOMAINS = (
    "users.noreply.github.com",
    "noreply.github.com",
)

# Role addresses whose LOCAL PART marks them as non-personal regardless of
# domain -- e.g. noreply@anthropic.com, the identity cloud sessions commit under.
# A no-reply mailbox is by construction not a person's address.
NOREPLY_LOCAL_PARTS = ("noreply", "no-reply", "donotreply", "do-not-reply")

PHONE_RE = re.compile(
    r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}\b"
)

SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

ACCOUNT_KEYWORD_RE = re.compile(
    r"(?:account|acct|routing|iban)\s*(?:number|no\.?|#)?\s*[:#]?\s*\d[\d\- ]{5,}\d",
    re.IGNORECASE,
)
ACCOUNT_CARD_RE = re.compile(r"\b\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}\b")
# Negative lookbehind: a digit run inside a URL path/query (tweet IDs, status
# links, mail thread ids) is not an account number.
#
# ':' was missing and had to be added 2026-08-02. A Gmail permalink in a KB
# source card carries a thread id as "permthid=thread-f:<19 digits>" — the
# character before the run is ':', so it was reported as an account number and
# blocked a migration commit. Safe to exclude: a genuine account keyword
# followed by a colon and digits is matched by ACCOUNT_KEYWORD_RE, which
# requires the keyword and already handles the colon itself.
#
# (Writing this comment with a literal example number tripped the very pattern
# it documents — the fifth such instance in one session. Describe the shape.)
ACCOUNT_BARE_RE = re.compile(r"(?<![/=&?#.:\-])\b\d{13,19}\b")

# The (no|number|#) marker is REQUIRED — with it optional, everyday prose
# ("in case we need", "worst case scenario") false-positives on every commit.
# The identifier token must CONTAIN A DIGIT — otherwise prose like
# "case numbers, court names" (the classification doc itself) trips it.
COURT_KEYWORD_RE = re.compile(
    r"\b(?:case|docket|cause)\s*(?:no\.?|number|#)\s*[:\-]?\s*"
    r"[A-Za-z:\-]*\d[A-Za-z0-9:\-]*",
    re.IGNORECASE,
)
COURT_FEDERAL_RE = re.compile(
    r"\b\d{1,2}:\d{2}-[a-z]{2}-\d{4,}\b", re.IGNORECASE
)

# State court dockets are routinely written "Case NNAANNNNNN" with NO
# no./number/# marker -- which COURT_KEYWORD_RE requires, and therefore misses
# entirely. Verified 2026-08-02: a real docket number sitting in tracked files
# scanned clean, exit 0, against the pattern meant to catch it.
#
# The marker stays REQUIRED in COURT_KEYWORD_RE for the reason documented
# there (without it, "in case we need" fires on every commit). This pattern
# takes a different route: the token AFTER case/docket/cause must be >= 6 chars
# AND contain a digit. Ordinary prose never satisfies both -- "we", "of",
# "scenario", "studies" are either too short or digit-free.
COURT_BARE_DOCKET_RE = re.compile(
    r"\b(?:case|docket|cause)\s+(?=[A-Za-z0-9\-]*\d)[A-Za-z0-9\-]{6,}\b",
    re.IGNORECASE,
)

# Scoped allow-markers (2026-07-11): a line carrying the marker is exempt
# from THAT pattern only — for public business contact details (office
# phone numbers, org emails), which are GIT-tier operational data. Markers
# exist ONLY for PHONE and EMAIL. SSN, ACCOUNT_NUMBER, COURT_CASE, and
# DENYLIST hits are absolute — no marker, no bypass, ever.
ALLOW_MARKERS = {
    "PHONE": "[pii-allow: phone]",
    "EMAIL": "[pii-allow: email]",
}

NAMED_PATTERNS = [
    ("EMAIL", [EMAIL_RE], "looks like an email address"),
    ("PHONE", [PHONE_RE], "looks like a US phone number"),
    ("SSN", [SSN_RE], "looks like a US Social Security Number"),
    (
        "ACCOUNT_NUMBER",
        [ACCOUNT_KEYWORD_RE, ACCOUNT_CARD_RE, ACCOUNT_BARE_RE],
        "looks like an account/card number",
    ),
    (
        "COURT_CASE",
        [COURT_KEYWORD_RE, COURT_FEDERAL_RE, COURT_BARE_DOCKET_RE],
        "looks like a court case/docket number",
    ),
]


# --- Denylist -------------------------------------------------------------


def load_denylist():
    """Return a list of (compiled_regex, original_term) tuples.

    Prints a warning to stderr (and returns []) if no denylist source is
    available at all. Never raises.
    """
    raw = None

    env_inline = os.environ.get("KB_PII_DENYLIST")
    if env_inline:
        raw = env_inline
    else:
        env_file = os.environ.get("KB_PII_DENYLIST_FILE")
        if env_file:
            try:
                raw = Path(env_file).read_text(encoding="utf-8")
            except OSError:
                raw = None
        if raw is None:
            default_path = Path.home() / ".kb" / "pii-denylist.txt"
            try:
                raw = default_path.read_text(encoding="utf-8")
            except OSError:
                raw = None

    if raw is None:
        print(
            "[PII] warning: no denylist loaded — regex patterns only "
            "(set KB_PII_DENYLIST / KB_PII_DENYLIST_FILE or create ~/.kb/pii-denylist.txt)",
            file=sys.stderr,
        )
        if os.environ.get("GITHUB_ACTIONS") == "true":
            # In CI a stderr line scrolls past unread; a workflow annotation is
            # surfaced on the run page and the PR. A repo whose KB_PII_DENYLIST
            # secret is unset/expired must not look identical to one fully
            # protected (2026-08-07 review finding: green-with-no-denylist was
            # indistinguishable from green).
            print(
                "::warning title=PII scan degraded::KB_PII_DENYLIST is not set — "
                "the denylist layer is OFF for this run; regex patterns only"
            )
        return []

    terms = []
    for line in raw.splitlines():
        # Strip a TRAILING inline comment before anything else. A generated or
        # hand-triaged list may annotate terms as "Term\t# seen 3x". Without this, the whole annotated line
        # becomes the term, gets re.escape'd, and matches nothing -- while the
        # scanner still reports a denylist as loaded. Silent total failure of
        # the only defence that catches bare proper nouns.
        term = line.split("#", 1)[0].strip() if not line.lstrip().startswith("#") else ""
        if not term:
            continue
        terms.append(term)

    compiled = [
        (re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE), term)
        for term in terms
    ]
    return compiled


# --- Path exclusion --------------------------------------------------------


def is_excluded(path: str) -> bool:
    norm = path.replace("\\", "/")
    if norm.startswith(".git/") or "/.git/" in norm:
        return True
    if norm.lower().endswith(BINARY_EXTENSIONS):
        return True
    for sub in EXCLUDED_SUBSTRINGS:
        if sub in norm:
            return True
    return False


# --- Diff parsing -----------------------------------------------------------


def parse_diff(diff_text: str):
    """Yield (file_path, line_no, content) for every ADDED line in a unified diff."""
    added = []
    current_file = None
    new_lineno = None
    binary = False

    for line in diff_text.split("\n"):
        if line.startswith("diff --git "):
            current_file = None
            new_lineno = None
            binary = False
            continue
        if line.startswith("Binary files ") and line.endswith(" differ"):
            binary = True
            continue
        if line.startswith("+++ "):
            path = line[4:]
            if path == "/dev/null":
                current_file = None
            elif path.startswith("b/"):
                current_file = path[2:]
            else:
                current_file = path
            continue
        if line.startswith("--- ") and current_file is None:
            # old-file header line, only meaningful before +++ sets current_file
            continue
        if line.startswith("@@"):
            m = HUNK_RE.match(line)
            if m:
                new_lineno = int(m.group(1))
            continue

        if binary or current_file is None or new_lineno is None:
            continue

        if line.startswith("+"):
            added.append((current_file, new_lineno, line[1:]))
            new_lineno += 1
        elif line.startswith("-"):
            pass  # removed line: does not consume a new-file line number
        elif line.startswith(" "):
            new_lineno += 1
        else:
            pass  # e.g. "\ No newline at end of file"

    return added


def _run(args, cwd=None):
    # Decode explicitly as UTF-8 with replacement. text=True alone uses the platform
    # default codec, which on Windows is cp1252: any non-ASCII byte in a staged diff (an
    # em-dash, a curly quote, a middot - all of which this repo's markdown is full of)
    # raised UnicodeDecodeError inside subprocess's reader thread, leaving stdout None and
    # the scan crashing with an unrelated AttributeError. A scanner that dies on ordinary
    # punctuation blocks every commit, and the failure mode gives no hint why.
    # errors="replace" is safe here: replacement affects only the rendering of a byte that
    # was never a regex match candidate, and the line is still scanned.
    return subprocess.run(
        args, cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace"
    )


def collect_staged_mode(cwd=None):
    head_check = _run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=cwd)
    base = "HEAD" if head_check.returncode == 0 else EMPTY_TREE_SHA
    result = _run(["git", "diff", "--cached", "--no-color", base], cwd=cwd)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git diff --cached failed: {result.stderr}")
    return parse_diff(result.stdout)


def collect_range_mode(range_str: str, cwd=None):
    rev_list = _run(["git", "rev-list", "--no-merges", range_str], cwd=cwd)
    if rev_list.returncode != 0:
        raise RuntimeError(f"git rev-list failed: {rev_list.stderr}")
    commits = [c.strip() for c in rev_list.stdout.splitlines() if c.strip()]
    commits.reverse()  # oldest first, for readable output ordering

    added = []
    for commit in commits:
        diff = _run(
            [
                "git",
                "diff-tree",
                "-p",
                "--no-color",
                "-r",
                "--root",
                "--no-commit-id",
                commit,
            ],
            cwd=cwd,
        )
        if diff.returncode != 0:
            raise RuntimeError(f"git diff-tree failed for {commit}: {diff.stderr}")
        added.extend(parse_diff(diff.stdout))
    return added


def collect_text_mode(path, label):
    """Scan an arbitrary text file as one unit, reported under `label`.

    Used for commit messages (label "<commit-msg>") and PR/issue bodies.

    This mode exists rather than reusing --files for a specific reason. A commit
    message lives at .git/COMMIT_EDITMSG, and is_excluded() skips anything under
    .git/ -- so `--files .git/COMMIT_EDITMSG` returns exit 0 having scanned
    NOTHING (verified 2026-08-02). That is a silent fail-open: no output, no
    hint. Here the LABEL is the identifier that reaches is_excluded() and the
    output, so the path exclusion cannot apply and the scan always runs.

    --label is therefore about clear, stable output ("<commit-msg>" rather than
    a machine-specific temp path), not about safety.
    """
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise RuntimeError(f"cannot read {path}: {exc}")
    if b"\x00" in raw:
        return []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Commit messages are UTF-8 by git convention, but a stray encoding must
        # not crash the hook into a fail-open. Decode lossily and scan anyway.
        text = raw.decode("utf-8", errors="replace")
    return [(label, idx, line) for idx, line in enumerate(text.splitlines(), start=1)]


def collect_message_range_mode(range_str: str, cwd=None):
    """Scan the full commit MESSAGE of every non-merge commit in a range.

    The server-side counterpart to the commit-msg hook: it catches messages
    written by anyone who bypassed or never installed the local hook, and every
    cloud/mobile writer, for whom the server gate is the only wall.
    """
    listing = _run(
        ["git", "rev-list", "--no-merges", range_str],
        cwd=cwd,
    )
    if listing.returncode != 0:
        raise RuntimeError(f"git rev-list failed for {range_str}: {listing.stderr}")

    added = []
    for commit in listing.stdout.split():
        msg = _run(["git", "log", "-1", "--format=%B", commit], cwd=cwd)
        if msg.returncode != 0:
            raise RuntimeError(f"git log failed for {commit}: {msg.stderr}")
        label = f"<commit-msg {commit[:8]}>"
        added.extend(
            (label, idx, line)
            for idx, line in enumerate(msg.stdout.splitlines(), start=1)
        )
    return added


def collect_files_mode(paths):
    added = []
    for p in paths:
        path_obj = Path(p)
        try:
            raw = path_obj.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"cannot read {p}: {exc}")
        if b"\x00" in raw:
            continue  # binary: skip silently
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue  # binary (or non-utf8): skip silently
        for idx, content in enumerate(text.splitlines(), start=1):
            added.append((str(p), idx, content))
    return added


# --- Scanning ---------------------------------------------------------------


def load_denylist_exempt_prefixes():
    """Path prefixes where DENYLIST hits are not raised, from this repo's
    .integrity-paths.json key `denylist_exempt_prefixes` (optional).

    WHY THIS EXISTS (2026-08-04). The denylist stops personal terms crossing
    INTO a shareable build repo. `personal-data/private/` is the tier *defined*
    as the home for personal-but-not-toxic content. Applying an absolute
    denylist there means the private store cannot hold private data, which is
    incoherent: it would block every personal write.

    SCOPE, deliberately narrow:
      - Only DENYLIST is exempted. SSN, ACCOUNT_NUMBER and COURT_CASE stay
        absolute EVERYWHERE, including here — those are crown-jewel classes that
        do not belong in any repo, private or not.
      - Only in repos that opt in by declaring the key. Absent key, absent
        config, or any read error => NO exemption. Fail-safe, matching the rest
        of this module: an error must never widen what is allowed.
      - Commit messages and --text-file labels are never exempt: their
        identifier is a label like `<commit-msg abc>`, which matches no path
        prefix.

    The absolute rule still applies wherever the key is absent — in particular
    any repo that is, or may become, public should never declare it.
    """
    try:
        cfg = integrity_config.load()
    except Exception:
        return ()
    prefixes = cfg.get("denylist_exempt_prefixes") or ()
    if not isinstance(prefixes, (list, tuple)):
        return ()
    return tuple(p for p in prefixes if isinstance(p, str) and p)


def denylist_exempt(file_path, exempt_prefixes):
    """True if this path is under an exempt prefix.

    Prefixes are repo-relative, and staged/--range modes report repo-relative
    paths, but --files reports whatever the caller passed — often absolute. An
    absolute path is therefore relativised against the repo root first. Without
    that the pre-seed scan would silently NOT match (stricter, so safe, but
    confusing: the same file exempt one way and flagged the other, which is the
    same mode-disagreement trap the BINARY_EXTENSIONS comment above records)."""
    if not file_path or not exempt_prefixes:
        return False
    norm = file_path.replace("\\", "/")
    candidates = [norm]
    if os.path.isabs(file_path):
        try:
            # realpath BOTH sides: on Windows the caller may hold an 8.3 short
            # path (C:/Users/ADMINI~1/...) while `git rev-parse --show-toplevel`
            # returns the long form (C:/Users/Administrator/...). A plain
            # startswith compares those as different trees and silently declines
            # to exempt. Verified on this machine 2026-08-04.
            real = os.path.realpath(file_path).replace("\\", "/")
            root = os.path.realpath(str(integrity_config.find_repo_root())).replace("\\", "/")
            if os.path.normcase(real).startswith(os.path.normcase(root)):
                candidates.append(real[len(root):].lstrip("/"))
        except Exception:
            pass
    return any(c.startswith(p) for c in candidates for p in exempt_prefixes)


def scan_line(file_path, line_no, content, denylist, exempt_prefixes=()):
    hits = []
    content_lower = content.lower()
    for name, regexes, explanation in NAMED_PATTERNS:
        marker = ALLOW_MARKERS.get(name)
        if marker and marker in content_lower:
            continue  # allow-marker: scoped, line-level, PHONE/EMAIL only
        if name == "EMAIL":
            # Ignore matches whose domain exists to avoid identifying anyone.
            # Only no-reply addresses are dropped; a real address on the same
            # line still trips, because each match is checked individually.
            def _is_noreply(addr):
                a = addr.lower()
                if any(a.endswith("@" + d) for d in NOREPLY_EMAIL_DOMAINS):
                    return True
                return a.split("@", 1)[0] in NOREPLY_LOCAL_PARTS

            real = [m for m in EMAIL_RE.findall(content) if not _is_noreply(m)]
            if real:
                hits.append((file_path, line_no, name, explanation))
            continue
        if any(rx.search(content) for rx in regexes):
            hits.append((file_path, line_no, name, explanation))
    if not denylist_exempt(file_path, exempt_prefixes):
        for rx, term in denylist:
            if rx.search(content):
                masked = term[0] + "***"
                hits.append(
                    (file_path, line_no, "DENYLIST", f"matches denylisted term {masked}")
                )
    return hits


def scan_added_lines(added_lines, denylist, exempt_prefixes=()):
    hits = []
    for file_path, line_no, content in added_lines:
        if file_path is None or is_excluded(file_path):
            continue
        hits.extend(scan_line(file_path, line_no, content, denylist, exempt_prefixes))
    return hits


# --- CLI ---------------------------------------------------------------


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Scan added lines for PII/secrets before they enter the repo."
    )
    parser.add_argument("--range", metavar="BASE..HEAD", help="scan a commit range")
    parser.add_argument(
        "--files", nargs="+", metavar="PATH", help="scan entire file contents"
    )
    parser.add_argument(
        "--text-file",
        metavar="PATH",
        help="scan an arbitrary text file as one unit (commit message, PR body)",
    )
    parser.add_argument(
        "--label",
        metavar="NAME",
        default="<text>",
        help="label for --text-file output (e.g. <commit-msg>); the label, not "
        "the path, is what the scan reports and excludes on",
    )
    parser.add_argument(
        "--message-range",
        metavar="BASE..HEAD",
        help="scan the commit MESSAGE of every non-merge commit in a range",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    try:
        args = parse_args(argv if argv is not None else sys.argv[1:])
        denylist = load_denylist()

        if args.text_file:
            added_lines = collect_text_mode(args.text_file, args.label)
        elif args.message_range:
            added_lines = collect_message_range_mode(args.message_range)
        elif args.files:
            added_lines = collect_files_mode(args.files)
        elif args.range:
            added_lines = collect_range_mode(args.range)
        else:
            added_lines = collect_staged_mode()

        hits = scan_added_lines(added_lines, denylist, load_denylist_exempt_prefixes())
    except Exception as exc:  # fail safe: any internal error blocks the write
        print(f"[PII] error: {exc}", file=sys.stderr)
        return 1

    if hits:
        for file_path, line_no, name, explanation in hits:
            print(f"[PII] {file_path}:{line_no}: {name} — {explanation}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
