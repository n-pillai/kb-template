#!/bin/bash
# setup-private-repo.sh — fill a new, empty private data repo with everything the KB needs.
#
# Usage:  bash scripts/setup-private-repo.sh <path-to-your-private-repo-clone>
#
# The private repo must already exist on GitHub with at least one commit on
# `main` (tick "Add a README file" when you create it), and be cloned locally.
#
# What it does, all on a new write/kb-setup-<timestamp> branch:
#   private/kb/                   an empty KB built from example-data/kb/ (the example
#                                 entry, card and theme are left out; projects.md keeps
#                                 its two example projects for you to replace)
#   .github/workflows/auto-merge.yml   checks and merges every write/** branch
#   scripts/hooks/                the integrity checks auto-merge.yml runs
#   .integrity-paths.json         which files those checks protect, and your
#                                 no-reply address as the approved author
# then commits and pushes the branch. auto-merge.yml is in that branch, so the
# push itself triggers it: if the run goes green and main gains private/kb/,
# the whole write path works end to end.
#
# Safe to re-run: it refuses to overwrite a private/kb/ that already exists.
set -euo pipefail

TEMPLATE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-}"

die() { echo "setup: $*" >&2; exit 1; }

# A Python that actually runs (on Windows `python3` can be a Microsoft Store stub).
PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" --version >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || die "Python 3 is not installed. Install it from https://www.python.org/downloads/ and re-run."

[ -n "$TARGET" ] || die "usage: bash scripts/setup-private-repo.sh <path-to-your-private-repo-clone>"
[ -d "$TARGET/.git" ] || die "$TARGET is not a git clone. Clone your private repo first: git clone https://github.com/<you>/personal-data"
TARGET="$(cd "$TARGET" && pwd)"
[ "$TARGET" != "$TEMPLATE_DIR" ] || die "that is this template repo; point it at your PRIVATE repo's clone"

[ -e "$TARGET/private/kb" ] && die "$TARGET/private/kb already exists, so this repo is already set up. Nothing changed."

git -C "$TARGET" fetch --quiet origin || die "could not reach the private repo's GitHub remote (git fetch failed)"
git -C "$TARGET" rev-parse --verify --quiet origin/main >/dev/null \
  || die "the private repo has no 'main' branch on GitHub yet. Add a README on GitHub (Add file -> Create new file -> README.md -> Commit), then re-run."
[ -z "$(git -C "$TARGET" status --porcelain)" ] || die "the private repo has uncommitted changes; commit or discard them first"

# The no-reply address every commit must be authored as.
EMAIL="${KB_GIT_EMAIL:-$(git -C "$TARGET" config user.email || true)}"
case "$EMAIL" in
  *@users.noreply.github.com) ;;
  *) die "your git email is '${EMAIL:-unset}', not a GitHub no-reply address.
  Find yours at https://github.com/settings/emails (it looks like 12345678+yourname@users.noreply.github.com),
  then run:  git -C \"$TARGET\" config user.email \"<that address>\"   and re-run this script." ;;
esac
NAME="${KB_GIT_NAME:-$(git -C "$TARGET" config user.name || true)}"
if [ -z "$NAME" ]; then NAME="${EMAIL%%@*}"; NAME="${NAME#*+}"; fi
git -C "$TARGET" config user.email "$EMAIL"
git -C "$TARGET" config user.name "$NAME"

BRANCH="write/kb-setup-$(date -u +%Y%m%dT%H%M%SZ)"
git -C "$TARGET" checkout --quiet -b "$BRANCH" origin/main

mkdir -p "$TARGET/private" "$TARGET/.github/workflows" "$TARGET/scripts"
cp -R "$TEMPLATE_DIR/example-data/kb" "$TARGET/private/kb"
rm -f "$TARGET/private/kb/README.md"   # explains the template folder, not your KB
# Start clean: the example entry, library card and theme show the formats in
# example-data/, but entries are protected from deletion once committed, so they
# are left out here rather than installed for you to remove later.
rm -f "$TARGET"/private/kb/entries/*example*.md "$TARGET"/private/kb/library/*example*.md
touch "$TARGET/private/kb/entries/.gitkeep" "$TARGET/private/kb/library/.gitkeep"
"$PY" - "$TARGET/private/kb" <<'PYEOF'
import re, sys
from pathlib import Path
kb = Path(sys.argv[1])
index = kb / "INDEX.md"
lines = [l for l in index.read_text(encoding="utf-8").splitlines(keepends=True)
         if "(EXAMPLE)" not in l and "`example-theme`" not in l]
index.write_text("".join(lines), encoding="utf-8")
themes = kb / "THEMES.md"
text = themes.read_text(encoding="utf-8")
themes.write_text(re.sub(r"### example-theme\n.*?(?=\n## )", "", text, flags=re.S), encoding="utf-8")
PYEOF
cp "$TEMPLATE_DIR/example-data/private-repo-files/auto-merge.yml" "$TARGET/.github/workflows/auto-merge.yml"
rm -rf "$TARGET/scripts/hooks"
cp -R "$TEMPLATE_DIR/scripts/hooks" "$TARGET/scripts/hooks"
find "$TARGET/scripts/hooks" -name '__pycache__' -prune -exec rm -rf {} +
sed "s|__YOUR_NOREPLY_ADDRESS__|$EMAIL|" \
  "$TEMPLATE_DIR/example-data/private-repo-files/integrity-paths.json" > "$TARGET/.integrity-paths.json"

# Turn on the local commit checks in this clone too (they read .integrity-paths.json).
git -C "$TARGET" config core.hooksPath scripts/hooks

git -C "$TARGET" add -A
git -C "$TARGET" commit --quiet -m "chore: set up the knowledge base (starter content, checks, auto-merge)"
git -C "$TARGET" push --quiet -u origin "$BRANCH"
git -C "$TARGET" checkout --quiet main 2>/dev/null || git -C "$TARGET" checkout --quiet -b main origin/main

cat <<EOF

Done. Pushed $BRANCH to your private repo.

Next:
  1. Open your private repo on GitHub -> Actions tab. A run called "auto-merge" should
     turn green within a minute or two.
  2. Then, in the repo's Code tab, main should now contain a private/kb/ folder and the
     $BRANCH branch should be gone. That means saving works end to end.
  3. Update your local copy:  git -C "$TARGET" pull

If the run is red, click it and read the failed step; the branch stays in place until fixed.
EOF
