from pathlib import Path
from datetime import datetime
import csv
import json
import re
import sys

import pandas as pd


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

INPUT_JSON = (
    ROOT
    / "data_interim"
    / "l172-family-bindings-deduplicated.json"
)

PROCESSING_INPUT = (
    ROOT
    / "data_processed"
    / "l172_family"
    / "l172-processing-steps.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data_processed"
    / "l172_family"
)

METADATA_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

SAMPLES_FILE = OUTPUT_DIR / "samples.csv"
PROCESSING_OUTPUT = (
    OUTPUT_DIR
    / "l172-processing-steps-with-sample-id.csv"
)
CONTEXT_FILE = (
    OUTPUT_DIR
    / "l172-attribute-context-25C-19_5.csv"
)
CONTEXT_JSON = (
    METADATA_DIR
    / "l172-attribute-context-25C-19_5.json"
)
LOG_FILE = (
    LOG_DIR
    / "l172-samples-processing-context-extraction.log"
)
ERROR_FILE = (
    LOG_DIR
    / "l172-samples-processing-context-extraction-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)

SAMPLE_ID_PATTERN = re.compile(
    r"L172[_-]S(\d+)[_-]Huo[_-]2015",
    flags=re.IGNORECASE,
)

TARGET_VALUES = {19.5, 25.0}


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def normalise_sample_id(value):
    """Extrae y normaliza l172-sN-huo-2015 desde una URI o texto."""

    if value is None:
        return None

    match = SAMPLE_ID_PATTERN.search(str(value))

    if not match:
        return None

    number = int(match.group(1))

    return f"l172-s{number}-huo-2015"


def sample_number(sample_id):
    if not sample_id:
        return 10**9

    match = re.search(
        r"-s(\d+)-",
        sample_id,
        flags=re.IGNORECASE,
    )

    return int(match.group(1)) if match else 10**9


def first_nonempty(row, names):
    for name in names:
        value = row.get(name)

        if value not in (None, ""):
            return value

    return None


def as_float(value):
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def query_map(document):
    """Relaciona query_sha256 con el texto y metadatos de su consulta."""

    result = {}

    for item in document.get("query_inventory", []):
        if not isinstance(item, dict):
            continue

        sha = item.get("query_sha256")

        if not sha:
            continue

        result.setdefault(
            sha,
            {
                "query_preview": item.get("query_preview"),
                "query_variables": item.get("variables"),
                "query_binding_count": item.get("binding_count"),
                "query_hit_position": item.get("hit_position"),
                "query_hit_id": item.get("hit_id"),
                "query_source_date": item.get("date"),
            },
        )

    return result


def safe_json(value):
    if value in (None, ""):
        return ""

    if isinstance(value, str):
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
    )


# ============================================================
# EXTRACCION DE MUESTRAS
# ============================================================

def build_samples(bindings):
    records = {}

    for binding_index, row in enumerate(bindings):
        if not isinstance(row, dict):
            continue

        sample_id = first_nonempty(
            row,
            ["sample_id"],
        )

        if not sample_id:
            sample_id = normalise_sample_id(
                first_nonempty(
                    row,
                    [
                        "sample",
                        "Sample",
                        "this",
                        "processing_step",
                        "step",
                    ],
                )
            )

        if not sample_id:
            continue

        sample_id = str(sample_id).lower()

        sample_uri = first_nonempty(
            row,
            ["sample", "Sample", "this"],
        )

        if not sample_uri:
            sample_uri = (
                "http://materialsmine.org/sample/"
                + sample_id
            )

        entry = records.setdefault(
            sample_id,
            {
                "sample_id": sample_id,
                "sample_number": sample_number(sample_id),
                "sample_uri": sample_uri,
                "study_code": "l172-huo-2015",
                "source_database": "MaterialsMine historical indexed response",
                "evidence_status": "documented_in_historical_indexed_response",
                "current_graph_status": "not_reproduced_in_current_sparql_graph",
                "first_binding_index": binding_index,
                "source_hit_ids": set(),
                "source_dates": set(),
                "query_sha256_values": set(),
                "response_sha256_values": set(),
                "source_occurrence_total": 0,
                "binding_indices": [],
            },
        )

        entry["binding_indices"].append(binding_index)

        for source_field, target_field in [
            ("_source_hit_id", "source_hit_ids"),
            ("_source_date", "source_dates"),
            ("_query_sha256", "query_sha256_values"),
            ("_response_sha256", "response_sha256_values"),
        ]:
            value = row.get(source_field)

            if value:
                entry[target_field].add(str(value))

        occurrence = row.get("source_occurrence_count")

        try:
            entry["source_occurrence_total"] += int(occurrence or 0)
        except (TypeError, ValueError):
            pass

    output = []

    for entry in records.values():
        for field in [
            "source_hit_ids",
            "source_dates",
            "query_sha256_values",
            "response_sha256_values",
        ]:
            entry[field] = "|".join(
                sorted(entry[field])
            )

        entry["binding_indices"] = "|".join(
            str(index)
            for index in sorted(entry["binding_indices"])
        )

        output.append(entry)

    output.sort(
        key=lambda item: item["sample_number"]
    )

    return output


