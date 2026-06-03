---
Rank: 4
ForceModel: gemma4
ControlModel: gemma4
Skills: bilevel_config, bilevel_run, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Optimize the SCEPCal calorimeter until it converges

## Context

I'm designing the SCEPCal crystal electromagnetic calorimeter and want the
crystal geometry with the best energy resolution — the cleanest signal-to-noise
on the reconstructed electron energy. Run an optimization campaign of repeated
epochs, **until it converges** — don't stop at a fixed count.

**Epoch 1 — the starting scan:**

- Crystals **5, 7, and 9 cm wide** × **8 or 11 cm deep at the front**
  (6 geometries).
- **Projective offset fixed at 10 cm**, **rear length fixed at 15 cm**.
- **100 electrons at 1 GeV** per geometry.
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **energy threshold over 0 to 1.0 GeV (5-point grid)**, scoring `snr_energy`.

**Every later epoch — derived from the previous epoch's report** using the
`bilevel_ana` trend rules:

- A parameter that **RISES** (or FALLS) to the edge of its scanned range →
  scan **4 values beyond that edge**, keeping the previous spacing.
- A **FLAT** parameter → fix it at its best value.
- If **all** scanned parameters are FLAT → scan a geometry parameter that has
  not been scanned in any epoch yet (first the **projective offset**, then the
  **rear length**): 4 values around its current value.
- Keep the reconstruction setup and event count unchanged. Each follow-up
  epoch scans exactly **4 geometries**.

**Stop condition (do-until):** stop and declare **CONVERGED** when the latest
epoch's report shows all of its swept parameters FLAT **and** every geometry
parameter (width, front length, offset, rear length) has been scanned in some
epoch — there is nothing left to explore at this statistics level. Safety cap:
stop after **8 epochs** at most and say the cap was hit.

Name the runs `inf1`, `inf2`, … (the skills place configs and outputs in this
run's campaign area automatically; SLURM is handled by the `bilevel_run`
skill's runner). After each epoch write its
report to `./analysis_<k>.md` — the reports stay in this working directory and
each epoch reads the previous one from here.

**Resume rule:** the campaign's progress is the report files. If you are
(re)starting, the next epoch to run is the first k with no `./analysis_<k>.md`.
Re-running an already-completed epoch is harmless — the runner returns its
cached result instantly.

## Todo

Repeat: derive the next epoch's scan (epoch 1 from the starting scan, later
epochs from the previous `./analysis_<k>.md`), build the validated config with
the `bilevel_config` skill, run and verify with the `bilevel_run` skill's
full-runner, analyze with the `bilevel_ana` skill into `./analysis_<k>.md` —
**until the stop condition above is met**.

Then write `./campaign.md`: a short per-epoch table (what was scanned, best
geometry, best score), the stop reason (CONVERGED or 8-epoch cap), the overall
best geometry across all epochs, and one recommendation for future work.
Finish with `done`: the overall best geometry, its score, how many epochs ran,
and the stop reason.

## Expect

- For every epoch k that ran: the builder printed `CONFIG_VALIDATED`
  (geometries=6 for epoch 1, geometries=4 after), the full-runner printed
  `RUN_VERIFIED run=inf<k>` with a job id, and `./analysis_<k>.md` exists with
  sections Best point, Trends, Reliability, Conclusion.
- At least 3 epochs ran (the starting scan alone cannot satisfy the stop
  condition — offset and rear still have to be scanned).
- No epochs ran after the stop condition was met, and at most 8 ran.
- `./campaign.md` exists with the per-epoch table, an explicit stop reason
  (CONVERGED or cap), the overall best geometry and score, and one
  recommendation.
