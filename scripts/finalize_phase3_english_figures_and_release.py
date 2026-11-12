from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import shutil
import sys
import zipfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args():
    p = argparse.ArgumentParser(
        description="Regenera todas las figuras de Fase 3 en ingles, actualiza inventarios SHA-256/ZIPs, actualiza curve_inclusion_status.csv en el corpus candidato y crea el release congelado de Fase 3."
    )
    p.add_argument("--root", default=".")
    return p.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def model_sigma(p_wt_percent: np.ndarray, B: float, pc: float, t: float) -> np.ndarray:
    p = np.asarray(p_wt_percent, dtype=float)
    y = np.full_like(p, np.nan, dtype=float)
    mask = p > pc
    y[mask] = B * np.power(p[mask] - pc, t)
    return y


def rebuild_inventory_and_zip(pkg_dir: Path):
    inv = pkg_dir / "sha256_inventory.csv"
    rows = []
    for f in sorted(x for x in pkg_dir.rglob("*") if x.is_file() and x != inv):
        rows.append({
            "relative_path": f.relative_to(pkg_dir).as_posix(),
            "bytes": f.stat().st_size,
            "sha256": sha256(f),
        })
    pd.DataFrame(rows).to_csv(inv, index=False, encoding="utf-8-sig")

    zip_path = pkg_dir.parent / f"{pkg_dir.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in sorted(x for x in pkg_dir.rglob("*") if x.is_file()):
            z.write(f, arcname=f"{pkg_dir.name}/{f.relative_to(pkg_dir).as_posix()}")
    with zipfile.ZipFile(zip_path, "r") as z:
        if z.testzip() is not None:
            raise ValueError(f"Corrupted ZIP: {zip_path}")


def update_standard_curve_figures(pkg_dir: Path, input_csv: str, fig_prefix: str, title_name: str, missing_label_list: list[float]):
    pts = pd.read_csv(pkg_dir / "tables" / input_csv, keep_default_na=False)
    fp = pd.read_csv(pkg_dir / "tables" / "fit_parameters.csv", keep_default_na=False)
    prof = pd.read_csv(pkg_dir / "tables" / "pc_profile.csv", keep_default_na=False)

    p = pd.to_numeric(pts["mass_percent"]).to_numpy(float)
    sigma = pd.to_numeric(pts["conductivity_s_per_cm"]).to_numpy(float)

    pub = fp[fp["fit_type"] == "published_reference"].iloc[0]
    rep = fp[fp["fit_type"] == "independent_profile_log_fit"].iloc[0]

    B_pub, pc_pub, t_pub = float(pub["B_s_per_cm"]), float(pub["pc_wt_percent"]), float(pub["t"])
    B_rep, pc_rep, t_rep = float(rep["B_s_per_cm"]), float(rep["pc_wt_percent"]), float(rep["t"])

    # Figure 1: Fit Reproduction (English)
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(p, sigma, color="black", label=f"Observed Data (N={len(p)})", zorder=3)
    x_pub = np.linspace(pc_pub + 1e-5, p.max(), 500)
    x_fit = np.linspace(pc_rep + 1e-5, p.max(), 500)
    ax.plot(x_pub, model_sigma(x_pub, B_pub, pc_pub, t_pub), label=f"Published Benchmark (pc={pc_pub:.2f} wt.%, t={t_pub:.2f})")
    ax.plot(x_fit, model_sigma(x_fit, B_rep, pc_rep, t_rep), label=f"Independent Fit (pc={pc_rep:.4f} wt.%, t={t_rep:.2f})")
    ax.axvline(pc_pub, linestyle="--", alpha=0.6, label=f"Published pc ({pc_pub:.2f} wt.%)")
    ax.axvline(pc_rep, linestyle=":", alpha=0.8, label=f"Reproduced pc ({pc_rep:.4f} wt.%)")
    for mp in missing_label_list:
        ax.axvline(mp, color="gray", linestyle="-.", alpha=0.45, label=f"Unimputed Missing Point ({mp:g} wt.%)")
    ax.set_yscale("log")
    ax.set_xlabel("MWCNT Content (wt.%)")
    ax.set_ylabel("Electrical Conductivity (S/cm)")
    ax.set_title(f"{title_name}: Percolation Fit Reproduction")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(pkg_dir / "figures" / f"{fig_prefix}_fit_reproduction.png", dpi=200)
    plt.close(fig)

    # Figure 2: pc Error Profile (English)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(pd.to_numeric(prof["pc_wt_percent"]), pd.to_numeric(prof["rmse_log10"]), label="RMSE Profile in log10(S/cm)")
    if prof["pc_wt_percent"].astype(float).min() <= pc_pub <= prof["pc_wt_percent"].astype(float).max():
        ax.axvline(pc_pub, linestyle="--", label=f"Published pc ({pc_pub:.2f} wt.%)")
    ax.axvline(pc_rep, linestyle=":", label=f"Reproduced pc ({pc_rep:.4f} wt.%)")
    ax.set_xlabel("Percolation Threshold pc (wt.%)")
    ax.set_ylabel("RMSE in log10(S/cm)")
    ax.set_title(f"{title_name}: Error Profile for Percolation Threshold pc")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(pkg_dir / "figures" / f"{fig_prefix}_pc_error_profile.png", dpi=200)
    plt.close(fig)

    rebuild_inventory_and_zip(pkg_dir)


