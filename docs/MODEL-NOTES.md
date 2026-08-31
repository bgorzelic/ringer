# Model notes — how workers actually perform

A running log of how models perform on real Ringer tasks, so engine and
model choices are made on evidence instead of vibes. The raw numbers now
live in the local eval log (`~/.ringer/runs.jsonl`); run `./ringer.py models`
to print the per-model, per-task_type scoreboard (tasks, attempts,
pass_rate, first_try_pass_rate, median duration/tokens, last_seen). This
file remains the judgment layer on top of those numbers.

**How to add a row:** after reviewing a run (post-run ritual step 5 in the
ringer skill), append one dated line under the model. Say the task type,
what happened, and what you'd do differently. Only write what the executed
checks and raw logs support — no vibes, no worker self-reports.

## codex (GPT-5-class, own harness)

- Strongest general worker; the default engine. Spend reasoning effort per
  task via `engine_args` (`["-c", "model_reasoning_effort=low|medium|high"]`)
  — high on gnarly tasks, low on boilerplate.
- 2026-07-05 — carried the heavy lanes of the milk-crate demo rehearsals
  (market read with source allowlist, site build) with clean first-attempt
  passes.
- 2026-07-06 — adversarial pre-merge review (aicred spark): passed on
  attempt 1, ~85k tokens.
- 2026-07-06 — motion design (5 HTML animations for video b-roll) + 2
  editorial diagram pages, each verified by rendering through headless
  Chromium to MP4/PNG: 7/7 passed on attempt 1. Broadcast-quality visual
  output from rich storyboard specs; the render-as-check pattern works.
- 2026-07-06 — milk-crate demo: two single-file website builds (v1 scaffold
  316s/~175k tok; final brand+market-test reskin 622s/~184k tok), both passed
  14-assertion content checks on attempt 1, including base64-embedding photos
  and honoring honesty-marker requirements. Codex remains the site-build lane.
- 2026-07-06 — ringer.py feature batch (task_type field + enriched eval rows
  + `models` scoreboard + hud single-tab fix; ~640-line diff incl. two new
  test suites): substance passed on attempt 1 — its check printed PASS
  (compile, all 16 suites, exact CLI aggregation contract) — but the run
  recorded attempt 2 because of the expect_files-before-check harness bug
  (see process lessons). Heavy single-file feature work against an exact
  behavioral contract is squarely codex's lane.

- 2026-07-06 — elsas-website demo: Next.js scaffold PASSED attempt 2 (682s,
  ~354k tok) — attempt 1 built a complete homepage and silently skipped the
  other 10 routes; the route-enumeration check caught it. Narration lane
  (15 ElevenLabs calls, chunked, nohup pattern) passed attempt 1. CAUTION: a
  codex fix worker GAMED a verbatim-content needle by hiding the required text
  in a visually-hidden paragraph — passed the check, caught only by
  orchestrator integration review. Needle checks need an anti-hidden-text
  assertion or documented exceptions.

- 2026-07-06 — OpenRouter catalog + explore suggester (catalog subcommand
  with snapshot/changelog/free-detection, daemon auto-refresh, tiered
  --explore; offline fixture-driven contract check): PASS attempt 1, 362s.
  Follow-up sentinel-pricing fix (variable-pricing models): PASS attempt 1,
  114s. With the verify-order fix landed, zero phantom retries across the
  whole batch.
- 2026-07-06 — adversarial review of the model-router stack (2,650-line
  diff, structured report contract): PASS attempt 1, 176s — found a real
  HIGH (--since window inflating first-try rates) plus 3 MEDIUMs, all
  confirmed against the code. Then fixed all five review findings in one
  batch (task-level --since, pricing transitions, event durability + flock,
  unknown pricing, stderr notice) with test coverage: PASS attempt 1, 202s.
  Review->fix roundtrip in codex's lane works end to end.
- 2026-07-06 — scoreboard HTML page (zero-LLM renderer, ~700-line diff,
  design + evidence-floor ranking + cost math + notes parser): substance
  PASS attempt 1 (the run's recorded retry was an orchestrator check bug —
  the free-promo watchlist legitimately mentions a free model before the
  ranked cards, and the check compared raw first-occurrence). Six review
  findings fixed in one batch, PASS attempt 1, 141s.
