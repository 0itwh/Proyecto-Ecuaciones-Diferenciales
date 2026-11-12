from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import csv
import hashlib
import json
import math
import shutil
import sys
import tempfile
import zipfile

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RELEASE = "phase3-exploratory-l254-v2.1"
REQUIRED = {
    "samples.csv": {"sample_id", "block_id_inferred", "filler_variant_id"},
    "sample_composition.csv": {"sample_id", "basis", "canonical_value"},
    "electrical_measurements.csv": {"measurement_id", "sample_id", "value_numeric", "canonical_unit"},
    "filler_variants.csv": {"filler_variant_id", "block_id", "aspect_ratio", "commercial_name"},
    "curve_inclusion_status.csv": {"block_id", "filler_variant_id", "complete_pair_count"},
}


def args():
    p = argparse.ArgumentParser(description="Construye el paquete exploratorio de Fase 3 sin ajustar modelos.")
    p.add_argument("--root", default=".")
    p.add_argument("--source", default="data_processed/l254_corpus_article_validated")
    p.add_argument("--output", default="analysis/phase3_exploratory_l254_v2_1")
    p.add_argument("--replace-output", action="store_true")
    return p.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_table(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    d = pd.read_csv(path, keep_default_na=False)
    missing = sorted(required - set(d.columns))
    if missing:
        raise ValueError(f"Columnas faltantes en {path.name}: {missing}")
    return d


def sign_changes(values: np.ndarray) -> tuple[int, int]:
    if len(values) < 2:
        return 0, 0
    delta = np.diff(values)
    decreases = int((delta < 0).sum())
    non_increases = int((delta <= 0).sum())
    return decreases, non_increases


def largest_log_jump(x: np.ndarray, y: np.ndarray):
    if len(y) < 2 or np.any(y <= 0):
        return "", "", ""
    jumps = np.diff(np.log10(y))
    i = int(np.argmax(np.abs(jumps)))
    return float(x[i]), float(x[i + 1]), float(jumps[i])


def build_long(samples, composition, measurements, fillers):
    comp = composition.pivot_table(index="sample_id", columns="basis", values="canonical_value", aggfunc="first").reset_index()
    comp.columns.name = None
    meas_cols = ["measurement_id", "sample_id", "value_numeric", "canonical_unit"]
    if "frequency_status" in measurements.columns:
        meas_cols.append("frequency_status")
    meas = measurements[meas_cols].copy()
    meas = meas.rename(columns={"value_numeric": "conductivity_s_per_cm", "canonical_unit": "conductivity_unit", "frequency_status": "electrical_frequency_status"})
    out = samples.merge(comp, on="sample_id", how="left").merge(meas, on="sample_id", how="left")
    out = out.merge(fillers[["filler_variant_id", "commercial_name", "aspect_ratio", "density_semantic_status"]], on="filler_variant_id", how="left")
    if "electrical_frequency_status" not in out.columns:
        out["electrical_frequency_status"] = ""
    # Frequency status is meaningful only where an electrical measurement exists.
    has_measurement = out["measurement_id"].astype(str).str.len().gt(0)
    out.loc[has_measurement & out["electrical_frequency_status"].astype(str).str.len().eq(0), "electrical_frequency_status"] = "not_reported_for_electrical_method"
    out.loc[~has_measurement, "electrical_frequency_status"] = "no_electrical_measurement"
    # The article documents 1 Hz for DMA only. This is study-level context, not an electrical condition.
    out["dma_frequency_hz"] = 1.0
    out["dma_frequency_scope"] = "DMA_only_not_electrical_conductivity"
    out["volume_fraction_status"] = "descriptive_within_curve_only"
    out["cross_variant_volume_comparison_status"] = "blocked_density_semantics_not_homogeneous"
    for c in ["mass_fraction", "volume_fraction", "conductivity_s_per_cm", "aspect_ratio"]:
        if c in out:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    out["mass_percent"] = out.get("mass_fraction", np.nan) * 100.0
    out["volume_percent"] = out.get("volume_fraction", np.nan) * 100.0
    for historical_col in ["frequency_status"]:
        if historical_col in out.columns:
            out = out.drop(columns=[historical_col])
    out["log10_conductivity"] = np.where(out["conductivity_s_per_cm"] > 0, np.log10(out["conductivity_s_per_cm"]), np.nan)
    out["complete_mass_pair"] = out["mass_fraction"].notna() & out["conductivity_s_per_cm"].notna()
    out["complete_volume_pair"] = out["volume_fraction"].notna() & out["conductivity_s_per_cm"].notna()
    return out


def curve_summary(long):
    rows = []
    curve_data = long[long["filler_variant_id"].astype(str).ne("")].copy()
    for variant, g in curve_data.groupby("filler_variant_id", sort=False):
        g = g.sort_values("mass_fraction")
        paired = g[g["complete_mass_pair"]].copy()
        y = paired["conductivity_s_per_cm"].to_numpy(float)
        x = paired["mass_percent"].to_numpy(float)
        decreases, non_increases = sign_changes(y)
        x0, x1, jump = largest_log_jump(x, y)
        rows.append({
            "filler_variant_id": variant,
            "commercial_name": g["commercial_name"].iloc[0],
            "aspect_ratio": g["aspect_ratio"].iloc[0],
            "sample_count": len(g),
            "mass_fraction_count": int(g["mass_fraction"].notna().sum()),
            "volume_fraction_count": int(g["volume_fraction"].notna().sum()),
            "conductivity_count": int(g["conductivity_s_per_cm"].notna().sum()),
            "complete_mass_pair_count": int(g["complete_mass_pair"].sum()),
            "complete_volume_pair_count": int(g["complete_volume_pair"].sum()),
            "conductivity_min_s_per_cm": paired["conductivity_s_per_cm"].min() if len(paired) else "",
            "conductivity_max_s_per_cm": paired["conductivity_s_per_cm"].max() if len(paired) else "",
            "conductivity_dynamic_range_decades": float(np.log10(y.max()/y.min())) if len(y) and y.min() > 0 else "",
            "strict_decrease_count": decreases,
            "non_increase_count": non_increases,
            "monotonic_non_decreasing": bool(non_increases == 0),
            "largest_abs_log10_jump_from_wt_percent": x0,
            "largest_abs_log10_jump_to_wt_percent": x1,
            "largest_log10_jump_decades": jump,
            "exploratory_status": "complete_curve" if len(paired) == 7 else "incomplete_curve",
        })
    return pd.DataFrame(rows)


def missingness(long):
    rows = []
    for _, r in long.iterrows():
        missing = []
        if pd.isna(r.get("mass_fraction")): missing.append("mass_fraction")
        if pd.isna(r.get("volume_fraction")): missing.append("volume_fraction")
        if pd.isna(r.get("conductivity_s_per_cm")): missing.append("electrical_conductivity")
        if missing:
            rows.append({
                "sample_id": r["sample_id"],
                "filler_variant_id": r.get("filler_variant_id", ""),
                "commercial_name": r.get("commercial_name", ""),
                "missing_fields": "|".join(missing),
                "exploratory_consequence": "exclude_only_from_analysis_requiring_missing_field",
            })
    return pd.DataFrame(rows)


def plot_curves(long, out_dir):
    fig, ax = plt.subplots(figsize=(9, 6))
    curve_data = long[long["filler_variant_id"].astype(str).ne("")]
    for variant, g in curve_data.groupby("filler_variant_id", sort=False):
        g = g[g["complete_mass_pair"]].sort_values("mass_percent")
        if g.empty: continue
        label = f"{g['commercial_name'].iloc[0]} (AR {int(g['aspect_ratio'].iloc[0])})"
        ax.plot(g["mass_percent"], g["conductivity_s_per_cm"], marker="o", label=label)
    ax.set_yscale("log")
    ax.set_xlabel("Contenido de MWCNT (% en masa)")
    ax.set_ylabel("Conductividad electrica (S/cm)")
    ax.set_title("L254: curvas composicion-conductividad")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out_dir / "conductividad_vs_fraccion_masica_log.png", dpi=200)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 6))
    for variant, g in curve_data.groupby("filler_variant_id", sort=False):
        g = g[g["complete_volume_pair"]].sort_values("volume_percent")
        if g.empty: continue
        label = f"{g['commercial_name'].iloc[0]} (AR {int(g['aspect_ratio'].iloc[0])})"
        ax.plot(g["volume_percent"], g["conductivity_s_per_cm"], marker="o", label=label)
    ax.set_yscale("log")
    ax.set_xlabel("Contenido de MWCNT (% en volumen)")
    ax.set_ylabel("Conductividad electrica (S/cm)")
    ax.set_title("L254: fraccion volumetrica descriptiva dentro de cada curva")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    ax.text(0.01, 0.01, "No comparar entre variantes: semantica de densidad no homogenea", transform=ax.transAxes, fontsize=9, va="bottom")
    fig.tight_layout()
    fig.savefig(out_dir / "conductividad_vs_fraccion_volumetrica_log_descriptiva.png", dpi=200)
    plt.close(fig)


