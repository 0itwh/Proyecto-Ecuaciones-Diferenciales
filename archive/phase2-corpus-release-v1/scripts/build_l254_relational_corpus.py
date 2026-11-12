from pathlib import Path
from datetime import datetime
import hashlib
import json
import math
import re
import shutil
import sys

import pandas as pd

ROOT = Path.cwd()
INTERIM = ROOT / "data_interim" / "cnt" / "l254_castillo_2011"
PROCESSED = ROOT / "data_processed" / "cnt" / "l254_castillo_2011"
BLOCK_DIR = PROCESSED / "block_comparison"
OUT = ROOT / "data_processed" / "l254_corpus"
META = ROOT / "metadata"
LOGS = ROOT / "logs"

for folder in (OUT, META, LOGS):
    folder.mkdir(parents=True, exist_ok=True)

COMBINED_IN = PROCESSED / "l254-combined-by-sample.csv"
SIGNATURES_IN = BLOCK_DIR / "l254-matrix-mwcnt-block-signatures.csv"
COMPONENTS_IN = INTERIM / "l254-material-components.csv"
PROCESSING_IN = INTERIM / "l254-processing-steps.csv"
PROVENANCE_IN = INTERIM / "l254-study-provenance.csv"
ATTRIBUTES_IN = INTERIM / "l254-sample-attributes.csv"
BLOCK_STATUS_IN = BLOCK_DIR / "l254-block-definition-status.csv"
MISSING_PROCESSING_IN = BLOCK_DIR / "l254-samples-missing-processing.csv"

STUDIES_OUT = OUT / "studies.csv"
SYSTEMS_OUT = OUT / "material_systems.csv"
FILLERS_OUT = OUT / "filler_variants.csv"
SAMPLES_OUT = OUT / "samples.csv"
COMPOSITION_OUT = OUT / "sample_composition.csv"
PROCESSING_OUT = OUT / "processing_steps.csv"
MEASUREMENTS_OUT = OUT / "electrical_measurements.csv"
CONDITIONS_OUT = OUT / "measurement_conditions.csv"
PROVENANCE_OUT = OUT / "provenance.csv"
EXCLUSIONS_OUT = OUT / "exclusions.csv"
CURVES_OUT = OUT / "curve_inclusion_status.csv"

QUALITY_OUT = META / "l254-corpus-quality-summary.csv"
MANIFEST_OUT = META / "l254-corpus-manifest.json"
LOG_OUT = LOGS / "l254-corpus-quality-report.txt"
ERROR_OUT = LOGS / "l254-corpus-build-error.log"

NOW = datetime.now().astimezone().isoformat(timespec="seconds")
STUDY_ID = "study-l254-castillo-2011"
SYSTEM_ID = "system-l254-pc-mwcnt"
DOI = "10.1016/j.polymer.2011.06.018"


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def read_optional(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False) if path.is_file() else pd.DataFrame()


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def as_float(value):
    try:
        number = float(clean(value))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def as_bool(value):
    return clean(value).lower() in {"true", "1", "yes", "si", "sí"}


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def write(frame, path, columns=None):
    frame = frame.copy()
    if columns:
        for column in columns:
            if column not in frame.columns:
                frame[column] = ""
        frame = frame[columns]
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return frame


def sample_number(sample_id):
    match = re.search(r"-s(\d+)-", clean(sample_id), re.I)
    return int(match.group(1)) if match else None


def variant_id(block):
    mapping = {
        "block_1_s2_s8": "l254-mwcnt-v1-ar134",
        "block_2_s9_s15": "l254-mwcnt-v2-ar94",
        "block_3_s16_s22": "l254-mwcnt-v3-ar55",
        "block_4_s23_s29": "l254-mwcnt-v4-ar73",
        "block_5_s30_s36": "l254-mwcnt-v5-ar69",
    }
    return mapping.get(clean(block), "")


def curve_status(block, complete_pairs, frequency_count):
    if block == "block_1_s2_s8" and complete_pairs == 7:
        return "primary_candidate_complete_curve_conditions_partial"
    if complete_pairs >= 5:
        return "conditional_candidate_incomplete_curve_conditions_unverified"
    return "insufficient_for_curve_modeling"


