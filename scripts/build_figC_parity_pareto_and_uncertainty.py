from __future__ import annotations

from pathlib import Path
import argparse
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Published thresholds from Castillo et al. (2011) Table 3 and bracket bounds
VARIANT_META = [
    {"vid": "l254-mwcnt-v1-ar134", "name": "Nanocyl NC7000", "short": "Nanocyl", "alpha": 134.0, "lo": 0.25, "hi": 0.375, "pc_pub": 0.28, "color": "#1f77b4"},
    {"vid": "l254-mwcnt-v2-ar94",  "name": "SWeNT SMW-100",  "short": "SWeNT",   "alpha": 94.0,  "lo": 0.25, "hi": 0.375, "pc_pub": 0.33, "color": "#ff7f0e"},
    {"vid": "l254-mwcnt-v4-ar73",  "name": "Baytubes C150P", "short": "Baytubes","alpha": 73.0,  "lo": 0.50, "hi": 0.625, "pc_pub": 0.61, "color": "#2ca02c"},
    {"vid": "l254-mwcnt-v5-ar69",  "name": "Continental Carbon", "short": "Continental", "alpha": 69.0, "lo": 0.375, "hi": 0.50, "pc_pub": 0.49, "color": "#9467bd"},
    {"vid": "l254-mwcnt-v3-ar55",  "name": "Hyperion MB (15 wt.%)", "short": "Hyperion MB", "alpha": 55.0, "lo": 0.375, "hi": 0.50, "pc_pub": 0.50, "color": "#d62728"},
]

DIRECT_VIDS = [
    "l254-mwcnt-v1-ar134",
    "l254-mwcnt-v2-ar94",
    "l254-mwcnt-v4-ar73",
    "l254-mwcnt-v5-ar69",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generates Figure C (Computational Materials Science Q1 style): "
            "(a) Global parity plot of log10(sigma), (b) Symbolic regression Pareto frontier "
            "(error vs. complexity & physical compliance), (c) Threshold pc uncertainty with "
            "5% RMSE bands and interior LOO error bars, and (d) Paired Leave-One-Series-Out (LOSO) "
            "absolute error comparison."
        )
    )
    parser.add_argument("--root", default=".", help="Project root directory.")
    parser.add_argument(
        "--dataset",
        default="analysis/phase3_exploratory_l254_v2_2/tables/exploratory_dataset.csv",
        help="Path to exploratory_dataset.csv relative to --root.",
    )
    parser.add_argument(
        "--unc-table",
        default="analysis/phase4_castillo_enriched_modeling_v1/tables/parameter_uncertainty_intervals.csv",
        help="Path to Phase 4 parameter_uncertainty_intervals.csv relative to --root.",
    )
    parser.add_argument(
        "--base-table",
        default="analysis/phase5_validation_and_model_selection_v1/tables/baseline_vs_percolation_comparison.csv",
        help="Path to Phase 5 baseline_vs_percolation_comparison.csv relative to --root.",
    )
    parser.add_argument(
        "--loso-table",
        default="analysis/phase5_validation_and_model_selection_v1/tables/leave_one_series_out_validation.csv",
        help="Path to Phase 5 leave_one_series_out_validation.csv relative to --root.",
    )
    parser.add_argument(
        "--out-dir",
        default="analysis/phase6_final_scientific_report_v1/figures",
        help="Output directory for PNG and PDF figures relative to --root.",
    )
    parser.add_argument(
        "--table-out",
        default="analysis/phase6_final_scientific_report_v1/tables/figC_pareto_and_loo_uncertainty_summary.csv",
        help="Output CSV summary table path relative to --root.",
    )
    parser.add_argument("--loo-grid", type=int, default=10001, help="Grid size for interior LOO pc stability (default: 10001).")
    parser.add_argument("--dpi", type=int, default=300, help="Output PNG resolution in DPI (default: 300).")
    return parser.parse_args()


