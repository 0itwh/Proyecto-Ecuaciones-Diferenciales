from pathlib import Path
from datetime import datetime
import json
import re
import sys

import pandas as pd

ROOT = Path.cwd()
BASE_I = ROOT / "data_interim" / "cnt" / "l254_castillo_2011"
BASE_P = ROOT / "data_processed" / "cnt" / "l254_castillo_2011"
META = ROOT / "metadata"
LOGS = ROOT / "logs"
OUT = BASE_P / "block_comparison"
for folder in (META, LOGS, OUT):
    folder.mkdir(parents=True, exist_ok=True)

COMBINED_IN = BASE_P / "l254-combined-by-sample.csv"
COMPONENTS_IN = BASE_I / "l254-material-components.csv"
PROCESSING_IN = BASE_I / "l254-processing-steps.csv"

SAMPLE_FEATURES_OUT = OUT / "l254-sample-features.csv"
BLOCK_FEATURES_OUT = OUT / "l254-block-feature-summary.csv"
BLOCK_DIFFERENCES_OUT = OUT / "l254-block-distinguishing-features.csv"
PROCESSING_MATRIX_OUT = OUT / "l254-block-processing-matrix.csv"
COMPONENT_MATRIX_OUT = OUT / "l254-block-component-matrix.csv"
QUALITY_OUT = META / "l254-block-comparison-quality.csv"
MANIFEST_OUT = META / "l254-block-comparison-manifest.json"
LOG_OUT = LOGS / "l254-block-comparison.log"
ERROR_OUT = LOGS / "l254-block-comparison-error.log"
NOW = datetime.now().astimezone().isoformat(timespec="seconds")


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def norm(value):
    return clean(value).lower()


def unique_join(values):
    return " | ".join(sorted({clean(v) for v in values if clean(v)}))


def sample_number(sample_id):
    match = re.search(r"-s(\d+)-", str(sample_id), re.I)
    return int(match.group(1)) if match else None


def derive_sample_from_uri(value):
    match = re.search(r"l254[_-]s(\d+)[_-]castillo[_-]2011", str(value), re.I)
    return f"l254-s{int(match.group(1))}-castillo-2011" if match else ""


def feature_key(*parts):
    return " :: ".join(norm(part) for part in parts if clean(part))


