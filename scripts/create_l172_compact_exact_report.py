from pathlib import Path
from datetime import datetime
import json
import sys

import pandas as pd


ROOT = Path.cwd()
BASE = ROOT / "data_processed" / "l172_family"
LOG_DIR = ROOT / "logs"
METADATA_DIR = ROOT / "metadata"

PROVENANCE_FILE = BASE / "l172-study-provenance.csv"
COMPONENTS_FILE = BASE / "l172-material-components.csv"
PROCESSING_FILE = BASE / "l172-processing-steps.csv"
ATTRIBUTES_FILE = BASE / "l172-observed-attributes.csv"
UNCLASSIFIED_FILE = BASE / "l172-unclassified-bindings.csv"

OUTPUT_FILE = LOG_DIR / "l172-compact-exact-values-report.txt"
OUTPUT_JSON = METADATA_DIR / "l172-compact-exact-values-report.json"
ERROR_FILE = LOG_DIR / "l172-compact-exact-values-report-error.log"

CHECKED_AT = datetime.now().astimezone().isoformat(timespec="seconds")

LOG_DIR.mkdir(parents=True, exist_ok=True)
METADATA_DIR.mkdir(parents=True, exist_ok=True)


def read_csv_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def clean(value):
    if value is None:
        return ""
    text = str(value).strip()
    return text


def unique_nonempty(frame, column):
    if column not in frame.columns:
        return []
    return sorted({clean(v) for v in frame[column] if clean(v)})


def exact_duplicate_groups(frame, columns):
    usable = [c for c in columns if c in frame.columns]
    if not usable or frame.empty:
        return []

    subset = frame[usable].copy()
    mask = subset.duplicated(subset=usable, keep=False)
    duplicate_rows = subset[mask]

    groups = []
    if duplicate_rows.empty:
        return groups

    for keys, group in duplicate_rows.groupby(usable, dropna=False, sort=True):
        if not isinstance(keys, tuple):
            keys = (keys,)
        groups.append({
            "count": len(group),
            "values": dict(zip(usable, [clean(v) for v in keys])),
        })
    return groups


def row_block(frame, columns, heading_prefix):
    lines = []
    if frame.empty:
        return ["- Sin filas"]

    for position, (_, row) in enumerate(frame.iterrows(), start=1):
        lines.append(f"{heading_prefix} {position}")
        for column in columns:
            if column not in frame.columns:
                continue
            value = clean(row[column])
            lines.append(f"  {column}: {value if value else '[VACIO]'}")
        lines.append("")
    return lines


