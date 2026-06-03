---
Rank: 3
ForceModel: gemma4
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Run bilevel generate stage in the container

## Todo

Generate the geometry XMLs and ddsim manifest for the ready config
`/srv/bilevel/scif_configs/smoke.yaml`, writing output to `/srv/runs`.

Run this single command. It sets up the environment, runs the generate stage
with all of bilevel's chatty logging sent to a log file, and prints only a short
status token:

```bash
cd /srv/bilevel && source ./env.sh >/dev/null 2>&1 && \
  bilevel_opt --config /srv/bilevel/scif_configs/smoke.yaml --stage outer --run-mode generate --run agent_local_test >/tmp/gen.log 2>&1 && \
  test -f /srv/runs/agent_local_test/sim_outputs/manifest.json && echo GENERATE_OK || { echo GENERATE_FAIL; tail -5 /tmp/gen.log; }
```

As soon as the command prints `GENERATE_OK`, the task is finished: **call the
`done` tool** with a one-line summary (e.g. "generate OK, manifest written").
Do NOT run the command a second time — running it once is enough. Only if it
prints `GENERATE_FAIL` should you read the printed log tail and fix the problem.

## Expect

- `/srv/runs/agent_local_test/sim_outputs/manifest.json` exists.
- `/srv/runs/agent_local_test/run0000.xml` exists.