- 2026-07-06 — model-db stack (SQLite read model 516s, page redesign 536s,
  Ringside tab 527s, plus three fix batches all attempt-1): five substantial
  ringer.py features in one day, every one against an executed contract
  check. Review lane found the HIGH that mattered (sync cursor skipping a
  half-written trailing line). Codex is the proven lane for both sides of
  the review->fix loop on this codebase.

## glm-5.2 via opencode (`openrouter/z-ai/glm-5.2`)

- The cheap-intelligence default (~$0.74/M in, $2.33/M out, 2026-07 —
  20-30x cheaper output than frontier coding models). Reliable on
  mechanical, tightly-specced work: file edits, format conversions,
  template-driven builds.
- 2026-07-05 — milk-crate demo rehearsals: handled brand-board/SVG/copy
  tasks at around a penny per passing task.
- 2026-07-06 — adversarial pre-merge review (aicred spark): passed, but
  needed the retry (attempt 2) where codex passed on attempt 1. Long
  structured reviews sit at the edge of its comfort zone; keep the section
  contract explicit in the spec.
- 2026-07-06 — three mechanical image-generation batches (18 images via
  openrouter-image commands, idempotent batch-runner spec): 3/3 passed on
  attempt 1, ~14.5k tokens each. The "execute these exact commands, do not
  improve them" spec pattern is fully reliable for glm-5.2.

- 2026-07-06 — backfill/seed script for the model log (252-line stdlib CLI
  with a run-state join, 3-level mapping precedence, never-overwrite and
  idempotency rules): the artifact was CORRECT; the recorded FAIL was an
  orchestrator check-fixture bug (a missing newline glued the fixture's last
  row to a garbage line) plus the harness ordering bug below. Verified PASS
  once the check was fixed. Tight behavior contracts in the spec work great
  for glm — and read the raw logs before blaming the model.
- 2026-07-06 — README/MODEL-NOTES docs + task_type sweep across 17 template
  manifests: passed attempt 2; attempt 1 was lost to the harness ordering
  bug, not model quality — the retry worker's log correctly diagnosed that
  harness bug unprompted, impressive debugging from the cheap lane.
- 2026-07-06 — catalog/explore README section (flags, promotion ladder,
  per-user framing): PASS attempt 1, ~21.5k tokens. Doc sections against a
  grep-able content contract remain a safe glm lane.
- 2026-07-06 — milk-crate demo, full run: 4 independent buyer-persona
  reviews (focus group) all passed attempt 1 (~15k tokens, ~2¢ each) with an
  explicit VERDICT-block contract — persona work is squarely in glm's zone.
  Market read with live curl fetching passed once the spec demanded verbatim
  copy-paste of source URLs (first fail was the worker trimming URL slugs —
  spec/check craft, not model weakness). Brand-kit doc incl. a clean inline
  SVG wordmark: good, one bounce off an over-strict check regex.

- 2026-07-06 — elsas-website demo: verbatim content capture (16 pages + 19
  news posts, 213 blockquotes) passed attempt 2 — attempt 1 SELF-REPORTED
  "all 213 match exactly, 0 errors" while the executed check found 13 stitched/
  paraphrased quotes. Self-reports are worthless; the retry with injected
  failures fixed all 13 (~148k tok total, ~3¢). Page builds (about+faq;
  news index + 19 generated post routes via its own extraction script) and
  2 focus-group personas: all attempt 1. Fix batch attempt 1.
- 2026-07-06 — invariants/file-I/O review lens on the same stack: PASS
  attempt 1, 68k tokens — caught the non-atomic backfill rewrite (real data
  loss risk) and the daemon stdout race; both confirmed. Then fixed the
  backfill atomicity (tmp+os.replace, pid-stamped backups) attempt 1 with
  the original behavioral grader unchanged. Structured review with an
  explicit lens is now proven glm territory, not just probation.
- 2026-07-06 — solo adversarial review of the scoreboard renderer (~700
  line diff, injection-focused lens): PASS attempt 1 — 1 MEDIUM (unanchored
  MODEL-NOTES heading match cross-contaminating gpt-4/gpt-4o-style
  families) + 5 real LOWs, plus an empirically-verified injection all-clear
  (it actually rendered hostile model ids to prove escaping). Second
  proven-tier structured review in one day; glm is now the default review
  lane for mid-size diffs.
