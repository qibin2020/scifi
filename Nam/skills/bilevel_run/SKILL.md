---
name: bilevel_run
description: Turn a natural-language bilevel detector-optimization run request (config + run name + intent) into the exact slurm_submit call or local command — encapsulates the stage/run-mode command chain and SLURM sizing.
---

You run bilevel detector-optimization. You do NOT have to know the long command
chain — a helper script prints it for you. Run the helper, copy its single
printed line, then submit or run it.

## Helper (always use it — never hand-build the && chain)

The helper lives at `/srv/skills/bilevel_run/run_cmd.py` (this path works in your
bash — the skills dir is mounted there). Run it:

```bash
python3 /srv/skills/bilevel_run/run_cmd.py --config <CFG> --run <NAME> --mode <MODE> --parallel <N>
```

Keep the whole command on ONE line (no backslash-newline). It prints ONE clean
line: the command for slurm_submit. `<CFG>` is a config path in the SLURM job's
`/srv` scheme (e.g. `/srv/scif_configs/opt_test.yaml`) — pass it through as text;
do not try to `ls` it from your bash, it only exists inside the SLURM job's
container. `<MODE>` is one of `full | generate | outer | inner | evaluate`.

**RUN NAME = config run-block name.** `<NAME>` is NOT a free-form label: it must
match a run defined in the config's `runs:` list, and it is also the output dir
(`/srv/runs/<NAME>`). If you pass a name with no matching block, the pipeline
exits 1 immediately with `Run '<NAME>' not found. Available: [...]`. So use the
name the task gives you, which is the block name in that config (e.g. the
`opt_test.yaml` config defines run `opt_test`).

## Map the request to a mode

| Request says...                                              | mode     | how to run        |
|-------------------------------------------------------------|----------|-------------------|
| "run the (full) optimization ... on SLURM"                  | full     | slurm_submit      |
| "generate geometry / manifest only" (fast)                  | generate | bash (local)      |
| "run the inner loop on existing ROOTs"                      | inner    | bash (local)      |
| "evaluate at fixed params on existing ROOTs"                | evaluate | bash (local)      |

`full` = generate -> parallel ddsim -> inner, as one chain. ddsim is long, so
**full mode goes through SLURM only** (slurm_submit), never an inline bash call.
generate/inner/evaluate are fast and may run locally (they still need the
container env; submit them or run them as configured by the task).

## How to launch FULL (the common case)

1. Get the command line (one line):
   ```bash
   python3 /srv/skills/bilevel_run/run_cmd.py --config /srv/scif_configs/<cfg>.yaml --run <NAME> --mode full --parallel 4
   ```
2. Call `slurm_submit(command=<that exact line>, time_minutes=60, cpus=4, name="<NAME>")`.
   Save the returned job id.
3. Poll `slurm_status(<id>)`, running `sleep 30` in bash between calls, until `DONE <exit>`.
4. On `DONE 0`, verify outputs in bash, then call `done` with the job id.

## SIZING RULE — use SMALL cpus (schedules instantly)

Perlmutter `shared` nodes are fragmented: a 36–64 CPU request PENDS for a
backfill window, but a small request (cpus≈4–8) backfills INSTANTLY. `regular`
(full node) is heavily allocated and queues too. So:

- **Use small cpus** and set `--parallel` to MATCH cpus (`MAX_PARALLEL=cpus`).
- A ~36-geometry full optimization: `cpus≈8`, `--parallel 8`, `time_minutes 60`.
- A tiny 2-geometry test: `cpus≈4`, `--parallel 4`, `time_minutes 30` (~3 min run).
- Never request 36–64 cores to "go faster" — it just queues. Batch the ddsim.

## bash-NOT-source RULE (already baked into the helper)

The full chain invokes the ddsim payload with `bash <payload>` (a subprocess),
NOT `source`. The payload has `set -e` and ends with `exit 0`; sourcing it would
kill the chain and SKIP the inner stage. The helper always emits the `bash` form
— do not rewrite it to `source`.

## Verify outputs (full mode)

```bash
D=/srv/runs/<NAME>
echo "roots=$(ls $D/sim_outputs/*.root 2>/dev/null | wc -l)"
test -f $D/results/summary.csv && echo SUMMARY_OK || echo SUMMARY_MISSING
```
A full run produces one ROOT per geometry under `sim_outputs/` and
`results/summary.csv`. When the ROOT count matches the geometry count and
`SUMMARY_OK`, call `done` (include the job id).
