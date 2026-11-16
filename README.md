# Project N3 — Physics-Constrained Equation Discovery for Percolation and Structure-Property Relationships in Polymer Nanocomposites

**Authors:** Said Alexis Escobar Vasquez & Reyna  
**Program:** Data Science and Artificial Intelligence, Faculty of Engineering in Applied Sciences (FICA), Universidad Técnica del Norte (UTN)  
**Primary Dataset:** MaterialsMine / NanoMine `l254-castillo-2011` (F. Y. Castillo et al., *Polymer* 52, 2011, 3835–3845, DOI: `10.1016/j.polymer.2011.06.018`)  
**Project Status:** **100% Completed across all 6 Phases (151 Automated Quality Checks Passed, 0 Failures)**

---

## 1. Executive Summary of the 6 Phases

| Phase | Scope | Status | Primary Reproducible Deliverable |
| :---: | :--- | :---: | :--- |
| **Phase 1** | Data Audit & Family Selection | **CLOSED** | Selection of `l254-castillo-2011`; scientific quarantine of `l172-corpus-v1`. |
| **Phase 2** | Relational Curation & Freeze | **CLOSED** | `archive/phase2-corpus-release-v1/` (36 samples, 70 compositions, 29 electrical measurements, 0 SHA-256 diffs). |
| **Phase 3** | Exploratory V2.2 & 5-Curve Fits | **CLOSED** | `archive/phase3-reproduction-release-v1/` (5 individual curve reproductions + joint comparison in English). |
| **Phase 4** | Physics-Constrained Modeling | **CLOSED** | `analysis/phase4_castillo_enriched_modeling_v1/` (Table 2 homogeneous volume conversion, 5%/10% RMSE bands, 10 candidate equations in `equation_registry.csv`). |
| **Phase 5** | LOSO Validation & Ablation | **CLOSED** | `analysis/phase5_validation_and_model_selection_v1/` (5 baselines, Leave-One-Series-Out validation, N=2000 perturbation sensitivity, applicability domains). |
| **Phase 6** | Final Manuscript & Release | **CLOSED** | `Project_N3_Q1_Scientific_Manuscript_Escobar_Reyna.docx`, `FINAL_SCIENTIFIC_REPORT_PROJECT_N3.md`, & `archive/phase6-final-project-release-v1/`. |

---

## 2. Selected Physics-Constrained Equations

1. **Piecewise Mass Percolation Law (`EQ-N3-002`):** `sigma(p) = 2.52e-19 + B * max(0, p - pc)^t` (reduces `log10(sigma)` RMSE by 90.8% vs. linear baseline: `0.1110` vs. `1.2120` decades across N=20 direct-powder conducting points, `R² = 0.9950`; 5-series mean RMSE = `0.1063` decades).
2. **Physics-Constrained Regularization (`EQ-N3-004`):** Enforcing `1.3 <= t <= 2.3` eliminates zero-degree-of-freedom overfitting (`t = 4.8476`) in under-sampled Hyperion Masterbatch, recovering `pc = 0.4952 wt.%` (within 0.96% of the published `0.50 wt.%`).
3. **Excluded-Volume Structure-Property Law (`EQ-N3-005`):** `pc(alpha) = 36.4649 / alpha` (`R² = 0.8093`), outperforming 2-parameter linear regression out-of-sample under Leave-One-Series-Out cross-validation (`RMSE_LOSO = 0.0840` vs. `0.1002 wt.%`, a 16.2% improvement).
4. **Rubbery-Plateau Mechanical Network Law (`EQ-N3-009`):** `E'_180C(alpha) = 0.3333 * alpha - 7.4578 MPa` (`R² = 0.9884`, `RMSE_LOSO = 3.1748 MPa`).
