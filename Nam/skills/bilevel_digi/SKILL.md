---
name: bilevel_digi
description: Scan the readout/digitization parameters — sampling rate Sa [GHz] × ADC bits N — of a COMPLETED bilevel run by replaying its cached simulation output (no new simulation), then interpret the printed digest. Run ONE bundled command (digi_scan.sh); never parse digi_scan.csv yourself.
---

# bilevel_digi — readout (Sa × N) scan on a finished run

A verified bilevel run leaves its simulation output under
`/srv/runs/<CAMPAIGN>/<RUN>/sim_outputs/`. This skill replays those cached
photons through the waveform digitizer + template fit for every (sampling
rate, ADC bits) grid point — fast, no new ddsim — and computes per point:

- `s_err` — scintillation-photon reconstruction error |S_reco−S_truth|/S_truth
  (lower is better; the campaign requirement is **s_err ≤ 2%**)
- `power` — analytic ADC readout power, N_crystals × 2^N × Sa (lower is better)

**Do NOT read or parse the output files yourself.** Run the one command and
read its digest.

## The one command (run AFTER the run's RUN_VERIFIED)

```bash
bash /srv/skills/bilevel_digi/digi_scan.sh --run <RUN_NAME>
```

Optional grid overrides (defaults shown — use them unless the task or a
previous digest `note:` says otherwise):

```bash
... --sa 0.005,0.01,0.02,0.05,0.1 --bits 6,8,10,12 --max-units 1500
```

It prints a digest between `DIGI_DIGEST_BEGIN` / `DIGI_DIGEST_END` and one
final token:

- `DIGI_VERIFIED run=<RUN> points=<P> best_serr=<x>` → success.
- `DIGI_FAIL <reason>` → the run is missing/incomplete. Report the reason; do
  not invent numbers.

Run it ONCE per run. It is idempotent: re-running with the same grid returns
the cached result instantly (`FORCE=1` forces a rescan). Every readout number
in your report must come from this digest.

## How to read the digest

- `global_best_cell` — the (Sa, N) with the lowest s_err averaged over all
  geometries. The averaging removes per-geometry noise; prefer this over
  `best_single` (one geometry, one cell — subject to selection bias).
- `compliance` — how many grid cells meet s_err ≤ 2%.
- `operating_point` — **the recommended readout**: the lowest-power cell among
  the compliant ones. Quote it in every report.
- `geometry_coupling` — whether the best (Sa, N) depends on geometry. Usually
  it does not; if it does, say so in the report.
- `trend_vs_Sa` / `trend_vs_N` — marginal s_err trends:
  - `FLAT` → the parameter does not limit accuracy in this range; choose its
    cheapest value (lowest Sa / smallest N).
  - `RISES` / `FALLS` → s_err grows/shrinks with the parameter; the optimum
    sits at (or beyond) a grid edge.
  - `PEAKED@v` → interior optimum near v (too-low Sa undersamples the pulse;
    too-high Sa lets noise dominate each narrow bin).
- `note:` lines — deterministic recommendations. **Copy them into your report
  verbatim (rephrasing is fine, changing the action is not).** Never invent
  your own grid changes: if no note asks to extend or refine the grid, keep
  the same grid next epoch.

## The combined metric J (when the run's inner stage has finished)

If the run has inner-loop results, the digest ends with a **combined-metric
section** joining all three quantities into ONE number per
(geometry, Sa, N):

```
J = snr_energy · (1 − s_err) − 0.02 · log10(power / 1 W)
```

higher is better — geometry quality × readout fidelity, minus a per-decade
power cost. Read it as:

- `J_best` — **THE overall recommended operating point** (geometry and
  readout together). Quote this tuple and its J, snr, s_err, power in every
  report.
- `J_marginal <param>` — per-geometry-parameter trends of the best-readout
  J (FLAT / RISES / FALLS / PEAKED@v, same vocabulary as bilevel_ana) — use
  THESE to derive the next epoch's geometry scan when the task says the
  campaign optimizes J.
- `J_trend_vs_Sa` / `J_trend_vs_N` — readout trends of J.
- `note:` lines — copy verbatim, as always.

## Physics context (keep it short in reports)

Sampling rate Sa controls how finely the SiPM pulse is sampled: too slow
loses the pulse shape (fit degrades), too fast spreads the same light over
many noisy samples. ADC bits N control amplitude quantization — above the
noise floor extra bits change nothing but multiply power (power ∝ 2^N × Sa).
The trade-off is real: the best accuracy region usually sits at modest Sa
with the smallest N that keeps quantization below the noise.

## Notes

- The run must be VERIFIED first (`RUN_VERIFIED` from bilevel_run); after any
  FAILED job the sim outputs are stale — never scan them.
- `--rundir <DIR>` is for foreign paths found via the ledger
  `/srv/runs/LEDGER.csv`; the normal `--run <NAME>` resolves inside this
  task's campaign area.
- Output files (`results/digi_scan.csv`, `digi_scan.json`) are for tooling;
  the digest is the only numbers source for reports.
