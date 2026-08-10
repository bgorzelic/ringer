# Ringer

## What this is

Ringer orchestrates parallel AI-agent workers, runs shell checks against their artifacts, retries failed work once with verification context, and records every attempt. It also includes Ringside: a local web dashboard and an optional Tauri desktop HUD for monitoring current and historical swarms.

## Setup / install

Ringer requires Python 3.11 or newer and uses only the standard library for its default local operation. The optional PostgreSQL evaluation backend requires `psycopg`.

Install and authenticate at least one worker CLI. Codex is the built-in default:

```bash
npm install -g @openai/codex
codex login
```

Clone setup and optional configuration:

```bash
git clone https://github.com/NateBJones-Projects/ringer
cd ringer
mkdir -p ~/.config/ringer
cp config.sample.toml ~/.config/ringer/config.toml
```

The configuration copy is optional; Ringer has defaults without it. To install Ringer's agent skill and reminder hooks at user level:

```bash
./ringer.py install-agent
```

Run the end-to-end demo with three real workers:

```bash
./ringer.py demo
```

## Build / test / lint

The main Python CLI has no build step.

Run the Python `unittest` suite from the repository root:

```bash
python3 -m unittest discover -s tests
```

Lint a Ringer manifest with the built-in manifest linter:

```bash
./ringer.py lint templates/review-swarm.json
```

No repository-wide Python code linter or formatter configuration was found.

The optional native Ringside HUD is under `hud/`. Its documented commands are:

```bash
cd hud
cargo install tauri-cli --locked
cargo tauri build
cargo tauri dev
```

The install command is needed once. Bundles are written under `hud/target/release/bundle/`.

## Code style / conventions

- Python source and tests use `from __future__ import annotations`, type annotations, `pathlib.Path`, and the standard-library `unittest` framework.
- The main Python implementation is a single executable module, `ringer.py`; tests import it by adding the repository root to `sys.path`.
- The native HUD uses Rust edition 2021 and Tauri v2.
- For HUD frontend work, edit `dashboard/dashboard.html` and `hud/frontend/hud.js`, not generated `hud/dist/`; `hud/scripts/sync-dist.sh` synchronizes the frontend before builds.
- Ringer verification checks must exit nonzero on failure and should print a useful failure reason so retries and evaluation logs receive actionable context.
- No repository-wide formatter, Python linter, or contributor style guide was found; additional style rules are not yet established.

## Working with multiple agents here

This repository can be worked on by multiple parallel Claude Code or Codex agents launched through this machine's `launch-agents` tool. Each agent receives its own git worktree automatically, so do not create manual branches just to isolate agents.

For a multi-agent task, check the shared coordination database for existing file claims before editing any file another agent may be touching. Claim the files you will change, keep changes scoped to that claim, and coordinate through the shared messaging database when ownership overlaps.

The recent history mixes conventional prefixes such as `docs:` with unprefixed subjects and merge commits, so a repository-wide commit convention is not yet established. Match the surrounding history and use a clear, imperative subject unless the coordinating task specifies a convention.

Never commit secrets. The current `.gitignore` excludes Python caches, build outputs, targets, run logs, and generic `*.log` files, but it does not list `.env` or credential-file patterns. Confirm that any environment or credential file is ignored before creating or staging it; do not assume it is safe merely because `.gitignore` exists.
