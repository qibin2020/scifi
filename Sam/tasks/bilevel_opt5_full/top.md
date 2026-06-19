---
Rank: 4
ForceModel: gemma4
ControlModel: gemma4
Campaign: purescifi
Skills: bilevel_config, bilevel_run, bilevel_digi, bilevel_ana
SlurmTool: on
SlurmWorkdir: /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal
SlurmWrapper: driver/enter_scifi_container.sh
BashTime: -1
NoMemory: on
Binds: /cvmfs, /global/cfs/projectdirs/m4956/binus/k4geo:/srv/k4geo:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal:/srv/bilevel:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/detector_config:/srv/detector_config:ro, /pscratch/sd/b/binus/Playground/AIS_design_det/bilevel_det_opt_internal/runs:/srv/runs:rw
---

# Optimize the SCEPCal calorimeter and its readout — a 5-epoch campaign

## Context

I'm designing the SCEPCal crystal electromagnetic calorimeter together with
its readout electronics. Run a **5-epoch** optimization campaign. The goal has
three parts:

1. the crystal geometry with the best energy resolution (highest `snr_energy`),
2. the readout operating point — sampling rate Sa and ADC bits N — with the
   **lowest power among points that reconstruct the scintillation light to
   2% or better** (the `bilevel_digi` digest computes this for you),
3. a characterization of how every parameter affects the result.

**Epoch 1 — the starting scan:**

- Crystals **4, 6, 8, and 10 cm wide** × **6, 10, 14, and 18 cm deep at the
  front** (16 geometries).
- **Projective offset fixed at 10 cm**, **rear length fixed at 15 cm**.
- **300 electrons at 1 GeV** per geometry.
- Tune the **cluster radius over 20 to 150 mm (15-point grid)** and the
  **energy threshold over 0 to 1.0 GeV (5-point grid)**, scoring `snr_energy`.
- After the run is verified, scan the readout on it with the `bilevel_digi`
  skill using its **default Sa/bits grid**.

**Every later epoch — derived from the previous epoch's report.** Each epoch
always scans a **4×4 grid of two geometry parameters (16 geometries)**; pick
the two parameters and their values with these rules:

- A parameter that **RISES** (or FALLS) to the edge of its scanned range →
  scan **4 values beyond that edge**, keeping the previous spacing.
- A parameter that is **PEAKED@v** → scan **4 values bracketing v at half the
  previous spacing**.
- A **FLAT** parameter → fix it at its best value and scan instead a geometry
  parameter not yet scanned in any epoch (first the **projective offset**,
  then the **rear length**): 4 values centered on its current value with
  **4 cm spacing**.
- Keep the event count, reconstruction setup, and score unchanged.
- Readout: keep the same Sa/bits grid as the previous epoch **unless** the
  previous readout digest printed a `note:` asking to extend or refine the
  grid — then apply exactly that note.

Name the runs `ps1` … `ps5` (the skills place configs and outputs in this
run's campaign area automatically; SLURM is handled by the `bilevel_run`
skill's runner). After each epoch write `./analysis_<k>.md` with sections
**Best point, Trends, Readout, Reliability, Conclusion** — the geometry
numbers from the `bilevel_ana` digest, the readout numbers (operating point
and its `note:` lines, copied) from the `bilevel_digi` digest, and in the
Conclusion the derivation of the next epoch's scan.

**Resume rule:** the campaign's progress is the report files. If you are
(re)starting, the next epoch to run is the first k with no `./analysis_<k>.md`.
Re-running an already-completed epoch is harmless — both runners return their
cached results instantly.

## Todo

For k = 1 … 5: derive the epoch's scan (epoch 1 from the starting scan, later
epochs from `./analysis_<k-1>.md`), build the validated config with the
`bilevel_config` skill, run and verify with the `bilevel_run` skill's
full-runner (16 geometries), scan the readout with the `bilevel_digi` skill on
run `ps<k>`, analyze with the `bilevel_ana` skill, and write
`./analysis_<k>.md`. Exactly 5 epochs — no more, no fewer.

Then write `./campaign.md` with:

- a per-epoch table: parameters scanned, their ranges, best geometry, best
  score, readout operating point;
- the overall best geometry across all epochs and whether it beats the
  runners-up significantly (use the digest noise lines — if not, say it is a
  plateau and quote the top candidates);
- the final recommended readout operating point (Sa, N, its s_err and power);
- a parameter-impact table: one line each for width, front length, rear
  length, projective offset, Sa, and N — the observed trend and what it means;
- one recommendation for future work.

Finish with `done`: overall best geometry, its score, the readout operating
point, and the main caveat.

## Expect

- For every epoch k = 1…5: the builder printed `CONFIG_VALIDATED
  geometries=16`, the full-runner printed `RUN_VERIFIED run=ps<k> roots=16`
  with a job id, the readout scan printed `DIGI_VERIFIED run=ps<k>`, the
  digest printed `ANA_OK geometries=16`, and `./analysis_<k>.md` exists with
  sections Best point, Trends, Readout, Reliability, Conclusion.
- Exactly 5 epochs ran: `./analysis_1.md` … `./analysis_5.md` all exist and
  no `./analysis_6.md`.
- `./campaign.md` exists with the per-epoch table, the overall best geometry
  with a significance statement, a readout operating point with s_err and
  power, a parameter-impact line for each of width, front length, rear
  length, offset, Sa, and N, and one future recommendation.
