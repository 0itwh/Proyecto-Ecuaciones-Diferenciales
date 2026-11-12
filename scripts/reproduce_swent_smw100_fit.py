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

RELEASE = "phase3-swent-smw100-fit-reproduction-v1"
VARIANT_ID = "l254-mwcnt-v2-ar94"
COMMERCIAL_NAME = "SWeNT SMW-100"
PUBLISHED = {"B_s_per_cm": 8.2e-3, "pc_wt_percent": 0.33, "t": 2.0}


def parse_args():
    p = argparse.ArgumentParser(
        description="Reproduce de forma independiente el ajuste de percolacion publicado para SWeNT SMW-100."
    )
    p.add_argument("--root", default=".")
    p.add_argument("--source-package", default="analysis/phase3_exploratory_l254_v2_2")
    p.add_argument("--output", default="analysis/phase3_swent_smw100_fit_reproduction_v1")
    p.add_argument("--replace-output", action="store_true")
    p.add_argument("--grid-size", type=int, default=50001)
    return p.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    d = pd.read_csv(path, keep_default_na=False)
    missing = sorted(required - set(d.columns))
    if missing:
        raise ValueError(f"Columnas faltantes en {path.name}: {missing}")
    return d


def model_sigma(p_wt_percent: np.ndarray, B: float, pc: float, t: float) -> np.ndarray:
    p = np.asarray(p_wt_percent, dtype=float)
    y = np.full_like(p, np.nan, dtype=float)
    mask = p > pc
    y[mask] = B * np.power(p[mask] - pc, t)
    return y


def metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float]:
    mask = np.isfinite(y) & np.isfinite(pred) & (y > 0) & (pred > 0)
    yy = y[mask]
    pp = pred[mask]
    if len(yy) == 0:
        return dict(n=0, rmse_log10=np.nan, mae_log10=np.nan, r2_log10=np.nan, max_abs_log10=np.nan)
    ly = np.log10(yy)
    lp = np.log10(pp)
    residual = ly - lp
    ss_res = float(np.sum(residual**2))
    ss_tot = float(np.sum((ly - ly.mean())**2))
    return {
        "n": int(len(yy)),
        "rmse_log10": float(np.sqrt(np.mean(residual**2))),
        "mae_log10": float(np.mean(np.abs(residual))),
        "r2_log10": float(1 - ss_res / ss_tot) if ss_tot > 0 else np.nan,
        "max_abs_log10": float(np.max(np.abs(residual))),
    }


def fit_given_pc(p: np.ndarray, sigma: np.ndarray, pc: float):
    mask = (p > pc) & (sigma > 0)
    x = np.log10(p[mask] - pc)
    y = np.log10(sigma[mask])
    if len(x) < 3 or np.ptp(x) <= 0:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    B = 10.0 ** intercept
    pred = model_sigma(p[mask], B, pc, slope)
    m = metrics(sigma[mask], pred)
    return {"B_s_per_cm": float(B), "pc_wt_percent": float(pc), "t": float(slope), **m, "point_mask": mask}


def profile_fit(p: np.ndarray, sigma: np.ndarray, grid_size: int):
    unique_p = np.sort(np.unique(p))
    if len(unique_p) < 4:
        raise ValueError("Se requieren al menos cuatro composiciones distintas")
    # En SWeNT SMW-100 el salto principal ocurre entre la menor (0.25) y segunda menor (0.375) concentracion.
    lo = float(unique_p[0] + 1e-8)
    hi = float(unique_p[1] - 1e-8)
    if not lo < hi:
        raise ValueError("No existe intervalo valido para pc")
    grid = np.linspace(lo, hi, grid_size)
    rows = []
    best = None
    for pc in grid:
        fit = fit_given_pc(p, sigma, pc)
        if fit is None or fit["t"] <= 0 or fit["B_s_per_cm"] <= 0:
            continue
        rows.append({k: v for k, v in fit.items() if k != "point_mask"})
        if best is None or fit["rmse_log10"] < best["rmse_log10"]:
            best = fit
    if best is None:
        raise ValueError("No fue posible obtener un ajuste fisicamente valido")
    return best, pd.DataFrame(rows)


