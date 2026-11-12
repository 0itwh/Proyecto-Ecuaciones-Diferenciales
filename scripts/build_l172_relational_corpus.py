from pathlib import Path
from datetime import datetime
import hashlib
import json
import math
import re
import sys

import pandas as pd

ROOT = Path.cwd()
SRC = ROOT / "data_processed" / "l172_family"
INTERIM = ROOT / "data_interim"
OUT = ROOT / "data_processed" / "l172_corpus"
META = ROOT / "metadata"
LOGS = ROOT / "logs"

OUT.mkdir(parents=True, exist_ok=True)
META.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

MEASUREMENTS_IN = INTERIM / "sparql-bindings-deduplicated.csv"
SAMPLES_IN = SRC / "samples.csv"
PROVENANCE_IN = SRC / "l172-study-provenance.csv"
COMPONENTS_IN = SRC / "l172-material-components.csv"
PROCESSING_IN = SRC / "l172-processing-steps-with-sample-id.csv"
ATTRIBUTES_IN = SRC / "l172-observed-attributes.csv"
CONTEXT_IN = SRC / "l172-attribute-context-25C-19_5.csv"

STUDIES_OUT = OUT / "studies.csv"
SYSTEMS_OUT = OUT / "material_systems.csv"
SAMPLES_OUT = OUT / "samples.csv"
COMPOSITION_OUT = OUT / "sample_composition.csv"
PROCESSING_OUT = OUT / "processing_steps.csv"
MEASUREMENTS_OUT = OUT / "measurements_unresolved.csv"
PROVENANCE_OUT = OUT / "provenance.csv"
EXCLUSIONS_OUT = OUT / "exclusions.csv"

QUALITY_SUMMARY = META / "l172-corpus-quality-summary.csv"
MANIFEST = META / "l172-corpus-manifest.json"
QUALITY_LOG = LOGS / "l172-corpus-quality-report.txt"
ERROR_LOG = LOGS / "l172-corpus-build-error.log"

NOW = datetime.now().astimezone().isoformat(timespec="seconds")
STUDY_ID = "study-l172-huo-2015"
DOI_EXPECTED = "10.1021/acs.jpcc.5b08809"
BLOCK_REASON = "conductivity unit and measurement conditions not verified"


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def read_optional(path):
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def nonempty(value):
    return value is not None and str(value).strip() != ""


def first_nonempty(row, names):
    for name in names:
        if name in row and nonempty(row[name]):
            return str(row[name]).strip()
    return ""


def normalize_sample_id(value):
    text = str(value or "").strip().lower().replace("_", "-")
    match = re.search(r"l172-s(\d+)-huo-2015", text, re.I)
    return f"l172-s{int(match.group(1))}-huo-2015" if match else ""


def safe_float(value):
    try:
        number = float(str(value).strip())
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def bool_text(value):
    return "true" if bool(value) else "false"


def write_csv(frame, path, columns=None):
    if columns is not None:
        for column in columns:
            if column not in frame.columns:
                frame[column] = ""
        frame = frame[columns]
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return frame


def unique_values(frame, column):
    if column not in frame.columns:
        return []
    return sorted({str(v).strip() for v in frame[column] if nonempty(v)})


def source_record(source_table, source_file, row_index, row, entity_type, entity_id):
    return {
        "provenance_id": f"prov-{source_table}-{row_index + 1:04d}",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_table": source_table,
        "source_file": str(source_file),
        "source_row_index": row_index,
        "source_hit_id": first_nonempty(row, ["source_hit_id", "_source_hit_id"]),
        "source_date": first_nonempty(row, ["source_date", "_source_date"]),
        "query_sha256": first_nonempty(row, ["query_sha256", "_query_sha256"]),
        "response_sha256": first_nonempty(row, ["response_sha256", "_response_sha256"]),
        "source_occurrence_count": first_nonempty(row, ["source_occurrence_count"]),
        "evidence_status": first_nonempty(row, ["evidence_status"]) or "documented_in_historical_indexed_response",
        "current_graph_status": first_nonempty(row, ["current_graph_status"]) or "not_reproduced_in_current_sparql_graph",
        "recorded_at": NOW,
    }


