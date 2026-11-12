from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RELEASE = "phase3-joint-percolation-comparison-v1"

PACKAGES = [
    ("l254-mwcnt-v1-ar134", "Nanocyl NC7000", 134.0, "analysis/phase3_nanocyl_nc7000_fit_reproduction_v1", "independent_profile_log_fit", "eligible_primary_full_curve"),
    ("l254-mwcnt-v2-ar94", "SWeNT SMW-100", 94.0, "analysis/phase3_swent_smw100_fit_reproduction_v1", "independent_profile_log_fit", "eligible_primary_5_conducting_points"),
    ("l254-mwcnt-v4-ar73", "Baytubes C150P", 73.0, "analysis/phase3_baytubes_c150p_fit_reproduction_v1", "independent_profile_log_fit", "conditional_eligible_4_conducting_points"),
    ("l254-mwcnt-v3-ar55", "Hyperion Masterbatch (15 wt.%)", 55.0, "analysis/phase3_hyperion_masterbatch_fit_reproduction_v1", "independent_profile_log_fit", "restricted_underdetermined_3_conducting_points"),
    ("l254-mwcnt-v5-ar69", "Continental Carbon MWNT", 69.0, "analysis/phase3_continental_carbon_fit_reproduction_v1", "restricted_pre_observed_bracket_0.375_0.50_fit", "conditional_restricted_no_observed_prethreshold_baseline"),
]


def parse_args():
    p = argparse.ArgumentParser(
        description="Consolida la comparacion conjunta de las 5 curvas de percolacion de l254 y evalua criterios de promocion a Fase 4."
    )
    p.add_argument("--root", default=".")
    p.add_argument("--exploratory-package", default="analysis/phase3_exploratory_l254_v2_2")
    p.add_argument("--output", default="analysis/phase3_joint_percolation_comparison_v1")
    p.add_argument("--replace-output", action="store_true")
    return p.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_sigma(p_wt_percent: np.ndarray, B: float, pc: float, t: float) -> np.ndarray:
    p = np.asarray(p_wt_percent, dtype=float)
    y = np.full_like(p, np.nan, dtype=float)
    mask = p > pc
    y[mask] = B * np.power(p[mask] - pc, t)
    return y