def linregress_np(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    xm = x - x.mean()
    ym = y - y.mean()
    slope = float(np.dot(xm, ym) / np.dot(xm, xm))
    intercept = float(y.mean() - slope * x.mean())
    return slope, intercept


def compute_interior_loo_pc(
    p_cond: np.ndarray,
    sigma_cond: np.ndarray,
    lo: float,
    hi: float,
    grid_size: int,
) -> tuple[float, float]:
    """Compute interior Leave-One-Out pc stability range (retaining lowest conducting anchor)."""
    order = np.argsort(p_cond)
    p_s = p_cond[order]
    y_s = np.log10(sigma_cond[order])
    n = len(p_s)
    if n < 4:
        return np.nan, np.nan

    hi_eff = min(hi, float(p_s[0]))
    pc_grid = np.linspace(lo + 1e-7, hi_eff - 1e-7, grid_size, dtype=float)

    loo_pcs = []
    for drop_idx in range(1, n):
        keep = np.ones(n, dtype=bool)
        keep[drop_idx] = False
        pk = p_s[keep]
        yk = y_s[keep]
        yk_mean = float(yk.mean())
        yk_c = yk - yk_mean

        x = np.log10(pk[None, :] - pc_grid[:, None])
        x_mean = x.mean(axis=1, keepdims=True)
        xc = x - x_mean
        denom = np.sum(xc * xc, axis=1)
        slope = np.sum(xc * yk_c[None, :], axis=1) / denom
        intercept = yk_mean - slope * x_mean[:, 0]
        pred = intercept[:, None] + slope[:, None] * x
        rmse = np.sqrt(np.mean((yk[None, :] - pred) ** 2, axis=1))
        valid = np.isfinite(rmse) & (slope > 0.0)
        best_idx = int(np.argmin(rmse[valid]))
        loo_pcs.append(float(pc_grid[valid][best_idx]))

    return float(min(loo_pcs)), float(max(loo_pcs))


def compute_pareto_mask(params: np.ndarray, rmse: np.ndarray) -> np.ndarray:
    """Return True for Pareto-non-dominated models minimizing (total_parameters, rmse_log10)."""
    n = len(params)
    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            if (params[j] <= params[i] and rmse[j] <= rmse[i]) and (
                params[j] < params[i] or rmse[j] < rmse[i]
            ):
                is_pareto[i] = False
                break
    return is_pareto


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()

    dataset_path = (root / args.dataset).resolve()
    unc_path = (root / args.unc_table).resolve()
    base_path = (root / args.base_table).resolve()
    loso_path = (root / args.loso_table).resolve()
    out_dir = (root / args.out_dir).resolve()
    table_out = (root / args.table_out).resolve()

    for req in (dataset_path, unc_path, base_path, loso_path):
        if not req.is_file():
            raise FileNotFoundError(f"Required input file not found: {req}")

    exp_df = pd.read_csv(dataset_path, keep_default_na=False)
    unc_df = pd.read_csv(unc_path, keep_default_na=False)
    base_df = pd.read_csv(base_path, keep_default_na=False)
    loso_df = pd.read_csv(loso_path, keep_default_na=False)

    # Numeric coercion for Pandas 3.0 safety
    for c in ["opt_B", "opt_pc", "opt_t", "pc_band_5pct_min", "pc_band_5pct_max", "phys_B", "phys_pc", "phys_t"]:
        unc_df[c] = pd.to_numeric(unc_df[c], errors="coerce")
    for c in ["total_parameters", "rmse_log10", "mae_log10", "r2_log10"]:
        base_df[c] = pd.to_numeric(base_df[c], errors="coerce")
    for c in ["held_out_aspect_ratio_alpha", "observed_pc_wt_percent", "eq005_abs_error_wt_percent", "eq006_abs_error_wt_percent"]:
        loso_df[c] = pd.to_numeric(loso_df[c], errors="coerce")

    # -------------------------------------------------------------------------
    # 1. Recompute exact parity predictions on the N=20 conducting direct points
    # -------------------------------------------------------------------------
    comp = exp_df[exp_df["complete_mass_pair"].astype(str).str.lower().eq("true")].copy()
    comp["p_wt"] = pd.to_numeric(comp["mass_percent"], errors="coerce")
    comp["sigma"] = pd.to_numeric(comp["conductivity_s_per_cm"], errors="coerce")
    comp["log10_sigma"] = np.log10(comp["sigma"].to_numpy(dtype=float))

    alpha_map = {m["vid"]: m["alpha"] for m in VARIANT_META}
    pc_map = dict(zip(unc_df["filler_variant_id"], unc_df["opt_pc"]))
    B_map = dict(zip(unc_df["filler_variant_id"], unc_df["opt_B"]))
    t_map = dict(zip(unc_df["filler_variant_id"], unc_df["opt_t"]))

    comp["alpha"] = comp["filler_variant_id"].map(alpha_map)
    comp["pc_s"] = comp["filler_variant_id"].map(pc_map)
    comp["B_s"] = comp["filler_variant_id"].map(B_map)
    comp["t_s"] = comp["filler_variant_id"].map(t_map)

    cond4 = comp[comp["filler_variant_id"].isin(DIRECT_VIDS) & (comp["p_wt"] > comp["pc_s"])].copy()
    p_c4 = cond4["p_wt"].to_numpy(dtype=float)
    a_c4 = cond4["alpha"].to_numpy(dtype=float)
    y_c4 = cond4["log10_sigma"].to_numpy(dtype=float)

    sl_lin, int_lin = linregress_np(p_c4, y_c4)
    pred_base03 = int_lin + sl_lin * p_c4

    X_biv = np.column_stack([np.ones_like(p_c4), p_c4, a_c4])
    beta_biv, _, _, _ = np.linalg.lstsq(X_biv, y_c4, rcond=None)
    pred_base05 = X_biv @ beta_biv

    x_exc = np.log10(p_c4 - cond4["pc_s"].to_numpy(dtype=float))
    sl_g, int_g = linregress_np(x_exc, y_c4)
    pred_eq008 = int_g + sl_g * x_exc

    pred_eq002 = np.log10(
        2.52e-19
        + cond4["B_s"].to_numpy(dtype=float)
        * np.power(p_c4 - cond4["pc_s"].to_numpy(dtype=float), cond4["t_s"].to_numpy(dtype=float))
    )

    rmse_b03 = float(np.sqrt(np.mean((y_c4 - pred_base03) ** 2)))
    rmse_b05 = float(np.sqrt(np.mean((y_c4 - pred_base05) ** 2)))
    rmse_e08 = float(np.sqrt(np.mean((y_c4 - pred_eq008) ** 2)))
    rmse_e02 = float(np.sqrt(np.mean((y_c4 - pred_eq002) ** 2)))

    # -------------------------------------------------------------------------
    # 2. Compute Pareto non-dominated mask on Phase 5 comparison table
    # -------------------------------------------------------------------------
    base_df["is_pareto"] = compute_pareto_mask(
        base_df["total_parameters"].to_numpy(dtype=float),
        base_df["rmse_log10"].to_numpy(dtype=float),
    )
    base_df["is_physics_model"] = base_df["model_category"].astype(str).str.startswith("physics")

    # -------------------------------------------------------------------------
    # 3. Compute interior LOO stability ranges for all 5 variants
    # -------------------------------------------------------------------------
    unc_summary_rows = []
    for meta in VARIANT_META:
        vid = meta["vid"]
        urow = unc_df[unc_df["filler_variant_id"] == vid].iloc[0]
        sub = comp[(comp["filler_variant_id"] == vid) & (comp["p_wt"] > meta["lo"] + 1e-12)]
        loo_lo, loo_hi = compute_interior_loo_pc(
            sub["p_wt"].to_numpy(dtype=float),
            sub["sigma"].to_numpy(dtype=float),
            meta["lo"],
            meta["hi"],
            args.loo_grid,
        )
        unc_summary_rows.append(
            {
                "filler_variant_id": vid,
                "short_name": meta["short"],
                "commercial_name": meta["name"],
                "alpha": meta["alpha"],
                "pc_pub": meta["pc_pub"],
                "opt_pc": float(urow["opt_pc"]),
                "band5_lo": float(urow["pc_band_5pct_min"]),
                "band5_hi": float(urow["pc_band_5pct_max"]),
                "loo_pc_lo": loo_lo,
                "loo_pc_hi": loo_hi,
                "phys_pc": float(urow["phys_pc"]),
                "phys_t": float(urow["phys_t"]),
                "opt_t": float(urow["opt_t"]),
                "color": meta["color"],
            }
        )
    unc_sum_df = pd.DataFrame(unc_summary_rows)

    # -------------------------------------------------------------------------
    # 4. Build 2x2 Publication-Grade Figure C (Computational Materials Science)
    # -------------------------------------------------------------------------
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.8,
            "axes.titlesize": 9.8,
            "axes.labelsize": 8.9,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "legend.fontsize": 7.3,
            "axes.linewidth": 0.9,
        }
    )

    fig, axes = plt.subplots(2, 2, figsize=(13.8, 9.6))

    # --- Panel (a): Global Parity Plot ---
    ax = axes[0, 0]
    lim_lo, lim_hi = -7.3, 0.2
    grid_11 = np.linspace(lim_lo, lim_hi, 200)
    ax.fill_between(grid_11, grid_11 - 0.25, grid_11 + 0.25, color="#2ca02c", alpha=0.12, label=r"$\pm 0.25$ decade band")
    ax.plot(grid_11, grid_11, color="black", linestyle="-", lw=1.2, alpha=0.8, label="1:1 Parity line")
    ax.plot(grid_11, grid_11 + 0.5, color="#7f7f7f", linestyle=":", lw=0.9, alpha=0.7)
    ax.plot(grid_11, grid_11 - 0.5, color="#7f7f7f", linestyle=":", lw=0.9, alpha=0.7, label=r"$\pm 0.50$ decade limits")

    ax.scatter(y_c4, pred_base03, marker="x", s=44, color="#ff7f0e", lw=1.4, alpha=0.85,
               label=f"BASE-03 Linear p (RMSE={rmse_b03:.3f})")
    ax.scatter(y_c4, pred_base05, marker="s", s=38, facecolors="none", edgecolors="#9467bd", lw=1.3,
               label=f"BASE-05 Bivariate p,α (RMSE={rmse_b05:.3f})")
    ax.scatter(y_c4, pred_eq008, marker="^", s=42, facecolors="none", edgecolors="#1f77b4", lw=1.3,
               label=f"EQ-N3-008 Global Master (RMSE={rmse_e08:.3f})")
    ax.scatter(y_c4, pred_eq002, marker="o", s=48, color="#2ca02c", edgecolor="black", lw=0.7, zorder=6,
               label=f"EQ-N3-002 Series Law (RMSE={rmse_e02:.3f}, R²=0.995)")

    ax.set_xlim(lim_lo, lim_hi)
    ax.set_ylim(lim_lo, lim_hi)
    ax.set_xlabel(r"Observed $\log_{10}(\sigma\ [\mathrm{S/cm}])$")
    ax.set_ylabel(r"Predicted $\log_{10}(\sigma\ [\mathrm{S/cm}])$")
    ax.set_title("(a) Global Parity Plot Across Conducting Direct-Powder Series (N = 20)", fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.28)
    ax.legend(loc="upper left", framealpha=0.94)

    # --- Panel (b): Pareto Trade-Off Frontier (Jalali et al. Fig. 2b style) ---
    ax = axes[0, 1]
    pareto_pts = base_df[base_df["is_pareto"]].sort_values("total_parameters")
    ax.step(
        pareto_pts["total_parameters"].to_numpy(dtype=float),
        pareto_pts["rmse_log10"].to_numpy(dtype=float),
        where="post",
        color="#1B365D",
        linestyle="--",
        lw=1.6,
        alpha=0.85,
        label="Pareto-optimal frontier",
    )

    label_offsets = {
        "BASE-01": (8, -13),
        "BASE-02": (8, 6),
        "BASE-03": (-18, -18),
        "BASE-04": (9, 4),
        "BASE-05": (9, -12),
        "EQ-N3-008": (9, 6),
        "EQ-N3-001": (-115, 10),
    }
    display_names = {
        "BASE-01": "BASE-01 (Mean)",
        "BASE-02": "BASE-02 (Median, dom.)",
        "BASE-03": "BASE-03 (Linear p)",
        "BASE-04": "BASE-04 (Quad. p, dom.)",
        "BASE-05": "BASE-05 (Linear p, α)",
        "EQ-N3-008": "EQ-N3-008 (Global Master)",
        "EQ-N3-001": "EQ-N3-002 (Series Law)",
    }

    for _, row in base_df.iterrows():
        mid = str(row["model_id"])
        xp = float(row["total_parameters"])
        yp = float(row["rmse_log10"])
        r2v = max(0.05, float(row["r2_log10"]))
        sz = 55 + 165 * r2v
        is_phys = bool(row["is_physics_model"])
        is_par = bool(row["is_pareto"])

        if is_phys:
            col = "#2ca02c" if mid == "EQ-N3-001" else "#1f77b4"
            ax.scatter([xp], [yp], s=sz, color=col, edgecolor="black", lw=1.1, zorder=6)
        else:
            ec = "#d62728" if not is_par else "#ff7f0e"
            ax.scatter([xp], [yp], s=sz, facecolors="white", edgecolors=ec, lw=1.7, zorder=5)

        dx, dy = label_offsets.get(mid, (6, 4))
        fw = "bold" if is_phys else "normal"
        ax.annotate(
            display_names.get(mid, mid),
            (xp, yp),
            xytext=(dx, dy),
            textcoords="offset points",
            fontsize=7.5,
            fontweight=fw,
            color="#111111" if is_par else "#7a2020",
        )

    # Custom legend proxies matching Jalali et al. visual grammar
    ax.scatter([], [], s=130, color="#2ca02c", edgecolor="black", label="Physics-constrained symbolic law (filled)")
    ax.scatter([], [], s=110, facecolors="white", edgecolors="#ff7f0e", lw=1.7, label="Statistical baseline on frontier (open)")
    ax.scatter([], [], s=90, facecolors="white", edgecolors="#d62728", lw=1.7, label="Dominated baseline (open, red)")

    ax.set_xlim(0.2, 13.4)
    ax.set_ylim(0.0, 1.78)
    ax.set_xlabel("Model Complexity (Total Free Parameters) [-]")
    ax.set_ylabel(r"Prediction Error $\mathrm{RMSE}_{\log_{10}(\sigma)}$ (decades)")
    ax.set_title("(b) Accuracy-Complexity Pareto Frontier (Marker Size $\\propto R^2$)", fontweight="bold")
    ax.grid(True, linestyle="--", alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.94)

    # --- Panel (c): Percolation Threshold Uncertainty (5% RMSE Band + LOO Whiskers) ---
    ax = axes[1, 0]
    y_pos = np.arange(len(unc_sum_df))

    for i, row in unc_sum_df.iterrows():
        # 5% RMSE identifiability thick bar
        ax.hlines(
            i,
            float(row["band5_lo"]),
            float(row["band5_hi"]),
            color="#4C9BE8",
            lw=7.5,
            alpha=0.45,
            zorder=2,
            label="5% RMSE identifiability band" if i == 0 else None,
        )
        # Interior LOO stability thin whisker with caps (where N_fit >= 4)
        if np.isfinite(row["loo_pc_lo"]) and np.isfinite(row["loo_pc_hi"]):
            ax.plot(
                [float(row["loo_pc_lo"]), float(row["loo_pc_hi"])],
                [i, i],
                color="#1B365D",
                lw=1.8,
                marker="|",
                markersize=9,
                zorder=3,
                label="Interior LOO stability range" if i == 0 else None,
            )

    # Highlight Hyperion rescue arrow
    hyp_idx = 4
    hyp_row = unc_sum_df.iloc[hyp_idx]
    ax.annotate(
        "",
        xy=(float(hyp_row["phys_pc"]) - 0.008, hyp_idx),
        xytext=(float(hyp_row["opt_pc"]) + 0.008, hyp_idx),
        arrowprops=dict(arrowstyle="->", color="#d62728", lw=1.8, linestyle="-"),
        zorder=4,
    )
    ax.text(
        0.435,
        hyp_idx - 0.14,
        "-96.2% err\n(1.3 <= t <= 2.3)",
        ha="center",
        va="bottom",
        fontsize=7.4,
        fontweight="bold",
        color="#A93226",
    )

    ax.scatter(
        unc_sum_df["pc_pub"].to_numpy(dtype=float),
        y_pos + 0.16,
        marker="s",
        s=50,
        color="black",
        zorder=6,
        label="Published $p_c$ (Castillo Table 3)",
    )
    ax.scatter(
        unc_sum_df["opt_pc"].to_numpy(dtype=float),
        y_pos,
        marker="o",
        s=52,
        color="#2ca02c",
        edgecolor="black",
        zorder=5,
        label="Unconstrained fit $p_c$",
    )
    ax.scatter(
        unc_sum_df["phys_pc"].to_numpy(dtype=float),
        y_pos - 0.16,
        marker="^",
        s=62,
        color="#d62728",
        edgecolor="black",
        zorder=7,
        label="Physics-constrained $p_c$ (1.3 <= t <= 2.3)",
    )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(
        [f"{r['short_name']}\n(α={int(r['alpha'])})" for _, r in unc_sum_df.iterrows()],
        fontsize=8.2,
    )
    ax.invert_yaxis()
    ax.set_xlim(0.22, 0.65)
    ax.set_xlabel(r"Percolation Threshold $p_c$ (wt.%)")
    ax.set_title("(c) Threshold Uncertainty: 5% RMSE Bands, LOO Whiskers & 3D Bound", fontweight="bold")
    ax.grid(True, axis="x", linestyle="--", alpha=0.28)
    ax.legend(loc="upper right", framealpha=0.95, fontsize=7.1)

    # --- Panel (d): Paired Leave-One-Series-Out (LOSO) Error Comparison (Jalali et al. Fig. 2a style) ---
    ax = axes[1, 1]
    e_eq006 = loso_df["eq006_abs_error_wt_percent"].to_numpy(dtype=float)
    e_eq005 = loso_df["eq005_abs_error_wt_percent"].to_numpy(dtype=float)
    names_loso = loso_df["held_out_commercial_name"].tolist()
    regimes_loso = loso_df["domain_evaluation_regime"].tolist()
    alphas_loso = loso_df["held_out_aspect_ratio_alpha"].to_numpy(dtype=float)

    rmse_006 = float(np.sqrt(np.mean(e_eq006 ** 2)))
    rmse_005 = float(np.sqrt(np.mean(e_eq005 ** 2)))
    mae_006 = float(np.mean(e_eq006))
    mae_005 = float(np.mean(e_eq005))
    impr_pct = 100.0 * (rmse_006 - rmse_005) / rmse_006

    # Plot paired lines connecting each held-out MWCNT grade across the two models
    x_left, x_right = 0.0, 1.0
    series_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd"]
    for i in range(len(loso_df)):
        reg_tag = "Extrap." if "extrap" in regimes_loso[i].lower() else "Interp."
        ls_pair = "-" if reg_tag == "Extrap." else "--"
        short_n = names_loso[i].split()[0]
        ax.plot(
            [x_left, x_right],
            [e_eq006[i], e_eq005[i]],
            color=series_colors[i],
            linestyle=ls_pair,
            lw=2.0,
            alpha=0.85,
            zorder=3,
            label=f"{short_n} (α={int(alphas_loso[i])}, {reg_tag})",
        )
        ax.scatter([x_left], [e_eq006[i]], color="white", edgecolor=series_colors[i], s=65, lw=2.0, zorder=5)
        ax.scatter([x_right], [e_eq005[i]], color=series_colors[i], edgecolor="black", s=65, lw=0.9, zorder=6)

        # Value annotations slightly outside points
        y_off_l = 0.003 if i != 2 else 0.004
        y_off_r = -0.005 if i == 3 else 0.004
        ax.text(x_left - 0.05, e_eq006[i] + y_off_l, f"{e_eq006[i]:.4f}", ha="right", va="center", fontsize=7.4, color=series_colors[i])
        ax.text(x_right + 0.05, e_eq005[i] + y_off_r, f"{e_eq005[i]:.4f}", ha="left", va="center", fontsize=7.4, fontweight="bold", color=series_colors[i])

    # Horizontal mean / RMSE bars
    ax.hlines(rmse_006, x_left - 0.14, x_left + 0.14, color="#d62728", lw=3.0, zorder=7, label=f"LOSO RMSE: {rmse_006:.4f} -> {rmse_005:.4f} wt.%")
    ax.hlines(rmse_005, x_right - 0.14, x_right + 0.14, color="#1B365D", lw=3.0, zorder=7)

    # Callout box highlighting out-of-sample win
    ax.text(
        0.50,
        0.014,
        f"1-Param Physical Law (EQ-N3-005)\nreduces LOSO RMSE by {impr_pct:.1f}%\n(MAE: {mae_006:.4f} -> {mae_005:.4f} wt.%)\nBest gains in Extrapolation (solid lines)",
        ha="center",
        va="bottom",
        fontsize=7.6,
        fontweight="bold",
        color="#1B365D",
        bbox=dict(boxstyle="round,pad=0.35", fc="#F4F7FA", ec="#1B365D", lw=1.0),
    )

    ax.set_xticks([x_left, x_right])
    ax.set_xticklabels(
        [
            "EQ-N3-006 (2-Param Linear)\npc = 43.84/α - 0.0902\n(Unconstrained Affine)",
            "EQ-N3-005 (1-Param Physical)\npc = 36.46/α\n(Zero-Intercept ODE / Excl. Vol.)",
        ],
        fontsize=8.2,
        fontweight="bold",
    )
    ax.set_xlim(-0.34, 1.34)
    ax.set_ylim(0.0, 0.196)
    ax.set_ylabel(r"Held-Out Absolute Error $|p_{c,\mathrm{pred}} - p_{c,\mathrm{obs}}|$ (wt.%)")
    ax.set_title("(d) Paired Leave-One-Series-Out (LOSO) Generalization Across Grades", fontweight="bold")
    ax.grid(True, axis="y", linestyle="--", alpha=0.28)
    ax.legend(loc="upper center", ncol=2, framealpha=0.95, fontsize=6.9, columnspacing=1.0)

    fig.suptitle(
        "Model Parity, Pareto Complexity-Accuracy Trade-Off, Uncertainty Intervals, and Paired LOSO Validation",
        fontsize=11.8,
        fontweight="bold",
        y=0.985,
    )
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.96])

    out_dir.mkdir(parents=True, exist_ok=True)
    table_out.parent.mkdir(parents=True, exist_ok=True)

    png_path = out_dir / "figC_parity_pareto_and_uncertainty.png"
    pdf_path = out_dir / "figC_parity_pareto_and_uncertainty.pdf"
    fig.savefig(png_path, dpi=args.dpi)
    fig.savefig(pdf_path)
    plt.close(fig)

    # Export clean combined summary CSV for traceability
    out_summary = unc_sum_df.drop(columns=["color"]).copy()
    out_summary.to_csv(table_out, index=False, encoding="utf-8-sig")

    print("FIGURE C GENERATED SUCCESSFULLY (COMPUTATIONAL MATERIALS SCIENCE STYLE)")
    print(f"PNG (300 DPI): {png_path}")
    print(f"PDF (Vector):  {pdf_path}")
    print(f"Summary CSV:   {table_out}")
    print("\nPARETO FRONTIER MODELS:")
    print(base_df[["model_id", "total_parameters", "rmse_log10", "r2_log10", "is_pareto", "is_physics_model"]].to_string(index=False))
    print("\nTHRESHOLD UNCERTAINTY & LOO SUMMARY:")
    print(out_summary[["commercial_name", "pc_pub", "opt_pc", "band5_lo", "band5_hi", "loo_pc_lo", "loo_pc_hi", "phys_pc"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)
