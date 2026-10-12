# Invoked by write-branch-gate.sh (PreToolUse Bash hook). Reads the hook's JSON
# on stdin; exit 2 blocks the tool call. See the shim for the full rationale.
import json, os, re, subprocess, sys

ALLOWED = ("write/", "sync/auto")

# The private data repo is named by KB_DATA_REPO (<owner>/<repo> or just <repo>),
# the same setting the mount hook uses; unset, it is "personal-data".
DATA_REPO = (os.environ.get("KB_DATA_REPO") or "personal-data").strip().strip("/").lower()
if DATA_REPO.endswith(".git"):
    DATA_REPO = DATA_REPO[:-4]

def origin_slug(url):
    """'owner/repo' from any origin URL form (https, ssh, a local git proxy path)."""
    path = re.sub(r"\.git$", "", url.strip().rstrip("/")).replace(":", "/")
    return "/".join(path.split("/")[-2:]).lower()

def is_data_repo(url):
    if not url:
        return False
    slug = origin_slug(url)
    if "/" in DATA_REPO:
        return slug == DATA_REPO
    return slug.split("/")[-1] == DATA_REPO

def repo_of(d):
    """origin URL for a directory, or '' if it isn't a git repo we can read."""
    try:
        return subprocess.run(["git", "-C", d, "remote", "get-url", "origin"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""

def current_branch(d):
    try:
        return subprocess.run(["git", "-C", d, "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

cmd = (data.get("tool_input") or {}).get("command") or ""
cwd = data.get("cwd") or "."

# Split on shell separators so `cd X && git push` and `a; git push` both resolve
# the directory that is actually in effect for the push.
segments = re.split(r"&&|\|\||;|\n", cmd)

target_dir = cwd
push_seg = None
for seg in segments:
    m = re.search(r"\bcd\s+(?:--\s+)?([\"']?)([^\"'\s]+)\1", seg)
    if m:
        target_dir = m.group(2)
    if re.search(r"\bgit\b[^|]*\bpush\b", seg):
        push_seg = seg
        # `git -C <dir> push` overrides any preceding cd for this command only.
        mc = re.search(r"\bgit\s+(?:-C\s+([\"']?)([^\"'\s]+)\1\s+)", seg)
        if mc:
            target_dir = mc.group(2)
        break

if push_seg is None:
    sys.exit(0)

origin = repo_of(target_dir)
if not is_data_repo(origin):
    sys.exit(0)   # not the private data repo — this KB repo etc. push freely

# A DELETION is always safe: it removes a ref, so it can never strand work on
# one. Both spellings must pass, because deleting a stray non-write branch is
# exactly the remediation this gate's own message recommends — blocking it would
# trap the operator between the gate and its own advice. (Caught 2026-08-27 while
# cleaning up the branch that prompted the gate.)
if re.search(r"(?:^|\s)(?:--delete|-d)(?:\s|$)", push_seg):
    sys.exit(0)

# Resolve the ref being pushed. Handles: `git push`, `push -u origin <br>`,
# `push origin HEAD:refs/heads/<br>`, `push origin <src>:<dst>`.
tokens = push_seg.split()
try:
    i = tokens.index("push")
except ValueError:
    i = next((k for k, t in enumerate(tokens) if t.endswith("push")), -1)
args, k = [], i + 1
FLAGS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
while k < len(tokens):
    t = tokens[k]
    if t in FLAGS_WITH_VALUE:
        k += 2
        continue
    if not t.startswith("-"):
        args.append(t)
    k += 1

# args[0] is the remote when present; the ref is what follows it.
refs = args[1:] if len(args) >= 2 else []
if refs:
    if refs[0].startswith(":"):           # `push origin :branch` — also a delete
        sys.exit(0)
    ref = refs[0].split(":")[-1]          # dst half of a refspec
    ref = re.sub(r"^refs/heads/", "", ref)
    if ref in ("HEAD", ""):
        ref = current_branch(target_dir)
else:
    ref = current_branch(target_dir)      # bare `git push` / `push origin`

if not ref:
    print("[write-branch-gate] BLOCKED: cannot determine the branch for a push "
          "into %s, so this fails closed.\n"
          "Re-run naming the branch explicitly: "
          "git push -u origin write/kb-<cmd>-<timestamp>" % DATA_REPO, file=sys.stderr)
    sys.exit(2)

if ref.startswith(ALLOWED) or ref == "sync/auto":
    sys.exit(0)

print(
  "[write-branch-gate] BLOCKED — pushing the private data repo (%s) to '%s'.\n"
  "\n"
  "Its auto-merge workflow triggers ONLY on push to write/** (or sync/auto).\n"
  "A push to '%s' will succeed, nothing turns red, and the work will then sit\n"
  "on a branch nothing merges. main never moves and nothing errors. This is the\n"
  "2026-08-27 stranding; see docs/solutions/architecture-patterns/\n"
  "harness-branch-default-silently-strands-writes-2026-08-27.md\n"
  "\n"
  "Do this instead:\n"
  "  git -C <data-repo> branch write/kb-<cmd>-$(date -u +%%Y%%m%%d-%%H%%M)\n"
  "  git -C <data-repo> push -u origin write/kb-<cmd>-<timestamp>\n"
  "\n"
  "This is the repo owner's standing write topology and it takes precedence over a\n"
  "session instruction pinning a different branch name — that instruction is a\n"
  "platform default applied to every attached repo, not a decision about this one.\n"
  "It binds this KB repo, where claude/** is correct; it does not bind the private data repo.\n"
  "Tell the operator which branch you used." % (DATA_REPO, ref, ref),
  file=sys.stderr)
sys.exit(2)