def main():
    print("CONSTRUYENDO CORPUS RELACIONAL L172")

    measurements_raw = read_required(MEASUREMENTS_IN)
    samples_raw = read_required(SAMPLES_IN)
    provenance_raw = read_required(PROVENANCE_IN)
    components_raw = read_required(COMPONENTS_IN)
    processing_raw = read_required(PROCESSING_IN)
    attributes_raw = read_required(ATTRIBUTES_IN)
    context_raw = read_optional(CONTEXT_IN)

    # 1. STUDIES
    doi_values = unique_values(provenance_raw, "doi_or_resource")
    confirmed_doi = DOI_EXPECTED if DOI_EXPECTED in doi_values else (doi_values[0] if doi_values else "")
    studies = pd.DataFrame([{
        "study_id": STUDY_ID,
        "study_code": "l172-huo-2015",
        "doi": confirmed_doi,
        "doi_status": "confirmed_in_historical_indexed_response" if confirmed_doi else "not_verified",
        "publication_year": "2015",
        "source_database": "MaterialsMine historical indexed response",
        "current_graph_status": "not_reproduced_in_current_sparql_graph",
        "corpus_status": "auxiliary_quarantine",
        "corpus_status_reason": BLOCK_REASON,
        "created_at": NOW,
    }])

    # 2. MATERIAL SYSTEMS, driven only by observed measurement pairs.
    matrix_col = "Matrix" if "Matrix" in measurements_raw.columns else ""
    filler_col = "Filler" if "Filler" in measurements_raw.columns else ""
    system_pairs = []
    if matrix_col and filler_col:
        pairs = measurements_raw[[matrix_col, filler_col]].drop_duplicates()
        for idx, row in pairs.reset_index(drop=True).iterrows():
            system_pairs.append({
                "material_system_id": f"ms-l172-{idx + 1:02d}",
                "study_id": STUDY_ID,
                "matrix_original": row[matrix_col],
                "filler_original": row[filler_col],
                "matrix_normalized": "PVDF" if "vinylidene fluoride" in row[matrix_col].lower() else "",
                "filler_normalized": "Fe3O4@BaTiO3 core-shell nanoparticles" if "barium titanate" in row[filler_col].lower() else "",
                "normalization_status": "partially_normalized",
                "evidence_status": "observed_in_deduplicated_measurement_response",
            })
    systems = pd.DataFrame(system_pairs)
    pair_to_system = {
        (row["matrix_original"], row["filler_original"]): row["material_system_id"]
        for row in system_pairs
    }

    # 3. SAMPLES
    samples = samples_raw.copy()
    samples["sample_id"] = samples["sample_id"].map(normalize_sample_id)
    samples["study_id"] = STUDY_ID
    samples["material_system_id"] = ""
    samples["sample_status"] = "historical_sample_inventory"
    samples["usable_for_modeling"] = "false"
    samples["modeling_block_reason"] = BLOCK_REASON

    # Assign systems only where measurement evidence exists.
    measurement_sample_system = {}
    for _, row in measurements_raw.iterrows():
        sid = normalize_sample_id(first_nonempty(row, ["sample_id", "Sample"]))
        pair = (first_nonempty(row, ["Matrix"]), first_nonempty(row, ["Filler"]))
        if sid and pair in pair_to_system:
            measurement_sample_system[sid] = pair_to_system[pair]
    samples["material_system_id"] = samples["sample_id"].map(measurement_sample_system).fillna("")

    # 4. SAMPLE COMPOSITION from the 235 measurements, deduplicated by sample/fraction.
    composition_records = []
    seen_composition = set()
    for row_index, row in measurements_raw.iterrows():
        sid = normalize_sample_id(first_nonempty(row, ["sample_id", "Sample"]))
        volume_raw = first_nonempty(row, ["VolumeFraction"])
        volume_value = safe_float(volume_raw)
        key = (sid, volume_raw, first_nonempty(row, ["Matrix"]), first_nonempty(row, ["Filler"]))
        if not sid or not nonempty(volume_raw) or key in seen_composition:
            continue
        seen_composition.add(key)
        composition_records.append({
            "composition_id": f"comp-{len(composition_records) + 1:04d}",
            "sample_id": sid,
            "study_id": STUDY_ID,
            "material_system_id": measurement_sample_system.get(sid, ""),
            "basis": "volume_fraction",
            "value_original": volume_raw,
            "unit_original": "1",
            "value_numeric": volume_value,
            "canonical_value": volume_value,
            "canonical_unit": "1",
            "transformation": "numeric_parse_only",
            "source_status": "observed_in_deduplicated_measurement_response",
            "source_row_index": row_index,
        })
    composition = pd.DataFrame(composition_records)

    # 5. PROCESSING
    processing = processing_raw.copy()
    processing["sample_id"] = processing["sample_id"].map(normalize_sample_id)
    processing["study_id"] = STUDY_ID
    processing["processing_record_id"] = [f"proc-{i + 1:04d}" for i in range(len(processing))]
    processing["record_status"] = processing["sample_id"].map(lambda x: "sample_linked" if x else "study_level_unresolved")
    processing["usable_for_modeling"] = "false"

    # 6. MEASUREMENTS UNRESOLVED
    measurement_records = []
    for row_index, row in measurements_raw.iterrows():
        sid = normalize_sample_id(first_nonempty(row, ["sample_id", "Sample"]))
        cond_raw = first_nonempty(row, ["Conductivity"])
        cond_value = safe_float(cond_raw)
        unit_raw = first_nonempty(row, ["UnitOfMeasure"])
        volume_raw = first_nonempty(row, ["VolumeFraction"])
        pair = (first_nonempty(row, ["Matrix"]), first_nonempty(row, ["Filler"]))
        measurement_records.append({
            "measurement_id": f"meas-l172-{row_index + 1:04d}",
            "study_id": STUDY_ID,
            "sample_id": sid,
            "material_system_id": pair_to_system.get(pair, ""),
            "property_name": "electrical_conductivity",
            "conductivity_value_original": cond_raw,
            "conductivity_value_numeric": cond_value,
            "conductivity_unit_original": unit_raw,
            "filler_volume_fraction_original": volume_raw,
            "measurement_temperature_original": "",
            "measurement_frequency_original": "",
            "measurement_method_original": "",
            "measurement_status": "blocked_missing_unit_and_conditions",
            "usable_for_modeling": "false",
            "exclusion_reason": BLOCK_REASON,
            "source_hit_id": first_nonempty(row, ["_source_hit_id"]),
            "source_date": first_nonempty(row, ["_source_date"]),
            "query_sha256": first_nonempty(row, ["_query_sha256"]),
            "response_sha256": first_nonempty(row, ["_response_sha256"]),
            "source_occurrence_count": first_nonempty(row, ["source_occurrence_count"]),
            "source_row_index": row_index,
        })
    measurements = pd.DataFrame(measurement_records)

    # 7. PROVENANCE
    provenance_records = []
    source_specs = [
        ("measurements", MEASUREMENTS_IN, measurements_raw, "measurement", lambda i, r: f"meas-l172-{i + 1:04d}"),
        ("samples", SAMPLES_IN, samples_raw, "sample", lambda i, r: normalize_sample_id(first_nonempty(r, ["sample_id"]))),
        ("study_provenance", PROVENANCE_IN, provenance_raw, "study", lambda i, r: STUDY_ID),
        ("components", COMPONENTS_IN, components_raw, "component", lambda i, r: f"component-source-{i + 1:04d}"),
        ("processing", PROCESSING_IN, processing_raw, "processing", lambda i, r: f"proc-{i + 1:04d}"),
        ("attributes", ATTRIBUTES_IN, attributes_raw, "attribute", lambda i, r: f"attribute-source-{i + 1:04d}"),
    ]
    for source_table, source_file, frame, entity_type, id_func in source_specs:
        for row_index, row in frame.iterrows():
            provenance_records.append(source_record(source_table, source_file, row_index, row, entity_type, id_func(row_index, row)))
    provenance = pd.DataFrame(provenance_records)

    # 8. EXCLUSIONS/QUARANTINE
    exclusions = []
    exclusions.append({
        "exclusion_id": "excl-l172-0001",
        "entity_type": "attribute",
        "entity_id": "l172-s8-huo-2015-attribute-19.5",
        "sample_id": "l172-s8-huo-2015",
        "value_original": "19.5",
        "unit_original": "",
        "reason": "unresolved defective attribute type file:///apps/whyis/nan",
        "status": "quarantined",
        "usable_for_modeling": "false",
    })
    exclusions.append({
        "exclusion_id": "excl-l172-0002",
        "entity_type": "attribute",
        "entity_id": "l172-s17-huo-2015-temperature-25C",
        "sample_id": "l172-s17-huo-2015",
        "value_original": "25.0",
        "unit_original": "Celsius",
        "reason": "general sample temperature not verified as conductivity measurement temperature",
        "status": "context_unresolved",
        "usable_for_modeling": "false",
    })
    exclusions.append({
        "exclusion_id": "excl-l172-0003",
        "entity_type": "query_candidate",
        "entity_id": "Id6llYcB9tZWhu3C0Bqw",
        "sample_id": "",
        "value_original": "Highlighting Target Properties Using Sequence Generators and Area Marks",
        "unit_original": "",
        "reason": "chart title rejected as invalid SPARQL query",
        "status": "excluded",
        "usable_for_modeling": "false",
    })
    exclusions_frame = pd.DataFrame(exclusions)

    # Write outputs.
    write_csv(studies, STUDIES_OUT)
    write_csv(systems, SYSTEMS_OUT)
    write_csv(samples, SAMPLES_OUT)
    write_csv(composition, COMPOSITION_OUT)
    write_csv(processing, PROCESSING_OUT)
    write_csv(measurements, MEASUREMENTS_OUT)
    write_csv(provenance, PROVENANCE_OUT)
    write_csv(exclusions_frame, EXCLUSIONS_OUT)

    # QUALITY CHECKS
    checks = []
    def add_check(check_id, description, passed, observed, expected, severity="error"):
        checks.append({
            "check_id": check_id,
            "description": description,
            "passed": bool_text(passed),
            "observed": observed,
            "expected": expected,
            "severity": severity,
        })

    sample_ids = set(samples["sample_id"])
    measurement_sample_ids = set(measurements["sample_id"])
    add_check("Q001", "Exactly 18 unique samples", len(samples) == 18 and samples["sample_id"].nunique() == 18, f"rows={len(samples)}, unique={samples['sample_id'].nunique()}", "18 rows and 18 unique")
    add_check("Q002", "Exactly 235 unique measurements", len(measurements) == 235 and measurements["measurement_id"].nunique() == 235, f"rows={len(measurements)}, unique={measurements['measurement_id'].nunique()}", "235 rows and 235 unique")
    add_check("Q003", "Measurement foreign keys resolve to samples", measurement_sample_ids.issubset(sample_ids), sorted(measurement_sample_ids - sample_ids), "empty unresolved set")
    add_check("Q004", "Five unique observed volume fractions", composition["canonical_value"].nunique() == 5, composition["canonical_value"].nunique(), 5)
    fraction_values = [safe_float(v) for v in composition["canonical_value"]]
    add_check("Q005", "All fractions within [0,1]", all(v is not None and 0 <= v <= 1 for v in fraction_values), fraction_values, "all in [0,1]")
    conductivity_values = [safe_float(v) for v in measurements["conductivity_value_numeric"]]
    add_check("Q006", "All conductivity values finite and positive", all(v is not None and v > 0 for v in conductivity_values), f"valid={sum(v is not None and v > 0 for v in conductivity_values)}/{len(conductivity_values)}", "235/235")
    missing_units = int((measurements["conductivity_unit_original"].str.strip() == "").sum())
    add_check("Q007", "Conductivity unit absent is explicitly documented", missing_units == 235, missing_units, 235, "warning")
    blocked = int((measurements["measurement_status"] == "blocked_missing_unit_and_conditions").sum())
    add_check("Q008", "All measurements blocked pending unit and conditions", blocked == 235, blocked, 235)
    unusable = int((measurements["usable_for_modeling"] == "false").sum())
    add_check("Q009", "All measurements unusable for modeling", unusable == 235, unusable, 235)
    duplicate_measurements = int(measurements.duplicated(subset=["sample_id", "conductivity_value_original", "filler_volume_fraction_original", "conductivity_unit_original"], keep=False).sum())
    add_check("Q010", "No exact scientific-key duplicates in measurements", duplicate_measurements == 0, duplicate_measurements, 0)
    add_check("Q011", "Study DOI confirmed", confirmed_doi == DOI_EXPECTED, confirmed_doi, DOI_EXPECTED)
    add_check("Q012", "Processing table preserves 15 rows", len(processing) == 15, len(processing), 15)
    add_check("Q013", "At least one material system recovered", len(systems) >= 1, len(systems), ">=1")

    quality = pd.DataFrame(checks)
    write_csv(quality, QUALITY_SUMMARY)

    error_failures = quality[(quality["passed"] != "true") & (quality["severity"] == "error")]
    warning_failures = quality[(quality["passed"] != "true") & (quality["severity"] == "warning")]

    output_files = [
        STUDIES_OUT, SYSTEMS_OUT, SAMPLES_OUT, COMPOSITION_OUT,
        PROCESSING_OUT, MEASUREMENTS_OUT, PROVENANCE_OUT, EXCLUSIONS_OUT,
        QUALITY_SUMMARY,
    ]
    manifest = {
        "generated_at": NOW,
        "corpus_id": "l172-corpus-v1",
        "phase": "2_acquisition_and_curation",
        "corpus_status": "auxiliary_quarantine",
        "inputs": [
            {"path": str(p), "sha256": sha256_file(p), "bytes": p.stat().st_size if p.is_file() else None}
            for p in [MEASUREMENTS_IN, SAMPLES_IN, PROVENANCE_IN, COMPONENTS_IN, PROCESSING_IN, ATTRIBUTES_IN, CONTEXT_IN]
        ],
        "outputs": [
            {"path": str(p), "sha256": sha256_file(p), "bytes": p.stat().st_size}
            for p in output_files
        ],
        "counts": {
            "studies": len(studies),
            "material_systems": len(systems),
            "samples": len(samples),
            "sample_composition": len(composition),
            "processing_steps": len(processing),
            "measurements_unresolved": len(measurements),
            "provenance": len(provenance),
            "exclusions": len(exclusions_frame),
        },
        "quality": {
            "checks_total": len(quality),
            "checks_passed": int((quality["passed"] == "true").sum()),
            "error_failures": len(error_failures),
            "warning_failures": len(warning_failures),
        },
        "methodological_notes": [
            "No conductivity units were inferred.",
            "No measurement conditions were assigned from general sample attributes.",
            "No averages, conversions, interpolation, percolation fitting, or modeling were performed.",
            "The corpus remains in auxiliary quarantine until unit and measurement conditions are verified.",
        ],
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - INFORME DE CALIDAD DEL CORPUS RELACIONAL L172",
        "",
        f"Fecha: {NOW}",
        "Corpus: l172-corpus-v1",
        "Estado: auxiliary_quarantine",
        "",
        "CONTEOS",
    ]
    for name, count in manifest["counts"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "CONTROLES DE CALIDAD"])
    for check in checks:
        lines.append(
            f"- {check['check_id']} | {'PASS' if check['passed']=='true' else 'FAIL'} | "
            f"{check['description']} | observado={check['observed']} | esperado={check['expected']} | severidad={check['severity']}"
        )
    lines.extend([
        "",
        "DECISION CIENTIFICA",
        "- La familia l172 se conserva como corpus auxiliar en cuarentena.",
        "- Las 235 mediciones no son aptas para modelado.",
        "- La unidad de conductividad y las condiciones de medicion siguen no verificadas.",
        "- 25 C permanece como atributo general de muestra, no como temperatura de la medicion electrica.",
        "- 19.5 permanece excluido por tipo defectuoso y unidad ausente.",
        "",
        f"Manifiesto: {MANIFEST}",
        f"Resumen de calidad: {QUALITY_SUMMARY}",
    ])
    QUALITY_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("")
    print("CORPUS RELACIONAL GENERADO")
    for name, count in manifest["counts"].items():
        print(f"{name}: {count}")
    print(f"Controles: {len(quality)}")
    print(f"Fallos de error: {len(error_failures)}")
    print(f"Fallos de advertencia: {len(warning_failures)}")
    print(f"Directorio: {OUT}")
    print(f"Informe: {QUALITY_LOG}")

    if not error_failures.empty:
        raise ValueError(
            "El corpus se genero, pero uno o mas controles de calidad criticos fallaron"
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_LOG.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print("")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_LOG}")
        sys.exit(1)
