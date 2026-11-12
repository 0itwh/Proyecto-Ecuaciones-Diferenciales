from pathlib import Path
from datetime import datetime
import json
import re
import sys

import pandas as pd

ROOT = Path.cwd()
BASE_I = ROOT / "data_interim" / "cnt" / "l254_castillo_2011"
BASE_P = ROOT / "data_processed" / "cnt" / "l254_castillo_2011"
BLOCK_DIR = BASE_P / "block_comparison"
META = ROOT / "metadata"
LOGS = ROOT / "logs"

COMBINED_IN = BASE_P / "l254-combined-by-sample.csv"
COMPONENTS_IN = BASE_I / "l254-material-components.csv"
PROCESSING_IN = BASE_I / "l254-processing-steps.csv"
SAMPLE_FEATURES_IN = BLOCK_DIR / "l254-sample-features.csv"

NORMALIZED_FEATURES_OUT = BLOCK_DIR / "l254-normalized-distinguishing-features.csv"
COMPONENT_MATRIX_OUT = BLOCK_DIR / "l254-normalized-component-matrix.csv"
PROCESSING_MATRIX_OUT = BLOCK_DIR / "l254-normalized-processing-matrix.csv"
MISSING_PROCESSING_OUT = BLOCK_DIR / "l254-samples-missing-processing.csv"
BLOCK_SUMMARY_OUT = BLOCK_DIR / "l254-normalized-block-summary.csv"
QUALITY_OUT = META / "l254-normalized-feature-quality.csv"
MANIFEST_OUT = META / "l254-normalized-feature-manifest.json"
LOG_OUT = LOGS / "l254-normalized-feature-analysis.log"
ERROR_OUT = LOGS / "l254-normalized-feature-analysis-error.log"
NOW = datetime.now().astimezone().isoformat(timespec="seconds")

for folder in (BLOCK_DIR, META, LOGS):
    folder.mkdir(parents=True, exist_ok=True)

SAMPLE_PATTERN = re.compile(r"l254[_-]s\d+[_-]castillo[_-]2011", re.I)
SAMPLE_URI_PATTERN = re.compile(r"https?://[^\s,;\]\[()<>\"']*l254[_-]s\d+[_-]castillo[_-]2011[^\s,;\]\[()<>\"']*", re.I)
GENERIC_URI_PATTERN = re.compile(r"https?://[^\s,;\]\[()<>\"']+", re.I)
UUIDISH_PATTERN = re.compile(r"\b[a-f0-9]{8,}(?:-[a-f0-9]{4,})+\b", re.I)
STEP_ID_PATTERN = re.compile(r"(?:solution[_-]processing[_-]step|processing[_-]step)[_-]?\d+", re.I)
WHITESPACE_PATTERN = re.compile(r"\s+")

COMPOSITION_PATTERN = re.compile(
    r"mass.?fraction|weight.?fraction|volume.?fraction|composition|concentration|loading|wt\.?%|vol\.?%",
    re.I,
)


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def clean(value):
    return WHITESPACE_PATTERN.sub(" ", str(value or "")).strip()


def derive_sample_id(value):
    match = SAMPLE_PATTERN.search(str(value or ""))
    if not match:
        return ""
    number = re.search(r"s(\d+)", match.group(0), re.I).group(1)
    return f"l254-s{int(number)}-castillo-2011"


def normalize_text(value):
    """Remove sample-specific and URI-specific identity while preserving scientific wording."""
    text = clean(value).lower()
    text = SAMPLE_URI_PATTERN.sub(" <sample_uri> ", text)
    text = SAMPLE_PATTERN.sub(" <sample_id> ", text)
    text = GENERIC_URI_PATTERN.sub(" <uri> ", text)
    text = UUIDISH_PATTERN.sub(" <identifier> ", text)
    text = STEP_ID_PATTERN.sub(" <processing_step> ", text)
    text = re.sub(r"\b(?:sample|specimen)[_-]?\d+\b", "<sample_id>", text, flags=re.I)
    text = re.sub(r"\s*::\s*", " :: ", text)
    return clean(text).strip(" :|")


