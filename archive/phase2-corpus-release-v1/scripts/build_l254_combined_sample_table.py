from pathlib import Path
from datetime import datetime
import json
import re
import sys

import pandas as pd

ROOT = Path.cwd()
BASE = ROOT / "data_interim" / "cnt" / "l254_castillo_2011"
OUTPUT_DIR = ROOT / "data_processed" / "cnt" / "l254_castillo_2011"
META_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"

SAMPLES_IN = BASE / "l254-samples.csv"
COMPOSITION_IN = BASE / "l254-composition.csv"
ELECTRICAL_IN = BASE / "l254-electrical-attributes.csv"
PROVENANCE_IN = BASE / "l254-study-provenance.csv"

OUTPUT_CSV = OUTPUT_DIR / "l254-combined-by-sample.csv"
QUALITY_CSV = META_DIR / "l254-combined-by-sample-quality.csv"
MANIFEST_JSON = META_DIR / "l254-combined-by-sample-manifest.json"
LOG_FILE = LOG_DIR / "l254-combined-by-sample.log"
ERROR_FILE = LOG_DIR / "l254-combined-by-sample-error.log"

NOW = datetime.now().astimezone().isoformat(timespec="seconds")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
META_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def sample_number(sample_id):
    match = re.search(r"-s(\d+)-", str(sample_id), flags=re.I)
    return int(match.group(1)) if match else None


def block_id(number):
    if number is None or number == 1:
        return "control_or_unassigned"
    if 2 <= number <= 8:
        return "block_1_s2_s8"
    if 9 <= number <= 15:
        return "block_2_s9_s15"
    if 16 <= number <= 22:
        return "block_3_s16_s22"
    if 23 <= number <= 29:
        return "block_4_s23_s29"
    if 30 <= number <= 36:
        return "block_5_s30_s36"
    return "outside_expected_range"


def numeric(series):
    return pd.to_numeric(series, errors="coerce")


def only_rows(frame, token):
    return frame[
        frame["attribute_type"].astype(str).str.contains(
            token, case=False, na=False, regex=False
        )
    ].copy()


def one_per_sample(frame, value_column, output_name):
    if frame.empty:
        return pd.DataFrame(columns=["sample_id", output_name])
    counts = frame.groupby("sample_id")[value_column].nunique(dropna=False)
    conflicts = counts[counts > 1]
    if not conflicts.empty:
        raise ValueError(
            f"Valores conflictivos para {output_name}: "
            + ", ".join(conflicts.index.astype(str))
        )
    result = frame[["sample_id", value_column]].drop_duplicates("sample_id")
    return result.rename(columns={value_column: output_name})


