# SCEPCal Optimization Campaign Summary

## Epoch Summary

| Epoch | Parameter(s) Scanned | Best Geometry (w, f, offset, r) | Best Score |
|-------|----------------------|-------------------------------|------------|
| 1     | width, front         | 7, 11, 10, 15                    | 0.8509     |
| 2     | width                | 8, 11, 10, 15                    | 0.8519     |
| 3     | projective offset     | 8, 11, 12, 15                    | 0.8507     |
| 4     | rear length          | 8, 11, 12, 14                    | 0.8595     |
| 5     | width (refined)       | 8.5, 11, 12, 14                  | 0.8639     |

## Overall Best Geometry
- Crystal Width: 8.5 cm
- Front Length: 11 cm
- Projective Offset: 12 cm
- Rear Length: 14 cm
- **Best Score (`snr_energy`): 0.8639**
- **Best Reco Params**: `R_cluster_mm=20`, `E_threshold_GeV=0.75`

## Final Recommendation
The campaign identified a relatively broad plateau in the geometry space. While 8.5 cm width and 14 cm rear length provided the numerical peak, the significance of the differences between the top geometries was low ($\approx 0.1\text{--}0.5\sigma$). To truly distinguish the optimal geometry, it is recommended to repeat the final candidate evaluation with $\geq 1000$ events per geometry to reduce the statistical noise floor below the observed score differences.
