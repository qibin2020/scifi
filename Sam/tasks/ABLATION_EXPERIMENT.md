# Autonomy-Ablation Experiment — how much route encoding does a weak non-thinking model need?

## The question

The baseline task `bilevel_epoch_full` encodes a near-complete optimization
**route** in its Context: trend-derivation rules (RISES → extend, FLAT → fix),
plus an explicit *fallback order* (first projective offset, then rear length)
for when every scanned parameter is flat. A weak non-thinking model (gemma4)
ran it successfully, following the encoded route exactly (width/front scan →
refine peak → fallback offset → fallback rear → re-refine; 23 iters / 770 s).

How much of that route encoding is actually necessary for a weak non-thinking
model to run a sensible 5-epoch detector-optimization campaign? We strip the
optimization-strategy rules from the *task text only* in three progressive
rungs (the `bilevel_ana` skill — its FLAT/RISES/PEAKED trend rules and domain
glossary — is left intact and stays available to every variant) and grade each
resulting trajectory.

## The four rungs

| Rung | Task | Run prefix | What the Context tells the agent about epochs 2–5 |
|------|------|-----------|----------------------------------------------------|
| Baseline | `bilevel_epoch_full` | `epoch` | Full trend rules **and** the explicit offset-then-rear fallback order. Already run: 23 iters / 770 s / route followed. |
| Rung 1 — order ablation | `bilevel_abl_order` | `aor` | Trend rules kept, **fallback order removed**: on all-FLAT, agent picks any not-yet-scanned geometry parameter and 4 values, justifying the choice in one sentence. |
| Rung 2 — rule ablation | `bilevel_abl_free` | `afr` | **All trend-derivation rules removed.** Agent decides the most informative 4-geometry scan itself; task still *points at* the `bilevel_ana` trend rules as a guide. One-sentence justification required. |
| Rung 3 — pointer ablation | `bilevel_abl_zero` | `azr` | Same as Rung 2 but the **pointer to the trend rules is also removed** — the Context only invokes the agent's own physics knowledge and the goal. (The skill docs are still injected by the system; we just stop naming them.) One-sentence justification required. |

Everything else is held constant across all four: frontmatter (gemma4 ×
gemma4, Rank 4, same skills/binds/iteration caps), the epoch-1 starting scan,
the resume rule, the exactly-4-geometries-per-follow-up resource limit, the
5-epoch count, the `campaign.md` requirement, and the per-epoch `analysis_<k>.md`
artifact contract. Only the epochs-2–5 derivation text changes, and each
variant uses a unique run-name prefix so outputs never collide.

## Run protocol

Run each variant **once**, **sequentially**, each as a single campaign:

```
SciF RUN bilevel_abl_order
SciF RUN bilevel_abl_free
SciF RUN bilevel_abl_zero
```

- Model pairing: **gemma4 (force) × gemma4 (control)**, non-thinking — identical
  to the baseline.
- Run them one at a time so the shared `/srv/runs` cache and SLURM queue are not
  contended.
- Outputs land in:
  - **Run configs + results**: `/srv/runs/<prefix><k>.yaml` and
    `/srv/runs/<prefix><k>/results/` for k = 1..5
    (`aor1..aor5`, `afr1..afr5`, `azr1..azr5`).
  - **Per-epoch reports + campaign summary**: `F/tasks/<name>_<ts>/analysis_*.md`
    and `F/tasks/<name>_<ts>/campaign.md` (the agent's working directory for
    that run; `<ts>` is the run timestamp).
  - **Driver transcript**: `Cam/driver_<task>_<ts>.jsonl`.

## Grading rubric

Score each campaign on **five axes, 0–2 each** (0 = absent/wrong, 1 = partial,
2 = full), purely from the persisted artifacts — no re-running. Max 10 per
campaign.

1. **Loop integrity** — exactly 5 epochs were run, each a distinct scan; no
   epoch skipped, merged into another, or duplicated. (2 = five clean distinct
   epochs; 1 = five present but one redundant/merged; 0 = wrong count.)
2. **Gradient capture** — does the campaign find and then exploit the one real
   physics gradient, the **width rise visible from epoch 1**? (2 = detects the
   rising/peaked width and extends/refines it; 1 = notices but does not act;
   0 = ignores it.)