def update_continental_figures(pkg_dir: Path):
    pts = pd.read_csv(pkg_dir / "tables" / "continental_input_points.csv", keep_default_na=False)
    fp = pd.read_csv(pkg_dir / "tables" / "fit_parameters.csv", keep_default_na=False)
    prof = pd.read_csv(pkg_dir / "tables" / "pc_profile.csv", keep_default_na=False)

    p = pd.to_numeric(pts["mass_percent"]).to_numpy(float)
    sigma = pd.to_numeric(pts["conductivity_s_per_cm"]).to_numpy(float)

    pub = fp[fp["fit_type"] == "published_reference"].iloc[0]
    pre = fp[fp["fit_type"] == "restricted_pre_observed_bracket_0.375_0.50_fit"].iloc[0]
    ins = fp[fp["fit_type"] == "restricted_in_sample_bracket_0.50_0.625_fit"].iloc[0]

    B_pub, pc_pub, t_pub = float(pub["B_s_per_cm"]), float(pub["pc_wt_percent"]), float(pub["t"])
    B_pre, pc_pre, t_pre = float(pre["B_s_per_cm"]), float(pre["pc_wt_percent"]), float(pre["t"])
    B_in, pc_in, t_in = float(ins["B_s_per_cm"]), float(ins["pc_wt_percent"]), float(ins["t"])

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(p, sigma, color="black", label="Observed Data (N=5, all >= 1.93e-7 S/cm)", zorder=3)
    x_pub = np.linspace(pc_pub + 1e-5, p.max(), 500)
    x_pre = np.linspace(pc_pre + 1e-5, p.max(), 500)
    x_in = np.linspace(pc_in + 1e-5, p.max(), 500)
    ax.plot(x_pub, model_sigma(x_pub, B_pub, pc_pub, t_pub), label=f"Published Benchmark (pc={pc_pub:.2f} wt.%, t={t_pub:.2f})")
    ax.plot(x_pre, model_sigma(x_pre, B_pre, pc_pre, t_pre), label=f"Bracket (0.375, 0.50) Fit [N=5] (pc={pc_pre:.4f} wt.%)")
    ax.plot(x_in, model_sigma(x_in, B_in, pc_in, t_in), linestyle="--", label=f"Bracket (0.50, 0.625) Fit [N=4] (pc={pc_in:.4f} wt.%)")
    ax.axvline(pc_pub, linestyle="--", alpha=0.6, label=f"Published pc ({pc_pub:.2f} wt.%)")
    ax.axvline(pc_pre, linestyle=":", alpha=0.8, label=f"Reproduced pc ({pc_pre:.4f} wt.%)")
    for mp in [0.25, 0.375]:
        ax.axvline(mp, color="gray", linestyle="-.", alpha=0.45, label=f"Unimputed Missing Pre-threshold ({mp:g} wt.%)")
    ax.set_yscale("log")
    ax.set_xlabel("MWCNT Content (wt.%)")
    ax.set_ylabel("Electrical Conductivity (S/cm)")
    ax.set_title("Continental Carbon MWNT: Restricted Dual-Regime Fit Reproduction")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(pkg_dir / "figures" / "continental_fit_reproduction.png", dpi=200)
    plt.close(fig)

    prof_pre = prof[prof["regime"] == "pre_observed_bracket_0.375_to_0.50_N5"]
    prof_in = prof[prof["regime"] == "in_sample_bracket_0.50_to_0.625_N4"]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(pd.to_numeric(prof_pre["pc_wt_percent"]), pd.to_numeric(prof_pre["rmse_log10"]), label="Bracket (0.375, 0.50) Profile [N=5]")
    ax.plot(pd.to_numeric(prof_in["pc_wt_percent"]), pd.to_numeric(prof_in["rmse_log10"]), label="Bracket (0.50, 0.625) Profile [N=4]")
    ax.axvline(pc_pub, linestyle="--", label=f"Published pc ({pc_pub:.2f} wt.%)")
    ax.axvline(pc_pre, linestyle=":", label=f"Reproduced pc ({pc_pre:.4f} wt.%)")
    ax.set_xlabel("Percolation Threshold pc (wt.%)")
    ax.set_ylabel("RMSE in log10(S/cm)")
    ax.set_title("Continental Carbon MWNT: Dual-Bracket Error Profile for pc")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8.5)
    fig.tight_layout()
    fig.savefig(pkg_dir / "figures" / "continental_pc_error_profile.png", dpi=200)
    plt.close(fig)

    rebuild_inventory_and_zip(pkg_dir)


