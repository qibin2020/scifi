---
Rank: 2
ThinkTime: 1800
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

**Method: CWoLa + VAE hybrid. Follow the recipe below exactly.**

### DO NOT
- Do NOT use labels.npy during training, fitting, preprocessing, or feature selection.
  labels.npy is ONLY for the final AUC evaluation (`roc_auc_score(labels, scores)`).
  Using true labels to select training subsets, fit scalers, or define background
  samples is label leakage and invalidates the result.
- Do NOT deviate from the recipe below. This is an execution benchmark, not a research task.
- Do NOT fabricate metrics. If AUC < 0.6 after training, print the real AUC and stop.

### CWoLa
Signal is a resonance at ~3.5 TeV in dijet mass (mjj, index 2).
1. Split events: signal_region (mjj > 3200 GeV) vs sideband (mjj ≤ 3200)
2. Train GradientBoostingClassifier(n_estimators=300, max_depth=5, learning_rate=0.05, random_state=42) on ALL features EXCEPT mjj (drop index 2, use remaining 14)
3. If training set > 200K, subsample to 200K (100K per class) for speed
4. Score ALL events: predict_proba(X_no_mjj)[:, 1]

### VAE
1. Select 5 features: pt1(3), pt2(4), mjj(2), width1(12), width2(13)
2. Preprocess: log1p, then StandardScaler fit on SIDEBAND events only (not labels.npy background). Save scaler.
3. Architecture with BatchNorm:
   ```
   Encoder: Linear(5,32)->BN(32)->LeakyReLU -> Linear(32,16)->BN(16)->LeakyReLU -> fc_mu(16,2), fc_logvar(16,2)
   Decoder: Linear(2,16)->BN(16)->LeakyReLU -> Linear(16,32)->BN(32)->LeakyReLU -> Linear(32,5)
   ```
4. Train on SIDEBAND events only, Adam lr=1e-3, batch=4096, 10 epochs. Loss = MSE + 0.5*KL.
5. Score ALL events: MSE reconstruction error + 0.5 * KL per event

### Hybrid
1. Min-max normalize CWoLa and VAE scores to [0,1]
2. score = 0.7 * norm(CWoLa) + 0.3 * norm(VAE)

**Package constraints:** `pip install 'torch>=2.0,<2.5' 'scipy<1.14' 'matplotlib<3.9' scikit-learn`
Set `export HOME=/tmp && export MPLCONFIGDIR=/tmp/mpl && mkdir -p /tmp/mpl` before matplotlib.

Target: AUC > 0.78.

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
- No label leakage: grep the training script for uses of labels.npy — it must ONLY appear in the final evaluation block (roc_auc_score), never in scaler.fit, model training data selection, or background mask construction