def main():
    print("COMPARANDO BLOQUES EXPERIMENTALES L254")
    combined = read_required(COMBINED_IN)
    components = read_required(COMPONENTS_IN)
    processing = read_required(PROCESSING_IN)

    # Repair sample ids from URIs only when the source sample_id is empty.
    if "sample_id" not in processing.columns:
        processing["sample_id"] = ""
    processing["sample_id"] = processing.apply(
        lambda row: clean(row["sample_id"]) or derive_sample_from_uri(row.get("processing_step", "")),
        axis=1,
    )
    if "sample_id" not in components.columns:
        components["sample_id"] = ""

    sample_to_block = dict(zip(combined["sample_id"], combined["block_id_inferred"]))
    components["block_id_inferred"] = components["sample_id"].map(sample_to_block).fillna("")
    processing["block_id_inferred"] = processing["sample_id"].map(sample_to_block).fillna("")

    # Create comparable categorical feature signatures.
    components["component_feature"] = components.apply(
        lambda row: feature_key(
            row.get("standard_name", ""), row.get("component_role", ""),
            row.get("attribute_type", ""), row.get("attribute_value_original", ""),
            row.get("attribute_unit_original", ""), row.get("full_label", "")
        ), axis=1
    )
    processing["processing_feature"] = processing.apply(
        lambda row: feature_key(
            row.get("processing_step", ""), row.get("parameter_label", ""),
            row.get("description_original", "")
        ), axis=1
    )

    # Sample-level audit table.
    records = []
    for _, sample in combined.sort_values("sample_number").iterrows():
        sid = sample["sample_id"]
        c = components[components["sample_id"] == sid]
        p = processing[processing["sample_id"] == sid]
        records.append({
            "sample_id": sid,
            "sample_number": sample["sample_number"],
            "block_id_inferred": sample["block_id_inferred"],
            "mass_fraction": sample["mass_fraction"],
            "volume_fraction": sample["volume_fraction"],
            "electrical_conductivity_s_per_cm": sample["electrical_conductivity_s_per_cm"],
            "frequency_hz": sample["frequency_hz"],
            "component_row_count": len(c),
            "processing_row_count": len(p),
            "component_standard_names": unique_join(c.get("standard_name", [])),
            "component_roles": unique_join(c.get("component_role", [])),
            "component_attributes": unique_join(c.get("component_feature", [])),
            "processing_parameters": unique_join(p.get("parameter_label", [])),
            "processing_descriptions": unique_join(p.get("description_original", [])),
            "processing_features": unique_join(p.get("processing_feature", [])),
        })
    sample_features = pd.DataFrame(records)
    sample_features.to_csv(SAMPLE_FEATURES_OUT, index=False, encoding="utf-8-sig")

    blocks = sorted(x for x in combined["block_id_inferred"].unique() if x.startswith("block_"))

    # Presence matrices: number of samples in each block containing each feature.
    component_presence = []
    for feature, group in components[components["component_feature"] != ""].groupby("component_feature"):
        row = {"feature": feature}
        for block in blocks:
            row[block] = group[group["block_id_inferred"] == block]["sample_id"].nunique()
        component_presence.append(row)
    component_matrix = pd.DataFrame(component_presence)
    component_matrix.to_csv(COMPONENT_MATRIX_OUT, index=False, encoding="utf-8-sig")

    processing_presence = []
    for feature, group in processing[processing["processing_feature"] != ""].groupby("processing_feature"):
        row = {"feature": feature}
        for block in blocks:
            row[block] = group[group["block_id_inferred"] == block]["sample_id"].nunique()
        processing_presence.append(row)
    processing_matrix = pd.DataFrame(processing_presence)
    processing_matrix.to_csv(PROCESSING_MATRIX_OUT, index=False, encoding="utf-8-sig")

    # Distinguishing features are present in one or more blocks but not uniformly in all.
    differences = []
    for source_name, frame in [("component", component_matrix), ("processing", processing_matrix)]:
        if frame.empty:
            continue
        for _, row in frame.iterrows():
            counts = [int(row.get(block, 0)) for block in blocks]
            if len(set(counts)) <= 1:
                continue
            present_blocks = [block for block in blocks if int(row.get(block, 0)) > 0]
            absent_blocks = [block for block in blocks if int(row.get(block, 0)) == 0]
            differences.append({
                "source_type": source_name,
                "feature": row["feature"],
                "present_blocks": "|".join(present_blocks),
                "absent_blocks": "|".join(absent_blocks),
                "block_counts": "|".join(f"{block}={int(row.get(block, 0))}" for block in blocks),
                "distinguishing_status": "candidate_distinguishing_feature",
                "evidence_status": "documented_presence_in_historical_bindings",
                "interpretation_status": "not_yet_confirmed_as_block_definition",
            })
    distinguishing = pd.DataFrame(differences)
    if distinguishing.empty:
        distinguishing = pd.DataFrame(columns=[
            "source_type", "feature", "present_blocks", "absent_blocks", "block_counts",
            "distinguishing_status", "evidence_status", "interpretation_status"
        ])
    distinguishing.to_csv(BLOCK_DIFFERENCES_OUT, index=False, encoding="utf-8-sig")

    # Block summary.
    summaries = []
    for block in blocks:
        s = sample_features[sample_features["block_id_inferred"] == block]
        c = components[components["block_id_inferred"] == block]
        p = processing[processing["block_id_inferred"] == block]
        summaries.append({
            "block_id": block,
            "sample_count": len(s),
            "samples_with_components": c["sample_id"].nunique(),
            "samples_with_processing": p["sample_id"].nunique(),
            "unique_component_features": c["component_feature"].replace("", pd.NA).dropna().nunique(),
            "unique_processing_features": p["processing_feature"].replace("", pd.NA).dropna().nunique(),
            "component_standard_names": unique_join(c.get("standard_name", [])),
            "component_roles": unique_join(c.get("component_role", [])),
            "processing_parameters": unique_join(p.get("parameter_label", [])),
            "processing_descriptions": unique_join(p.get("description_original", [])),
            "complete_pair_count": int(s["electrical_conductivity_s_per_cm"].astype(str).ne("").sum()),
        })
    block_summary = pd.DataFrame(summaries)
    block_summary.to_csv(BLOCK_FEATURES_OUT, index=False, encoding="utf-8-sig")

    checks = [
        ("Q001", "Five inferred blocks analysed", len(blocks) == 5, len(blocks), 5),
        ("Q002", "All 36 samples preserved", len(sample_features) == 36, len(sample_features), 36),
        ("Q003", "No component row linked outside sample inventory", components["sample_id"].isin(set(combined["sample_id"]) | {""}).all(), "checked", True),
        ("Q004", "No processing row linked outside sample inventory", processing["sample_id"].isin(set(combined["sample_id"]) | {""}).all(), "checked", True),
        ("Q005", "Block comparison outputs created", True, "created", True),
    ]
    quality = pd.DataFrame(checks, columns=["check_id", "description", "passed", "observed", "expected"])
    quality.to_csv(QUALITY_OUT, index=False, encoding="utf-8-sig")

    manifest = {
        "generated_at": NOW,
        "inputs": [str(COMBINED_IN), str(COMPONENTS_IN), str(PROCESSING_IN)],
        "outputs": [
            str(SAMPLE_FEATURES_OUT), str(BLOCK_FEATURES_OUT),
            str(BLOCK_DIFFERENCES_OUT), str(PROCESSING_MATRIX_OUT),
            str(COMPONENT_MATRIX_OUT), str(QUALITY_OUT)
        ],
        "counts": {
            "samples": len(sample_features),
            "blocks": len(blocks),
            "component_rows": len(components),
            "processing_rows": len(processing),
            "candidate_distinguishing_features": len(distinguishing),
            "component_features": len(component_matrix),
            "processing_features": len(processing_matrix),
        },
        "method": {
            "block_status": "inferred_not_experimentally_verified",
            "feature_definition_components": "standard name + role + attribute type + value + unit + full label",
            "feature_definition_processing": "processing step + parameter label + description",
            "distinguishing_rule": "feature presence count differs across inferred blocks",
        },
        "notes": [
            "A distinguishing feature is a candidate explanation, not proof of an experimental block definition.",
            "No missing feature was imputed.",
            "No statistical model, percolation fit, or regression was performed.",
        ],
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - COMPARACION DE BLOQUES L254",
        "",
        f"Fecha: {NOW}",
        "",
        "CONTEOS",
    ]
    lines.extend(f"- {key}: {value}" for key, value in manifest["counts"].items())
    lines.extend(["", "COBERTURA POR BLOQUE"])
    for _, row in block_summary.iterrows():
        lines.append(
            f"- {row['block_id']}: muestras={row['sample_count']}, "
            f"con_componentes={row['samples_with_components']}, "
            f"con_procesamiento={row['samples_with_processing']}, "
            f"rasgos_componentes={row['unique_component_features']}, "
            f"rasgos_procesamiento={row['unique_processing_features']}"
        )
    lines.extend(["", "RESULTADO"])
    if len(distinguishing):
        lines.append(f"- Se localizaron {len(distinguishing)} rasgos candidatos que varian entre bloques.")
        lines.append("- Deben revisarse sus valores exactos antes de declarar la variable experimental de cada bloque.")
    else:
        lines.append("- No se localizaron rasgos documentados que distingan los bloques en componentes o procesamiento.")
    lines.extend([
        "- La ausencia de un rasgo puede reflejar metadatos incompletos, no ausencia experimental.",
        "- Los bloques siguen siendo inferidos.",
        "- No se ejecutaron modelos.",
        "",
        f"Resumen de bloques: {BLOCK_FEATURES_OUT}",
        f"Rasgos distintivos: {BLOCK_DIFFERENCES_OUT}",
        f"Matriz de componentes: {COMPONENT_MATRIX_OUT}",
        f"Matriz de procesamiento: {PROCESSING_MATRIX_OUT}",
        f"Muestras enriquecidas: {SAMPLE_FEATURES_OUT}",
        f"Manifiesto: {MANIFEST_OUT}",
    ])
    LOG_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("COMPARACION COMPLETADA")
    for key, value in manifest["counts"].items():
        print(f"{key}: {value}")
    print(f"Log: {LOG_OUT}")

    if not quality["passed"].astype(bool).all():
        raise ValueError("Uno o mas controles de calidad fallaron")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_OUT.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_OUT}")
        sys.exit(1)
