from pathlib import Path
from datetime import datetime
import hashlib
import json
import sys

import pandas as pd


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

INPUT_FILE = (
    ROOT
    / "data_interim"
    / "l172-family-bindings-deduplicated.json"
)

OUTPUT_DIR = (
    ROOT
    / "data_processed"
    / "l172_family"
)

METADATA_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

METADATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

PROVENANCE_FILE = (
    OUTPUT_DIR
    / "l172-study-provenance.csv"
)

COMPONENTS_FILE = (
    OUTPUT_DIR
    / "l172-material-components.csv"
)

PROCESSING_FILE = (
    OUTPUT_DIR
    / "l172-processing-steps.csv"
)

ATTRIBUTES_FILE = (
    OUTPUT_DIR
    / "l172-observed-attributes.csv"
)

UNCLASSIFIED_FILE = (
    OUTPUT_DIR
    / "l172-unclassified-bindings.csv"
)

MANIFEST_FILE = (
    METADATA_DIR
    / "l172-curated-tables-manifest.json"
)

SUMMARY_FILE = (
    METADATA_DIR
    / "l172-curated-tables-summary.csv"
)

LOG_FILE = (
    LOG_DIR
    / "l172-curated-tables-extraction.log"
)

ERROR_FILE = (
    LOG_DIR
    / "l172-curated-tables-extraction-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def clean_value(value):
    """
    Convierte valores vacíos, NaN y estructuras complejas
    en una representación segura para CSV.
    """

    if value is None:
        return None

    if isinstance(value, float) and pd.isna(value):
        return None

    if isinstance(value, (dict, list)):
        return json.dumps(
            value,
            ensure_ascii=False,
        )

    return value


def get_first(row, names):
    """
    Recupera el primer campo no vacío de una lista.
    """

    for name in names:
        value = row.get(name)

        if value not in (None, ""):
            return clean_value(value)

    return None


def scientific_payload(row):
    """
    Conserva solamente campos científicos y de trazabilidad.
    """

    excluded = {
        "source_occurrences",
    }

    return {
        key: clean_value(value)
        for key, value in row.items()
        if key not in excluded
    }


def source_metadata(row):
    """
    Extrae la trazabilidad del binding histórico.
    """

    return {
        "source_hit_id": row.get(
            "_source_hit_id"
        ),
        "source_index": row.get(
            "_source_index"
        ),
        "source_date": row.get(
            "_source_date"
        ),
        "query_sha256": row.get(
            "_query_sha256"
        ),
        "response_sha256": row.get(
            "_response_sha256"
        ),
        "binding_position": row.get(
            "_binding_position"
        ),
        "source_occurrence_count": row.get(
            "source_occurrence_count"
        ),
    }


def write_csv(records, path, preferred_columns):
    """
    Escribe siempre una cabecera, incluso si no hay filas.
    """

    all_columns = set(preferred_columns)

    for record in records:
        all_columns.update(record.keys())

    remaining = sorted(
        column
        for column in all_columns
        if column not in preferred_columns
    )

    columns = preferred_columns + remaining

    frame = pd.DataFrame(
        records,
        columns=columns,
    )

    frame.to_csv(
        path,
        index=False,
        encoding="utf-8-sig",
    )

    return frame


def file_sha256(path):
    if not path.is_file():
        return None

    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


# ============================================================
# CLASIFICACION DE BINDINGS
# ============================================================

def classify_binding(row):
    """
    Clasifica cada binding por sus variables observadas.

    Una fila puede alimentar más de una tabla cuando contiene,
    por ejemplo, DOI y etiqueta de proceso.
    """

    keys = {
        key
        for key, value in row.items()
        if value not in (None, "")
    }

    classifications = []

    if keys.intersection(
        {
            "DOI",
            "doi",
            "sample_label",
            "process_label",
        }
    ):
        classifications.append("provenance")

    if keys.intersection(
        {
            "std_name",
            "role",
            "attrType",
            "attrValue",
            "attrUnits",
            "fullLabel",
        }
    ):
        classifications.append("components")

    if keys.intersection(
        {
            "step",
            "param_label",
            "Descr",
            "process_label",
        }
    ):
        classifications.append("processing")

    if keys.intersection(
        {
            "AttrType",
            "value",
            "Units",
            "attrType",
            "attrValue",
            "attrUnits",
        }
    ):
        classifications.append("attributes")

    if not classifications:
        classifications.append("unclassified")

    return classifications


# ============================================================
# CONSTRUCTORES DE TABLAS
# ============================================================

def provenance_record(row):
    record = {
        "sample_id": row.get("sample_id"),
        "doi_or_resource": get_first(
            row,
            ["DOI", "doi"],
        ),
        "sample_label": row.get(
            "sample_label"
        ),
        "process_label": row.get(
            "process_label"
        ),
        "evidence_status": (
            "documented_in_historical_indexed_response"
        ),
        "current_graph_status": (
            "not_reproduced_in_current_sparql_graph"
        ),
    }

    record.update(
        source_metadata(row)
    )

    return record


def component_record(row):
    record = {
        "sample_id": row.get("sample_id"),
        "standard_name": row.get(
            "std_name"
        ),
        "component_role": row.get(
            "role"
        ),
        "attribute_type": row.get(
            "attrType"
        ),
        "attribute_value_original": row.get(
            "attrValue"
        ),
        "attribute_unit_original": row.get(
            "attrUnits"
        ),
        "full_label": row.get(
            "fullLabel"
        ),
        "canonical_value": None,
        "canonical_unit": None,
        "transformation": None,
        "evidence_status": (
            "documented_in_historical_indexed_response"
        ),
    }

    record.update(
        source_metadata(row)
    )

    return record


def processing_record(row):
    record = {
        "sample_id": row.get("sample_id"),
        "process_label": row.get(
            "process_label"
        ),
        "processing_step": row.get(
            "step"
        ),
        "parameter_label": row.get(
            "param_label"
        ),
        "description_original": row.get(
            "Descr"
        ),
        "normalized_parameter": None,
        "canonical_value": None,
        "canonical_unit": None,
        "transformation": None,
        "evidence_status": (
            "documented_in_historical_indexed_response"
        ),
    }

    record.update(
        source_metadata(row)
    )

    return record


def attribute_records(row):
    """
    Genera atributos tanto para la estructura:
    AttrType/value/Units
    como para:
    attrType/attrValue/attrUnits.
    """

    records = []

    if any(
        row.get(name) not in (None, "")
        for name in [
            "AttrType",
            "value",
            "Units",
        ]
    ):
        record = {
            "sample_id": row.get("sample_id"),
            "attribute_schema": (
                "AttrType_value_Units"
            ),
            "attribute_type": row.get(
                "AttrType"
            ),
            "value_original": row.get(
                "value"
            ),
            "unit_original": row.get(
                "Units"
            ),
            "standard_name": None,
            "component_role": None,
            "full_label": None,
            "canonical_value": None,
            "canonical_unit": None,
            "transformation": None,
            "evidence_status": (
                "documented_in_historical_indexed_response"
            ),
        }

        record.update(
            source_metadata(row)
        )

        records.append(record)

    if any(
        row.get(name) not in (None, "")
        for name in [
            "attrType",
            "attrValue",
            "attrUnits",
        ]
    ):
        record = {
            "sample_id": row.get("sample_id"),
            "attribute_schema": (
                "attrType_attrValue_attrUnits"
            ),
            "attribute_type": row.get(
                "attrType"
            ),
            "value_original": row.get(
                "attrValue"
            ),
            "unit_original": row.get(
                "attrUnits"
            ),
            "standard_name": row.get(
                "std_name"
            ),
            "component_role": row.get(
                "role"
            ),
            "full_label": row.get(
                "fullLabel"
            ),
            "canonical_value": None,
            "canonical_unit": None,
            "transformation": None,
            "evidence_status": (
                "documented_in_historical_indexed_response"
            ),
        }

        record.update(
            source_metadata(row)
        )

        records.append(record)

    return records


# ============================================================
# VALIDACIONES
# ============================================================

def duplicate_count(frame, columns):
    usable = [
        column
        for column in columns
        if column in frame.columns
    ]

    if not usable or frame.empty:
        return 0

    return int(
        frame.duplicated(
            subset=usable,
            keep=False,
        ).sum()
    )


def nonempty_count(frame, column):
    if column not in frame.columns:
        return 0

    return int(
        frame[column]
        .notna()
        .sum()
    )


# ============================================================
# EJECUCION PRINCIPAL
# ============================================================

def main():
    print("EXTRAYENDO TABLAS CURADAS L172")

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    raw = INPUT_FILE.read_bytes()

    document = json.loads(
        raw.decode("utf-8-sig")
    )

    bindings = document.get(
        "bindings",
        [],
    )

    if not isinstance(bindings, list):
        raise ValueError(
            "El campo bindings no es una lista"
        )

    if len(bindings) != 49:
        raise ValueError(
            "Se esperaban 49 bindings unicos, "
            f"pero se encontraron {len(bindings)}"
        )

    provenance = []
    components = []
    processing = []
    attributes = []
    unclassified = []

    classification_counts = {
        "provenance": 0,
        "components": 0,
        "processing": 0,
        "attributes": 0,
        "unclassified": 0,
    }

    for binding_index, row in enumerate(
        bindings
    ):
        if not isinstance(row, dict):
            continue

        classes = classify_binding(row)

        if "provenance" in classes:
            record = provenance_record(row)
            record["binding_index"] = (
                binding_index
            )
            provenance.append(record)

            classification_counts[
                "provenance"
            ] += 1

        if "components" in classes:
            record = component_record(row)
            record["binding_index"] = (
                binding_index
            )
            components.append(record)

            classification_counts[
                "components"
            ] += 1

        if "processing" in classes:
            record = processing_record(row)
            record["binding_index"] = (
                binding_index
            )
            processing.append(record)

            classification_counts[
                "processing"
            ] += 1

        if "attributes" in classes:
            records = attribute_records(row)

            for record in records:
                record["binding_index"] = (
                    binding_index
                )

                attributes.append(record)

            classification_counts[
                "attributes"
            ] += 1

        if "unclassified" in classes:
            unclassified.append(
                {
                    "binding_index": (
                        binding_index
                    ),
                    "sample_id": row.get(
                        "sample_id"
                    ),
                    "available_fields": "|".join(
                        sorted(
                            key
                            for key, value
                            in row.items()
                            if value not in (
                                None,
                                "",
                            )
                        )
                    ),
                    "binding_json": json.dumps(
                        scientific_payload(row),
                        ensure_ascii=False,
                    ),
                }
            )

            classification_counts[
                "unclassified"
            ] += 1

    provenance_frame = write_csv(
        provenance,
        PROVENANCE_FILE,
        [
            "binding_index",
            "sample_id",
            "doi_or_resource",
            "sample_label",
            "process_label",
            "evidence_status",
            "current_graph_status",
            "source_hit_id",
            "source_index",
            "source_date",
            "query_sha256",
            "response_sha256",
            "binding_position",
            "source_occurrence_count",
        ],
    )

    components_frame = write_csv(
        components,
        COMPONENTS_FILE,
        [
            "binding_index",
            "sample_id",
            "standard_name",
            "component_role",
            "attribute_type",
            "attribute_value_original",
            "attribute_unit_original",
            "full_label",
            "canonical_value",
            "canonical_unit",
            "transformation",
            "evidence_status",
            "source_hit_id",
            "source_index",
            "source_date",
            "query_sha256",
            "response_sha256",
            "binding_position",
            "source_occurrence_count",
        ],
    )

    processing_frame = write_csv(
        processing,
        PROCESSING_FILE,
        [
            "binding_index",
            "sample_id",
            "process_label",
            "processing_step",
            "parameter_label",
            "description_original",
            "normalized_parameter",
            "canonical_value",
            "canonical_unit",
            "transformation",
            "evidence_status",
            "source_hit_id",
            "source_index",
            "source_date",
            "query_sha256",
            "response_sha256",
            "binding_position",
            "source_occurrence_count",
        ],
    )

    attributes_frame = write_csv(
        attributes,
        ATTRIBUTES_FILE,
        [
            "binding_index",
            "sample_id",
            "attribute_schema",
            "attribute_type",
            "value_original",
            "unit_original",
            "standard_name",
            "component_role",
            "full_label",
            "canonical_value",
            "canonical_unit",
            "transformation",
            "evidence_status",
            "source_hit_id",
            "source_index",
            "source_date",
            "query_sha256",
            "response_sha256",
            "binding_position",
            "source_occurrence_count",
        ],
    )

    unclassified_frame = write_csv(
        unclassified,
        UNCLASSIFIED_FILE,
        [
            "binding_index",
            "sample_id",
            "available_fields",
            "binding_json",
        ],
    )

    # ========================================================
    # VALIDACIONES E INTEGRIDAD
    # ========================================================

    doi_count = nonempty_count(
        provenance_frame,
        "doi_or_resource",
    )

    component_name_count = nonempty_count(
        components_frame,
        "standard_name",
    )

    processing_step_count = nonempty_count(
        processing_frame,
        "processing_step",
    )

    attribute_value_count = nonempty_count(
        attributes_frame,
        "value_original",
    )

    attribute_unit_count = nonempty_count(
        attributes_frame,
        "unit_original",
    )

    validation = {
        "input_bindings": len(bindings),
        "provenance_rows": len(
            provenance_frame
        ),
        "component_rows": len(
            components_frame
        ),
        "processing_rows": len(
            processing_frame
        ),
        "attribute_rows": len(
            attributes_frame
        ),
        "unclassified_rows": len(
            unclassified_frame
        ),
        "doi_values_present": doi_count,
        "component_names_present": (
            component_name_count
        ),
        "processing_steps_present": (
            processing_step_count
        ),
        "attribute_values_present": (
            attribute_value_count
        ),
        "attribute_units_present": (
            attribute_unit_count
        ),
        "duplicate_provenance_rows": (
            duplicate_count(
                provenance_frame,
                [
                    "sample_id",
                    "doi_or_resource",
                    "process_label",
                ],
            )
        ),
        "duplicate_component_rows": (
            duplicate_count(
                components_frame,
                [
                    "sample_id",
                    "standard_name",
                    "component_role",
                    "attribute_type",
                    "attribute_value_original",
                    "attribute_unit_original",
                ],
            )
        ),
        "duplicate_processing_rows": (
            duplicate_count(
                processing_frame,
                [
                    "sample_id",
                    "processing_step",
                    "parameter_label",
                    "description_original",
                ],
            )
        ),
        "duplicate_attribute_rows": (
            duplicate_count(
                attributes_frame,
                [
                    "sample_id",
                    "attribute_type",
                    "value_original",
                    "unit_original",
                    "standard_name",
                    "component_role",
                ],
            )
        ),
    }

    # ========================================================
    # MANIFIESTO
    # ========================================================

    output_files = [
        PROVENANCE_FILE,
        COMPONENTS_FILE,
        PROCESSING_FILE,
        ATTRIBUTES_FILE,
        UNCLASSIFIED_FILE,
    ]

    manifest = {
        "generated_at": CHECKED_AT,
        "input_file": str(INPUT_FILE),
        "input_sha256": hashlib.sha256(
            raw
        ).hexdigest(),
        "classification_counts": (
            classification_counts
        ),
        "validation": validation,
        "outputs": [
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in output_files
        ],
        "methodological_notes": [
            (
                "Los bindings pueden alimentar más "
                "de una tabla cuando contienen campos "
                "de varias categorías."
            ),
            (
                "Los valores originales y unidades "
                "se conservaron sin conversión."
            ),
            (
                "Las columnas canónicas permanecen "
                "vacías hasta definir transformaciones."
            ),
            (
                "Los DOI o recursos se conservan "
                "exactamente como aparecen."
            ),
            (
                "No se calcularon medias ni modelos."
            ),
        ],
    }

    MANIFEST_FILE.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # RESUMEN CSV
    # ========================================================

    summary_rows = [
        {
            "table": "study_provenance",
            "rows": len(provenance_frame),
            "key_values_present": doi_count,
            "output_file": str(
                PROVENANCE_FILE
            ),
        },
        {
            "table": "material_components",
            "rows": len(components_frame),
            "key_values_present": (
                component_name_count
            ),
            "output_file": str(
                COMPONENTS_FILE
            ),
        },
        {
            "table": "processing_steps",
            "rows": len(processing_frame),
            "key_values_present": (
                processing_step_count
            ),
            "output_file": str(
                PROCESSING_FILE
            ),
        },
        {
            "table": "observed_attributes",
            "rows": len(attributes_frame),
            "key_values_present": (
                attribute_value_count
            ),
            "output_file": str(
                ATTRIBUTES_FILE
            ),
        },
        {
            "table": "unclassified",
            "rows": len(unclassified_frame),
            "key_values_present": 0,
            "output_file": str(
                UNCLASSIFIED_FILE
            ),
        },
    ]

    pd.DataFrame(
        summary_rows
    ).to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # LOG
    # ========================================================

    log_lines = [
        "FASE 2 - EXTRACCION DE TABLAS CURADAS L172",
        "",
        f"Fecha: {CHECKED_AT}",
        f"Entrada: {INPUT_FILE}",
        (
            "SHA256: "
            f"{manifest['input_sha256']}"
        ),
        f"Bindings de entrada: {len(bindings)}",
        "",
        "TABLAS GENERADAS",
        (
            "- Procedencia: "
            f"{len(provenance_frame)} filas"
        ),
        (
            "- Componentes: "
            f"{len(components_frame)} filas"
        ),
        (
            "- Procesamiento: "
            f"{len(processing_frame)} filas"
        ),
        (
            "- Atributos: "
            f"{len(attributes_frame)} filas"
        ),
        (
            "- No clasificados: "
            f"{len(unclassified_frame)} filas"
        ),
        "",
        "VALORES CLAVE",
        f"- DOI/recursos presentes: {doi_count}",
        (
            "- Nombres de componentes presentes: "
            f"{component_name_count}"
        ),
        (
            "- Pasos de procesamiento presentes: "
            f"{processing_step_count}"
        ),
        (
            "- Valores de atributos presentes: "
            f"{attribute_value_count}"
        ),
        (
            "- Unidades de atributos presentes: "
            f"{attribute_unit_count}"
        ),
        "",
        "DUPLICADOS POTENCIALES",
        (
            "- Procedencia: "
            f"{validation['duplicate_provenance_rows']}"
        ),
        (
            "- Componentes: "
            f"{validation['duplicate_component_rows']}"
        ),
        (
            "- Procesamiento: "
            f"{validation['duplicate_processing_rows']}"
        ),
        (
            "- Atributos: "
            f"{validation['duplicate_attribute_rows']}"
        ),
        "",
        "ADVERTENCIAS",
        (
            "- Un binding puede aparecer en más "
            "de una tabla por diseño."
        ),
        (
            "- Los duplicados potenciales no se "
            "eliminaron automáticamente."
        ),
        (
            "- Los valores y unidades originales "
            "se conservaron sin transformación."
        ),
        (
            "- Las columnas canónicas permanecen "
            "vacías."
        ),
        (
            "- No se calcularon medias."
        ),
        (
            "- No se ejecutaron modelos."
        ),
        "",
        f"Procedencia: {PROVENANCE_FILE}",
        f"Componentes: {COMPONENTS_FILE}",
        f"Procesamiento: {PROCESSING_FILE}",
        f"Atributos: {ATTRIBUTES_FILE}",
        f"No clasificados: {UNCLASSIFIED_FILE}",
        f"Resumen: {SUMMARY_FILE}",
        f"Manifiesto: {MANIFEST_FILE}",
    ]

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("EXTRACCION COMPLETADA")
    print(
        "Procedencia:",
        len(provenance_frame),
    )
    print(
        "Componentes:",
        len(components_frame),
    )
    print(
        "Procesamiento:",
        len(processing_frame),
    )
    print(
        "Atributos:",
        len(attributes_frame),
    )
    print(
        "No clasificados:",
        len(unclassified_frame),
    )
    print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        ERROR_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        ERROR_FILE.write_text(
            (
                f"{type(error).__name__}: "
                f"{error}\n"
            ),
            encoding="utf-8",
        )

        print("")
        print(
            f"ERROR: {type(error).__name__}: "
            f"{error}"
        )

        print(f"Log de error: {ERROR_FILE}")

        sys.exit(1)