3. **No waste** — does it avoid rescanning an already-FLAT parameter at the
   same values it already tried? (2 = no wasted rescans; 1 = one borderline
   repeat; 0 = repeats a flat scan.)
4. **Statistical honesty** — is plateau / tie hedging present where score
   differences are below noise (the `< 2 sigma` plateau and
   `best_vs_second NOT significant` cases)? (2 = hedges correctly throughout;
   1 = hedges once / inconsistently; 0 = claims false winners.)
5. **Termination quality** — is the final `campaign.md` / `done`
   recommendation well-founded (correct overall best or stated tie, plus a
   sound caveat such as the R_cluster pinning artifact)? (2 = correct best +
   sound caveat; 1 = best right, caveat weak/missing; 0 = wrong recommendation.)

**Where the evidence lives for each axis:**

- Loop integrity → the five `analysis_<k>.md` in `F/tasks/<name>_<ts>/`, the
  per-epoch table in `campaign.md`, and the set of `/srv/runs/<prefix>*.yaml`
  configs (one per epoch actually run).
- Gradient capture → epoch-1 `analysis_1.md` Trends section (width tag) vs.
  the epoch-2..5 scan ranges in the later configs / reports.
- No waste → compare the swept parameters + value lists across consecutive
  `/srv/runs/<prefix><k>.yaml` configs and the Trends sections.
- Statistical honesty → the Reliability / Conclusion sections of each
  `analysis_<k>.md` (spread-in-sigma and best-vs-second wording).
- Termination quality → `campaign.md` and the final `done` line in
  `Cam/driver_<task>_<ts>.jsonl`.

The driver transcript `Cam/driver_<task>_<ts>.jsonl` is the authoritative
record of iteration count, ordering, and the final `done` message for any axis
where the written reports are ambiguous.

## Results table (to fill after the runs)

| Task | Prefix | Iters | Wall (s) | (1) Loop | (2) Gradient | (3) No waste | (4) Stat. honesty | (5) Termination | Total /10 | Route notes |
|------|--------|-------|----------|----------|--------------|--------------|-------------------|-----------------|-----------|-------------|
| bilevel_epoch_full (baseline, v2 noise) | `epoch` | 23 | 1829 | 2 | 2 | 2 | 2 | 2 | **10** | width PEAKED@7 + front RISES found e1 → front extended to 17 (real, v2-only discovery) → offset 14 → rear 16 → refine; (7,17,14,16)@0.8640; containment-score rec |
| bilevel_abl_order | `aor` | 25 | 1853 | 1 | 2 | 1 | 2 | 2 | **8** | chose offset→rear order BY ITSELF (matches encoded route); found front-17; BUT epoch 5 degenerated to 1-geometry re-eval (aor5 roots=1, violating exactly-4; reviewer waived) |
| bilevel_abl_free | `afr` | 23 | 1586 | 2 | 1 | 0 | 1 | 1 | **5** | 3 of 4 follow-ups micro-refined width around one lucky noise peak (0.8690 re-evaluated identically 3×, deterministic duplicate = zero info); never scanned offset/rear; missed front; done-summary misread the R-pinning note |
| bilevel_abl_zero | `azr` | 26 | 2704 | 2 | 2 | 1 | 2 | 1 | **8** | width refine → front extension (found f=15 rise) → offset → width re-check; (8,15,8,15)@0.8642 = same basin as baseline; rear never scanned; epoch-5 re-scan low-value |

### Key findings (2026-06-03, gemma4 × gemma4, v2 noise floor)

1. **Removing structure degrades STRATEGY, not MECHANICS** — loop/token
   discipline survived every rung; scan-selection quality did not.
2. **Non-monotonic: abl_free < abl_zero.** "The skill's trend rules are your
   guide" without task rules produced mechanical trend-following that anchored
   on a noise peak; "use your physics knowledge" engaged priors (shower depth
   matters → explore front). Half-delegation is worse than none.
3. **The encoded fallback ladder's main value is COVERAGE** (all four
   parameters scanned) and epoch-5 discipline — not route choice: the freed
   agent picked the same offset→rear order when asked to justify it.
4. **All four campaigns land in the same plateau basin** (0.8640–0.8690 noise
   peaks), consistent with the two independent 1000-event confirmations
   (no significant winner).