def normalized_component_feature(row):
    attr_type = clean(row.get("attribute_type", ""))
    full_label = clean(row.get("full_label", ""))
    # Composition values are already represented in the combined table and are excluded
    # from block discrimination to prevent the seven loading levels from inflating differences.
    if COMPOSITION_PATTERN.search(" ".join([attr_type, full_label])):
        return "", "excluded_composition_feature"
    fields = [
        normalize_text(row.get("standard_name", "")),
        normalize_text(row.get("component_role", "")),
        normalize_text(attr_type),
        normalize_text(row.get("attribute_unit_original", "")),
        normalize_text(full_label),
    ]
    feature = " :: ".join(item for item in fields if item)
    return feature, "included_noncomposition_component_feature" if feature else "empty_after_normalization"


def normalized_processing_feature(row):
    fields = [
        normalize_text(row.get("parameter_label", "")),
        normalize_text(row.get("description_original", "")),
    ]
    feature = " :: ".join(item for item in fields if item)
    return feature, "included_processing_feature" if feature else "empty_after_normalization"


def presence_matrix(frame, feature_column, blocks):
    records = []
    usable = frame[frame[feature_column].astype(str).str.strip() != ""]
    for feature, group in usable.groupby(feature_column):
        record = {"normalized_feature": feature}
        for block in blocks:
            record[block] = group[group["block_id_inferred"] == block]["sample_id"].nunique()
        records.append(record)
    columns = ["normalized_feature"] + blocks
    return pd.DataFrame(records, columns=columns)


