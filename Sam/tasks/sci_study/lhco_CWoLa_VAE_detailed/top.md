---
Rank: 2
Timeout: 1800
BashTime: 1800
Skills: common_env
NoMemory: on
CommonStorage: rw
---

# LHCO 2020 (Guided v2): Train CWoLa + VAE anomaly detector

## Context

R&D features at /mnt/lhco/data/features/:
- features.npy — shape (1100000, 15), 15 jet physics features
- labels.npy — 0=background (1M), 1=signal (100K)
- feature_names: mj1(0), mj2(1), mjj(2), pt1(3), pt2(4), eta1(5), eta2(6), deta(7), dphi(8), dR(9), nconst1(10), nconst2(11), width1(12), width2(13), pt_ratio(14)

**Method: weakly-supervised + density-based hybrid (CWoLa + VAE is the canonical baseline; you may deviate as long as the final score reaches the AUC target).**

Signal is a resonance at ~3.5 TeV in dijet mass (mjj, index 2).

### Suggested baseline (CWoLa)
Train a classifier (e.g. GradientBoostingClassifier with n_estimators≈300, max_depth≈5,
learning_rate≈0.05) to discriminate "signal_region" vs "sideband" on all features except mjj.
A typical SR/SB split is mjj > 3200 GeV vs mjj ≤ 3200, but you may narrow or shift the
split (e.g. SR=[3.4, 3.6] TeV, SB=[2.0, 3.2] ∪ [3.8, 4.2] TeV) if it helps performance.
Score ALL events with predict_proba.

### Suggested baseline (VAE)
Select a small set of jet-substructure features (e.g. pt1, pt2, width1, width2, optionally
mjj). Preprocess with log1p + StandardScaler fit on background only. Train a small VAE
(latent dim ~2, BatchNorm encoder/decoder) on background only with Adam lr≈1e-3,
batch≈4096, ≥10 epochs. Score all events with MSE + β·KL (β around 0.1–1).

### Hybrid
Combine the two scores after normalising each to [0, 1]; tune the mix (e.g. 0.7·CWoLa + 0.3·VAE
is a reasonable starting point but other splits or rank-based combinations are fine).

### Freedom
You may swap any component (different classifier, different VAE depth, alternative density
estimator, different feature subsets, narrower SR, multiple ensemble seeds and average) as
long as: (a) the method is unsupervised or weakly supervised (no use of `labels.npy`
during fitting), (b) results files are produced as listed in Expect, (c) final hybrid AUC
on the full dataset against `labels.npy` is **strictly above 0.78**. If a single seed gives
unstable AUC, average over a few seeds and pick the median.

**Package constraints:** `pip install 'torch>=2.0,<2.5' 'scipy<1.14' 'matplotlib<3.9' scikit-learn`
Set `export HOME=/tmp && export MPLCONFIGDIR=/tmp/mpl && mkdir -p /tmp/mpl` before matplotlib.

Target: AUC > 0.78. If after two distinct attempts your hybrid AUC stays under 0.6,
the dataset may not contain the expected signal — print the AUC and bail rather than
fabricating a passing metric.

## Todo

1. **Fetch data if absent.** If `/mnt/lhco/data/features/features.npy` and `/mnt/lhco/data/features/labels.npy` are not already present, download them into `/mnt/lhco/data/features/`. Acceptable sources:
   - HuggingFace Datasets (e.g. `huggingface_hub.snapshot_download(repo_id="JustWhit3/LHCO2020", repo_type="dataset")`) and convert to the required `features.npy` + `labels.npy` shapes described above.
   - Or any equivalent mirror you know of that provides the LHCO 2020 R&D dataset.
   - If no internet access is available, fail gracefully and print a clear "data unavailable" message rather than fabricating data.
2. Write one Python script that trains CWoLa + VAE + hybrid, evaluates, saves models and plots
3. Run it with timeout 1500
4. Save models to /mnt/lhco/guided_v2/models/ (cwola_model.pkl, vae_model.pt, scaler.npz)
5. Save results to /mnt/lhco/guided_v2/results/ (metrics.json, roc_curve.png, score_dist.png)

## Expect

- /mnt/lhco/data/features/features.npy exists after the task runs
- /mnt/lhco/data/features/labels.npy exists after the task runs
- /mnt/lhco/guided_v2/models/cwola_model.pkl exists, > 100 KB
- /mnt/lhco/guided_v2/models/vae_model.pt exists, > 5 KB
- /mnt/lhco/guided_v2/results/metrics.json exists with 'auc' > 0.78
- /mnt/lhco/guided_v2/results/roc_curve.png exists, > 5 KB
- /mnt/lhco/guided_v2/results/score_dist.png exists, > 5 KB