def main():
    print("CONSTRUYENDO CORPUS RELACIONAL DEFINITIVO L254")

    combined = read_required(COMBINED_IN)
    signatures = read_required(SIGNATURES_IN)
    components = read_required(COMPONENTS_IN)
    processing = read_required(PROCESSING_IN)
    study_provenance = read_required(PROVENANCE_IN)
    attributes = read_required(ATTRIBUTES_IN)
    block_status = read_optional(BLOCK_STATUS_IN)
    missing_processing = read_optional(MISSING_PROCESSING_IN)

    # 1. Study
    studies = pd.DataFrame([{
        "study_id": STUDY_ID,
        "study_code": "l254-castillo-2011",
        "doi": DOI,
        "publication_year": "2011",
        "matrix_family": "polycarbonate",
        "filler_family": "multi-wall carbon nanotubes",
        "source_database": "MaterialsMine historical indexed response",
        "corpus_status": "primary_candidate_under_measurement_condition_validation",
        "study_evidence_status": "documented",
        "created_at": NOW,
    }])

    # 2. Material system
    systems = pd.DataFrame([{
        "material_system_id": SYSTEM_ID,
        "study_id": STUDY_ID,
        "matrix_name_original": "Poly(bisphenol A carbonate)",
        "matrix_product": "Makrolon 2600",
        "matrix_manufacturer": "Bayer MaterialScience AG, Leverkusen, Germany",
        "matrix_density_kg_m3": 1200.0,
        "filler_name_original": "Multi-wall carbon nanotubes",
        "filler_variant_count": 5,
        "system_status": "documented_matrix_and_five_distinct_mwcnt_variants",
    }])

    # 3. Filler variants, separated from matrix metadata.
    filler_rows = []
    for _, row in signatures.iterrows():
        block = clean(row.get("block_id", ""))
        filler_rows.append({
            "filler_variant_id": variant_id(block),
            "material_system_id": SYSTEM_ID,
            "study_id": STUDY_ID,
            "block_id": block,
            "filler_name_original": clean(row.get("mwcnt_name", "")) or "Multi-wall carbon nanotubes",
            "aspect_ratio": as_float(row.get("mwcnt_aspect_ratio", "")),
            "density_value_original": clean(row.get("mwcnt_density_original", "")),
            "density_unit_original": clean(row.get("mwcnt_density_unit_original", "")),
            "density_value_canonical_kg_m3": as_float(row.get("mwcnt_density_canonical_kg_m3", "")),
            "density_semantic_status": clean(row.get("mwcnt_density_semantic_status", "")) or "documented_value_density_kind_not_verified",
            "commercial_name": clean(row.get("mwcnt_commercial_name", "")),
            "manufacturer": clean(row.get("mwcnt_manufacturer", "")),
            "commercial_identity_status": clean(row.get("mwcnt_identity_status", "")) or "not_verified",
            "variant_definition_status": "confirmed_as_distinct_mwcnt_variant_by_aspect_ratio_and_study_design",
        })
    fillers = pd.DataFrame(filler_rows)

    # 4. Samples
    samples = combined[[
        "sample_id", "sample_number", "sample_uri", "block_id_inferred",
        "composition_status", "electrical_status", "frequency_status"
    ]].copy()
    samples["study_id"] = STUDY_ID
    samples["material_system_id"] = SYSTEM_ID
    samples["filler_variant_id"] = samples["block_id_inferred"].map(variant_id)
    samples["sample_role"] = samples["sample_number"].map(
        lambda n: "control_or_reference_unverified" if clean(n) == "1" else "nanocomposite_sample"
    )
    samples["block_definition_status"] = samples["block_id_inferred"].map(
        lambda b: "control_or_unassigned" if b == "control_or_unassigned" else "confirmed_as_distinct_mwcnt_variant_block"
    )

    # 5. Composition in long form.
    composition_rows = []
    for _, row in combined.iterrows():
        sid = row["sample_id"]
        for basis, column in [("mass_fraction", "mass_fraction"), ("volume_fraction", "volume_fraction")]:
            value = as_float(row.get(column, ""))
            if value is None:
                continue
            composition_rows.append({
                "composition_id": f"comp-{sid}-{basis}",
                "study_id": STUDY_ID,
                "sample_id": sid,
                "filler_variant_id": variant_id(row.get("block_id_inferred", "")),
                "component_role": "filler",
                "basis": basis,
                "value_original": clean(row.get(column, "")),
                "value_numeric": value,
                "canonical_value": value,
                "canonical_unit": "1",
                "transformation": "numeric_parse_only",
                "evidence_status": "documented",
            })
    composition = pd.DataFrame(composition_rows)

    # 6. Processing. Preserve source rows and flag missing sample metadata.
    processing_out = processing.copy()
    processing_out["processing_record_id"] = [f"proc-l254-{i+1:04d}" for i in range(len(processing_out))]
    processing_out["study_id"] = STUDY_ID
    processing_out["material_system_id"] = SYSTEM_ID
    processing_out["filler_variant_id"] = processing_out.get("sample_id", pd.Series(dtype=str)).map(
        dict(zip(samples["sample_id"], samples["filler_variant_id"]))
    ).fillna("")
    processing_out["metadata_status"] = "documented_in_extracted_bindings"

    # 7. Electrical measurements.
    measurement_rows = []
    condition_rows = []
    for _, row in combined.iterrows():
        conductivity = as_float(row.get("electrical_conductivity_s_per_cm", ""))
        if conductivity is not None:
            mid = f"meas-{row['sample_id']}-conductivity"
            frequency = as_float(row.get("frequency_hz", ""))
            complete_pair = as_bool(row.get("complete_pair", ""))
            measurement_rows.append({
                "measurement_id": mid,
                "study_id": STUDY_ID,
                "sample_id": row["sample_id"],
                "filler_variant_id": variant_id(row.get("block_id_inferred", "")),
                "property_name": "electrical_conductivity",
                "value_original": clean(row.get("electrical_conductivity_s_per_cm", "")),
                "value_numeric": conductivity,
                "unit_original": clean(row.get("conductivity_unit_original", "")) or "Siemens per Centimeter",
                "canonical_value": conductivity,
                "canonical_unit": "S/cm",
                "transformation": "unit_label_normalization_only",
                "composition_pair_status": "complete" if complete_pair else "composition_missing",
                "frequency_status": "documented" if frequency is not None else "not_verified",
                "measurement_status": "documented_value_unit_explicit_conditions_partial",
                "usable_for_final_modeling": False,
                "modeling_block_reason": "measurement frequency and other conditions not verified for all points in curve",
            })
            condition_rows.append({
                "condition_id": f"cond-{row['sample_id']}-frequency",
                "measurement_id": mid,
                "sample_id": row["sample_id"],
                "condition_name": "frequency",
                "value_original": clean(row.get("frequency_hz", "")),
                "value_numeric": frequency if frequency is not None else "",
                "unit_original": "Hertz" if frequency is not None else "",
                "canonical_value": frequency if frequency is not None else "",
                "canonical_unit": "Hz" if frequency is not None else "",
                "condition_status": "documented" if frequency is not None else "not_verified",
            })
    measurements = pd.DataFrame(measurement_rows)
    conditions = pd.DataFrame(condition_rows)

    # 8. Curve status by block.
    curve_rows = []
    for block in [f"block_{i}_s{2+7*(i-1)}_s{8+7*(i-1)}" for i in range(1, 6)]:
        group = combined[combined["block_id_inferred"] == block]
        complete_pairs = int(group["complete_pair"].map(as_bool).sum())
        frequency_count = int(group["frequency_hz"].map(lambda v: as_float(v) is not None).sum())
        conductivity_count = int(group["electrical_conductivity_s_per_cm"].map(lambda v: as_float(v) is not None).sum())
        missing_samples = group[group["electrical_conductivity_s_per_cm"].map(lambda v: as_float(v) is None)]["sample_id"].tolist()
        curve_rows.append({
            "curve_id": f"curve-{variant_id(block)}",
            "study_id": STUDY_ID,
            "block_id": block,
            "filler_variant_id": variant_id(block),
            "sample_count": len(group),
            "composition_count": int(group["mass_fraction"].map(lambda v: as_float(v) is not None).sum()),
            "conductivity_count": conductivity_count,
            "complete_pair_count": complete_pairs,
            "frequency_documented_count": frequency_count,
            "missing_conductivity_sample_ids": "|".join(missing_samples),
            "curve_status": curve_status(block, complete_pairs, frequency_count),
            "usable_for_final_modeling": False,
            "decision_reason": "curve retained separately; measurement conditions incomplete",
        })
    curves = pd.DataFrame(curve_rows)

    # 9. Exclusions and unresolved records.
    exclusions = []
    for _, row in combined.iterrows():
        if as_float(row.get("electrical_conductivity_s_per_cm", "")) is None:
            exclusions.append({
                "exclusion_id": f"excl-{row['sample_id']}-missing-conductivity",
                "entity_type": "sample_measurement",
                "entity_id": row["sample_id"],
                "sample_id": row["sample_id"],
                "reason": "electrical_conductivity_missing",
                "status": "excluded_from_electrical_curve_fit",
            })
        if as_float(row.get("frequency_hz", "")) is None:
            exclusions.append({
                "exclusion_id": f"excl-{row['sample_id']}-frequency-unverified",
                "entity_type": "measurement_condition",
                "entity_id": row["sample_id"],
                "sample_id": row["sample_id"],
                "reason": "measurement_frequency_not_verified",
                "status": "blocks_final_modeling_not_raw_data_retention",
            })
    exclusions.append({
        "exclusion_id": "excl-l254-s33-processing-metadata",
        "entity_type": "processing_metadata",
        "entity_id": "l254-s33-castillo-2011",
        "sample_id": "l254-s33-castillo-2011",
        "reason": "no_processing_rows_in_extracted_bindings",
        "status": "metadata_missing_not_proof_of_no_processing",
    })
    exclusions_frame = pd.DataFrame(exclusions)

    # 10. Provenance inventory for all source and output entities.
    provenance_rows = []
    source_frames = [
        ("study_provenance", PROVENANCE_IN, study_provenance),
        ("sample_attributes", ATTRIBUTES_IN, attributes),
        ("material_components", COMPONENTS_IN, components),
        ("processing_steps", PROCESSING_IN, processing),
        ("combined_samples", COMBINED_IN, combined),
        ("corrected_signatures", SIGNATURES_IN, signatures),
    ]
    for table_name, source_file, frame in source_frames:
        for idx, row in frame.iterrows():
            provenance_rows.append({
                "provenance_id": f"prov-{table_name}-{idx+1:04d}",
                "source_table": table_name,
                "source_file": str(source_file),
                "source_row_index": idx,
                "sample_id": clean(row.get("sample_id", "")),
                "source_hit_id": clean(row.get("source_hit_id", "")),
                "source_date": clean(row.get("source_date", "")),
                "query_sha256": clean(row.get("query_sha256", "")),
                "response_sha256": clean(row.get("response_sha256", "")),
                "source_occurrence_count": clean(row.get("source_occurrence_count", "")),
                "evidence_status": "documented_in_historical_indexed_response",
                "recorded_at": NOW,
            })
    provenance = pd.DataFrame(provenance_rows)

    # Write corpus tables.
    write(studies, STUDIES_OUT)
    write(systems, SYSTEMS_OUT)
    write(fillers, FILLERS_OUT)
    write(samples, SAMPLES_OUT)
    write(composition, COMPOSITION_OUT)
    write(processing_out, PROCESSING_OUT)
    write(measurements, MEASUREMENTS_OUT)
    write(conditions, CONDITIONS_OUT)
    write(provenance, PROVENANCE_OUT)
    write(exclusions_frame, EXCLUSIONS_OUT)
    write(curves, CURVES_OUT)

    # Quality controls.
    checks = []
    def check(cid, description, passed, observed, expected, severity="error"):
        checks.append({
            "check_id": cid, "description": description,
            "passed": bool(passed), "observed": observed,
            "expected": expected, "severity": severity,
        })

    check("Q001", "One study", len(studies) == 1, len(studies), 1)
    check("Q002", "One material system", len(systems) == 1, len(systems), 1)
    check("Q003", "Five filler variants", len(fillers) == 5 and fillers["filler_variant_id"].nunique() == 5, len(fillers), 5)
    check("Q004", "Five distinct aspect ratios", fillers["aspect_ratio"].nunique() == 5 and fillers["aspect_ratio"].notna().all(), sorted(fillers["aspect_ratio"].tolist()), 5)
    check("Q005", "36 unique samples", len(samples) == 36 and samples["sample_id"].nunique() == 36, len(samples), 36)
    check("Q006", "70 composition rows", len(composition) == 70, len(composition), 70)
    check("Q007", "29 electrical measurements", len(measurements) == 29, len(measurements), 29)
    check("Q008", "28 complete composition-conductivity pairs", int((measurements["composition_pair_status"] == "complete").sum()) == 28, int((measurements["composition_pair_status"] == "complete").sum()), 28)
    check("Q009", "Four documented frequencies", int((conditions["condition_status"] == "documented").sum()) == 4, int((conditions["condition_status"] == "documented").sum()), 4)
    check("Q010", "Five independent curves", len(curves) == 5, len(curves), 5)
    check("Q011", "Matrix metadata absent from MWCNT commercial identity", fillers["commercial_name"].map(clean).eq("").all() and fillers["manufacturer"].map(clean).eq("").all(), "checked", True)
    check("Q012", "All conductivity values positive", (measurements["value_numeric"] > 0).all(), "checked", True)
    check("Q013", "All composition values within 0 to 1", composition["canonical_value"].between(0, 1).all(), "checked", True)
    check("Q014", "No curve marked usable for final modeling", not curves["usable_for_final_modeling"].map(as_bool).any(), "checked", True, "warning")
    check("Q015", "s33 missing processing metadata documented", "l254-s33-castillo-2011" in set(exclusions_frame["sample_id"]), "checked", True)

    quality = pd.DataFrame(checks)
    write(quality, QUALITY_OUT)
    failures = quality[(quality["passed"] != True) & (quality["severity"] == "error")]

    output_files = [
        STUDIES_OUT, SYSTEMS_OUT, FILLERS_OUT, SAMPLES_OUT, COMPOSITION_OUT,
        PROCESSING_OUT, MEASUREMENTS_OUT, CONDITIONS_OUT, PROVENANCE_OUT,
        EXCLUSIONS_OUT, CURVES_OUT, QUALITY_OUT,
    ]
    manifest = {
        "generated_at": NOW,
        "corpus_id": "l254-corpus-v1",
        "phase": "2_acquisition_and_curation",
        "corpus_status": "primary_candidate_under_measurement_condition_validation",
        "counts": {
            "studies": len(studies), "material_systems": len(systems),
            "filler_variants": len(fillers), "samples": len(samples),
            "sample_composition": len(composition), "processing_steps": len(processing_out),
            "electrical_measurements": len(measurements), "measurement_conditions": len(conditions),
            "provenance": len(provenance), "exclusions": len(exclusions_frame),
            "curves": len(curves),
        },
        "inputs": [{
            "path": str(path), "sha256": sha256_file(path),
            "bytes": path.stat().st_size if path.is_file() else None,
        } for path in [
            COMBINED_IN, SIGNATURES_IN, COMPONENTS_IN, PROCESSING_IN,
            PROVENANCE_IN, ATTRIBUTES_IN, BLOCK_STATUS_IN, MISSING_PROCESSING_IN,
        ]],
        "outputs": [{
            "path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size,
        } for path in output_files],
        "quality": {
            "checks_total": len(quality),
            "checks_passed": int(quality["passed"].sum()),
            "critical_failures": len(failures),
        },
        "scientific_decisions": [
            "The five MWCNT variants are retained as five separate curves.",
            "Makrolon 2600 and Bayer MaterialScience are matrix metadata only.",
            "MWCNT commercial identities remain unverified.",
            "Density values are retained but density semantic kind remains unverified.",
            "Conductivity unit is S/cm; no numerical unit conversion was performed.",
            "Frequency is assigned only where explicitly documented.",
            "No curve is released for final modeling while measurement conditions remain incomplete.",
        ],
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - INFORME DE CALIDAD DEL CORPUS RELACIONAL DEFINITIVO L254",
        "", f"Fecha: {NOW}", "Corpus: l254-corpus-v1",
        "Estado: primary_candidate_under_measurement_condition_validation", "",
        "CONTEOS",
    ]
    lines.extend(f"- {key}: {value}" for key, value in manifest["counts"].items())
    lines.extend(["", "ESTADO DE CURVAS"])
    for _, row in curves.iterrows():
        lines.append(
            f"- {row['block_id']} | variante={row['filler_variant_id']} | "
            f"pares={row['complete_pair_count']} | frecuencia={row['frequency_documented_count']} | "
            f"estado={row['curve_status']}"
        )
    lines.extend(["", "CONTROLES DE CALIDAD"])
    for _, row in quality.iterrows():
        lines.append(
            f"- {row['check_id']} | {'PASS' if row['passed'] else 'FAIL'} | "
            f"{row['description']} | observado={row['observed']} | esperado={row['expected']}"
        )
    lines.extend([
        "", "DECISION CIENTIFICA",
        "- l254 es el corpus principal candidato de Fase 2.",
        "- Los cinco bloques representan cinco variantes distintas de MWCNT y se conservan separados.",
        "- Ninguna curva queda liberada para modelado final por cobertura incompleta de condiciones de medicion.",
        "- El bloque 1 conserva siete pares completos y es el candidato principal para analisis exploratorio.",
        "- No se imputaron conductividades, frecuencias, procesamiento ni identidades comerciales.",
        "- No se ejecutaron modelos.",
        "", f"Corpus: {OUT}", f"Calidad: {QUALITY_OUT}", f"Manifiesto: {MANIFEST_OUT}",
    ])
    LOG_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("CORPUS RELACIONAL L254 GENERADO")
    for key, value in manifest["counts"].items():
        print(f"{key}: {value}")
    print(f"Controles: {len(quality)}")
    print(f"Fallos criticos: {len(failures)}")
    print(f"Directorio: {OUT}")
    print(f"Informe: {LOG_OUT}")

    if not failures.empty:
        raise ValueError("El corpus se genero, pero fallaron controles criticos")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_OUT.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_OUT}")
        sys.exit(1)
