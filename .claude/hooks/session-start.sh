#!/bin/bash
# SessionStart hook — cloud sandbox only: make headless Chromium trust the
# sandbox's TLS-inspection proxy so `fetch-docs --render` (tier 2) works.
#
# Why per-session: the env setup script runs at snapshot time, before the
# session proxy writes /root/.ccr/ca-bundle.crt, so the CA import can't be
# baked into the snapshot (verified 2026-07-22). Chromium on Linux reads the
# NSS store (~/.pki/nssdb), not the system CA store — without this import
# every proxied HTTPS page fails ERR_CERT_AUTHORITY_INVALID in agent-browser.
#
# Design: idempotent (skips when certs are already present), soft-failing
# (never blocks the session — on any failure the fetch ladder just degrades
# to WebFetch, same as an unprovisioned environment), desktop no-op.
set -uo pipefail

# Desktop / local sessions: nothing to do.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

CA_BUNDLE=/root/.ccr/ca-bundle.crt
NSSDB=/root/.pki/nssdb

# No proxy CA bundle → no TLS inspection to trust.
[ -f "$CA_BUNDLE" ] || exit 0

# certutil comes from libnss3-tools; the env setup script should install it,
# but recover in-session if it's missing.
if ! command -v certutil >/dev/null 2>&1; then
  apt-get install -y libnss3-tools >/dev/null 2>&1 || {
    echo "session-start: libnss3-tools unavailable — skipping NSS CA import; fetch-docs --render will fall back to WebFetch" >&2
    exit 0
  }
fi

# Defensive: if the snapshot lost the agent-browser config, restore it so the
# CLI finds the sandbox's pre-installed Chromium (see docs/cloud-environment-setup.md).
if command -v agent-browser >/dev/null 2>&1 && [ ! -f /root/.agent-browser/config.json ] && [ -x /opt/pw-browsers/chromium ]; then
  mkdir -p /root/.agent-browser
  printf '{\n  "executablePath": "/opt/pw-browsers/chromium"\n}\n' > /root/.agent-browser/config.json
fi

# Already imported in this container → done.
if certutil -d sql:"$NSSDB" -L 2>/dev/null | grep -q "anthropic-egress-ca-0"; then
  exit 0
fi

mkdir -p "$NSSDB"
certutil -d sql:"$NSSDB" -N --empty-password 2>/dev/null || true

tmpd=$(mktemp -d)
trap 'rm -rf "$tmpd"' EXIT
if ! csplit -sz -f "$tmpd/ca-" "$CA_BUNDLE" '/-----BEGIN CERTIFICATE-----/' '{*}' 2>/dev/null; then
  echo "session-start: could not split $CA_BUNDLE — skipping NSS CA import" >&2
  exit 0
fi

# The bundle mixes ~150 standard roots (Chromium already trusts those) with the
# Anthropic egress/TLS-inspection CAs; import only the Anthropic ones.
i=0
for f in "$tmpd"/ca-*; do
  if openssl x509 -in "$f" -noout -subject 2>/dev/null | grep -q "O = Anthropic"; then
    if certutil -d sql:"$NSSDB" -A -t "C,," -n "anthropic-egress-ca-$i" -i "$f" </dev/null 2>/dev/null; then
      i=$((i+1))
    fi
  fi
done

if [ "$i" -gt 0 ]; then
  echo "session-start: imported $i Anthropic CA(s) into Chromium NSS store — fetch-docs --render is live"
else
  echo "session-start: no Anthropic CAs found in $CA_BUNDLE — fetch-docs --render may fail on cert errors" >&2
fi
exit 0