def main():
    print("GENERANDO INFORME COMPACTO DE VALORES EXACTOS")

    provenance = read_csv_required(PROVENANCE_FILE)
    components = read_csv_required(COMPONENTS_FILE)
    processing = read_csv_required(PROCESSING_FILE)
    attributes = read_csv_required(ATTRIBUTES_FILE)
    unclassified = read_csv_required(UNCLASSIFIED_FILE)

    duplicate_definitions = {
        "provenance": ["sample_id", "doi_or_resource", "process_label"],
        "components": [
            "sample_id", "standard_name", "component_role", "attribute_type",
            "attribute_value_original", "attribute_unit_original"
        ],
        "processing": [
            "sample_id", "processing_step", "parameter_label",
            "description_original"
        ],
        "attributes": [
            "sample_id", "attribute_type", "value_original", "unit_original",
            "standard_name", "component_role"
        ],
    }

    duplicate_groups = {
        "provenance": exact_duplicate_groups(provenance, duplicate_definitions["provenance"]),
        "components": exact_duplicate_groups(components, duplicate_definitions["components"]),
        "processing": exact_duplicate_groups(processing, duplicate_definitions["processing"]),
        "attributes": exact_duplicate_groups(attributes, duplicate_definitions["attributes"]),
    }

    report = [
        "FASE 2 - INFORME COMPACTO DE VALORES EXACTOS L172",
        "",
        f"Fecha: {CHECKED_AT}",
        f"Directorio fuente: {BASE}",
        "",
        "RESUMEN",
        f"- Procedencia: {len(provenance)} filas",
        f"- Componentes: {len(components)} filas",
        f"- Procesamiento: {len(processing)} filas",
        f"- Atributos: {len(attributes)} filas",
        f"- No clasificados: {len(unclassified)} filas",
        "",
        "1. PROCEDENCIA Y DOI/RECURSOS",
        "",
    ]

    report.extend(row_block(
        provenance,
        [
            "binding_index", "sample_id", "doi_or_resource", "sample_label",
            "process_label", "source_date", "source_hit_id", "query_sha256",
            "response_sha256", "source_occurrence_count"
        ],
        "PROCEDENCIA",
    ))

    report.extend(["2. COMPONENTES MATERIALES", ""])
    report.extend(row_block(
        components,
        [
            "binding_index", "sample_id", "standard_name", "component_role",
            "attribute_type", "attribute_value_original",
            "attribute_unit_original", "full_label", "source_date",
            "source_hit_id", "query_sha256", "response_sha256",
            "source_occurrence_count"
        ],
        "COMPONENTE",
    ))

    report.extend(["3. PROCESAMIENTO", ""])
    report.extend(row_block(
        processing,
        [
            "binding_index", "sample_id", "process_label", "processing_step",
            "parameter_label", "description_original", "source_date",
            "source_hit_id", "query_sha256", "response_sha256",
            "source_occurrence_count"
        ],
        "PROCESO",
    ))

    report.extend(["4. ATRIBUTOS OBSERVADOS", ""])
    report.extend(row_block(
        attributes,
        [
            "binding_index", "sample_id", "attribute_schema", "attribute_type",
            "value_original", "unit_original", "standard_name",
            "component_role", "full_label", "source_date", "source_hit_id",
            "query_sha256", "response_sha256", "source_occurrence_count"
        ],
        "ATRIBUTO",
    ))

    report.extend(["5. VALORES UNICOS PRINCIPALES", ""])
    fields = [
        ("DOI/recursos", provenance, "doi_or_resource"),
        ("Muestras en procedencia", provenance, "sample_id"),
        ("Nombres de componentes", components, "standard_name"),
        ("Roles de componentes", components, "component_role"),
        ("Tipos de atributo de componentes", components, "attribute_type"),
        ("Unidades de componentes", components, "attribute_unit_original"),
        ("Etiquetas de proceso", processing, "process_label"),
        ("Pasos de procesamiento", processing, "processing_step"),
        ("Parametros de procesamiento", processing, "parameter_label"),
        ("Tipos de atributos observados", attributes, "attribute_type"),
        ("Unidades observadas", attributes, "unit_original"),
    ]

    for label, frame, column in fields:
        values = unique_nonempty(frame, column)
        report.append(f"{label}: {len(values)}")
        if values:
            report.extend(f"- {value}" for value in values)
        else:
            report.append("- Ninguno")
        report.append("")

    report.extend(["6. GRUPOS DE DUPLICADOS EXACTOS POTENCIALES", ""])
    for table_name, groups in duplicate_groups.items():
        report.append(f"Tabla: {table_name}")
        report.append(f"Grupos: {len(groups)}")
        if not groups:
            report.append("- Ninguno")
        else:
            for number, group in enumerate(groups, start=1):
                report.append(f"- Grupo {number}, filas: {group['count']}")
                for key, value in group["values"].items():
                    report.append(f"    {key}: {value if value else '[VACIO]'}")
        report.append("")

    report.extend([
        "7. FILAS NO CLASIFICADAS",
        "",
    ])
    report.extend(row_block(
        unclassified,
        ["binding_index", "sample_id", "available_fields", "binding_json"],
        "NO CLASIFICADO",
    ))

    report.extend([
        "ADVERTENCIAS METODOLOGICAS",
        "- Los valores se reproducen exactamente como aparecen en los CSV curados.",
        "- [VACIO] significa ausencia en la fuente, no cero.",
        "- Los duplicados potenciales se informan, pero no se eliminan.",
        "- Una coincidencia exacta puede corresponder a muestras o fechas distintas.",
        "- No se normalizaron unidades.",
        "- No se calcularon medias.",
        "- No se ejecutaron modelos.",
        "",
        f"Informe: {OUTPUT_FILE}",
        f"Resumen JSON: {OUTPUT_JSON}",
    ])

    OUTPUT_FILE.write_text("\n".join(report) + "\n", encoding="utf-8")

    json_summary = {
        "generated_at": CHECKED_AT,
        "sources": {
            "provenance": str(PROVENANCE_FILE),
            "components": str(COMPONENTS_FILE),
            "processing": str(PROCESSING_FILE),
            "attributes": str(ATTRIBUTES_FILE),
            "unclassified": str(UNCLASSIFIED_FILE),
        },
        "row_counts": {
            "provenance": len(provenance),
            "components": len(components),
            "processing": len(processing),
            "attributes": len(attributes),
            "unclassified": len(unclassified),
        },
        "exact_values": {
            label: unique_nonempty(frame, column)
            for label, frame, column in fields
        },
        "duplicate_groups": duplicate_groups,
    }
    OUTPUT_JSON.write_text(
        json.dumps(json_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("")
    print("INFORME GENERADO")
    print(f"Procedencia: {len(provenance)}")
    print(f"Componentes: {len(components)}")
    print(f"Procesamiento: {len(processing)}")
    print(f"Atributos: {len(attributes)}")
    print(f"No clasificados: {len(unclassified)}")
    print(f"TXT: {OUTPUT_FILE}")
    print(f"JSON: {OUTPUT_JSON}")


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
