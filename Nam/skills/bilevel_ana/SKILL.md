---
name: bilevel_ana
description: Analyze the output of a finished bilevel detector-optimization run — run ONE bundled command (ana.sh) to get a metric digest, then interpret it with the domain rules in this doc and write a short analysis.md conclusion. Never parse summary.json/npz yourself.
---

# bilevel_ana — digest + interpret a bilevel optimization result

A finished bilevel run leaves its optimization results under
`/srv/runs/<NAME>/results/` (`summary.json`, landscape `.npz`, plots). **Do NOT
read or parse those files yourself.** This skill ships `ana.sh`, which extracts
every metric you need into one short digest. Your job has exactly two steps:
run the one command, then write `analysis.md` interpreting the digest using the
domain rules below.

## The two-step workflow (this is the whole job)

When a task gives you only a RUN NAME (e.g. "analyze run ana_seed"), you have
all you need — there are no other commands to write:

1. **Digest** → `bash /srv/skills/bilevel_ana/ana.sh --run <NAME>`
   (resolves inside this run's campaign area; use
   `--results <DIR>` only for an explicit foreign path)
2. **Report** → write `./analysis.md` (in the task dir) from the digest numbers,
   using the template + domain rules below.
3. **Done** → call `done` with a one-line conclusion.

That is the entire task. Do not invent extra steps, do not parse files, do not
recompute numbers. The run name maps directly to the results path
`/srv/runs/<NAME>/results` and the report always goes to `./analysis.md`.

## Step 1 — the one command

```bash
bash /srv/skills/bilevel_ana/ana.sh --run <NAME>
```

It prints a digest between `ANA_DIGEST_BEGIN` / `ANA_DIGEST_END` and one final
token:

- `ANA_OK geometries=<N> best_score=<S>` → success. Go to Step 2.
- `ANA_FAIL <reason>` → the results are missing/incomplete. Report the reason;
  do not invent an analysis.

Run it ONCE. Every number you write in Step 2 must come from the digest —
never compute, estimate, or invent numbers.

## Step 2 — write `analysis.md` (in the task dir, i.e. `./analysis.md`)

Use exactly this structure, filling in digest numbers:

```markdown
# Bilevel Analysis — <run name>

## Best point
- Geometry: <swept params of global_best, plus the fixed_geometry values>
- Reco params: <global_best reco params, e.g. R_cluster_mm=20 E_threshold_GeV=0.75>
- Score (snr_energy): <best> (mean <mean> ± <std> over <N> geometries)

## Trends
- <one line per swept parameter, from the `marginals` block: its trend tag and
  what it means — see the trend rules>

## Reliability
- <one line per reco param: pinned or interior, from `reco_params`>
- Score spread <spread> = <X> sigma of statistical noise (<events> events/geom,
  sigma ≈ <noise_sigma>): <whether geometry differences are significant>
- Best vs second: <gap significance from the `significance` line>
- <failed_cells line, if present in the digest>

## Conclusion
<2–4 sentences: which geometry to pick (or that it's a plateau), whether the
result can be trusted, and ONE concrete recommendation for the next iteration.>
```

When `analysis.md` is written, call `done` with a one-line conclusion (e.g.
"best w=8,f=10 at score 0.80, R_cluster pinned low — rerun with constrained R").

## Domain rules (how to interpret each digest line)

**What the score is.** `snr_energy` = signal-to-noise ratio of the
reconstructed electron energy after clustering crystals around the shower seed.
Higher is better. Typical values 0.5–1.0 for 1 GeV electrons. The geometry with
the highest score reconstructs energy most cleanly.

**Statistical noise (`noise_sigma`).** The score of one geometry fluctuates
with the Monte-Carlo sample: sigma ≈ 0.30/√(events per geometry) — measured
0.030 at 100 events, 0.013 at 500, 0.010 at 1000. Use the digest's
`significance` line directly:

- `spread = K sigma` with K < 2 → the whole scan is a **plateau**: geometry
  choice in this range barely matters; differences are mostly noise.
