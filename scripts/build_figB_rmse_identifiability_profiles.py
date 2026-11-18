from __future__ import annotations

from pathlib import Path
import argparse
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Variant metadata grounded in Castillo et al. (2011) Tables 1-3 and Phase 3/4 frozen artifacts
VARIANTS = [
    {
        "filler_variant_id": "l254-mwcnt-v1-ar134",
        "panel": "(a)",
        "label": "Nanocyl NC7000",
        "alpha": 134,
        "lo": 0.25,
        "hi": 0.375,
        "pc_pub": 0.28,
        "t_pub": 1.30,
        "color": "#1f77b4",
    },
    {
        "filler_variant_id": "l254-mwcnt-v2-ar94",
        "panel": "(b)",
        "label": "SWeNT SMW-100",
        "alpha": 94,
        "lo": 0.25,
        "hi": 0.375,
        "pc_pub": 0.33,
        "t_pub": 2.00,
        "color": "#ff7f0e",
    },
    {
        "filler_variant_id": "l254-mwcnt-v4-ar73",
        "panel": "(c)",
        "label": "Baytubes C150P",
        "alpha": 73,
        "lo": 0.50,
        "hi": 0.625,
        "pc_pub": 0.61,
        "t_pub": 2.00,
        "color": "#2ca02c",
    },
    {
        "filler_variant_id": "l254-mwcnt-v5-ar69",
        "panel": "(d)",
        "label": "Continental Carbon",
        "alpha": 69,
        "lo": 0.375,
        "hi": 0.50,
        "pc_pub": 0.49,
        "t_pub": 1.80,
        "color": "#9467bd",
    },
    {
        "filler_variant_id": "l254-mwcnt-v3-ar55",
        "panel": "(e)",
        "label": "Hyperion MB (15 wt.%)",
        "alpha": 55,
        "lo": 0.375,
        "hi": 0.50,
        "pc_pub": 0.50,
        "t_pub": 1.70,
        "color": "#d62728",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generates Figure B (Computational Materials Science Q1 style): "
            "RMSE_log10(pc) error-well landscapes, critical exponent t(pc) profiles, "
            "5% RMSE identifiability bands, and 3D physical exponent regularization (1.3 <= t <= 2.3)."
        )
    )
    parser.add_argument("--root", default=".", help="Project root directory.")
    parser.add_argument(
        "--dataset",
        default="analysis/phase3_exploratory_l254_v2_2/tables/exploratory_dataset.csv",
        help="Path to exploratory_dataset.csv relative to --root.",
    )
    parser.add_argument(
        "--out-dir",
        default="analysis/phase6_final_scientific_report_v1/figures",
        help="Output directory for PNG and PDF figures relative to --root.",
    )
    parser.add_argument(
        "--table-out",
        default="analysis/phase6_final_scientific_report_v1/tables/figB_profile_identifiability_summary.csv",
        help="Output path for the numerical profile summary CSV relative to --root.",
    )
    parser.add_argument(
        "--grid-size",
        type=int,
        default=50001,
        help="Number of candidate pc grid points per variant (default: 50001).",
    )
    parser.add_argument("--dpi", type=int, default=300, help="Output PNG resolution in DPI (default: 300).")
    return parser.parse_args()


