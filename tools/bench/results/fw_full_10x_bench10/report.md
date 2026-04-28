# fw_full_10x bench10 — FPGA toolchain task suite, gemma4 worker × gemma4 control

**Plan**: `tools/bench/plans/fw_full_10x.json` · **Report**: `tools/bench/reports/fw_full_10x_20260428T032320Z.json` · **Run timestamp**: 20260428T032320Z

## Configuration

- `lock_model: gemma4` (only gemma4 in rank.yaml during bench)
- `total_wall_s: 2700` (45-minute hard cap per run)
- `state_paths: [F/mnt]` — bootstrap installs verilator/g++/make/python+numpy at `/mnt/sci_envs/fpga_toolchain`, pinned as `warm`; each task batch starts from the `warm` snapshot
- Initial probe: skipped (relaunch after portal.py fix; baseline TPS=41.4 tok/s captured from prior probe)
- Inter-batch lite probes recorded

## Headline results

| Batch | Task | Rank | n (valid) | PASS | FAIL | ERROR | UNK | Pass rate | wall p50 | wall min/max | iters p50 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bootstrap | sci_study/fw_bootstrap | 1 | 1 | 1 | 0 | 0 | 0 | 100% | 373s | 373/373s | 20 |
| c1_warm | sci_study/fw_complete1 | 2 | 10 | 5 | 1 | 0 | 4 | 50% | 1344s | 601/1450s | 90 |
| c2_warm | sci_study/fw_complete2 | 3 | 10 | 9 | 0 | 0 | 1 | 90% | 356s | 183/1567s | 34 |
| c3_warm | sci_study/fw_complete3 | 4 | 8 | 7 | 0 | 0 | 1 | 88% | 490s | 288/1448s | 49 |

## Excluded runs

| Batch | Idx | Reason | Detail |
|---|---|---|---|
| c3_warm | #5 | `config_corruption` | rank.yaml inline-comment YAML parse bug; mid-run rank.yaml edit at 19:46:45 PT introduced active deepseek-v4-pro entries with comments; pam.py:67 captured comment as part of model name; LiteLLM 400 Invalid model name → ERROR_LIMIT → blacklist gemma4 → fail. |
| c3_warm | #10 | `manually_stopped` | SIGTERM by user to wrap up the batch (8 valid c3 runs already collected). |

## Gateway TPS drift (initial 41.4 tok/s baseline)

| Probe | TPS | Δ vs initial | oh p50 |
|---|---|---|---|
| Initial (before relaunch) | 41.4 | — | 1.7 ms |
| After bootstrap | 47.4 | +14.5% | 1.3 ms |
| After c1_warm | 44.8 | +8.2% | 1.2 ms |
| After c2_warm | 44.1 | +6.5% | 1.3 ms |
| After c3_warm | 31.2 | -24.6% | 1.6 ms |

**Notable**: Sustained drop after c3_warm (−24.6% vs initial). Likely Ollama Cloud rate-pressure or model-reload after the 4-parallel + #10 SIGTERM burst. Recovered TPS not re-measured.

## Findings

### Bugs found and fixed during this run
1. **portal.py required env vars dropped without portal update** — commit `3ee84f0` removed `WALL_LIMIT_PER_RANK`/`ITER_LIMIT_PER_RANK` from ENV.sh saying "driver defaults are fine," but `portal.py:_env()` still hard-failed on missing vars. **All bench runs failed `rc=1 wall=0s`** until fixed. Fix: switched to `_env_opt(...)` with the documented defaults.
2. **bench.py `post_chat` required `LITELLM_MASTER_KEY`** — ENV.sh leaves it commented out (gateway runs authless). Probe crashed before the first batch. Fix: header now optional.
3. **pam.py `_parse_rank_yaml` did not strip inline `# ...` comments** — when an external agent edited `gateway.rank.yaml` mid-run (19:46:45 PT) to add planned-feature `deepseek-v4-*` entries with inline comments on `name:` lines, pam captured the entire suffix into the model name. LiteLLM returned 400 *Invalid model name*. 5 errors → ERROR_LIMIT → blacklist → c3 #5 `rc=1 wall=948s`. Fix: strip inline `#`-comments before each scalar parse.
4. **bench.py shared-file backup shadowing** — both `total_wall_s` and `max_retries` mutate ENV.sh; the second backup overwrote the first key in `backups{}` so restore would leak the original. Fix: pass an `existing_backup` through both setters.
5. **bench.py validate_plan rejected pins from prior runs** — pins had to be defined in the same plan. Fix: also accept any pin already in `tools/bench/states/`.

### Hardcoded thresholds → ENV.sh (env-tunable, default-preserving)
| Variable | Default | Where it was | What it does |
|---|---|---|---|
| `ERROR_LIMIT` | 5 | `driver.py:2242` | Consecutive API errors before pam blacklists worker model |
| `NUDGE_LIMIT` | 5 | `driver.py:2272`,`2288` | Consecutive no-tool / malformed-tool turns before blacklist |
| `MAX_RECOVERY` | 3 | `driver.py:2415` | Delay/retry rounds after LOOP_EXHAUSTED |
| `MAX_REVIEW_ITER_VERIFY` | 30 | `driver.py:1830` | Iter floor for verify-heavy done-case reviews |
| `TOOL_RESULT_CAP` | 10000 | `driver.py:1380` | Chars retained of tool result (head + last 5 lines) |
Forwarded into the container by `portal.py`; defaults documented in `ENV.sh` and `F.design.md` sec 6.8 / 14.

### Gemma4 capability findings on FPGA tasks
- **fw_bootstrap (rank 1)**: trivially passes (1/1, 373s, 20 iters).
- **fw_complete1 (rank 2, fill `...` placeholders)**: `5 PASS / 1 FAIL / 4 UNKNOWN` over 10 valid runs — only 50% pass rate. The "fill the blanks" framing is *harder* than expected because the half-written skeleton can mislead the agent down the wrong path. Wall median 1344s, max 1450s (multiple UNKNOWNs hit 90+ iterations and walked off the iter cap).
- **fw_complete2 (rank 3, write wrapper from scratch)**: `9 PASS / 1 UNKNOWN` (90% valid pass rate). Wall median 356s, min 183s — *much faster* than c1 because there's nothing misleading to read. The empty-wrapper framing apparently maps cleanly to gemma4's pattern memory. One outlier (#5, 1567s, UNKNOWN — same over-iterate pattern).
- **fw_complete3 (rank 4, write wrapper + binder from scratch)**: `7 PASS / 1 UNKNOWN` over 8 valid runs (87.5% pass rate among non-excluded). Wall median 490s, range 288–1448s. The most-from-scratch task; gemma4 still solves it most of the time.
- **Counterintuitive ordering** (c1 hardest by pass rate, c2 fastest, c3 moderate) is consistent across runs and not just noise. Suggests *partial-skeleton tasks are harder than fully-empty or fully-given tasks* for this model — likely because the agent over-anchors on the existing tokens.

## Files in this folder
- `runs.csv` — per-run row (batch, idx, verdict, iters, wall_s, bash_s, llm_s, bash_pct, exit_code, excluded, exclude_reason)
- `report.md` — this file
- `bench_report.json` — verbatim copy of the bench tool's JSON output (linked here for self-containment)