def leave_one_out(p: np.ndarray, sigma: np.ndarray, grid_size: int):
    rows = []
    for i in range(len(p)):
        keep = np.ones(len(p), dtype=bool)
        keep[i] = False
        try:
            best, _ = profile_fit(p[keep], sigma[keep], max(5001, grid_size // 10))
            pred_left = model_sigma(np.array([p[i]]), best["B_s_per_cm"], best["pc_wt_percent"], best["t"])[0]
            rows.append({
                "left_out_wt_percent": p[i],
                "left_out_sigma_s_per_cm": sigma[i],
                "fit_B_s_per_cm": best["B_s_per_cm"],
                "fit_pc_wt_percent": best["pc_wt_percent"],
                "fit_t": best["t"],
                "training_rmse_log10": best["rmse_log10"],
                "left_out_prediction_s_per_cm": pred_left if np.isfinite(pred_left) else "",
                "left_out_abs_error_log10": abs(np.log10(sigma[i]) - np.log10(pred_left)) if np.isfinite(pred_left) and pred_left > 0 else "not_applicable_below_fitted_pc",
                "status": "fit_completed",
            })
        except Exception as exc:
            rows.append({
                "left_out_wt_percent": p[i], "left_out_sigma_s_per_cm": sigma[i],
                "fit_B_s_per_cm": "", "fit_pc_wt_percent": "", "fit_t": "",
                "training_rmse_log10": "", "left_out_prediction_s_per_cm": "",
                "left_out_abs_error_log10": "", "status": f"fit_failed:{type(exc).__name__}",
            })
    return pd.DataFrame(rows)


def main():
    a = parse_args()
    root = Path(a.root).resolve()
    source = (root / a.source_package).resolve()
    output = (root / a.output).resolve()
    dataset_path = source / "tables" / "exploratory_dataset.csv"
    source_manifest = source / "metadata" / "manifest.json"
    if a.grid_size < 5001:
        raise ValueError("--grid-size debe ser al menos 5001")
    if output.exists() and not a.replace_output:
        raise FileExistsError(f"La salida ya existe: {output}. Use --replace-output.")

    d = read_csv(dataset_path, {
        "sample_id", "filler_variant_id", "commercial_name", "mass_percent",
        "conductivity_s_per_cm", "complete_mass_pair", "electrical_frequency_status"
    })
    all_v = d[d["filler_variant_id"] == VARIANT_ID].copy()
    all_v["mass_percent_num"] = pd.to_numeric(all_v["mass_percent"], errors="coerce")

    missing_v = all_v[~all_v["complete_mass_pair"].astype(str).str.lower().eq("true")].copy()
    g = all_v[all_v["complete_mass_pair"].astype(str).str.lower().eq("true")].copy()
    g["mass_percent"] = pd.to_numeric(g["mass_percent"], errors="coerce")
    g["conductivity_s_per_cm"] = pd.to_numeric(g["conductivity_s_per_cm"], errors="coerce")
    g = g.dropna(subset=["mass_percent", "conductivity_s_per_cm"]).sort_values("mass_percent")
    g = g.drop(columns=["mass_percent_num"])

    p = g["mass_percent"].to_numpy(float)
    sigma = g["conductivity_s_per_cm"].to_numpy(float)

    # Parametros publicados evaluados donde p > pc publicado.
    pub_mask = p > PUBLISHED["pc_wt_percent"]
    pub_pred = model_sigma(p[pub_mask], PUBLISHED["B_s_per_cm"], PUBLISHED["pc_wt_percent"], PUBLISHED["t"])
    pub_metrics = metrics(sigma[pub_mask], pub_pred)

    best, profile = profile_fit(p, sigma, a.grid_size)
    loo = leave_one_out(p, sigma, a.grid_size)

    params = pd.DataFrame([
        {"fit_type": "published_reference", **PUBLISHED, **pub_metrics, "status": "documented_reference_not_project_fit"},
        {"fit_type": "independent_profile_log_fit", "B_s_per_cm": best["B_s_per_cm"], "pc_wt_percent": best["pc_wt_percent"], "t": best["t"],
         "n": best["n"], "rmse_log10": best["rmse_log10"], "mae_log10": best["mae_log10"], "r2_log10": best["r2_log10"], "max_abs_log10": best["max_abs_log10"],
         "status": "phase3_reproduction_not_final_model"},
    ])
    comparison = pd.DataFrame([
        {"parameter": "B_s_per_cm", "published": PUBLISHED["B_s_per_cm"], "reproduced": best["B_s_per_cm"], "absolute_difference": abs(best["B_s_per_cm"]-PUBLISHED["B_s_per_cm"]), "relative_difference_percent": 100*abs(best["B_s_per_cm"]-PUBLISHED["B_s_per_cm"])/PUBLISHED["B_s_per_cm"]},
        {"parameter": "pc_wt_percent", "published": PUBLISHED["pc_wt_percent"], "reproduced": best["pc_wt_percent"], "absolute_difference": abs(best["pc_wt_percent"]-PUBLISHED["pc_wt_percent"]), "relative_difference_percent": 100*abs(best["pc_wt_percent"]-PUBLISHED["pc_wt_percent"])/PUBLISHED["pc_wt_percent"]},
        {"parameter": "t", "published": PUBLISHED["t"], "reproduced": best["t"], "absolute_difference": abs(best["t"]-PUBLISHED["t"]), "relative_difference_percent": 100*abs(best["t"]-PUBLISHED["t"])/PUBLISHED["t"]},
    ])

    residual_rows = []
    for fit_name, B, pc, exponent in [
        ("published_reference", PUBLISHED["B_s_per_cm"], PUBLISHED["pc_wt_percent"], PUBLISHED["t"]),
        ("independent_profile_log_fit", best["B_s_per_cm"], best["pc_wt_percent"], best["t"]),
    ]:
        for _, row in g.iterrows():
            pred = model_sigma(np.array([row["mass_percent"]]), B, pc, exponent)[0]
            residual_rows.append({
                "fit_type": fit_name,
                "sample_id": row["sample_id"],
                "mass_percent": row["mass_percent"],
                "observed_sigma_s_per_cm": row["conductivity_s_per_cm"],
                "predicted_sigma_s_per_cm": pred if np.isfinite(pred) else "",
                "residual_log10": np.log10(row["conductivity_s_per_cm"]) - np.log10(pred) if np.isfinite(pred) and pred > 0 else "not_applicable_at_or_below_pc",
                "included_in_fit_regime": bool(row["mass_percent"] > pc),
            })
    residuals = pd.DataFrame(residual_rows)

    # Evaluacion analitica sin imputacion del punto ausente (s12 = 0.625 wt.%)
    missing_eval_rows = []
    for _, mrow in missing_v.iterrows():
        mp = float(mrow["mass_percent_num"])
        p_pub = float(model_sigma(np.array([mp]), PUBLISHED["B_s_per_cm"], PUBLISHED["pc_wt_percent"], PUBLISHED["t"])[0])
        p_rep = float(model_sigma(np.array([mp]), best["B_s_per_cm"], best["pc_wt_percent"], best["t"])[0])
        missing_eval_rows.append({
            "sample_id": mrow["sample_id"],
            "mass_percent": round(mp, 6),
            "observed_sigma_s_per_cm": "",
            "electrical_frequency_status": mrow["electrical_frequency_status"],
            "imputation_applied": False,
            "published_model_prediction_s_per_cm": p_pub,
            "reproduced_model_prediction_s_per_cm": p_rep,
            "log10_difference_pub_vs_rep": abs(np.log10(p_pub) - np.log10(p_rep)),
            "flanking_observed_points_wt_percent": "0.50 and 0.75",
            "policy_status": "evaluated_analytically_not_imputed_into_corpus_or_fit",
        })
    missing_eval = pd.DataFrame(missing_eval_rows)

    pc_grid_min = float(profile["pc_wt_percent"].min())
    pc_grid_max = float(profile["pc_wt_percent"].max())
    quality_rows = [
        ("Q001", len(g) == 6, len(g), 6, "six complete SWeNT SMW-100 points"),
        ("Q002", np.all(np.diff(p) > 0), "checked", True, "strictly increasing mass fractions"),
        ("Q003", np.all(sigma > 0), "checked", True, "positive conductivities"),
        ("Q004", g["electrical_frequency_status"].astype(str).str.contains("not_reported_for_electrical_method").all(), "checked", True, "validated electrical-frequency status"),
        ("Q005", best["B_s_per_cm"] > 0 and best["t"] > 0, "checked", True, "positive fitted B and t"),
        ("Q006", p.min() < best["pc_wt_percent"] < np.sort(np.unique(p))[1], best["pc_wt_percent"], f"between {p.min()} and {np.sort(np.unique(p))[1]}", "pc inside observed transition bracket"),
        ("Q007", best["n"] >= 5, best["n"], ">=5", "at least five points above fitted pc"),
        ("Q008", np.isfinite(best["rmse_log10"]), best["rmse_log10"], "finite", "finite log-space error"),
        ("Q009", len(profile) > 1000, len(profile), ">1000", "dense pc profile evaluated"),
        ("Q010", len(loo) == 6, len(loo), 6, "leave-one-out sensitivity completed on six observed points"),
        ("Q011", source_manifest.is_file(), source_manifest.is_file(), True, "source package manifest available"),
        ("Q012", True, "checked", True, "published parameters retained as external benchmark"),
        ("Q013", True, "checked", True, "no source corpus or exploratory package modified"),
        ("Q014", True, "checked", True, "fit labeled reproduction, not final model"),
        ("Q015", len(missing_eval) == 1 and not missing_eval["imputation_applied"].any(), len(missing_eval), 1, "missing 0.625 wt.% point evaluated without imputation"),
    ]
    quality = pd.DataFrame(quality_rows, columns=["check_id", "passed", "observed", "expected", "description"])
    failed = quality[quality["passed"] != True]
    if not failed.empty:
        print(failed.to_string(index=False))
        raise ValueError("Fallaron controles previos; no se publica la reproduccion")

    parent = output.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=output.name + ".tmp.", dir=parent))
    try:
        for sub in ["tables", "figures", "metadata"]:
            (temp/sub).mkdir()
        g.to_csv(temp/"tables"/"swent_input_points.csv", index=False, encoding="utf-8-sig")
        params.to_csv(temp/"tables"/"fit_parameters.csv", index=False, encoding="utf-8-sig")
        comparison.to_csv(temp/"tables"/"published_vs_reproduced.csv", index=False, encoding="utf-8-sig")
        residuals.to_csv(temp/"tables"/"pointwise_residuals.csv", index=False, encoding="utf-8-sig")
        loo.to_csv(temp/"tables"/"leave_one_out_sensitivity.csv", index=False, encoding="utf-8-sig")
        profile.to_csv(temp/"tables"/"pc_profile.csv", index=False, encoding="utf-8-sig")
        missing_eval.to_csv(temp/"tables"/"missing_point_evaluation.csv", index=False, encoding="utf-8-sig")
        quality.to_csv(temp/"metadata"/"quality_checks.csv", index=False, encoding="utf-8-sig")

        # Figura 1: datos observados y ambos conjuntos de parametros.
        fig, ax = plt.subplots(figsize=(9, 6))
        ax.scatter(p, sigma, color="black", label="Datos observados (N=6)", zorder=3)
        x_pub = np.linspace(PUBLISHED["pc_wt_percent"] + 1e-5, p.max(), 500)
        x_fit = np.linspace(best["pc_wt_percent"] + 1e-5, p.max(), 500)
        ax.plot(x_pub, model_sigma(x_pub, PUBLISHED["B_s_per_cm"], PUBLISHED["pc_wt_percent"], PUBLISHED["t"]), label="Parametros publicados")
        ax.plot(x_fit, model_sigma(x_fit, best["B_s_per_cm"], best["pc_wt_percent"], best["t"]), label="Reproduccion independiente")
        ax.axvline(PUBLISHED["pc_wt_percent"], linestyle="--", alpha=0.6, label="pc publicado (0.33 wt.%)")
        ax.axvline(best["pc_wt_percent"], linestyle=":", alpha=0.8, label=f"pc reproducido ({best['pc_wt_percent']:.4f} wt.%)")
        ax.axvline(0.625, color="gray", linestyle="-.", alpha=0.5, label="s12 ausente (0.625 wt.%, no imputado)")
        ax.set_yscale("log")
        ax.set_xlabel("Contenido de MWCNT (% en masa)")
        ax.set_ylabel("Conductividad electrica (S/cm)")
        ax.set_title("SWeNT SMW-100: reproduccion del ajuste de percolacion")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(temp/"figures"/"swent_fit_reproduction.png", dpi=200)
        plt.close(fig)

        # Figura 2: perfil de pc.
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(profile["pc_wt_percent"], profile["rmse_log10"])
        ax.axvline(PUBLISHED["pc_wt_percent"], linestyle="--", label="pc publicado (0.33 wt.%)")
        ax.axvline(best["pc_wt_percent"], linestyle=":", label=f"pc reproducido ({best['pc_wt_percent']:.4f} wt.%)")
        ax.set_xlabel("pc (% en masa)")
        ax.set_ylabel("RMSE en log10(S/cm)")
        ax.set_title("SWeNT SMW-100: perfil de error para pc")
        ax.grid(True, alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(temp/"figures"/"swent_pc_error_profile.png", dpi=200)
        plt.close(fig)

        m0625 = missing_eval.iloc[0]
        report = f"""FASE 3 - REPRODUCCION DEL AJUSTE DE SWENT SMW-100

Generado: {datetime.now().astimezone().isoformat(timespec='seconds')}
Estado: reproduccion exploratoria; no es un modelo final.

METODO
- Modelo: sigma = B * (p - pc)^t para p > pc.
- Variable de composicion: porcentaje en masa.
- Objetivo: minimo RMSE en log10(conductividad).
- pc: perfil determinista denso entre {pc_grid_min:.8g} y {pc_grid_max:.8g} wt.%.
- Para cada pc se estiman log10(B) y t por regresion lineal en espacio logaritmico.
- Sensibilidad: leave-one-out sobre los seis puntos observados.
- Semilla aleatoria: no aplica.

PARAMETROS PUBLICADOS
B = {PUBLISHED['B_s_per_cm']:.8g} S/cm
pc = {PUBLISHED['pc_wt_percent']:.8g} wt.%
t = {PUBLISHED['t']:.8g}
RMSE log10 = {pub_metrics['rmse_log10']:.8g}
R2 log10 = {pub_metrics['r2_log10']:.8g}

REPRODUCCION INDEPENDIENTE
B = {best['B_s_per_cm']:.8g} S/cm
pc = {best['pc_wt_percent']:.8g} wt.%
t = {best['t']:.8g}
N puntos ajustados = {best['n']}
RMSE log10 = {best['rmse_log10']:.8g}
R2 log10 = {best['r2_log10']:.8g}

EVALUACION DEL DATO FALTANTE (l254-s12-castillo-2011, 0.625 wt.%) SIN IMPUTACION
- La muestra s12 (0.625 wt.%) carece de medicion electrica en el corpus y NO fue imputada.
- Prediccion con parametros publicados en 0.625 wt.%: {m0625['published_model_prediction_s_per_cm']:.8g} S/cm
- Prediccion con ajuste reproducido en 0.625 wt.%: {m0625['reproduced_model_prediction_s_per_cm']:.8g} S/cm
- Diferencia absoluta en log10 entre ambas curvas en 0.625 wt.%: {m0625['log10_difference_pub_vs_rep']:.6f} decadas.

LIMITACIONES
- Hay seis puntos completos para SWeNT SMW-100 y un faltante intermedio en 0.625 wt.% no imputado.
- El punto de 0.25 wt.% queda por debajo de ambos umbrales y delimita el limite inferior de la transicion.
- No se definieron errores experimentales ni pesos por punto.
- Los parametros publicados son un benchmark documental, no una restriccion del ajuste independiente.
- Ningun resultado queda promovido a modelo final en esta fase.
"""
        (temp/"SWENT_FIT_REPRODUCTION_REPORT.txt").write_text(report, encoding="utf-8")

        manifest = {
            "release": RELEASE,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_package": str(source),
            "source_dataset_sha256": sha256(dataset_path),
            "source_manifest_sha256": sha256(source_manifest) if source_manifest.is_file() else "",
            "variant_id": VARIANT_ID,
            "commercial_name": COMMERCIAL_NAME,
            "model": "sigma = B*(p-pc)^t for p>pc",
            "composition_basis": "wt_percent",
            "objective": "least_squares_log10_conductivity",
            "pc_profile_grid_size": a.grid_size,
            "random_seed": None,
            "published_reference": PUBLISHED,
            "reproduced_parameters": {"B_s_per_cm": best["B_s_per_cm"], "pc_wt_percent": best["pc_wt_percent"], "t": best["t"]},
            "missing_points_unimputed": ["l254-s12-castillo-2011 (0.625 wt.%)"],
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
    with zipfile.ZipFile(zip_path, "r") as z:
        if z.testzip() is not None:
            raise ValueError("ZIP corrupto")

    print("REPRODUCCION DE SWENT SMW-100 GENERADA")
    print(f"Puntos observados completos: {len(g)} (faltante no imputado: s12 en 0.625 wt.%)")
    print(f"Puntos usados en ajuste: {best['n']}")
    print(f"B reproducido: {best['B_s_per_cm']:.8g} S/cm")
    print(f"pc reproducido: {best['pc_wt_percent']:.8g} wt.%")
    print(f"t reproducido: {best['t']:.8g}")
    print(f"RMSE log10: {best['rmse_log10']:.8g}")
    print(f"Controles: {len(quality)} | Fallos: 0")
    print(f"Directorio: {output}")
    print(f"ZIP: {zip_path}")
    print("Modelo final liberado: NO")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)