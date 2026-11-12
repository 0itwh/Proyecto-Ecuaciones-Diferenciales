# Physics-Constrained Equation Discovery for Percolation and Structure-Property Relationships in Polymer Nanocomposites

**Authors:** Said Alexis Escobar Vasquez & Reyna
**Affiliation:** Universidad Tecnica del Norte (UTN), Facultad de Ingenieria en Ciencias Aplicadas, Carrera de Ciencia de Datos e Inteligencia Artificial, Ibarra, Ecuador
**Date:** 2026-11-12
**Release Package:** `phase6-final-scientific-report-and-release-v1`

---

## 1. Title
*Physics-Constrained Equation Discovery for Percolation and Structure-Property Relationships in Melt-Mixed Polycarbonate / Multi-Walled Carbon Nanotube Nanocomposites*

## 2. Abstract
We present an end-to-end, cryptographically auditable workflow for physics-constrained equation discovery in polymer nanocomposites, applied to multi-walled carbon nanotube (MWCNT) / polycarbonate (PC, Makrolon 2600) systems curated from MaterialsMine/NanoMine (`l254-castillo-2011`, DOI: `10.1016/j.polymer.2011.06.018`). Across 36 experimental samples spanning five commercial MWCNT grades with TEM-measured median aspect ratios alpha = L_x50 / D_x50 in [55, 134] and filler loadings p in [0.25, 3.0] wt.%, we audit data provenance, resolve a 37x-96x volume-fraction distortion caused by bulk-powder density entries in NanoMine, reproduce series-specific percolation laws, and evaluate 10 candidate symbolic equations against statistical baselines and Leave-One-Series-Out (LOSO) cross-validation. Series-specific percolation models (`EQ-N3-002`) reduce log10(sigma) RMSE by 90.8% relative to linear baselines (0.1110 vs. 1.2120 decades, R2 = 0.9950). Imposing physical 3D critical exponent bounds (1.3 <= t <= 2.3, `EQ-N3-004`) prevents zero-degree-of-freedom overfitting (t = 4.85) in under-sampled series (Hyperion Masterbatch), recovering its published threshold within 0.96% (pc = 0.4952 vs. 0.50 wt.%). Across direct-powder grades, the single-parameter excluded-volume law pc(alpha) = 36.4649 / alpha (`EQ-N3-005`, R2 = 0.8093) outperforms two-parameter linear regression out-of-sample under LOSO validation (RMSE_LOSO = 0.0840 vs. 0.1002 wt.%), while rubbery-plateau DMA storage modulus at 180 C scales linearly with aspect ratio (`EQ-N3-009`, R2 = 0.9884). Dynamic SINDy models (`EQ-N3-010`) are formally excluded because the corpus comprises static composition series rather than temporal trajectories.

## 3. Introduction & 4. Scientific Gap
Data-driven equation discovery in polymer nanocomposites is frequently undermined by silent unit mismatches, mixing of bulk and embedded filler densities, unverified measurement conditions, and unconstrained symbolic overparameterization on small experimental series (N = 5-7 points per curve). This study bridges that gap by coupling relational provenance auditing with dimensionally and physically constrained regression.

## 5. Fundamentals of Nanocomposites & 6. Percolation Theory
Above the critical percolation threshold pc, electrical conductivity follows the Stauffer-Aharony power law sigma(p) = sigma_m + B*(p - pc)^t, while continuum percolation of penetrable rods predicts a theoretical threshold phi_p = 1/(2*alpha). Electron hopping/tunneling and length polydispersity shift experimental thresholds below phi_p, whereas cohesive primary agglomerates (Baytubes C150P) shift pc upward.

## 7. Data & Provenance, 8. Selection Criteria, & 9. Experimental Hierarchy
- **Primary Corpus (`l254-castillo-2011`):** 1 study, 1 matrix system (PC Makrolon 2600), 5 MWCNT filler variants, 36 samples (`s1` pure PC control + 35 filled samples), 70 composition records, 29 electrical measurements, and 28 complete composition-conductivity pairs.
- **Quarantined Corpus (`l172-corpus-v1`):** Held in scientific quarantine (18 samples, 235 deduplicated electrical points) due to unverified electrical units and measurement conditions.
- **Zero-Imputation Policy:** Seven missing electrical measurements (`s12, s20, s21, s26, s28, s30, s31`) were never imputed; their positions were evaluated analytically.

