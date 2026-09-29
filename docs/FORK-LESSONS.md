# Fork lessons — what other ringer forks learned

Distilled 2026-09-29 from the fork landscape scan (see memory: ringer fork
landscape). Primary source: `jroethel/ringer` `docs/MODEL-NOTES.md`, whose
process lessons are the most transferable material in any fork. Feature ports
on this branch are credited in README; this file records the lessons, including
from work we did not port.

## Process lessons (jroethel, cross-model)

- **The orchestrator's checks were the top failure source.** Three check bugs
  (fixture newline join, first-occurrence ordering vs the watchlist strip,
  claim-prefix split on `.` instead of `:`) each produced FAIL verdicts on
  correct work. Every one was caught by reading raw logs before blaming the
  model. Check fixtures deserve the review care production code gets.
- **A verifier that inspects expected files before running the check poisons
  the routing signal.** Their `Verifier.verify` evaluated `expect_files` first,
  so any check that itself creates its deliverable failed attempt 1 — and
  `first_try_pass_rate` is what the scoreboard routes on. Cost them 3 phantom
  retries in one run.
- **A bakeoff is only a bakeoff if the manifest names the model.** Their
  three-model bakeoff ran every task on the engine block's pinned model; task
  keys said glm/gpt/kimi, one model wrote all three "competing" reviews. Verify
  with the run state's `model` column, never the task key.
- **opencode workers must write inside their own taskdir.** A GLM worker could
  not write to a shared output dir created by the parent process (EPERM on
  macOS), then burned ~3000s on sandbox workarounds and logged FAIL despite the
  deliverable existing. Harvest via `expect_files`; never hand workers a
  directory another process created.
- **opencode's bash tool kills foreground commands around two minutes.** The
  working pattern: `nohup` the long command, poll for the output file in
  separate short commands.
- **opencode's sqlite hits "database is locked" with several simultaneous
  spawns.** Retry absorbs it; staggering spawns avoids wasting the attempt.
- **Check-craft rules their post-mortems kept re-learning:** URL allowlists must
  be prefix-tolerant; heading regexes must tolerate numbered headings; a fixed
  length floor must scale with the source; needle-exception lists must be shared
  across every check consuming the needle set.

## One idea worth keeping (jroethel, from a rejected PR)

An *explicitly blessed* answer cache: key a reviewed answer to the exact request
plus the exact selected source packet, replay it with zero upstream calls, and
never auto-accept a model answer. Fires only on byte-identical repeats. The
pre-call gateway it came from was rightly rejected — it metered a flat-rate
plan and stripped the tool list — but the cache idea is sound if the problem
returns.

## A discipline worth copying (jroethel's JEV)

Their JEV integration flags FAILs as check-faults so ringer can skip doomed
retries, with every rollout decision gated by an offline replay over
`~/.ringer/runs.jsonl`: 47 FAIL pairs, 15 hand-labeled, bar set at flagging at
least 9 of 11 check-bug pairs. The external service it depends on is not
adopted here; the replay-gated rollout pattern is the transferable part.

## What did not port onto this branch, and why

- **dudarenok's resolver-order and aggregate-signature refactor** (1320 lines in
  `ringer.py`): their tests assume `aggregate_model_log_rows(..., registry=...)`
  and a resolve() that prefers identity entries over noncanonical routes.
  Upstream resolves noncanonical first; changing that order is a semantic
  decision for upstream, not a port. Their tests on this subject were dropped
  with the decision recorded in the commit.
- **heyjawrsh's attempt-record infrastructure** (`recordedDuration`,
  `attempt_records`, worker/check cost split): the ledger and burn-rate halves
  of their commits depend on it. Only the null-display sliver was portable.
- **heyjawrsh's pty live workers, 0.25s state sampling, wall-clock timeline**:
  large, coherent series touching the run loop. The right path is upstream
  review of their fork, not a unilateral port.
- **jroethel's JEV**: needs an external API key; default-off there, absent here.