- `best_vs_second ... NOT significant` → do NOT claim a single winner; say the
  top geometries are statistically equivalent and quote both.
- If a real winner matters, the fix is **more events per geometry** (500–1000),
  not more geometries.

**Pinning tags (`reco_params`).** Brute optimization searched each reco
parameter on a grid between bounds. When a parameter is pinned at a bound, the
digest adds an indented `note:` line under it — that note IS the correct
next-iteration recommendation. **Copy the `note:` into your Reliability and
Conclusion sections verbatim (rephrasing is fine, changing the action is not).**
Never invent your own fix for a pinned parameter — in particular, when
`R_cluster_mm` is PINNED_LOW the note distinguishes the two cases (unconstrained
range → constrain R to a physical range; already-physical bound → switch to a
containment-aware score, do NOT lower the R bound). Background: smaller clusters
always score higher under `snr_energy` (the clustering degeneracy), so a low-pinned
R is an artifact — the R value is not physically meaningful, but the geometry
*ranking* is still usable.

- **INTERIOR** → trustworthy optimum for that parameter; quote its value.
- **PINNED_LOW / PINNED_HIGH** → follow the digest's `note:` line.
- **MOSTLY_PINNED_*** → same as pinned, with a few exceptions usually caused by
  noise.

**Trend tags (`marginals`).** Mean score per value of each swept geometry
parameter, with a noise-aware threshold:

- `FLAT` → the parameter does not matter in the scanned range; fix it at any
  convenient value and spend the next iteration elsewhere.
- `RISES` / `FALLS` → the optimum is at (or beyond) the edge of the scanned
  range; extend the scan in that direction.
- `PEAKED@v` → genuine interior optimum near v; refine the grid around v.

**`failed_cells`.** Landscape grid points with score `-inf` are parameter
combinations where the reconstruction kept no events (typically a high
`E_threshold_GeV` rejecting every hit). A moderate count is normal and
harmless as long as the best point is INTERIOR; if the best point sits next to
failed cells, the threshold range should be reduced.

**Physics context for the Conclusion (keep it short).**
Crystal width controls transverse shower containment (Molière radius);
front/rear length control longitudinal containment (radiation lengths);
the projective offset avoids inter-crystal channeling. Wider/longer crystals
contain more of the shower but cost resolution granularity — the scan exists
because the optimum is a trade-off.

## Worked example

Digest (abridged):

```
geometries: 36   events_per_geom: 100   noise_sigma: 0.0300
score: best=0.8018 ... spread=0.1483
significance: spread=4.9 sigma | best_vs_second=0.1 sigma -> NOT significant
global_best: scepcal_xtal_length_f=10 scepcal_xtal_theta_width=8 | R_cluster_mm=5 E_threshold_GeV=0.5 | score=0.8018
reco_params:
  R_cluster_mm: bounds[5,200] ... | PINNED_LOW
  E_threshold_GeV: bounds[0,0.5] ... | PINNED_HIGH
marginals:
  scepcal_xtal_length_f: ... | PEAKED@12
  scepcal_xtal_theta_width: ... | PEAKED@9
```

→ Conclusion: "The scan shows a real geometry dependence (spread 4.9σ above
noise) peaking near width 9 cm, front length 10–12 cm; the single best point
(w=8, f=10, score 0.802) is statistically tied with its runner-up. Both reco
parameters pinned at their bounds: R_cluster at the grid minimum (the known
small-cluster degeneracy) and E_threshold at its maximum, so rerun with R
constrained to a physical range and the threshold bound widened above 0.5 GeV
before trusting the reco-parameter values."

## Notes

- `--run <NAME>` resolves to the campaign area (`/srv/runs/<campaign>/<NAME>/results`).
  `--results <DIR>` (or the run dir itself) is for foreign paths, e.g. a run
  found via the ledger `/srv/runs/LEDGER.csv`.
- If the event count is missing from the digest, pass `--events <N>` when the
  task states it; otherwise skip the noise-based statements.
- Write `analysis.md` with the `write_file` tool in the task dir (`./`), NOT
  under `/srv/runs` (usually mounted read-only).