## 10. Statistical Methods, 11. Symbolic Regression, & 12. SINDy Exclusion
- **Static Formulation:** P = F(p, phi, alpha, Delta_L_rel; theta) estimated via deterministic grid profiling and constrained log-space least squares.
- **SINDy Exclusion (`EQ-N3-010`):** Melt mixing was fixed at 280 C, 200 rpm, and 5 min; because independent filler concentrations do not constitute a temporal trajectory, dq/dt = k_f*(1 - q) - k_d*q is excluded per Section 33 of the research protocol.

## 13. Physical Constraints & 14. Dimensional Analysis
1. **Homogeneous Volume Conversion:** Resolved via Table 2 footnote of Castillo et al. (rho_PC = 1.20 g/cm3, rho_MWNT_embedded = 1.75 g/cm3).
2. **Critical Exponent Bound (1.3 <= t <= 2.3):** Regularizes under-sampled curves (`EQ-N3-004`).
3. **Asymptotic Threshold Positivity (pc(alpha) -> 0+ as alpha -> inf):** Enforced in `EQ-N3-005`, eliminating the unphysical negative intercept of `EQ-N3-006` for alpha > 486.

## 15. Validation, 16. Results, 17. Generalization, 18. Applicability Domain, & 19. Uncertainty

### Table A: Five-Series Percolation Reproduction & 5% RMSE Uncertainty Bands
```text
               commercial_name  aspect_ratio_alpha    opt_B   opt_pc  pc_band_5pct_min  pc_band_5pct_max    opt_t  phys_pc   phys_t  opt_rmse_log10
                Nanocyl NC7000               134.0 0.056675 0.251005          0.250000          0.269285 1.473096 0.251005 1.473096        0.044998
                 SWeNT SMW-100                94.0 0.008093 0.333395          0.324355          0.340990 2.080576 0.333395 2.080576        0.099782
                Baytubes C150P                73.0 0.008187 0.592895          0.587105          0.597910 2.335809 0.595080 2.299922        0.107156
       Continental Carbon MWNT                69.0 0.005864 0.491125          0.488130          0.493510 2.183539 0.491125 2.183539        0.166344
Hyperion Masterbatch (15 wt.%)                55.0 0.000469 0.375000          0.375000          0.377605 4.847549 0.495200 2.299594        0.113339
```

### Table B: Baseline vs. Physics-Constrained Model Comparison (N=20 Conducting Points)
```text
 model_id                                  model_name          model_category  total_parameters  n_evaluated  rmse_log10  mae_log10  medae_log10  r2_log10  max_abs_error_log10
  BASE-01               Constant Mean in log10(sigma)          naive_baseline                 1           20    1.563582   1.270828     1.147287  0.000000             3.820954
  BASE-02             Constant Median in log10(sigma)          naive_baseline                 1           20    1.582204   1.246887     1.188349 -0.023961             4.062986
  BASE-03         Linear Regression in Mass Percent p    statistical_baseline                 2           20    1.212022   0.935548     0.642034  0.399131             3.132152
  BASE-04      Quadratic Polynomial in Mass Percent p    statistical_baseline                 3           20    1.157382   0.868420     0.570733  0.452087             2.806255
  BASE-05              Bivariate Linear in (p, alpha)    statistical_baseline                 3           20    0.818980   0.618639     0.385184  0.725650             2.189365
EQ-N3-008 Global Master Percolation Law (shared B, t) physics_symbolic_global                 6           20    0.558780   0.466561     0.413761  0.872286             1.230508
EQ-N3-001       Series-Specific Percolation Power Law physics_symbolic_series                12           20    0.110953   0.077193     0.046815  0.994965             0.300217
```