def main():
    print("NORMALIZANDO RASGOS DE BLOQUES L254")
    combined = read_required(COMBINED_IN)
    components = read_required(COMPONENTS_IN)
    processing = read_required(PROCESSING_IN)
    sample_features = read_required(SAMPLE_FEATURES_IN)

    sample_to_block = dict(zip(combined["sample_id"], combined["block_id_inferred"]))

    if "sample_id" not in processing.columns:
        processing["sample_id"] = ""
    processing["sample_id"] = processing.apply(
        lambda row: clean(row.get("sample_id", "")) or derive_sample_id(row.get("processing_step", "")),
        axis=1,
    )
    components["sample_id"] = components.get("sample_id", "")
    components["block_id_inferred"] = components["sample_id"].map(sample_to_block).fillna("")
    processing["block_id_inferred"] = processing["sample_id"].map(sample_to_block).fillna("")

    component_norm = components.apply(normalized_component_feature, axis=1, result_type="expand")
    component_norm.columns = ["normalized_feature", "normalization_status"]
    components = pd.concat([components, component_norm], axis=1)

    processing_norm = processing.apply(normalized_processing_feature, axis=1, result_type="expand")
    processing_norm.columns = ["normalized_feature", "normalization_status"]
    processing = pd.concat([processing, processing_norm], axis=1)

    blocks = sorted(value for value in combined["block_id_inferred"].unique() if value.startswith("block_"))
    component_matrix = presence_matrix(components, "normalized_feature", blocks)
    processing_matrix = presence_matrix(processing, "normalized_feature", blocks)
    component_matrix.to_csv(COMPONENT_MATRIX_OUT, index=False, encoding="utf-8-sig")
    processing_matrix.to_csv(PROCESSING_MATRIX_OUT, index=False, encoding="utf-8-sig")

    differences = []
    for source_type, matrix in [("component", component_matrix), ("processing", processing_matrix)]:
        for _, row in matrix.iterrows():
            counts = [int(row[block]) for block in blocks]
            if len(set(counts)) <= 1:
                continue
            present = [block for block in blocks if int(row[block]) > 0]
            absent = [block for block in blocks if int(row[block]) == 0]
            differences.append({
                "source_type": source_type,
                "normalized_feature": row["normalized_feature"],
                "present_blocks": "|".join(present),
                "absent_blocks": "|".join(absent),
                "block_sample_counts": "|".join(f"{block}={int(row[block])}" for block in blocks),
                "feature_scope": "block_level_candidate",
                "evidence_status": "documented_after_identifier_normalization",
                "interpretation_status": "candidate_not_confirmed_as_block_definition",
            })
    differences_frame = pd.DataFrame(differences)
    if differences_frame.empty:
        differences_frame = pd.DataFrame(columns=[
            "source_type", "normalized_feature", "present_blocks", "absent_blocks",
            "block_sample_counts", "feature_scope", "evidence_status", "interpretation_status"
        ])
    differences_frame.to_csv(NORMALIZED_FEATURES_OUT, index=False, encoding="utf-8-sig")

    # Identify samples with zero processing rows, and specifically the inferred block 5 gap.
    sample_features["processing_row_count_numeric"] = pd.to_numeric(
        sample_features["processing_row_count"], errors="coerce"
    ).fillna(0).astype(int)
    missing_processing = sample_features[sample_features["processing_row_count_numeric"] == 0][
        ["sample_id", "sample_number", "block_id_inferred", "processing_row_count"]
    ].copy()
    missing_processing["missingness_status"] = "documented_no_processing_rows_in_extracted_bindings"
    missing_processing["interpretation_status"] = "metadata_missing_not_proof_of_no_processing"
    missing_processing.to_csv(MISSING_PROCESSING_OUT, index=False, encoding="utf-8-sig")

    # Block summaries after normalization.
    summaries = []
    for block in blocks:
        c = components[components["block_id_inferred"] == block]
        p = processing[processing["block_id_inferred"] == block]
        s = sample_features[sample_features["block_id_inferred"] == block]
        summaries.append({
            "block_id": block,
            "sample_count": len(s),
            "samples_with_components": c[c["normalized_feature"] != ""]["sample_id"].nunique(),
            "samples_with_processing": p[p["normalized_feature"] != ""]["sample_id"].nunique(),
            "normalized_component_feature_count": c["normalized_feature"].replace("", pd.NA).dropna().nunique(),
            "normalized_processing_feature_count": p["normalized_feature"].replace("", pd.NA).dropna().nunique(),
            "samples_missing_processing": "|".join(
                missing_processing[missing_processing["block_id_inferred"] == block]["sample_id"]
            ),
        })
    block_summary = pd.DataFrame(summaries)
    block_summary.to_csv(BLOCK_SUMMARY_OUT, index=False, encoding="utf-8-sig")

    block5_missing = missing_processing[
        missing_processing["block_id_inferred"] == "block_5_s30_s36"
    ]["sample_id"].tolist()

    checks = [
        ("Q001", "All 36 samples preserved", len(sample_features) == 36, len(sample_features), 36),
        ("Q002", "Exactly five inferred blocks compared", len(blocks) == 5, len(blocks), 5),
        ("Q003", "Block 5 missing-processing sample identified", block5_missing == ["l254-s33-castillo-2011"], "|".join(block5_missing), "l254-s33-castillo-2011"),
        ("Q004", "Composition features excluded from distinction", not components[components["normalization_status"] == "excluded_composition_feature"].empty, int((components["normalization_status"] == "excluded_composition_feature").sum()), ">0"),
        ("Q005", "No sample identifier remains in normalized distinguishing features", not differences_frame["normalized_feature"].astype(str).str.contains(SAMPLE_PATTERN, na=False).any(), "checked", True),
        ("Q006", "No HTTP URI remains in normalized distinguishing features", not differences_frame["normalized_feature"].astype(str).str.contains(r"https?://", case=False, regex=True, na=False).any(), "checked", True),
    ]
    quality = pd.DataFrame(checks, columns=["check_id", "description", "passed", "observed", "expected"])
    quality.to_csv(QUALITY_OUT, index=False, encoding="utf-8-sig")

    manifest = {
        "generated_at": NOW,
        "inputs": [str(COMBINED_IN), str(COMPONENTS_IN), str(PROCESSING_IN), str(SAMPLE_FEATURES_IN)],
        "outputs": [str(NORMALIZED_FEATURES_OUT), str(COMPONENT_MATRIX_OUT), str(PROCESSING_MATRIX_OUT), str(MISSING_PROCESSING_OUT), str(BLOCK_SUMMARY_OUT), str(QUALITY_OUT)],
        "counts": {
            "raw_candidate_features_previous": 143,
            "normalized_component_features": len(component_matrix),
            "normalized_processing_features": len(processing_matrix),
            "normalized_distinguishing_features": len(differences_frame),
            "excluded_composition_component_rows": int((components["normalization_status"] == "excluded_composition_feature").sum()),
            "samples_missing_processing": len(missing_processing),
        },
        "block_5_missing_processing_samples": block5_missing,
        "normalization_rules": [
            "Remove l254 sample identifiers and sample-specific URIs.",
            "Replace remaining HTTP(S) URIs with a generic placeholder and exclude the placeholder from scientific identity.",
            "Remove UUID-like identifiers and processing-step sequence identifiers.",
            "Exclude mass-fraction, volume-fraction, loading, concentration, and composition features from block discrimination.",
            "Compare component names, roles, non-composition attribute types/units/labels, processing parameter labels, and normalized descriptions.",
        ],
        "interpretation_limits": [
            "Feature absence can indicate incomplete metadata rather than experimental absence.",
            "Normalized differences remain candidates and do not prove the block definition.",
            "No missing processing information was imputed.",
            "No model was fitted.",
        ],
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - NORMALIZACION DE RASGOS DE BLOQUES L254",
        "",
        f"Fecha: {NOW}",
        "",
        "CONTEOS",
    ]
    lines.extend(f"- {key}: {value}" for key, value in manifest["counts"].items())
    lines.extend([
        "",
        "MUESTRAS SIN PROCESAMIENTO EXTRAIDO",
    ])
    if missing_processing.empty:
        lines.append("- Ninguna")
    else:
        for _, row in missing_processing.iterrows():
            lines.append(f"- {row['sample_id']} | {row['block_id_inferred']} | filas={row['processing_row_count']}")
    lines.extend([
        "",
        "RESULTADO DEL BLOQUE 5",
        "- l254-s33-castillo-2011 es la muestra del bloque 5 sin filas de procesamiento extraidas." if block5_missing == ["l254-s33-castillo-2011"] else f"- Muestras detectadas: {'|'.join(block5_missing) or 'ninguna'}",
        "- Este resultado confirma ausencia de metadatos extraidos, no ausencia real de procesamiento.",
        "",
        "INTERPRETACION",
        "- Se eliminaron identificadores de muestra, URI, identificadores largos y numeros de etapa de las claves comparativas.",
        "- Se excluyeron fracciones y cargas de composicion de la discriminacion entre bloques.",
        "- Los rasgos restantes comparan materiales, roles, atributos no composicionales y descripciones de proceso normalizadas.",
        "- Las diferencias siguen siendo candidatas hasta contrastarlas con el articulo o metadatos completos.",
        "- No se ejecutaron imputaciones ni modelos.",
        "",
        f"Rasgos normalizados: {NORMALIZED_FEATURES_OUT}",
        f"Muestras sin procesamiento: {MISSING_PROCESSING_OUT}",
        f"Resumen por bloque: {BLOCK_SUMMARY_OUT}",
        f"Manifiesto: {MANIFEST_OUT}",
    ])
    LOG_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("NORMALIZACION COMPLETADA")
    for key, value in manifest["counts"].items():
        print(f"{key}: {value}")
    print("block_5_missing_processing:", "|".join(block5_missing) or "ninguna")
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