# ============================================================
# ENRIQUECIMIENTO DE PROCESAMIENTO
# ============================================================

def enrich_processing():
    if not PROCESSING_INPUT.is_file():
        raise FileNotFoundError(
            f"No se encontro: {PROCESSING_INPUT}"
        )

    frame = pd.read_csv(
        PROCESSING_INPUT,
        dtype=str,
        keep_default_na=False,
    )

    if "sample_id" not in frame.columns:
        frame["sample_id"] = ""

    if "processing_step" not in frame.columns:
        raise ValueError(
            "Falta la columna processing_step"
        )

    derived = []
    derivation_status = []

    for _, row in frame.iterrows():
        existing = str(row.get("sample_id", "")).strip()
        from_uri = normalise_sample_id(
            row.get("processing_step")
        )

        if existing:
            derived.append(existing.lower())
            derivation_status.append(
                "source_sample_id_retained"
            )

        elif from_uri:
            derived.append(from_uri)
            derivation_status.append(
                "derived_from_processing_step_uri"
            )

        else:
            derived.append("")
            derivation_status.append(
                "not_derivable"
            )

    frame["sample_id"] = derived
    frame["sample_id_derivation"] = derivation_status
    frame["sample_id_derivation_rule"] = (
        "regex L172[_-]S(n)[_-]Huo[_-]2015 from processing_step URI"
    )

    frame.to_csv(
        PROCESSING_OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    return frame


# ============================================================
# CONTEXTO DE 25 C Y 19.5
# ============================================================

def extract_target_context(bindings, queries):
    records = []

    for binding_index, row in enumerate(bindings):
        if not isinstance(row, dict):
            continue

        for schema_name, type_field, value_field, unit_field in [
            (
                "AttrType_value_Units",
                "AttrType",
                "value",
                "Units",
            ),
            (
                "attrType_attrValue_attrUnits",
                "attrType",
                "attrValue",
                "attrUnits",
            ),
        ]:
            numeric = as_float(row.get(value_field))

            if numeric not in TARGET_VALUES:
                continue

            query_sha = row.get("_query_sha256")
            query_context = queries.get(
                query_sha,
                {},
            )

            context = {
                "binding_index": binding_index,
                "sample_id": normalise_sample_id(
                    first_nonempty(
                        row,
                        [
                            "sample_id",
                            "sample",
                            "Sample",
                            "this",
                            "processing_step",
                            "step",
                        ],
                    )
                ),
                "attribute_schema": schema_name,
                "attribute_type_original": row.get(type_field),
                "value_original": row.get(value_field),
                "value_numeric": numeric,
                "unit_original": row.get(unit_field),
                "source_hit_id": row.get("_source_hit_id"),
                "source_index": row.get("_source_index"),
                "source_date": row.get("_source_date"),
                "query_sha256": query_sha,
                "response_sha256": row.get("_response_sha256"),
                "binding_position": row.get("_binding_position"),
                "source_occurrence_count": row.get("source_occurrence_count"),
                "source_occurrences": safe_json(
                    row.get("source_occurrences")
                ),
                "query_variables": query_context.get("query_variables"),
                "query_binding_count": query_context.get("query_binding_count"),
                "query_hit_position": query_context.get("query_hit_position"),
                "query_hit_id": query_context.get("query_hit_id"),
                "query_source_date": query_context.get("query_source_date"),
                "query_preview": query_context.get("query_preview"),
                "interpretation_status": (
                    "temperature_candidate"
                    if numeric == 25.0
                    else "unknown_attribute_type"
                ),
                "evidence_status": "documented_in_historical_indexed_response",
                "current_graph_status": "not_reproduced_in_current_sparql_graph",
            }

            records.append(context)

    return records


# ============================================================
# EJECUCION PRINCIPAL
# ============================================================

def main():
    print("EXTRAYENDO MUESTRAS, SAMPLE_ID Y CONTEXTO SPARQL")

    if not INPUT_JSON.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_JSON}"
        )

    document = json.loads(
        INPUT_JSON.read_text(
            encoding="utf-8-sig"
        )
    )

    bindings = document.get("bindings", [])

    if not isinstance(bindings, list):
        raise ValueError(
            "El campo bindings no es una lista"
        )

    if len(bindings) != 49:
        raise ValueError(
            "Se esperaban 49 bindings unicos, "
            f"pero se encontraron {len(bindings)}"
        )

    queries = query_map(document)

    samples = build_samples(bindings)
    samples_frame = pd.DataFrame(samples)

    expected_samples = {
        f"l172-s{number}-huo-2015"
        for number in range(1, 19)
    }
    observed_samples = set(
        samples_frame["sample_id"]
        if not samples_frame.empty
        else []
    )

    missing_samples = sorted(
        expected_samples - observed_samples,
        key=sample_number,
    )
    extra_samples = sorted(
        observed_samples - expected_samples,
        key=sample_number,
    )

    samples_frame.to_csv(
        SAMPLES_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    processing_frame = enrich_processing()

    contexts = extract_target_context(
        bindings,
        queries,
    )
    context_frame = pd.DataFrame(contexts)

    preferred_context_columns = [
        "binding_index",
        "sample_id",
        "attribute_schema",
        "attribute_type_original",
        "value_original",
        "value_numeric",
        "unit_original",
        "interpretation_status",
        "source_hit_id",
        "source_index",
        "source_date",
        "query_sha256",
        "response_sha256",
        "binding_position",
        "source_occurrence_count",
        "source_occurrences",
        "query_variables",
        "query_binding_count",
        "query_hit_position",
        "query_hit_id",
        "query_source_date",
        "query_preview",
        "evidence_status",
        "current_graph_status",
    ]

    if context_frame.empty:
        context_frame = pd.DataFrame(
            columns=preferred_context_columns
        )
    else:
        context_frame = context_frame.reindex(
            columns=preferred_context_columns
        )

    context_frame.to_csv(
        CONTEXT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    context_payload = {
        "generated_at": CHECKED_AT,
        "input_file": str(INPUT_JSON),
        "target_values": sorted(TARGET_VALUES),
        "records": contexts,
        "notes": [
            "25.0 Celsius remains a temperature candidate until the query context is reviewed.",
            "19.5 remains uninterpretable because its attribute type is file:///apps/whyis/nan.",
            "No unit conversion, averaging, or modeling was performed.",
        ],
    }

    CONTEXT_JSON.write_text(
        json.dumps(
            context_payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    processing_derived = int(
        (
            processing_frame["sample_id_derivation"]
            == "derived_from_processing_step_uri"
        ).sum()
    )
    processing_unresolved = int(
        (
            processing_frame["sample_id_derivation"]
            == "not_derivable"
        ).sum()
    )

    values_found = sorted(
        context_frame["value_numeric"].tolist()
        if not context_frame.empty
        else []
    )

    log_lines = [
        "FASE 2 - MUESTRAS, SAMPLE_ID Y CONTEXTO SPARQL L172",
        "",
        f"Fecha: {CHECKED_AT}",
        f"Entrada: {INPUT_JSON}",
        f"Bindings de entrada: {len(bindings)}",
        "",
        "SAMPLES.CSV",
        f"Muestras extraidas: {len(samples_frame)}",
        f"Muestras esperadas: {len(expected_samples)}",
        f"Muestras faltantes: {len(missing_samples)}",
        f"Muestras adicionales: {len(extra_samples)}",
        "",
        "LISTA DE MUESTRAS",
    ]

    log_lines.extend(
        f"- {sample_id}"
        for sample_id in sorted(
            observed_samples,
            key=sample_number,
        )
    )

    log_lines.extend(
        [
            "",
            "PROCESAMIENTO",
            f"Filas de procesamiento: {len(processing_frame)}",
            f"sample_id derivados desde URI: {processing_derived}",
            f"sample_id no derivables: {processing_unresolved}",
            "",
            "CONTEXTO DE 25 C Y 19.5",
            f"Registros encontrados: {len(context_frame)}",
            "Valores: "
            + (
                ", ".join(str(value) for value in values_found)
                if values_found
                else "ninguno"
            ),
        ]
    )

    for _, row in context_frame.iterrows():
        log_lines.extend(
            [
                "",
                f"Valor: {row['value_original']}",
                f"Tipo: {row['attribute_type_original']}",
                f"Unidad: {row['unit_original'] or '[VACIO]'}",
                f"Estado: {row['interpretation_status']}",
                f"Hit: {row['source_hit_id']}",
                f"Fecha: {row['source_date']}",
                f"Variables de consulta: {row['query_variables']}",
                "Consulta:",
                str(row['query_preview'] or "[NO DISPONIBLE]"),
            ]
        )

    log_lines.extend(
        [
            "",
            "VALIDACION",
            (
                "samples.csv completo: "
                + ("SI" if not missing_samples and len(samples_frame) == 18 else "NO")
            ),
            (
                "25.0 recuperado: "
                + ("SI" if 25.0 in values_found else "NO")
            ),
            (
                "19.5 recuperado: "
                + ("SI" if 19.5 in values_found else "NO")
            ),
            "",
            "ADVERTENCIAS",
            "- sample_id se deriva de URI sin modificar la evidencia original.",
            "- Las filas originales de procesamiento no se sobrescriben.",
            "- 25 C permanece como candidato hasta revisar su consulta SPARQL.",
            "- 19.5 permanece sin significado por su tipo defectuoso.",
            "- No se normalizaron unidades.",
            "- No se calcularon medias.",
            "- No se ejecutaron modelos.",
            "",
            f"Samples: {SAMPLES_FILE}",
            f"Procesamiento enriquecido: {PROCESSING_OUTPUT}",
            f"Contexto CSV: {CONTEXT_FILE}",
            f"Contexto JSON: {CONTEXT_JSON}",
        ]
    )

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    if len(samples_frame) != 18 or missing_samples:
        raise ValueError(
            "La tabla samples.csv no contiene exactamente las 18 muestras esperadas"
        )

    if set(values_found) != TARGET_VALUES:
        raise ValueError(
            "No se recuperaron exactamente los valores objetivo 19.5 y 25.0"
        )

    print("")
    print("EXTRACCION COMPLETADA")
    print(f"Muestras: {len(samples_frame)}")
    print(f"Procesamiento: {len(processing_frame)}")
    print(f"sample_id derivados: {processing_derived}")
    print(f"sample_id no derivables: {processing_unresolved}")
    print(f"Contextos objetivo: {len(context_frame)}")
    print(f"Valores: {values_found}")
    print(f"Samples: {SAMPLES_FILE}")
    print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_FILE.write_text(
            f"{type(error).__name__}: {error}\n",
            encoding="utf-8",
        )
        print("")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_FILE}")
        sys.exit(1)
