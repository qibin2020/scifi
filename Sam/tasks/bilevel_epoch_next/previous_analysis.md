# Bilevel Analysis — nl_full

## Best point
- Geometry: scepcal_xtal_length_f=11, scepcal_xtal_theta_width=9, scepcal_projective_offset_r=10, scepcal_xtal_length_r=15
- Reco params: R_cluster_mm=20 E_threshold_GeV=0.9495
- Score (snr_energy): 0.9507 (mean 0.9051 ± 0.0408 over 6 geometries)

## Trends
- scepcal_xtal_length_f: FLAT — the front depth (8 vs 11 cm) has little impact on reconstructed energy SNR.
- scepcal_xtal_theta_width: RISES — wider crystals (9 cm) generally improve the score compared to 5 cm.

## Reliability
- R_cluster_mm: PINNED_LOW (All 6 geometries hit the minimum bound of 20 mm).
- E_threshold_GeV: INTERIOR.
- Score spread 0.1065 = 3.6 sigma of statistical noise (100 events/geom, sigma ≈ 0.030): geometry differences are significant.
- Best vs second: 0.2 sigma -> NOT significant.

## Conclusion
The geometry with front depth 11 cm and width 9 cm performs best with a score of 0.9507. While the overall geometry differences are significant, the top two geometries are statistically indistinguishable. The cluster radius is pinned at the lower bound (20 mm), suggesting the optimum is outside the current search range or the score is insensitive to further reductions. I recommend exploring smaller cluster radii or shifting to a containment-aware score to better resolve the optimal clustering radius.
