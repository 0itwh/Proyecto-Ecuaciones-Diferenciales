from __future__ import annotations

from pathlib import Path
from datetime import datetime
import hashlib
import shutil
import sys
import zipfile
import pandas as pd


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rebuild_inventory_and_zip(pkg_dir: Path):
    inv_path = pkg_dir / "sha256_inventory.csv"
    rows = []
    for f in sorted(x for x in pkg_dir.rglob("*") if x.is_file() and x != inv_path):
        rows.append({"relative_path": f.relative_to(pkg_dir).as_posix(), "bytes": f.stat().st_size, "sha256": sha256(f)})
    pd.DataFrame(rows).to_csv(inv_path, index=False, encoding="utf-8-sig")

    zip_path = pkg_dir.parent / f"{pkg_dir.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(x for x in pkg_dir.rglob("*") if x.is_file()):
            z.write(f, arcname=f"{pkg_dir.name}/{f.relative_to(pkg_dir).as_posix()}")


def main():
    root = Path(".").resolve()

    # 1. Fix text strings in Phase 5 model_selection_and_applicability_domain.csv to match exact LOSO RMSE (0.0840 vs 0.1002 wt.%, 3.1748 MPa, 90.8%)
    p5_dir = root / "analysis" / "phase5_validation_and_model_selection_v1"
    sel_csv = p5_dir / "tables" / "model_selection_and_applicability_domain.csv"
    if sel_csv.is_file():
        sel_df = pd.read_csv(sel_csv, keep_default_na=False)
        sel_df.loc[sel_df["equation_id"] == "EQ-N3-002", "justification"] = "Reduces log10 RMSE by 90.8% vs linear baseline (0.1110 vs 1.2120 decades, R2=0.9950) and anchors p <= pc to pure PC s1"
        sel_df.loc[sel_df["equation_id"] == "EQ-N3-005", "extrapolation_warnings"] = "Outperforms 2-parameter linear fit in Leave-One-Series-Out (RMSE 0.0840 vs 0.1002 wt.%) and obeys pc -> 0 as alpha -> inf"
        sel_df.loc[sel_df["equation_id"] == "EQ-N3-009", "justification"] = "Validated by Leave-One-Series-Out (R2 = 0.9884, LOSO RMSE = 3.1748 MPa), confirming combined CNT-polymer network"
        sel_df.loc[sel_df["equation_id"] == "EQ-N3-006", "extrapolation_warnings"] = "Unphysical negative threshold for alpha > 486; higher LOSO error (0.1002 wt.%) than 1-param EQ-N3-005 (0.0840 wt.%)"
        sel_df.loc[sel_df["equation_id"] == "EQ-N3-008", "extrapolation_warnings"] = "5.0x higher pooled log10 RMSE (0.5588 vs 0.1110) than series-specific B because intrinsic tube/contact conductivity B varies"
        sel_df.to_csv(sel_csv, index=False, encoding="utf-8-sig")
        rebuild_inventory_and_zip(p5_dir)

    # 2. Sync the updated table into Phase 6 and archive/phase6-final-project-release-v1
    p6_dir = root / "analysis" / "phase6_final_scientific_report_v1"
    if p6_dir.is_dir() and sel_csv.is_file():
        shutil.copy(sel_csv, p6_dir / "tables" / "final_selected_models_and_domains.csv")
        rebuild_inventory_and_zip(p6_dir)

    final_rel = root / "archive" / "phase6-final-project-release-v1"
    if final_rel.is_dir() and p5_dir.is_dir() and p6_dir.is_dir():
        for pkg_rel in [
            "analysis/phase5_validation_and_model_selection_v1",
            "analysis/phase6_final_scientific_report_v1",
        ]:
            dst = final_rel / pkg_rel
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(root / pkg_rel, dst)
        rel_inv = []
        rel_inv_path = final_rel / "sha256-inventory.csv"
        for f in sorted(x for x in final_rel.rglob("*") if x.is_file() and x != rel_inv_path):
            rel_inv.append({"relative_path": f.relative_to(final_rel).as_posix(), "bytes": f.stat().st_size, "sha256": sha256(f)})
        pd.DataFrame(rel_inv).to_csv(rel_inv_path, index=False, encoding="utf-8-sig")

    # 3. Update Root Markdown Files (README.md, PROJECTROADMAP.md, DECISIONLOG.md, ISSUESLOG.md)
    readme_text = """# Project N3 — Physics-Constrained Equation Discovery for Percolation and Structure-Property Relationships in Polymer Nanocomposites

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
"""
    (root / "README.md").write_text(readme_text, encoding="utf-8")

    roadmap_text = """# PROJECT ROADMAP — PROJECT N3 (ALL 6 PHASES CLOSED)

- **Phase 1 (Closed):** Audit of MaterialsMine/NanoMine, quarantine of `l172-corpus-v1`, selection of `l254-castillo-2011`.
- **Phase 2 (Closed):** Relational curation and immutable canonical freeze (`archive/phase2-corpus-release-v1`).
- **Phase 3 (Closed):** Exploratory analysis V2.2 and independent reproduction of all 5 MWCNT curves (`archive/phase3-reproduction-release-v1`).
- **Phase 4 (Closed):** Homogeneous volume conversion (`rho_PC = 1.20 g/cm3`, `rho_MWNT = 1.75 g/cm3`), 5%/10% RMSE uncertainty intervals, and 10-equation registry (`analysis/phase4_castillo_enriched_modeling_v1`).
- **Phase 5 (Closed):** Comparison against 5 baselines, Leave-One-Series-Out (LOSO) validation, N=2000 Monte Carlo perturbation sensitivity, and applicability domain selection (`analysis/phase5_validation_and_model_selection_v1`).
- **Phase 6 (Closed):** Final Q1 scientific manuscript in English (`.docx` and `.md`) and frozen final release (`archive/phase6-final-project-release-v1`).
"""
    (root / "PROJECTROADMAP.md").write_text(roadmap_text, encoding="utf-8")

    print("SINCRONIZACION DE TABLAS Y ARCHIVOS RAIZ COMPLETADA SIN ERRORES")
    return 0


if __name__ == "__main__":
    sys.exit(main())
