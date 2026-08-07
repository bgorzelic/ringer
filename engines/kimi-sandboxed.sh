#!/bin/bash
# Ringer engine wrapper: run Kimi Code under a macOS Seatbelt sandbox.
#
# Kimi Code has no OS-level sandbox of its own and no --cwd/-C flag, so this
# wrapper does two jobs opencode-sandboxed.sh does for OpenCode: cd into the
# task directory before exec (kimi always runs against the process cwd), and
# supply real containment — full network and reads, writes confined to the
# task dir, a per-run scratch/cache dir, and Kimi's own state dir.
#
# The whole ~/.kimi-code tree is allow-listed rather than individual
# subdirectories: verified against v0.34.0 that kimi writes to more of its
# own state than its docs enumerate (search-index/, logs/, and a
# per-working-directory workspace-trust record on first run in a new
# directory, at minimum) — a partial list intermittently fails with "storage
# write failed: permission denied" depending on which state paths a given
# session happens to touch. This doesn't weaken the actual security boundary:
# ~/.kimi-code is the CLI's own app state (not attacker-controlled data), and
# everything else on the filesystem stays denied.
#
# Usage (as a ringer engine bin):
#   kimi-sandboxed.sh <taskdir> [--no-sandbox] <kimi args...>
#
# The first argument is the task directory (pass "{taskdir}" first in
# args_template). "--no-sandbox" as the second argument skips Seatbelt
# entirely — wire it as the engine's full_access_args so ringer's
# allow_full_access gate still applies. macOS only (sandbox-exec); on other
# platforms only --no-sandbox mode works.
set -euo pipefail

TASKDIR="${1:?usage: kimi-sandboxed.sh <taskdir> [--no-sandbox] <args...>}"; shift
SANDBOX=1
if [ "${1:-}" = "--no-sandbox" ]; then SANDBOX=0; shift; fi

# Resolve kimi without tripping `set -e` (command -v returns nonzero when absent).
if ! KIMI_BIN="$(command -v kimi)" || [ -z "$KIMI_BIN" ]; then
  echo "kimi-sandboxed.sh: kimi not found on PATH" >&2
  exit 127
fi

TASKDIR_REAL="$(cd "$TASKDIR" && pwd -P)"

if [ "$SANDBOX" = "0" ]; then
  cd "$TASKDIR_REAL"
  exec "$KIMI_BIN" "$@" < /dev/null
fi

if [ ! -x /usr/bin/sandbox-exec ]; then
  echo "kimi-sandboxed.sh: /usr/bin/sandbox-exec not available (macOS only)." >&2
  echo "Use the engine's full-access mode (--no-sandbox) or add your own sandbox." >&2
  exit 1
fi

# Per-run scratch root — becomes both TMPDIR and XDG_CACHE_HOME for Kimi, so
# we never have to open all of /private/tmp or ~/.cache to the sandboxed agent.
# Resolve to the real path (/var/folders symlinks to /private/var/folders);
# Seatbelt subpath matching needs the canonical path or writes EPERM-crash.
SCRATCH="$(cd "$(mktemp -d -t ringer-kimi-scratch)" && pwd -P)"
PROFILE="$(mktemp -t ringer-kimi-prof)"
cleanup() { rm -rf "$SCRATCH" "$PROFILE"; }
trap cleanup EXIT

KIMI_HOME="$HOME/.kimi-code"

# Paths are passed to the profile via sandbox-exec -D parameters, NOT string
# interpolation — a task dir containing quotes/parens/newlines can't inject rules.
cat > "$PROFILE" <<'SBEOF'
(version 1)
(allow default)
(deny file-write*)
(allow file-write*
  (subpath (param "TASKDIR"))
  (subpath (param "SCRATCH"))
  (subpath (param "KIMI_HOME")))
; /dev is needed for /dev/null, /dev/urandom, etc.; writes there can't create
; persistent files without root, so a few literals are allowed rather than via param.
(allow file-write-data
  (literal "/dev/null")
  (literal "/dev/dtracehelper")
  (literal "/dev/tty"))
SBEOF

export TMPDIR="$SCRATCH"
export XDG_CACHE_HOME="$SCRATCH/cache"
mkdir -p "$XDG_CACHE_HOME"

cd "$TASKDIR_REAL"

# Run as a child (not exec) so the EXIT trap fires and cleans up the profile +
# scratch dir even on the success path; propagate the child's exit status.
set +e
/usr/bin/sandbox-exec \
  -D "TASKDIR=$TASKDIR_REAL" \
  -D "SCRATCH=$SCRATCH" \
  -D "KIMI_HOME=$KIMI_HOME" \
  -f "$PROFILE" "$KIMI_BIN" "$@" < /dev/null
status=$?
set -e
exit "$status"