def compute_profile(
    p: np.ndarray,
    sigma: np.ndarray,
    lo: float,
    hi: float,
    grid_size: int,
    t_min_phys: float = 1.3,
    t_max_phys: float = 2.3,
) -> dict[str, np.ndarray | float | int]:
    """Compute vectorized log-space OLS percolation profile over candidate pc grid (NumPy only)."""
    m_use = (p > lo + 1e-12) & (sigma > 0.0)
    p_c = p[m_use]
    y_c = np.log10(sigma[m_use])
    n_fit = int(len(p_c))
    if n_fit < 3:
        raise ValueError(f"Insufficient conducting points (N={n_fit}) in bracket ({lo}, {hi}).")

    hi_eff = min(hi, float(p_c.min()))
    pc_grid = np.linspace(lo + 1e-8, hi_eff - 1e-8, grid_size, dtype=float)

    t_arr = np.empty(grid_size, dtype=float)
    B_arr = np.empty(grid_size, dtype=float)
    rmse_arr = np.empty(grid_size, dtype=float)

    y_mean = float(y_c.mean())
    yc_centered = y_c - y_mean
    chunk = 5000
    for start in range(0, grid_size, chunk):
        end = min(start + chunk, grid_size)
        pcs = pc_grid[start:end, None]
        x = np.log10(p_c[None, :] - pcs)
        x_mean = x.mean(axis=1, keepdims=True)
        xc = x - x_mean
        denom = np.sum(xc * xc, axis=1)
        slope = np.sum(xc * yc_centered[None, :], axis=1) / denom
        intercept = y_mean - slope * x_mean[:, 0]
        pred = intercept[:, None] + slope[:, None] * x
        res = y_c[None, :] - pred
        rmse = np.sqrt(np.mean(res * res, axis=1))

        t_arr[start:end] = slope
        B_arr[start:end] = np.power(10.0, intercept)
        rmse_arr[start:end] = rmse

    valid = np.isfinite(rmse_arr) & (t_arr > 0.0)
    pc_v = pc_grid[valid]
    t_v = t_arr[valid]
    B_v = B_arr[valid]
    rmse_v = rmse_arr[valid]

    idx_opt = int(np.argmin(rmse_v))
    rmse_min = float(rmse_v[idx_opt])
    m5 = rmse_v <= rmse_min * 1.05
    m10 = rmse_v <= rmse_min * 1.10

    m_phys = (t_v >= t_min_phys) & (t_v <= t_max_phys)
    if np.any(m_phys):
        phys_indices = np.where(m_phys)[0]
        idx_phys = int(phys_indices[int(np.argmin(rmse_v[m_phys]))])
    else:
        idx_phys = idx_opt

    return {
        "n_fit": n_fit,
        "pc_grid": pc_v,
        "t_grid": t_v,
        "B_grid": B_v,
        "rmse_grid": rmse_v,
        "opt_pc": float(pc_v[idx_opt]),
        "opt_t": float(t_v[idx_opt]),
        "opt_B": float(B_v[idx_opt]),
        "opt_rmse": rmse_min,
        "band5_lo": float(pc_v[m5].min()),
        "band5_hi": float(pc_v[m5].max()),
        "band10_lo": float(pc_v[m10].min()),
        "band10_hi": float(pc_v[m10].max()),
        "phys_pc": float(pc_v[idx_phys]),
        "phys_t": float(t_v[idx_phys]),
        "phys_B": float(B_v[idx_phys]),
        "phys_rmse": float(rmse_v[idx_phys]),
    }


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    dataset_path = (root / args.dataset).resolve()
    out_dir = (root / args.out_dir).resolve()
    table_out = (root / args.table_out).resolve()

    if not dataset_path.is_file():
        raise FileNotFoundError(f"Required dataset not found: {dataset_path}")

    exp_df = pd.read_csv(dataset_path, keep_default_na=False)
    complete_mask = exp_df["complete_mass_pair"].astype(str).str.lower().eq("true")

    profiles = []
    summary_rows = []
    for meta in VARIANTS:
        vid = meta["filler_variant_id"]
        sub = exp_df[(exp_df["filler_variant_id"] == vid) & complete_mask].copy()
        p_arr = pd.to_numeric(sub["mass_percent"], errors="coerce").to_numpy(dtype=float)
        s_arr = pd.to_numeric(sub["conductivity_s_per_cm"], errors="coerce").to_numpy(dtype=float)
        prof = compute_profile(p_arr, s_arr, meta["lo"], meta["hi"], args.grid_size)
        profiles.append((meta, prof))

        summary_rows.append(
            {
                "filler_variant_id": vid,
                "commercial_name": meta["label"],
                "aspect_ratio_alpha": meta["alpha"],
                "n_conducting_points": prof["n_fit"],
                "bracket_lo_wt": meta["lo"],
                "bracket_hi_wt": meta["hi"],
                "published_pc_wt": meta["pc_pub"],
                "opt_pc_wt": prof["opt_pc"],
                "opt_t": prof["opt_t"],
                "opt_rmse_log10": prof["opt_rmse"],
                "band_5pct_lo_wt": prof["band5_lo"],
                "band_5pct_hi_wt": prof["band5_hi"],
                "band_5pct_width_wt": prof["band5_hi"] - prof["band5_lo"],
                "band_10pct_width_wt": prof["band10_hi"] - prof["band10_lo"],
                "phys_pc_wt": prof["phys_pc"],
                "phys_t": prof["phys_t"],
                "phys_rmse_log10": prof["phys_rmse"],
                "phys_constraint_active": bool(abs(prof["phys_pc"] - prof["opt_pc"]) > 1e-4),
            }
        )

    summary_df = pd.DataFrame(summary_rows)

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 8.8,
            "axes.titlesize": 9.6,
            "axes.labelsize": 8.8,
            "xtick.labelsize": 8.0,
            "ytick.labelsize": 8.0,
            "legend.fontsize": 7.0,
            "axes.linewidth": 0.9,
        }
    )

    fig, axes = plt.subplots(2, 3, figsize=(15.4, 8.4))
    axes_flat = axes.ravel()

    legend_locs = {
        "l254-mwcnt-v1-ar134": "upper center",
        "l254-mwcnt-v2-ar94": "upper right",
        "l254-mwcnt-v4-ar73": "lower left",
        "l254-mwcnt-v5-ar69": "lower left",
        "l254-mwcnt-v3-ar55": "upper left",
    }

    for idx, (meta, prof) in enumerate(profiles):
        ax = axes_flat[idx]
        vid = meta["filler_variant_id"]
        pc_g = prof["pc_grid"]
        rmse_g = prof["rmse_grid"]
        t_g = prof["t_grid"]

        step = max(1, len(pc_g) // 2500)
        pc_p = pc_g[::step]
        rmse_p = rmse_g[::step]
        t_p = t_g[::step]

        ax.axvspan(
            prof["band5_lo"],
            prof["band5_hi"],
            color="#4C9BE8",
            alpha=0.18,
            label="5% RMSE band",
        )

        ax.plot(pc_p, rmse_p, color="#1B365D", lw=2.0, label=r"$\mathrm{RMSE}_{\log_{10}}(p_c)$")
        ax.set_xlabel(r"Candidate Threshold $p_c$ (wt.%)")
        ax.set_ylabel(r"$\mathrm{RMSE}_{\log_{10}(\sigma)}$ (decades)", color="#1B365D")
        ax.tick_params(axis="y", labelcolor="#1B365D")
        ax.grid(True, linestyle="--", alpha=0.28)

        ax.axvline(
            meta["pc_pub"],
            color="black",
            linestyle=":",
            lw=1.4,
            label=f"Published $p_c$ ({meta['pc_pub']:.2f})",
        )

        ax.scatter(
            [prof["opt_pc"]],
            [prof["opt_rmse"]],
            color="#2ca02c",
            edgecolor="black",
            s=54,
            zorder=5,
            label=f"Unconstr. ({prof['opt_pc']:.3f}, t={prof['opt_t']:.2f})",
        )

        if abs(prof["phys_pc"] - prof["opt_pc"]) > 1e-4:
            ax.scatter(
                [prof["phys_pc"]],
                [prof["phys_rmse"]],
                color="#d62728",
                marker="^",
                edgecolor="black",
                s=70,
                zorder=6,
                label=f"Constrained ({prof['phys_pc']:.3f}, t={prof['phys_t']:.2f})",
            )

        ax_r = ax.twinx()
        ax_r.axhspan(1.3, 2.3, color="#2ca02c", alpha=0.11, label="3D physical band (1.3 <= t <= 2.3)")
        ax_r.plot(pc_p, t_p, color="#C0392B", linestyle="--", lw=1.6, alpha=0.90, label=r"Exponent $t(p_c)$")
        ax_r.set_ylabel(r"Critical Exponent $t(p_c)$ [-]", color="#C0392B")
        ax_r.tick_params(axis="y", labelcolor="#C0392B")

        rmse_cap = min(float(np.percentile(rmse_g, 96)) * 1.12, max(float(prof["phys_rmse"]) * 1.35, 0.75))
        if vid == "l254-mwcnt-v3-ar55":
            ax.set_ylim(0.0, 1.50)
            ax_r.set_ylim(0.8, 5.6)
            ax.annotate(
                "0-dof boundary\ncollapse (t = 4.85)",
                xy=(prof["opt_pc"], prof["opt_rmse"]),
                xytext=(0.402, 0.34),
                arrowprops=dict(arrowstyle="->", color="#1E6B2E", lw=1.2),
                fontsize=7.3,
                fontweight="bold",
                color="#1E6B2E",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#1E6B2E", alpha=0.88),
            )
            ax.annotate(
                "3D bound rescue\n(pc = 0.495 wt.%)",
                xy=(prof["phys_pc"], prof["phys_rmse"]),
                xytext=(0.448, 1.25),
                arrowprops=dict(arrowstyle="->", color="#A93226", lw=1.2),
                fontsize=7.1,
                fontweight="bold",
                color="#A93226",
                zorder=8,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#A93226", alpha=0.92),
            )
        else:
            ax.set_ylim(0.0, max(rmse_cap, 0.35))
            ax_r.set_ylim(0.8, min(3.2, float(np.percentile(t_g, 97)) * 1.15))

        pad = 0.04 * (meta["hi"] - meta["lo"])
        ax.set_xlim(meta["lo"] - pad, meta["hi"] + pad)
        ax.set_title(
            f"{meta['panel']} {meta['label']} ($\\alpha={meta['alpha']}$, $N_{{fit}}={prof['n_fit']}$)",
            fontweight="bold",
        )

        h1, lab1 = ax.get_legend_handles_labels()
        h2, lab2 = ax_r.get_legend_handles_labels()
        leg_fs = 6.5 if vid == "l254-mwcnt-v3-ar55" else 7.0
        ax.legend(
            h1 + h2,
            lab1 + lab2,
            loc=legend_locs[vid],
            fontsize=leg_fs,
            framealpha=0.93,
            borderpad=0.30,
            handlelength=1.6,
        )

    # Panel (f): Normalized Error-Well Sharpness Comparison across the 4 Identifiable Direct-Powder Series
    ax_f = axes_flat[5]
    for meta, prof in profiles[:4]:
        pc_g = prof["pc_grid"]
        rmse_rel = prof["rmse_grid"] / prof["opt_rmse"]
        delta_pc = pc_g - prof["opt_pc"]
        mask_win = (delta_pc >= -0.025) & (delta_pc <= 0.025) & (rmse_rel <= 2.2)
        d_sub = delta_pc[mask_win]
        r_sub = rmse_rel[mask_win]
        step_f = max(1, len(d_sub) // 1000)
        width_5 = prof["band5_hi"] - prof["band5_lo"]
        ax_f.plot(
            d_sub[::step_f],
            r_sub[::step_f],
            color=meta["color"],
            lw=2.1,
            label=f"{meta['label'].split()[0]} ($\\Delta p_c^{{5\\%}}={width_5:.4f}$ wt.%)",
        )

    ax_f.axhline(1.05, color="#1B365D", linestyle="--", lw=1.2, label="+5% RMSE tolerance (1.05x)")
    ax_f.axhline(1.10, color="#7f7f7f", linestyle=":", lw=1.2, label="+10% RMSE tolerance (1.10x)")
    ax_f.axvline(0.0, color="black", linestyle="-", lw=0.8, alpha=0.45)
    ax_f.set_xlim(-0.022, 0.022)
    ax_f.set_ylim(0.98, 1.55)
    ax_f.set_xlabel(r"Threshold Shift $p_c - p_{c,\mathrm{opt}}$ (wt.%)")
    ax_f.set_ylabel(r"Normalized Error $\mathrm{RMSE}(p_c) / \mathrm{RMSE}_{\min}$ [-]")
    ax_f.set_title("(f) Error-Well Sharpness (4 Identifiable Direct Series)", fontweight="bold")
    ax_f.grid(True, linestyle="--", alpha=0.28)
    ax_f.legend(loc="upper center", framealpha=0.93, fontsize=7.3)

    fig.suptitle(
        "Percolation Threshold Identifiability Landscapes and 3D Physical Exponent Regularization (l254-castillo-2011)",
        fontsize=12.0,
        fontweight="bold",
        y=0.985,
    )
    fig.tight_layout(rect=[0.0, 0.0, 1.0, 0.96])

    out_dir.mkdir(parents=True, exist_ok=True)
    table_out.parent.mkdir(parents=True, exist_ok=True)

    png_path = out_dir / "figB_rmse_identifiability_profiles.png"
    pdf_path = out_dir / "figB_rmse_identifiability_profiles.pdf"
    fig.savefig(png_path, dpi=args.dpi)
    fig.savefig(pdf_path)
    plt.close(fig)

    summary_df.to_csv(table_out, index=False, encoding="utf-8-sig")

    print("FIGURE B GENERATED SUCCESSFULLY (COMPUTATIONAL MATERIALS SCIENCE STYLE)")
    print(f"PNG (300 DPI): {png_path}")
    print(f"PDF (Vector):  {pdf_path}")
    print(f"Summary CSV:   {table_out}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)
