#!/usr/bin/env python3
"""Shared integrity-layer configuration loader.

The L1 (append-only) and L2 (lossy-rewrite) path lists used to be hardcoded in
append_only.py and diff_heuristic.py. That stops working the moment a second
repo runs the same scripts: personal-data protects private/kb/ rather than this
repo's paths, and default branches differ. So the paths live in per-repo
config, leaving one implementation that every repo can share unchanged.

Config lives at <repo-root>/.integrity-paths.json:

    {
      "protected_branch": "master",
      "l1_exact":    ["knowledge/Recent_Completions.md"],
      "l1_prefixes": ["archives/", "logs/"],
      "l1_suffix":   ".md",
      "l2_files":    ["knowledge/Current_Task_List.md"],
      "l2_prefixes": ["private/kb/entries/"]
    }

`l2_prefixes` is OPTIONAL (added 2026-08-08): directories whose every file gets
the L2 rules — for growing directories that the exact-path `l2_files` list
cannot cover without per-file config churn. Absent or empty is a no-op, so a
repo that does not use it is unaffected; the key exists so each repo can
declare per-path whether its data files admit governed in-place edits (L2) or
stay strictly append-only (L1).

FAIL-SAFE, NOT FAIL-OPEN. A missing or malformed config raises. It must never
degrade to a default path list: in a repo whose config is absent, a default
borrowed from another repo would protect paths that do not exist there and silently protect
NOTHING — a green hook guarding an unguarded tree. Same contract as pii_scan,
where an internal error blocks the write rather than letting it through.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

CONFIG_NAME = ".integrity-paths.json"

REQUIRED_KEYS = ("protected_branch", "l1_exact", "l1_prefixes", "l1_suffix", "l2_files")


class ConfigError(RuntimeError):
    """Raised when the integrity config is missing or malformed."""


def find_repo_root(cwd=None) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=cwd, capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise ConfigError(f"not inside a git work tree: {result.stderr.strip()}")
    return Path(result.stdout.strip())


_CACHE: dict = {}


def load(repo_root=None) -> dict:
    """Load and validate the config. Memoized per repo root -- is_l1() is called
    once per changed path, and an uncached load would spawn a `git rev-parse`
    subprocess for every one of them."""
    cache_key = str(repo_root) if repo_root else "<auto>"
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    root = Path(repo_root) if repo_root else find_repo_root()
    path = root / CONFIG_NAME
    if not path.is_file():
        raise ConfigError(
            f"{CONFIG_NAME} not found at {root}. Every repo running the integrity "
            f"hooks must declare its own L1/L2 paths -- there is deliberately no "
            f"default, because a default would silently protect nothing here."
        )
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot parse {path}: {exc}")

    missing = [k for k in REQUIRED_KEYS if k not in cfg]
    if missing:
        raise ConfigError(f"{path} is missing required key(s): {', '.join(missing)}")

    for key in ("l1_exact", "l1_prefixes", "l2_files"):
        if not isinstance(cfg[key], list) or any(not isinstance(v, str) for v in cfg[key]):
            raise ConfigError(f"{path}: '{key}' must be a list of strings")
    for key in ("protected_branch", "l1_suffix"):
        if not isinstance(cfg[key], str):
            raise ConfigError(f"{path}: '{key}' must be a string")

    # Optional key; normalized here so consumers can index it unconditionally.
    cfg.setdefault("l2_prefixes", [])
    if not isinstance(cfg["l2_prefixes"], list) or any(
        not isinstance(v, str) for v in cfg["l2_prefixes"]
    ):
        raise ConfigError(f"{path}: 'l2_prefixes' must be a list of strings")

    _CACHE[cache_key] = cfg
    return cfg


def is_l1(path: str, cfg: dict) -> bool:
    """True if `path` is L1 (strict append-only) under this repo's config."""
    if path in cfg["l1_exact"]:
        return True
    suffix = cfg["l1_suffix"]
    for prefix in cfg["l1_prefixes"]:
        if path.startswith(prefix) and path.endswith(suffix):
            return True
    return False