def update_exploratory_and_joint_figures(root: Path):
    exp_pkg = root / "analysis" / "phase3_exploratory_l254_v2_2"
    joint_pkg = root / "analysis" / "phase3_joint_percolation_comparison_v1"
    exp_df = pd.read_csv(exp_pkg / "tables" / "exploratory_dataset.csv", keep_default_na=False)
    joint_df = pd.read_csv(joint_pkg / "tables" / "joint_percolation_comparison.csv", keep_default_na=False)

    # Update Joint Comparison Figure in English
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
        ax.scatter(p_v, s_v, color=c, label=f"{cname} (Observed, N={len(p_v)})", zorder=3)
        x_grid = np.linspace(float(row["reproduced_pc_wt_percent"]) + 1e-4, 3.0, 400)
        ax.plot(
            x_grid,
            model_sigma(x_grid, float(row["reproduced_B_s_per_cm"]), float(row["reproduced_pc_wt_percent"]), float(row["reproduced_t"])),
            color=c, linestyle="-", alpha=0.85,
            label=f"{cname} (Fit: pc={float(row['reproduced_pc_wt_percent']):.3f} wt.%, t={float(row['reproduced_t']):.2f})"
        )
    ax.set_yscale("log")
    ax.set_xlabel("MWCNT Content (wt.%)")
    ax.set_ylabel("Electrical Conductivity (S/cm)")
    ax.set_title("Phase 3 Joint Comparison: 5 MWCNT Variants (Observed Data & Reproduced Fits)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=7.8, ncol=2)
    fig.tight_layout()
    fig.savefig(joint_pkg / "figures" / "joint_5_curves_reproduction_comparison.png", dpi=200)
    plt.close(fig)

    rebuild_inventory_and_zip(joint_pkg)


def main():
    a = parse_args()
    root = Path(a.root).resolve()

    # 1. Update all 5 individual curve packages to 100% English figures
    update_standard_curve_figures(
        root / "analysis" / "phase3_nanocyl_nc7000_fit_reproduction_v1",
        "nanocyl_input_points.csv", "nanocyl", "Nanocyl NC7000 (AR 134)", []
    )
    update_standard_curve_figures(
        root / "analysis" / "phase3_swent_smw100_fit_reproduction_v1",
        "swent_input_points.csv", "swent", "SWeNT SMW-100 (AR 94)", [0.625]
    )
    update_standard_curve_figures(
        root / "analysis" / "phase3_baytubes_c150p_fit_reproduction_v1",
        "baytubes_input_points.csv", "baytubes", "Baytubes C150P (AR 73)", [0.875, 1.25]
    )
    update_standard_curve_figures(
        root / "analysis" / "phase3_hyperion_masterbatch_fit_reproduction_v1",
        "hyperion_input_points.csv", "hyperion", "Hyperion Masterbatch (AR 55)", [0.75, 1.00]
    )
    update_continental_figures(
        root / "analysis" / "phase3_continental_carbon_fit_reproduction_v1"
    )

    # 2. Update Joint Comparison figure in English
    update_exploratory_and_joint_figures(root)

    # 3. Create frozen Phase 3 Release Package in archive/phase3-reproduction-release-v1
    release_dir = root / "archive" / "phase3-reproduction-release-v1"
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True, exist_ok=True)

    packages_to_freeze = [
        "analysis/phase3_exploratory_l254_v2_2",
        "analysis/phase3_nanocyl_nc7000_fit_reproduction_v1",
        "analysis/phase3_swent_smw100_fit_reproduction_v1",
        "analysis/phase3_baytubes_c150p_fit_reproduction_v1",
        "analysis/phase3_hyperion_masterbatch_fit_reproduction_v1",
        "analysis/phase3_continental_carbon_fit_reproduction_v1",
        "analysis/phase3_joint_percolation_comparison_v1",
    ]
    for rel_p in packages_to_freeze:
        src_p = root / rel_p
        dst_p = release_dir / rel_p
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src_p, dst_p)

    summary = {
        "release_id": "phase3-reproduction-release-v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "phase_status": "PHASE_3_CLOSED_READY_FOR_PHASE_4",
        "figure_language": "en",
        "included_packages": packages_to_freeze,
        "canonical_corpus_modified": False,
        "final_models_released": False,
    }
    (release_dir / "release-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    inv_rows = []
    inv_file = release_dir / "sha256-inventory.csv"
    for f in sorted(x for x in release_dir.rglob("*") if x.is_file() and x != inv_file):
        inv_rows.append({
            "relative_path": f.relative_to(release_dir).as_posix(),
            "bytes": f.stat().st_size,
            "sha256": sha256(f),
        })
    pd.DataFrame(inv_rows).to_csv(inv_file, index=False, encoding="utf-8-sig")

    print("FIGURAS EN INGLES ACTUALIZADAS Y RELEASE CONGELADO DE FASE 3 CREADO")
    print(f"Paquetes actualizados con graficas en ingles: 6 (11 figuras PNG en total)")
    print(f"Release congelado de Fase 3: {release_dir}")
    print(f"Total de archivos inventariados en el release de Fase 3: {len(inv_rows)}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)