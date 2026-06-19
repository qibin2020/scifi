---
name: bilevel_run
description: Run a bilevel detector-optimization from a config + run name with ONE bundled command — run_full.sh for SLURM full runs (submit, wait, verify), run_local.sh for fast local stages. The agent never sizes, polls, or verifies by hand.
---

You run bilevel detector-optimization. Every mode is ONE bundled command that
prints ONE final status token — you never build command chains, size SLURM
jobs, poll, or verify outputs yourself.

## Map the request to a mode

| Request says...                                              | mode     | command       |
|-------------------------------------------------------------|----------|---------------|
| "run the (full) optimization ... on SLURM"                  | full     | run_full.sh   |
| "generate geometry / manifest only" (fast)                  | generate | run_local.sh  |
| "run the inner loop on existing ROOTs"                      | inner    | run_local.sh  |
| "evaluate at fixed params on existing ROOTs"                | evaluate | run_local.sh  |

`full` = generate -> parallel ddsim -> inner, on a SLURM compute node.
generate/inner/evaluate are fast and run locally.

## Campaign area + discovery ledger (where everything lives)

All runs are placed under `/srv/runs/<campaign>/` automatically — the campaign
is the task's `Campaign:` key (a stable name shared by chained tasks) or, when
absent, this task invocation's unique session id. You never construct these
paths: `build.sh` puts the config there, the runners find it there, and the
success tokens print the real paths. Every finished run is also appended to
the discovery ledger `/srv/runs/LEDGER.csv`
(`date,campaign,session,run,geometries,job,status,path`). To find an earlier
run you don't know the path of:

```bash
grep ',share,' /srv/runs/LEDGER.csv | grep VERIFIED | tail -1
```

— the last column is the path.

**RUN NAME = config run-block name.** `<NAME>` is NOT a free-form label: it
must match a run defined in the config's `runs:` list, and it is also the
output dir (`/srv/runs/<NAME>`). Use the name the task gives you. A config
shipped in your task dir (e.g. `./run_slurm.yaml`) can be passed as-is to
either command — staging is automatic.

## FULL mode — one command (submit -> wait -> verify)

Run the bundled full-runner with a LONG bash timeout (`timeout: 86400`) — it
blocks until the SLURM job finishes (typically minutes, plus queue time):

```bash
bash /srv/skills/bilevel_run/run_full.sh <CFG> <NAME> <G>
```

- `<CFG>` — the config. For a config built this same task by `bilevel_config`,
  just pass `<NAME>.yaml` (it is found in the campaign area). A task-shipped
  `./file.yaml` is staged automatically. An explicit `/srv/...` path passes
  through.
- `<G>` — the geometry count the task states. Everything is derived from it
  internally (SLURM cpus, wall time, the verification target).

It prints `SUBMITTED job=<id>` first, then ONE final line:

- `RUN_VERIFIED run=<NAME> roots=<N> job=<id>` → success. Call `done` with a
  one-line summary including the job id.
- `RUN_FAIL <reason>` → report what it names. `OUT_OF_MEMORY` → rerun with a
  larger `<G>`; `TIMEOUT` → rerun with a larger wall time (optional 4th arg,
  minutes). Outputs under `/srv/runs/<NAME>` after a failure are stale or
  partial — never verify or analyze them yourself.

Do NOT use the `slurm_submit`/`slurm_status` tools for bilevel runs and do NOT
re-verify by hand — `run_full.sh` already submits, waits, and verifies. It is
idempotent: calling it again on an already-completed run returns the cached
`RUN_VERIFIED` line instantly without submitting (set `FORCE=1` to rerun).

## Local stages (generate / inner / evaluate) — one command

```bash
bash /srv/skills/bilevel_run/run_local.sh <CFG> <NAME> <MODE>
```

It sources the env, runs the stage with logging captured, and checks the
stage's output. It prints ONE line:

- `LOCAL_VERIFIED mode=<MODE> run=<NAME> [geometries=<N>]` → success. Call
  `done` immediately.
- `LOCAL_FAIL <reason>` → fix what it names (usually a wrong path or run name)
  and rerun the same command.

## Worked examples

A 6-geometry full optimization, run name `ana_seed`, config just built by
`bilevel_config` this task:

```bash
bash /srv/skills/bilevel_run/run_full.sh ana_seed.yaml ana_seed 6
```
→ `SUBMITTED job=53870826` ... → `RUN_VERIFIED run=ana_seed roots=6 job=53870826`.
Call `done` with the job id.

A shipped 1-geometry config `./run_local.yaml` (run `run_local`), generate only:

```bash
bash /srv/skills/bilevel_run/run_local.sh ./run_local.yaml run_local generate
```
→ `LOCAL_VERIFIED mode=generate run=run_local geometries=1`. Call `done`.

## Internals (you never manage these — for reference only)

- SLURM sizing is `cpus = min(32, max(4, G))`, small on purpose: small shared
  requests backfill instantly on Perlmutter; big ones queue. ddsim parallelism
  self-sizes to the allocation inside the job (memory-safe clamp).
- The command chain invokes the ddsim payload with `bash` (a subprocess), never
  `source` — sourcing would kill the chain and skip the inner stage.
- `run_cmd.py` (prints the raw command chain) and `verify.sh` (re-checks a
  finished run: `bash verify.sh <NAME> <G>` → `RUN_VERIFIED`/`RUN_FAIL`) exist
  for manual debugging and for reviewers re-checking a run.