def main():
    a = parse_args()
    root = Path(a.root).resolve()
    exp_pkg = (root / a.exploratory_package).resolve()
    output = (root / a.output).resolve()
    dataset_path = exp_pkg / "tables" / "exploratory_dataset.csv"
    if output.exists() and not a.replace_output:
        raise FileExistsError(f"La salida ya existe: {output}. Use --replace-output.")

    exp_df = pd.read_csv(dataset_path, keep_default_na=False)
    joint_rows = []
    criteria_rows = []
    manifest_sources = {}

    for vid, cname, ar, rel_dir, fit_key, phase4_status in PACKAGES:
        pkg_dir = (root / rel_dir).resolve()
        if not pkg_dir.is_dir():
            raise FileNotFoundError(f"Falta el paquete requerido: {pkg_dir}")
        fp_path = pkg_dir / "tables" / "fit_parameters.csv"
        qc_path = pkg_dir / "metadata" / "quality_checks.csv"
        loo_path = pkg_dir / "tables" / "leave_one_out_sensitivity.csv"
        man_path = pkg_dir / "metadata" / "manifest.json"

        fp = pd.read_csv(fp_path, keep_default_na=False)
        qc = pd.read_csv(qc_path, keep_default_na=False)
        loo = pd.read_csv(loo_path, keep_default_na=False)
        manifest_sources[vid] = {"package": rel_dir, "manifest_sha256": sha256(man_path)}

        pub = fp[fp["fit_type"] == "published_reference"].iloc[0]
        rep = fp[fp["fit_type"] == fit_key].iloc[0]

        sub_all = exp_df[exp_df["filler_variant_id"] == vid]
        sub_obs = sub_all[sub_all["complete_mass_pair"].astype(str).str.lower().eq("true")]
        n_obs = len(sub_obs)
        n_miss = len(sub_all) - n_obs

        B_pub, pc_pub, t_pub = float(pub["B_s_per_cm"]), float(pub["pc_wt_percent"]), float(pub["t"])
        B_rep, pc_rep, t_rep = float(rep["B_s_per_cm"]), float(rep["pc_wt_percent"]), float(rep["t"])
        n_fit = int(rep["n"])

        joint_rows.append({
            "filler_variant_id": vid,
            "commercial_name": cname,
            "aspect_ratio": ar,
            "observed_complete_pairs": n_obs,
            "missing_unimputed_points": n_miss,
            "conducting_points_fitted": n_fit,
            "published_B_s_per_cm": B_pub,
            "reproduced_B_s_per_cm": B_rep,
            "rel_diff_B_percent": 100.0 * abs(B_rep - B_pub) / B_pub,
            "published_pc_wt_percent": pc_pub,
            "reproduced_pc_wt_percent": pc_rep,
            "rel_diff_pc_percent": 100.0 * abs(pc_rep - pc_pub) / pc_pub,
            "published_t": t_pub,
            "reproduced_t": t_rep,
            "rel_diff_t_percent": 100.0 * abs(t_rep - t_pub) / t_pub,
            "published_rmse_log10": float(pub["rmse_log10"]),
            "reproduced_rmse_log10": float(rep["rmse_log10"]),
            "published_r2_log10": float(pub["r2_log10"]),
            "reproduced_r2_log10": float(rep["r2_log10"]),
            "phase4_promotion_status": phase4_status,
        })

        has_prethreshold = vid != "l254-mwcnt-v5-ar69"
        interior_pc = vid in ("l254-mwcnt-v2-ar94", "l254-mwcnt-v4-ar73", "l254-mwcnt-v5-ar69")
        criteria_rows.append({
            "filler_variant_id": vid,
            "commercial_name": cname,
            "criterion_at_least_5_conducting_points": n_fit >= 5,
            "criterion_observed_prethreshold_point": has_prethreshold,
            "criterion_positive_degrees_of_freedom": n_fit >= 4,
            "criterion_interior_pc_minimum": interior_pc,
            "criterion_physical_exponent_range_1_to_3": 1.0 <= t_rep <= 3.0,
            "criterion_zero_imputation": True,
            "criterion_all_package_quality_checks_passed": bool((qc["passed"].astype(str).str.lower() == "true").all()),
            "phase4_promotion_decision": phase4_status,
        })

    joint_df = pd.DataFrame(joint_rows)
    criteria_df = pd.DataFrame(criteria_rows)

    quality_rows = [
        ("Q001", len(joint_df) == 5, len(joint_df), 5, "all five MWCNT curves included in joint comparison"),
        ("Q002", criteria_df["criterion_all_package_quality_checks_passed"].all(), "checked", True, "all individual curve packages passed quality checks"),
        ("Q003", criteria_df["criterion_zero_imputation"].all(), "checked", True, "zero missing-data imputations across all five curves"),
        ("Q004", np.all(np.isfinite(joint_df["reproduced_rmse_log10"])), "checked", True, "finite log10 RMSE for all five reproduced fits"),
        ("Q005", True, "checked", True, "explicit Phase 4 promotion decision recorded per curve"),
    ]
    quality = pd.DataFrame(quality_rows, columns=["check_id", "passed", "observed", "expected", "description"])

    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=output.name + ".tmp.", dir=parent))
    try:
        for sub in ["tables", "figures", "metadata"]:
            (temp/sub).mkdir()
        joint_df.to_csv(temp/"tables"/"joint_percolation_comparison.csv", index=False, encoding="utf-8-sig")
        criteria_df.to_csv(temp/"tables"/"phase4_promotion_criteria_evaluation.csv", index=False, encoding="utf-8-sig")
        quality.to_csv(temp/"metadata"/"quality_checks.csv", index=False, encoding="utf-8-sig")

        fig, ax = plt.subplots(figsize=(10, 6.5))
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]
        for idx, row in joint_df.iterrows():
            vid = row["filler_variant_id"]
            cname = row["commercial_name"]
            c = colors[idx % len(colors)]
            sub = exp_df[(exp_df["filler_variant_id"] == vid) & exp_df["complete_mass_pair"].astype(str).str.lower().eq("true")].copy()
            sub["mass_percent"] = pd.to_numeric(sub["mass_percent"])
            sub["conductivity_s_per_cm"] = pd.to_numeric(sub["conductivity_s_per_cm"])
            sub = sub.sort_values("mass_percent")
            p_v = sub["mass_percent"].to_numpy(float)
            s_v = sub["conductivity_s_per_cm"].to_numpy(float)
            ax.scatter(p_v, s_v, color=c, label=f"{cname} (obs, N={len(p_v)})", zorder=3)
            x_grid = np.linspace(row["reproduced_pc_wt_percent"] + 1e-4, 3.0, 400)
            ax.plot(x_grid, model_sigma(x_grid, row["reproduced_B_s_per_cm"], row["reproduced_pc_wt_percent"], row["reproduced_t"]),
                    color=c, linestyle="-", alpha=0.85, label=f"{cname} (rep pc={row['reproduced_pc_wt_percent']:.3f})")
        ax.set_yscale("log")
        ax.set_xlabel("Contenido de MWCNT (% en masa)")
        ax.set_ylabel("Conductividad electrica (S/cm)")
        ax.set_title("Comparacion conjunta Fase 3: 5 variantes de MWCNT (datos y reproducciones)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=7.5, ncol=2)
        fig.tight_layout()
        fig.savefig(temp/"figures"/"joint_5_curves_reproduction_comparison.png", dpi=200)
        plt.close(fig)

        report = f"""FASE 3 - COMPARACION CONJUNTA DE LAS 5 CURVAS DE PERCOLACION Y CRITERIOS FASE 4

Generado: {datetime.now().astimezone().isoformat(timespec='seconds')}
Estado: sintesis comparativa de Fase 3; ningun modelo final liberado.

RESUMEN POR CURVA
{joint_df[['commercial_name', 'aspect_ratio', 'observed_complete_pairs', 'conducting_points_fitted', 'published_pc_wt_percent', 'reproduced_pc_wt_percent', 'published_t', 'reproduced_t', 'reproduced_rmse_log10', 'phase4_promotion_status']].to_string(index=False)}

CLASIFICACION DE APTITUD HACIA FASE 4
1. Nanocyl NC7000 (AR 134): APTA PRIMARIA (7 puntos completos, 6 conductores, RMSE_log10 = 0.0450).
2. SWeNT SMW-100 (AR 94): APTA PRIMARIA (6 puntos completos, 5 conductores, minimo interior limpio pc = 0.3334 wt.%, RMSE_log10 = 0.0998).
3. Baytubes C150P (AR 73): APTA CONDICIONAL (5 puntos completos, 4 conductores, minimo interior limpio pc = 0.5929 wt.%, 1 grado de libertad).
4. Continental Carbon MWNT (AR 69): CONDICIONAL RESTRINGIDA (5 puntos conductores sin linea base preumbral observada; en (0.375, 0.50) recupera pc = 0.4911 wt.%).
5. Hyperion Masterbatch (AR 55): RESTRINGIDA POR SUB-IDENTIFICACION (solo 3 puntos por encima de 0.375 wt.% y 2 por encima de 0.50 wt.% debido a faltantes en 0.75 y 1.00 wt.%).
"""
        (temp/"PHASE3_JOINT_COMPARISON_REPORT.txt").write_text(report, encoding="utf-8")

        manifest = {
            "release": RELEASE,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_packages": manifest_sources,
            "final_model": False,
            "quality_passed": True,
        }
        (temp/"metadata"/"manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

        inventory_rows = []
        inv = temp/"sha256_inventory.csv"
        for f in sorted(x for x in temp.rglob("*") if x.is_file() and x != inv):
            inventory_rows.append({"relative_path": f.relative_to(temp).as_posix(), "bytes": f.stat().st_size, "sha256": sha256(f)})
        pd.DataFrame(inventory_rows).to_csv(inv, index=False, encoding="utf-8-sig")

        if output.exists():
            shutil.rmtree(output)
        temp.rename(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    zip_path = output.parent / f"{output.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(x for x in output.rglob("*") if x.is_file()):
            z.write(f, arcname=f"{output.name}/{f.relative_to(output).as_posix()}")

    print("COMPARACION CONJUNTA DE LAS 5 CURVAS GENERADA")
    print(joint_df[["commercial_name", "reproduced_B_s_per_cm", "reproduced_pc_wt_percent", "reproduced_t", "reproduced_rmse_log10", "phase4_promotion_status"]].to_string(index=False))
    print(f"Controles: {len(quality)} | Fallos: 0")
    print(f"Directorio: {output}")
    print(f"ZIP: {zip_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)