### Table C: Leave-One-Series-Out (Evaluation C) Out-of-Sample Generalization
```text
held_out_commercial_name  held_out_aspect_ratio_alpha domain_evaluation_regime  observed_pc_wt_percent  eq005_predicted_pc_wt_percent  eq006_predicted_pc_wt_percent  observed_E_prime_180C_MPa  eq009_predicted_E_prime_180C_MPa
          Nanocyl NC7000                        134.0            extrapolation                0.251005                       0.274429                       0.181104                       37.8                         31.985767
           SWeNT SMW-100                         94.0            interpolation                0.333395                       0.401536                       0.392606                       22.3                         24.402361
          Baytubes C150P                         73.0            interpolation                0.592892                       0.453276                       0.455981                       17.1                         16.729457
 Continental Carbon MWNT                         69.0            extrapolation                0.491122                       0.550484                       0.605154                       16.3                         14.901527
```

### Table D: Final Model Selection & Applicability Domains
```text
equation_id                                selection_tier                                                      symbolic_expression    composition_domain_wt_percent                                                     aspect_ratio_domain_alpha
  EQ-N3-002                   SELECTED_PRIMARY_SERIES_LAW                                sigma(p) = sigma_m + B * max(0, p - pc)^t                  0.0 to 3.0 wt.%       69 to 134 (direct-powder CVD MWNTs); 55 with t in [1.3, 2.3] constraint
  EQ-N3-003                   SELECTED_PRIMARY_VOLUME_LAW sigma(phi) = A_vol * (phi - phi_c)^t_vol  subject to 1.3 <= t_vol <= 2.3          p > pc (up to 3.0 wt.%) 55 to 134 (with physical exponent bound active for under-sampled Hyperion MB)
  EQ-N3-005       SELECTED_PRIMARY_STRUCTURE_PROPERTY_LAW                                              pc(alpha) = 36.4649 / alpha Predicts pc in [0.25, 0.61] wt.%                                      69 <= alpha <= 134 (direct-powder MWNTs)
  EQ-N3-007       SELECTED_CONDITIONAL_THEORETICAL_BRIDGE          pc_exp = 0.3136 * pc_theory + 0.1115  where phi_p = 1/(2*alpha)   pc_theory in [0.54, 1.32] wt.%       55 <= alpha <= 134 (excluding high-agglomerate-strength Baytubes C150P)
  EQ-N3-009             SELECTED_SECONDARY_MECHANICAL_LAW                                 E'_180C(alpha) = 0.3333 * alpha - 7.4578           Fixed at 3.0 wt.% MWNT                                      69 <= alpha <= 134 (direct-powder MWNTs)
  EQ-N3-006                   RETAINED_INTERPOLATION_ONLY                               pc(alpha) = 43.8386 * (1 / alpha) - 0.0902          pc in [0.25, 0.60] wt.%                                                   Strictly 69 <= alpha <= 134
  EQ-N3-008 REJECTED_AS_FINAL_RETAINED_AS_GLOBAL_BASELINE                   log10(sigma) = -1.7715 + 2.2604 * log10(p - pc(alpha))            p > pc up to 3.0 wt.%                                                            69 <= alpha <= 134
  EQ-N3-010            EXCLUDED_BY_STATIC_CORPUS_PROTOCOL                                              dq/dt = k_f*(1 - q) - k_d*q                   Not applicable                                                                Not applicable
```

## 20. Limitations, 21. Discussion, & 22. Conclusions
1. **Primary Selected Equations:** `EQ-N3-002` (piecewise mass percolation law), `EQ-N3-003` (homogeneous volume percolation law), `EQ-N3-005` (zero-intercept excluded-volume law pc = 36.4649/alpha), `EQ-N3-007` (continuum-theory bridge), and `EQ-N3-009` (rubbery network modulus E'_180C(alpha)).
2. **Methodological Contribution:** Demonstrates that physical bounds and parsimonious zero-intercept scaling laws outperform unconstrained multi-parameter fits when experimental nanocomposite series have missing intermediate points or limited sample sizes.

## 23. Data Availability, 24. Code Availability, & 25. References
- **Repository:** `https://github.com/0itwh/Proyecto-Ecuaciones-Diferenciales`
- **Primary Reference:** F. Y. Castillo et al., *Polymer* 52 (2011) 3835-3845, DOI: `10.1016/j.polymer.2011.06.018`.