def main():
    print("CONSTRUYENDO TABLA COMBINADA L254 POR MUESTRA")

    samples = read_required(SAMPLES_IN)
    composition = read_required(COMPOSITION_IN)
    electrical = read_required(ELECTRICAL_IN)
    provenance = read_required(PROVENANCE_IN)

    samples = samples[["sample_id", "sample_uri"]].drop_duplicates("sample_id")
    samples["sample_number"] = samples["sample_id"].map(sample_number)
    samples["block_id_inferred"] = samples["sample_number"].map(block_id)
    samples["block_assignment_status"] = "inferred_from_sample_number_pattern"

    mass = only_rows(composition, "MassFraction")
    volume = only_rows(composition, "VolumeFraction")
    conductivity = only_rows(electrical, "ElectricalConductivity")
    frequency = only_rows(electrical, "Frequency")

    mass["value_numeric"] = numeric(mass["attribute_value_original"])
    volume["value_numeric"] = numeric(volume["attribute_value_original"])
    conductivity["value_numeric"] = numeric(conductivity["attribute_value_original"])
    frequency["value_numeric"] = numeric(frequency["attribute_value_original"])

    combined = samples.copy()
    combined = combined.merge(
        one_per_sample(mass, "value_numeric", "mass_fraction"),
        on="sample_id", how="left"
    )
    combined = combined.merge(
        one_per_sample(volume, "value_numeric", "volume_fraction"),
        on="sample_id", how="left"
    )
    combined = combined.merge(
        one_per_sample(
            conductivity, "value_numeric", "electrical_conductivity_s_per_cm"
        ),
        on="sample_id", how="left"
    )
    combined = combined.merge(
        one_per_sample(frequency, "value_numeric", "frequency_hz"),
        on="sample_id", how="left"
    )

    doi_values = sorted(
        value for value in provenance.get("doi_or_resource", pd.Series(dtype=str)).unique()
        if str(value).strip()
    )
    doi = doi_values[0] if len(doi_values) == 1 else "|".join(doi_values)
    combined["doi"] = doi
    combined["matrix_original"] = "Polycarbonate"
    combined["filler_original"] = "Multi-wall carbon nanotubes"
    combined["conductivity_unit_original"] = "Siemens per Centimeter"
    combined["frequency_unit_original"] = combined["frequency_hz"].map(
        lambda value: "Hertz" if pd.notna(value) else ""
    )

    combined["composition_status"] = combined.apply(
        lambda row: "mass_and_volume_fraction_available"
        if pd.notna(row["mass_fraction"]) and pd.notna(row["volume_fraction"])
        else "composition_missing",
        axis=1,
    )
    combined["electrical_status"] = combined["electrical_conductivity_s_per_cm"].map(
        lambda value: "conductivity_available" if pd.notna(value) else "conductivity_missing"
    )
    combined["frequency_status"] = combined["frequency_hz"].map(
        lambda value: "frequency_documented" if pd.notna(value) else "frequency_not_verified"
    )

    combined["complete_pair"] = (
        combined["mass_fraction"].notna()
        & combined["volume_fraction"].notna()
        & combined["electrical_conductivity_s_per_cm"].notna()
    )

    # Conservative modeling flag: complete composition/conductivity pair, assigned block,
    # and frequency documented. A second, less strict candidate flag is also retained.
    combined["candidate_for_block_analysis"] = combined["complete_pair"]
    combined["usable_for_modeling"] = (
        combined["complete_pair"]
        & combined["frequency_hz"].notna()
        & combined["block_id_inferred"].ne("control_or_unassigned")
    )
    combined["modeling_status"] = combined.apply(
        lambda row: "eligible_complete_pair_with_documented_frequency"
        if row["usable_for_modeling"]
        else (
            "candidate_complete_pair_frequency_unverified"
            if row["complete_pair"]
            else "not_usable_missing_composition_or_conductivity"
        ),
        axis=1,
    )
    combined["block_interpretation_status"] = "inferred_not_experimentally_verified"

    columns = [
        "sample_id", "sample_number", "sample_uri", "doi",
        "matrix_original", "filler_original",
        "mass_fraction", "volume_fraction",
        "electrical_conductivity_s_per_cm", "conductivity_unit_original",
        "frequency_hz", "frequency_unit_original",
        "composition_status", "electrical_status", "frequency_status",
        "block_id_inferred", "block_assignment_status",
        "block_interpretation_status", "complete_pair",
        "candidate_for_block_analysis", "usable_for_modeling", "modeling_status",
    ]
    combined = combined[columns].sort_values("sample_number")
    combined.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    checks = [
        ("Q001", "36 unique samples", len(combined) == 36 and combined["sample_id"].nunique() == 36, len(combined), 36),
        ("Q002", "35 samples with composition", int((combined["composition_status"] == "mass_and_volume_fraction_available").sum()) == 35, int((combined["composition_status"] == "mass_and_volume_fraction_available").sum()), 35),
        ("Q003", "29 samples with conductivity", int((combined["electrical_status"] == "conductivity_available").sum()) == 29, int((combined["electrical_status"] == "conductivity_available").sum()), 29),
        ("Q004", "28 complete composition-conductivity pairs", int(combined["complete_pair"].sum()) == 28, int(combined["complete_pair"].sum()), 28),
        ("Q005", "4 samples with documented frequency", int((combined["frequency_status"] == "frequency_documented").sum()) == 4, int((combined["frequency_status"] == "frequency_documented").sum()), 4),
        ("Q006", "All fractions are within 0 to 1", bool(combined["mass_fraction"].dropna().between(0, 1).all() and combined["volume_fraction"].dropna().between(0, 1).all()), "checked", "all true"),
        ("Q007", "All conductivity values are positive", bool((combined["electrical_conductivity_s_per_cm"].dropna() > 0).all()), "checked", "all true"),
        ("Q008", "Five inferred seven-sample composition blocks", all(int((combined["block_id_inferred"] == f"block_{i}_s{2 + 7*(i-1)}_s{8 + 7*(i-1)}").sum()) == 7 for i in range(1, 6)), "checked", "7 samples in each block"),
    ]
    quality = pd.DataFrame(
        checks, columns=["check_id", "description", "passed", "observed", "expected"]
    )
    quality.to_csv(QUALITY_CSV, index=False, encoding="utf-8-sig")

    block_summary = []
    for block, group in combined.groupby("block_id_inferred", sort=True):
        block_summary.append({
            "block_id": block,
            "sample_count": len(group),
            "complete_pair_count": int(group["complete_pair"].sum()),
            "conductivity_count": int(group["electrical_conductivity_s_per_cm"].notna().sum()),
            "composition_count": int(group["mass_fraction"].notna().sum()),
            "frequency_documented_count": int(group["frequency_hz"].notna().sum()),
            "mass_fraction_min": group["mass_fraction"].min(),
            "mass_fraction_max": group["mass_fraction"].max(),
            "volume_fraction_min": group["volume_fraction"].min(),
            "volume_fraction_max": group["volume_fraction"].max(),
            "conductivity_min_s_per_cm": group["electrical_conductivity_s_per_cm"].min(),
            "conductivity_max_s_per_cm": group["electrical_conductivity_s_per_cm"].max(),
        })

    manifest = {
        "generated_at": NOW,
        "input_files": [str(SAMPLES_IN), str(COMPOSITION_IN), str(ELECTRICAL_IN), str(PROVENANCE_IN)],
        "output_file": str(OUTPUT_CSV),
        "row_count": len(combined),
        "doi_values": doi_values,
        "counts": {
            "samples": len(combined),
            "composition_available": int(combined["mass_fraction"].notna().sum()),
            "conductivity_available": int(combined["electrical_conductivity_s_per_cm"].notna().sum()),
            "complete_pairs": int(combined["complete_pair"].sum()),
            "frequency_documented": int(combined["frequency_hz"].notna().sum()),
            "strictly_usable_for_modeling": int(combined["usable_for_modeling"].sum()),
        },
        "block_rule": {
            "status": "inferred_not_experimentally_verified",
            "definition": {
                "block_1_s2_s8": "samples s2 through s8",
                "block_2_s9_s15": "samples s9 through s15",
                "block_3_s16_s22": "samples s16 through s22",
                "block_4_s23_s29": "samples s23 through s29",
                "block_5_s30_s36": "samples s30 through s36",
                "control_or_unassigned": "sample s1",
            },
        },
        "block_summary": block_summary,
        "notes": [
            "Mass and volume fractions are retained as documented dimensionless fractions.",
            "Electrical conductivity is retained in Siemens per Centimeter; no unit conversion was performed.",
            "Frequency 1 Hz is assigned only to samples where it is explicitly documented.",
            "The five-block allocation is inferred from sample numbering and repeated composition patterns.",
            "No percolation model or regression was fitted.",
        ],
    }
    MANIFEST_JSON.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - TABLA COMBINADA POR MUESTRA L254",
        "",
        f"Fecha: {NOW}",
        f"Salida: {OUTPUT_CSV}",
        "",
        "CONTEOS",
    ]
    for key, val in manifest["counts"].items():
        lines.append(f"- {key}: {val}")
    lines.extend(["", "RESUMEN POR BLOQUE INFERIDO"])
    for row in block_summary:
        lines.append(
            f"- {row['block_id']}: muestras={row['sample_count']}, pares_completos={row['complete_pair_count']}, "
            f"conductividad={row['conductivity_count']}, composicion={row['composition_count']}, "
            f"frecuencia_documentada={row['frequency_documented_count']}"
        )
    lines.extend(["", "CONTROLES"])
    for _, row in quality.iterrows():
        lines.append(
            f"- {row['check_id']} | {'PASS' if bool(row['passed']) else 'FAIL'} | "
            f"{row['description']} | observado={row['observed']} | esperado={row['expected']}"
        )
    lines.extend([
        "",
        "INTERPRETACION",
        "- La tabla combina inventario de muestras, composicion, conductividad y frecuencia por sample_id.",
        "- Los bloques son inferidos y no deben tratarse como condiciones experimentales confirmadas.",
        "- Solo las muestras con frecuencia explicitamente documentada reciben frequency_hz=1.",
        "- Los pares completos sin frecuencia permanecen candidatos para analisis de bloque, no aptos aun para modelado definitivo.",
        "- No se ejecutaron conversiones, promedios ni modelos.",
        "",
        f"Tabla: {OUTPUT_CSV}",
        f"Calidad: {QUALITY_CSV}",
        f"Manifiesto: {MANIFEST_JSON}",
    ])
    LOG_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    failed = quality[quality["passed"] != True]
    print("TABLA COMBINADA GENERADA")
    print(f"Muestras: {len(combined)}")
    print(f"Composicion: {manifest['counts']['composition_available']}")
    print(f"Conductividad: {manifest['counts']['conductivity_available']}")
    print(f"Pares completos: {manifest['counts']['complete_pairs']}")
    print(f"Frecuencia documentada: {manifest['counts']['frequency_documented']}")
    print(f"Salida: {OUTPUT_CSV}")
    print(f"Log: {LOG_FILE}")
    if not failed.empty:
        raise ValueError("Uno o mas controles de calidad fallaron")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_FILE.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_FILE}")
        sys.exit(1)