def write_inventory(base):
    rows = []
    inv = base / "sha256_inventory.csv"
    for p in sorted(x for x in base.rglob("*") if x.is_file() and x != inv):
        rows.append({"relative_path": p.relative_to(base).as_posix(), "bytes": p.stat().st_size, "sha256": sha256(p)})
    pd.DataFrame(rows).to_csv(inv, index=False, encoding="utf-8-sig")
    return rows


def main():
    a = args()
    root = Path(a.root).resolve()
    source = (root / a.source).resolve()
    output = (root / a.output).resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    if output.exists() and not a.replace_output:
        raise FileExistsError(f"La salida existe: {output}. Use --replace-output.")

    tables = {name: read_table(source / name, cols) for name, cols in REQUIRED.items()}
    long = build_long(tables["samples.csv"], tables["sample_composition.csv"], tables["electrical_measurements.csv"], tables["filler_variants.csv"])
    summary = curve_summary(long)
    miss = missingness(long)

    checks = [
        ("Q001", len(tables["samples.csv"]) == 36, len(tables["samples.csv"]), 36, "36 samples"),
        ("Q002", len(tables["electrical_measurements.csv"]) == 29, len(tables["electrical_measurements.csv"]), 29, "29 electrical measurements"),
        ("Q003", len(summary) == 5, len(summary), 5, "five independent curves"),
        ("Q004", int(long["complete_mass_pair"].sum()) == 28, int(long["complete_mass_pair"].sum()), 28, "28 complete mass-conductivity pairs"),
        ("Q005", (long.loc[long["conductivity_s_per_cm"].notna(), "conductivity_s_per_cm"] > 0).all(), "checked", True, "positive conductivities"),
        ("Q006", summary["complete_mass_pair_count"].tolist() == [7,6,5,5,5], summary["complete_mass_pair_count"].tolist(), [7,6,5,5,5], "expected curve coverage"),
        ("Q007", not tables["curve_inclusion_status.csv"]["usable_for_final_modeling"].astype(str).str.lower().eq("true").any(), "checked", True, "no final-model release"),
        ("Q008", tables["filler_variants.csv"]["commercial_name"].astype(str).str.len().gt(0).all(), "checked", True, "commercial identities documented"),
        ("Q009", long.loc[long["measurement_id"].astype(str).str.len().gt(0), "electrical_frequency_status"].eq("not_reported_for_electrical_method; 1_Hz_is_DMA_only").all(), int(long.loc[long["measurement_id"].astype(str).str.len().gt(0), "electrical_frequency_status"].eq("not_reported_for_electrical_method; 1_Hz_is_DMA_only").sum()), 29, "all 29 electrical measurements carry the validated frequency status"),
        ("Q009B", long.loc[long["measurement_id"].astype(str).str.len().eq(0), "electrical_frequency_status"].eq("no_electrical_measurement").all(), int(long.loc[long["measurement_id"].astype(str).str.len().eq(0), "electrical_frequency_status"].eq("no_electrical_measurement").sum()), 7, "samples without conductivity are not assigned an electrical frequency status"),
        ("Q010", long["dma_frequency_hz"].eq(1.0).all() and long["dma_frequency_scope"].eq("DMA_only_not_electrical_conductivity").all(), "checked", True, "1 Hz labeled as DMA only"),
        ("Q011", long["cross_variant_volume_comparison_status"].eq("blocked_density_semantics_not_homogeneous").all(), "checked", True, "cross-variant volume comparison blocked"),
        ("Q012", "frequency_status" not in long.columns, "checked", True, "historical ambiguous frequency column removed"),
    ]
    quality = pd.DataFrame(checks, columns=["check_id", "passed", "observed", "expected", "description"])
    failed = quality[quality["passed"] != True]
    if not failed.empty:
        print(failed.to_string(index=False))
        raise ValueError("Fallaron controles previos")

    temp = Path(tempfile.mkdtemp(prefix=output.name + ".tmp.", dir=output.parent if output.parent.exists() else root))
    try:
        (temp / "tables").mkdir(parents=True)
        (temp / "figures").mkdir()
        (temp / "metadata").mkdir()
        long.to_csv(temp / "tables" / "exploratory_dataset.csv", index=False, encoding="utf-8-sig")
        summary.to_csv(temp / "tables" / "curve_summary.csv", index=False, encoding="utf-8-sig")
        miss.to_csv(temp / "tables" / "missingness_by_sample.csv", index=False, encoding="utf-8-sig")
        volume_policy = pd.DataFrame([{
            "variable": "volume_fraction",
            "allowed_use": "descriptive_within_curve_only",
            "blocked_use": "cross_variant_threshold_or_loading_comparison",
            "reason": "MWCNT density semantic status is not homogeneous across variants",
            "evidence_status": "confirmed_from_corpus_metadata_and_article_validation"
        }])
        volume_policy.to_csv(temp / "tables" / "volume_fraction_interpretation_policy.csv", index=False, encoding="utf-8-sig")
        quality.to_csv(temp / "metadata" / "quality_checks.csv", index=False, encoding="utf-8-sig")
        plot_curves(long, temp / "figures")

        report = [
            "FASE 3 - PAQUETE EXPLORATORIO L254", "",
            f"Generado: {datetime.now().astimezone().isoformat(timespec='seconds')}",
            "Alcance: descriptivo; no se ajustaron modelos de percolacion.", "",
            "COBERTURA POR CURVA",
        ]
        for _, r in summary.iterrows():
            report.append(f"- {r['commercial_name']} | AR={int(r['aspect_ratio'])} | pares={r['complete_mass_pair_count']} | disminuciones={r['strict_decrease_count']} | rango={r['conductivity_dynamic_range_decades']} decadas")
        report += ["", "INTERPRETACION PERMITIDA",
                   "- Las figuras muestran tendencias observadas en escala logaritmica.",
                   "- Los saltos mayores son descriptores, no umbrales ajustados.",
                   "- Las curvas incompletas conservan sus faltantes sin imputacion.",
                   "- Los benchmarks publicados no se ajustan ni se presentan como resultados propios.",
                   "- La frecuencia electrica se registra como no reportada; 1 Hz corresponde solo a DMA.",
                   "- La fraccion volumetrica es descriptiva dentro de cada curva y no comparable entre variantes.",
                   "", "SIGUIENTE DECISION",
                   "- Revisar monotonicidad, puntos influyentes y cobertura antes de reproducir los ajustes publicados."]
        (temp / "PHASE3_EXPLORATORY_REPORT.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

        manifest = {
            "release": RELEASE,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_corpus": str(source),
            "source_manifest_sha256": sha256(source / "article_validation_manifest.json") if (source / "article_validation_manifest.json").is_file() else "",
            "counts": {"samples": len(tables["samples.csv"]), "measurements": len(tables["electrical_measurements.csv"]), "curves": len(summary), "complete_pairs": int(long["complete_mass_pair"].sum())},
            "scope": "exploratory_only_no_percolation_fit",
            "electrical_frequency_status": "not_reported_for_electrical_method",
            "dma_frequency_hz": 1.0,
            "dma_frequency_scope": "DMA_only_not_electrical_conductivity",
            "volume_fraction_policy": "descriptive_within_curve_only_cross_variant_comparison_blocked",
            "transformations": ["mass fraction multiplied by 100 for plotting", "volume fraction multiplied by 100 for plotting", "base-10 logarithm used only for descriptive visualization", "historical sample frequency status removed", "1 Hz labeled as DMA-only context", "volume fraction labeled as non-comparable across variants"],
            "random_seed": None,
            "model_fitted": False,
            "quality_passed": True,
        }
        (temp / "metadata" / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        inventory = write_inventory(temp)

        if output.exists(): shutil.rmtree(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        temp.rename(output)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    zip_path = output.parent / f"{output.name}.zip"
    if zip_path.exists(): zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(x for x in output.rglob("*") if x.is_file()):
            z.write(p, arcname=f"{output.name}/{p.relative_to(output).as_posix()}")
    with zipfile.ZipFile(zip_path, "r") as z:
        if z.testzip() is not None: raise ValueError("ZIP corrupto")

    print("PAQUETE EXPLORATORIO DE FASE 3 GENERADO")
    print(f"Muestras: {len(tables['samples.csv'])}")
    print(f"Mediciones: {len(tables['electrical_measurements.csv'])}")
    print(f"Curvas: {len(summary)}")
    print(f"Pares completos: {int(long['complete_mass_pair'].sum())}")
    print(f"Controles: {len(quality)} | Fallos: 0")
    print(f"Directorio: {output}")
    print(f"ZIP: {zip_path}")
    print("Modelos ajustados: NO")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
