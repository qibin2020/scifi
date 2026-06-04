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

# Run a full SCEPCal optimization campaign (5 epochs)

## Context

I'm designing the SCEPCal crystal electromagnetic calorimeter and want the
crystal geometry with the best energy resolution — the cleanest signal-to-noise
on the reconstructed electron energy. Run a **5-epoch campaign**: each epoch
runs a scan, and its analysis decides the next epoch's scan.

**Epoch 1 — the starting scan:**

- Crystals **5, 7, and 9 cm wide** × **8 or 11 cm deep at the front**
  (6 geometries).
- **Projective offset fixed at 10 cm**, **rear length fixed at 15 cm**.
- **100 electrons at 1 GeV** per geometry.
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **energy threshold over 0 to 1.0 GeV (5-point grid)**, scoring `snr_energy`.

**Epochs 2–5 — each derived from the previous epoch's report:**

- Each later epoch: decide the next 4-geometry scan yourself from the previous
  epoch's report, your physics knowledge of electromagnetic calorimetry, and
  the goal of finding the best-resolution geometry. Justify each choice in one
  sentence in the report.
- Keep the reconstruction setup and event count unchanged. Each follow-up
  epoch scans exactly **4 geometries**.

Name the runs `azr1` … `azr5` (the skills place configs and outputs in this run's campaign area automatically; SLURM
handled by the `bilevel_run` skill's runner). After each epoch, write its
report to `./analysis_<k>.md` — the reports stay in this working directory,
and each epoch reads the previous one from here.

**Resume rule:** the campaign's progress is the report files. If you are
(re)starting, the next epoch to run is the first k in 1..5 with no
`./analysis_<k>.md`. Re-running an already-completed epoch is harmless — the
runner returns its cached result instantly.

## Todo

For k = 1..5: derive the epoch-k scan (epoch 1 from the starting scan above,
later epochs from `./analysis_<k-1>.md`), build the validated config with the
`bilevel_config` skill, run and verify with the `bilevel_run` skill's
full-runner, and analyze with the `bilevel_ana` skill into `./analysis_<k>.md`.

After epoch 5, write `./campaign.md`: a short per-epoch table (what was
scanned, best geometry, best score), the overall best geometry across all
epochs, and one recommendation for future work. Finish with `done`: the
overall best geometry, its score, and the main caveat.

## Expect

- For each k in 1..5: the builder printed `CONFIG_VALIDATED` (geometries=6 for
  epoch 1, geometries=4 for epochs 2–5), the full-runner printed
  `RUN_VERIFIED run=azr<k>` with a job id, and `./analysis_<k>.md` exists
  with sections Best point, Trends, Reliability, Conclusion.
- Each `analysis_<k>.md` (k>=2) contains a one-sentence justification of the
  scan choice.
- `./campaign.md` exists with the 5-epoch summary, the overall best geometry
  and score, and one recommendation.