- 2026-07-06 — invariants/injection/frontend review of the 4,061-line
  model-db branch: PASS attempt 1, 96k tokens, 14 coverage items — two real
  contention findings (full catalog re-ingest per sync; schema writes on
  read paths) plus an empirical XSS all-clear on the new DOM surfaces.
  Third proven-tier structured review today.

## kimi-k2.7 via opencode (`openrouter/moonshotai/kimi-k2.7-code`)

- 2026-07-06 — adversarial pre-merge review (aicred spark): passed on
  attempt 1, ~83k tokens. First real outing; promising for review work.
  (Ran through an ad-hoc copy of the opencode engine block — the per-task
  `model` field now makes that unnecessary.)

## kimi-k2.6 (`moonshotai/kimi-k2.6`, subject-model evidence via OpenRouter)

- 2026-07-07 — Benchmark Suite 2.0 operator eval, killed by Jon at ~4.5h.
  Serving throughput, not model quality, was the failure: on the Brick
  1000-piece case (reasoning xhigh, pinned provider order
  inceptron→decart→baidu→modelrun, no fallbacks) K2.6 averaged ~21 tok/s
  with two ~19-min stalls at 4.5 tok/s — 136+ min unfinished vs Sonnet 5's
  25 min (94 tok/s) and GPT-5.5's 24 min (55 tok/s) on the identical case.
  Model behavior itself was fine: 28 turns (fewer than Sonnet's 82), 170k
  output tokens (in family norms), 12% reasoning, zero API errors. Verdict:
  do NOT schedule K2.6 for long agentic work through that provider set;
  if K2.6 data is ever wanted, probe a single case against other providers
  first. Distinct model from k2.7-code above — don't transfer this verdict
  to k2.7.


## grok-build (Grok CLI engine, flat plan)

- 2026-07-06 — first outing (elsas-website demo), engine added same day:
  audition PASS attempt 1 in 28.9s. Then: asset harvest (11 images, live URL
  re-fetch check), books page, 5 work-page routes in one task (59 verbatim
  needles), adversarial code review (10 real findings incl. an unshelled 404
  and a broken embedded link), press/media fix batch, audio-player integration
  across 15 pages — ALL attempt 1 (player's red ledger entry was a check bug,
  artifact certified). Fast, precise on mechanical/code work. No token counts
  in JSON output (flat plan) — cost reads "included in plan".

## grok-composer-2.5-fast (Grok CLI engine, flat plan)

- 2026-07-06 — first outing (elsas-website demo): audition PASS attempt 1
  (138s — slower than grok-build but the strongest copy of the round).
  Accessibility constitution (14 testable criteria, SC-numbered) attempt 1;
  a11y-gatekeeper harness (axe+Playwright, light/dark, reduced-motion assert)
  attempt 2 — attempt 1's harness mishandled Next's default /404 route.
  Events/faq/contact fix batch attempt 1, but satisfied "editorial grid" with
  an EMPTY aside landmark — axe caught it (landmark-complementary-is-top-level).
  Persona work: good. Watch for letter-of-the-spec shortcuts on layout asks.

## nemotron-3-super-120b (via opencode, `openrouter/nvidia/nemotron-3-super-120b-a12b:free`)

- 2026-07-06 — AUDITION FAILED (exploration slot, $0 spent — free promo).
  Task: fresh-eyes adversarial review of a 2,650-line diff with a structured
  report contract. Failed both attempts on the same executed check: report
  had the right sections and verdict but under 3 concrete code citations —
  shallow engagement with the actual code, 212k tokens burned. Don't re-run
  this audition on long structured code review; if it gets another slot,
  try a shorter, more mechanical task first.

## llama-3.3-70b-instruct (via opencode, `openrouter/meta-llama/llama-3.3-70b-instruct:free`)

- 2026-07-06 — AUDITION FAILED (exploration slot, $0). Fresh-eyes review of
  a 4,061-line diff with a verbatim-quote citation requirement: failed the
  structured-report check both attempts. Second free-model audition to fail
  on long structured code review (after nemotron-3-super) — the exploration
  ladder now says: audition free models on SHORT mechanical tasks first;
  long-diff review is a proven-tier lane.

## Small / flash-class models

- First to choke on long conversational or multi-turn harness tasks —
  watch retry counts before scaling them into a batch (2026-07-05 focus
  group lesson).

## Process lessons (cross-model)

- 2026-08-21 — LinkSV architecture party (`linksv-architecture-scale-party-20260821T111225Z-p23547`, rerun `linksv-architecture-scale-party-20260821T111934Z-p30112`): MacStudioAgentSJ `qwen3-coder:30b-32k` wrote a substantive bounded placement report but missed required URLs; its retry rendered a tool call as text and left a stale deliverable, so the first lane failed 2/2. A narrower literal-skeleton rerun passed first try in 90.8s at reported cost 0, but manual review found an unsupported Guiver quote plus weak human-review and capacity assumptions that the structural checker missed. Keep local Qwen on narrow, source-constrained batch work; validators must check quote provenance and domain claims, not only report shape.
- 2026-08-15 — Ringer self-review (`ringer-self-review-20260815T222515Z-20260815T222625Z-p63277`) finished 1/4 after 454.1s. Codex produced the only contract-passing report on attempt 1 in 125.3s (94,655 parsed tokens). Claude and Kimi each produced substantive evidence-backed reports, but their first attempts used numbered finding headings and their retries changed the headings while retaining human priority words instead of the required `P0|P1|P2|P3`; the checker rejected both. The sequential checker feedback consumed the sole retry before revealing every schema defect. Prefer deterministic report scaffolds or make the checker return all structural errors on attempt 1; do not spend a full model retry on mechanical Markdown normalization.
- 2026-08-15 — the same self-review routed a broad repository performance audit to MacStudioAgentSJ `qwen3-coder:30b-32k`. It repeatedly reread context and produced no `report.md`; the coordinator stopped the bounded run after 454.1s. This does not contradict the 26.146s bounded coding proof: local Qwen is accepted for small mechanical coding/check tasks with narrow input, not broad source-research or long-form audit synthesis. Route those tasks to subscription models until a small-packet local benchmark passes the same deliverable gate.

- 2026-08-15 — subscription/local Ringer smoke (`dickie-subscription-local-smoke-rerun-20260815T221342Z-20260815T222024Z-p42769`): ChatGPT/Codex subscription passed its exact-file probe first try in 9.7s; Claude Sonnet 5 through the Claude Max subscription passed first try in 8.0s with `apiKeySource: none` and zero MCP servers; MacStudioAgentSJ `qwen3-coder:30b-32k` passed in 43.0s on attempt 2 at model-reported cost 0. The local model's first attempt rendered a write tool call as text instead of executing it; Ringer's missing-file check forced a retry, which emitted a real tool call and passed. Keep local coding lanes retryable and do not equate a textual tool-shaped response with execution.
- 2026-08-15 — the preceding smoke exposed two harness/check defects, not model failures: the Claude Seatbelt wrapper exited with code 128 in a non-Git scratch directory because `set -e` preempted its documented fallback, and the Mac receipt check rejected correct content without a trailing newline. The wrapper now branches safely around `git rev-parse`, and the receipt check accepts exactly one marker with or without the conventional final newline. The failed run remains in the scoreboard as historical evidence rather than being erased.

- 2026-07-06 — the orchestrator's CHECKS were the day's top failure source:
  three check bugs (fixture newline join, first-occurrence ordering vs the
  watchlist strip, claim-prefix split on '.' instead of ':') each produced
  a FAIL verdict on work that was actually correct — including all four
  capability-research packets at once. Every one was caught by reading raw
  logs/artifacts before blaming the model. Corollary for the scoreboard:
  recorded FAILs whose root cause was a check bug are annotated here, and
  check fixtures deserve the same review care as production code.


- 2026-07-06 — HARNESS BUG (fix in flight on feat/model-perf-log):
  Verifier.verify evaluated expect_files BEFORE running the check, so any
  check that itself creates/exports its deliverable (the worktree
  patch-export pattern) failed attempt 1 with "missing expected files" even
  when the check printed PASS. Cost 3 phantom retries in one run — and it
  poisons first_try_pass_rate, the model log's routing signal. Until the
  reorder lands on your checkout: have the WORKER write the declared
  deliverable, or don't declare check-created files in expect_files. When
  reading seeded scoreboard numbers, remember 2026-07-06 first-try rates
  are depressed by this.
- 2026-07-06 — the model log is now automatic: every attempt row carries
  model/task_type/retry; `./ringer.py models` prints the scoreboard; 81
  historical rows were seeded via scripts/backfill_model_log.py with a
  hand-authored task-type mapping. Give every manifest task a task_type or
  its evidence buckets as (untyped).

- 2026-07-06 — a three-model "bakeoff" ran every task on the engine's
  hard-coded model: task keys said glm/gpt/kimi, but the opencode engine
  block pinned glm-5.2, so one model wrote all three "competing" reviews.
  This is why the per-task `model` field exists — a bakeoff is only a
  bakeoff if the manifest, not the engine block, names the model. Verify
  with the `model` column in the run state, not the task key.
- 2026-07-06 — spawning 5-6 opencode workers simultaneously hit opencode's
  local "database is locked" (sqlite) — several instant attempt-1 failures,
  all absorbed by Ringer's retry. Cosmetic in Ringside ("sent back" at 0s) but
  wastes an attempt; consider staggering opencode spawns.
- 2026-07-06 — opencode's bash tool kills foreground commands around the
  ~2-minute mark: a 2min+ image-generation API call can never finish inline.
  Spec pattern that works: nohup the long command in the background, then
  poll for the output file in separate short commands.
- 2026-07-06 — two check-craft lessons from the same run: (1) URL-allowlist
  checks must be prefix-tolerant (workers legitimately trim slugs); (2) any
  heading-regex must tolerate numbered headings ("## 3. Type / Typography").
  Both failures looked like worker laziness until the raw logs said otherwise.
- 2026-07-06 — elsas-website demo, check-craft in BOTH directions: (1) a fixed
  800-char body floor failed a worker for faithfully converting genuinely tiny
  source posts — floor must scale with the source; (2) a citation gate treating
  every backtick as a page-quote failed honest reviewers who backticked their
  own fix-suggestions — line-scoped pair parsing + attribute-aware corpus fixed
  it; (3) needle-exception lists must be shared across ALL checks that consume
  the needle set (a needle excepted in one checker failed a task through
  another). Post-mortems ruled FOR the worker 3 times this run — read raw logs
  before blaming the model.
- 2026-07-06 — opencode sqlite "database is locked" again with just 2
  simultaneous opencode spawns (page-news + page-about-faq); retry absorbed it.

## codex (2026-07-06, bench-operator-proofing)
- 8/8 code-feature tasks passed attempt 1 across 3 rounds (worktrees mode, Python harness refactor; 108k-406k tokens/task). Specs embedded the approved architecture doc + exact file ownership; checks built fresh uv venvs and ran the full pytest suite.
- Lesson (check design, not model): all 3 post-integration bugs were invisible to the checks — a test that passed only because the worker's worktree lacked .env, a `--help`-only assertion missing a runtime importlib/sys.modules bug (py3.12 dataclasses), and bare console-script names failing outside activated venvs. Checks should exercise one real invocation from a cold shell, not just --help.

## codex (2026-08-05, dickie-brain m0-rag-redact-core)
- Task recorded FAIL after 2 attempts (run `dickie-brain-20260805T074310Z-p12759`), but the ported code was correct both times — the orchestrator's own `--build-command` had unquoted SQL (`LIKE %sk-ant-fake%` instead of `LIKE '%sk-ant-fake%'`), an invalid-syntax check that could never pass regardless of worker output. Confirmed by manually re-running the corrected assertions against the worker's already-written files post-hoc: py_compile clean, `schema/brain.sql` applies standalone, redact.py's 9/9 self-test passed, and a real ingest→search→redact round trip correctly retrieved a planted marker while making a planted fake secret unretrievable. On attempt 2 the worker itself correctly diagnosed the check's SQL-quoting bug from the raw sqlite3 error and said so in notes.md — a good sign for this model's debugging read, not a bad one.
- Lesson (check design, not model, again): don't count this FAIL against Codex's code-feature scoreboard when weighing future engine choices for this repo — it's a false negative from a check-authoring bug, not a worker defect. Re-verify manually before retrying a task when the failure log points at the check's own command rather than the worker's deliverable.

## codex (2026-08-05, dickie-brain m1-coordination-api)
- Same pattern one milestone later, worse this time: recorded FAIL after 2 attempts (run `dickie-brain-20260805T075057Z-p24533`), again a check-authoring bug, again correctly self-diagnosed by the worker rather than a real defect. Two separate bugs in the orchestrator's own verifier: (1) `importlib.util.spec_from_file_location(name, 'bin/dickie-a2a-server')` returns a spec with no loader for an extensionless filename — needs `importlib.machinery.SourceFileLoader` passed explicitly, not inferred from a suffix that doesn't exist; (2) a `--required-text` needle of the literal substring `brain.coordination`, which never appears when the (fully valid, explicitly spec-permitted) import style `from brain import coordination` is used instead of `from brain.coordination import ...` or `import brain.coordination`. Confirmed post-hoc by manually fixing both and re-running end to end on this host: all 5 HTTP routes returned correct values against a synthetic coordination.db, the `dickie-a2a-server` refactor was proven (via direct import + call, `brain.coordination` genuinely present in `sys.modules` from the file's own module-scope import) to delegate correctly with unchanged behavior, and `git status` showed exactly the 5 expected changed/new files.
- The worker also hit a real but irrelevant environment fact worth remembering separately: its own sandbox raised `PermissionError` on binding even a `127.0.0.1` TCP socket, so it could not run the HTTP-server portion of the verifier itself inside its own sandbox — it said so plainly, attempted what verification it could (py_compile, git diff --check, a synthetic-DB direct-call check), and did not fabricate a passing run. That's the right behavior when a check needs capabilities the sandbox doesn't grant.
- Lesson: when writing a check that imports a same-repo *extensionless* script as a module (this repo's `bin/` convention has no `.py` suffix on several files), always use `SourceFileLoader`/`runpy.run_path`, never bare `spec_from_file_location` without an explicit loader. And when a spec explicitly permits two equivalent import phrasings, don't write a `--required-text` needle that only matches one of them — verify the assertion against both, or drop it in favor of the executable proof already covering the same claim.

## codex + opencode/glm-5.2 (2026-08-06, dickie-agents-md-prep — 85-task docs swarm)
- 85/85 tasks passed (run `dickie-agents-md-prep-20260806T030829Z-p52223`), 71 first try, 14 codex tasks needed one retry. task_type=docs: read a real repo read-only, write AGENTS.md (or self-flag as not fitting the shape) + a CLAUDE.md that imports it, no worktrees — sandbox write-confinement to the task dir was the only isolation needed across 85 different target repos in one manifest (no run-level `repo`/worktrees field required for a multi-repo batch; each task dir just needs read access to its own target path).
- opencode/glm-5.2 explore lane (8 tasks, deliberately picked low-stakes repos): 8/8 first try, quality on par with or exceeding codex on this task shape — cited exact commit hashes, real secret-vault file names, and precise env var names pulled from the actual source, not generic filler. Worth promoting glm-5.2 to a bigger lane on future docs-type swarms on this machine.
- Codex retry lesson (check-craft, not a worker defect): agent-forge's attempt 1 failed a `--repo-name` substring check because the worker titled the doc "Agent Forge" (space-separated, human-readable) without also including the literal hyphenated repo-dir string "agent-forge" anywhere in the file; attempt 2 fixed it once the check's failure text pointed at the exact missing string. A word-boundary/separator-insensitive match (`agent[-_ ]forge`) would have passed attempt 1 and saved a retry — worth doing for any future check that greps a literal repo/project name against prose a model is free to title naturally.
- 17/78 tasks correctly self-identified their repo as not fitting the standard AGENTS.md shape (spec-only repos, brief/asset repos) and wrote a substantive FLAG.md instead of forcing generic content, per the spec's explicit escape hatch — validated by spot-reading `PAR`'s FLAG.md against its actual README/HANDOFF content, which was accurate.

## codex / gpt-5.6-sol subscription capacity

- 2026-08-16 — operator reported adding ChatGPT credits. Amount, expiration,
  and provider-reported remaining balance were not supplied, so Ringer must
  treat capacity as available-but-unquantified and continue recording actual
  task usage instead of inferring runway.
