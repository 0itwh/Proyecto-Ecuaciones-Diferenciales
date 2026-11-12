from pathlib import Path
from datetime import datetime
import csv
import hashlib
import json
import re
import sys


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

INPUT_FILE = (
    ROOT
    / "data_raw"
    / "explorer"
    / "l172-huo-2015-search-response.json"
)

OUTPUT_DIR = (
    ROOT
    / "data_processed"
    / "l172_family"
    / "conductivity_context"
)

METADATA_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"
ARCHIVE_DIR = (
    ROOT
    / "archive"
    / "rejected_queries"
)

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

ARCHIVE_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

INVENTORY_FILE = (
    METADATA_DIR
    / "l172-conductivity-context-query-inventory.csv"
)

REJECTED_FILE = (
    METADATA_DIR
    / "l172-conductivity-context-rejected-candidates.csv"
)

BINDINGS_FILE = (
    OUTPUT_DIR
    / "l172-conductivity-context-bindings.csv"
)

RESULT_JSON = (
    METADATA_DIR
    / "l172-conductivity-context-analysis.json"
)

LOG_FILE = (
    LOG_DIR
    / "l172-conductivity-context-analysis.log"
)

ERROR_FILE = (
    LOG_DIR
    / "l172-conductivity-context-analysis-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# ============================================================
# TERMINOS
# ============================================================

CONDUCTIVITY_TERMS = [
    "electricconductivity",
    "electric conductivity",
    "conductivity",
    "volume resistivity",
    "volumeresistivity",
    "surface resistivity",
    "surfaceresistivity",
]

RELATION_TERMS = [
    "sio:inrelationto",
    "inrelationto",
]

CONDITION_TERMS = {
    "frequency": [
        "frequency",
        "frequencysweep",
        "frequencydependence",
        "minfrequency",
        "maxfrequency",
        "hertz",
        " hz",
    ],
    "temperature": [
        "temperature",
        "temperaturedependence",
        "temperaturesweep",
        "celsius",
        "kelvin",
    ],
    "unit": [
        "hasunit",
        "unitofmeasure",
        "?unit",
        "?units",
    ],
    "value": [
        "hasvalue",
        "?value",
        "?conductivity",
    ],
    "measurement": [
        "measurementmethod",
        "measurementmode",
        "instrument",
        "electrical",
        "dielectric",
        "impedance",
    ],
}

SAMPLE_PATTERN = re.compile(
    r"l172-s\d+-huo-2015",
    flags=re.IGNORECASE,
)


# ============================================================
# FUNCIONES GENERALES
# ============================================================

def normalize_query(value):
    if not isinstance(value, str):
        return ""

    return (
        value.replace(
            "\r\n",
            "\n",
        )
        .replace(
            "\r",
            "\n",
        )
        .strip()
    )


def text_sha256(value):
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def file_sha256(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def safe_filename(value):
    return re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        str(value),
    )


def find_terms(text, terms):
    lower = str(text).lower()

    return sorted(
        {
            term
            for term in terms
            if term.lower() in lower
        }
    )


def extract_sample_ids(value):
    text = json.dumps(
        value,
        ensure_ascii=False,
    )

    return sorted(
        {
            item.lower()
            for item in SAMPLE_PATTERN.findall(
                text
            )
        }
    )


def get_response(hit):
    source = hit.get(
        "_source",
        {},
    )

    response = source.get(
        "response"
    )

    return (
        response
        if isinstance(response, dict)
        else None
    )


def get_bindings(response):
    if not isinstance(response, dict):
        return []

    results = response.get(
        "results",
        {},
    )

    if not isinstance(results, dict):
        return []

    bindings = results.get(
        "bindings",
        [],
    )

    return (
        bindings
        if isinstance(bindings, list)
        else []
    )


def get_response_variables(response):
    if not isinstance(response, dict):
        return []

    head = response.get(
        "head",
        {},
    )

    if not isinstance(head, dict):
        return []

    variables = head.get(
        "vars",
        [],
    )

    return (
        variables
        if isinstance(variables, list)
        else []
    )


def flatten_binding(binding):
    row = {}

    for variable, cell in binding.items():
        if isinstance(cell, dict):
            row[variable] = cell.get(
                "value"
            )

            row[
                f"{variable}__type"
            ] = cell.get(
                "type"
            )

            row[
                f"{variable}__datatype"
            ] = cell.get(
                "datatype"
            )

            row[
                f"{variable}__xml_lang"
            ] = cell.get(
                "xml:lang"
            )

        else:
            row[variable] = cell

    return row


# ============================================================
# VALIDACION SPARQL
# ============================================================

def validate_sparql(query, response):
    upper = query.upper()

    checks = {
        "not_empty": bool(
            query.strip()
        ),
        "contains_select": (
            "SELECT" in upper
        ),
        "contains_where": (
            "WHERE" in upper
        ),
        "contains_open_brace": (
            "{" in query
        ),
        "contains_close_brace": (
            "}" in query
        ),
        "balanced_braces": (
            query.count("{")
            == query.count("}")
        ),
        "no_truncation_marker": (
            "[TRUNCADO]" not in query
            and "... [TRUNCADO]" not in query
        ),
        "response_is_object": isinstance(
            response,
            dict,
        ),
    }

    checks["all_passed"] = all(
        checks.values()
    )

    return checks


# ============================================================
# CLASIFICACION
# ============================================================

def classify_candidate(
    query,
    hit,
):
    query_lower = query.lower()

    complete_hit_text = json.dumps(
        hit,
        ensure_ascii=False,
    ).lower()

    conductivity_in_query = find_terms(
        query_lower,
        CONDUCTIVITY_TERMS,
    )

    conductivity_in_hit = find_terms(
        complete_hit_text,
        CONDUCTIVITY_TERMS,
    )

    relation_terms = find_terms(
        query_lower,
        RELATION_TERMS,
    )

    condition_matches = {}

    for name, terms in (
        CONDITION_TERMS.items()
    ):
        condition_matches[name] = sorted(
            set(
                find_terms(
                    query_lower,
                    terms,
                )
                + find_terms(
                    complete_hit_text,
                    terms,
                )
            )
        )

    textually_relevant = bool(
        conductivity_in_query
        or conductivity_in_hit
    )

    return {
        "textually_relevant": (
            textually_relevant
        ),
        "conductivity_in_query": (
            conductivity_in_query
        ),
        "conductivity_in_hit": (
            conductivity_in_hit
        ),
        "relation_terms": (
            relation_terms
        ),
        "condition_matches": (
            condition_matches
        ),
    }


def scientific_classification(
    relation_terms,
    condition_matches,
):
    if relation_terms:
        return (
            "conductivity_with_inRelationTo"
        )

    if any(
        condition_matches.values()
    ):
        return (
            "conductivity_with_condition_terms"
        )

    return "conductivity_only"


# ============================================================
# ESCRITURA CSV SEGURA
# ============================================================

def write_csv(
    path,
    rows,
    preferred_columns,
):
    columns = list(
        preferred_columns
    )

    discovered = sorted(
        {
            key
            for row in rows
            for key in row.keys()
            if key not in columns
        }
    )

    columns.extend(
        discovered
    )

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(
            rows
        )


# ============================================================
# LIMPIAR SALIDAS ANTERIORES INVALIDAS
# ============================================================

def archive_previous_sparql_files():
    archived = []

    for path in OUTPUT_DIR.glob(
        "*.sparql"
    ):
        destination = (
            ARCHIVE_DIR
            / path.name
        )

        counter = 1

        while destination.exists():
            destination = (
                ARCHIVE_DIR
                / (
                    path.stem
                    + f"-previous-{counter}"
                    + path.suffix
                )
            )

            counter += 1

        path.replace(
            destination
        )

        archived.append(
            str(destination)
        )

    return archived


# ============================================================
# EJECUCION
# ============================================================

def main():
    print(
        "BUSCANDO CONSULTAS SPARQL VALIDAS "
        "DE CONDUCTIVIDAD"
    )

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    raw = INPUT_FILE.read_bytes()

    document = json.loads(
        raw.decode(
            "utf-8-sig"
        )
    )

    hits = document.get(
        "data",
        {},
    ).get(
        "hits",
        [],
    )

    if not isinstance(hits, list):
        raise ValueError(
            "data.hits no es una lista"
        )

    archived_files = (
        archive_previous_sparql_files()
    )

    valid_inventory = []
    rejected_inventory = []
    binding_rows = []
    detailed_hits = []

    textually_relevant_count = 0

    for position, hit in enumerate(
        hits
    ):
        if not isinstance(
            hit,
            dict,
        ):
            continue

        source = hit.get(
            "_source",
            {},
        )

        query = normalize_query(
            source.get(
                "label",
                "",
            )
        )

        response = get_response(
            hit
        )

        classification_data = (
            classify_candidate(
                query,
                hit,
            )
        )

        if not classification_data[
            "textually_relevant"
        ]:
            continue

        textually_relevant_count += 1

        hit_id = str(
            hit.get(
                "_id",
                "",
            )
        )

        validation = validate_sparql(
            query,
            response,
        )

        bindings = get_bindings(
            response
        )

        response_variables = (
            get_response_variables(
                response
            )
        )

        sample_ids = extract_sample_ids(
            hit
        )

        condition_matches = (
            classification_data[
                "condition_matches"
            ]
        )

        common_record = {
            "search_position": position,
            "index": hit.get(
                "_index"
            ),
            "hit_id": hit_id,
            "source_date": source.get(
                "date"
            ),
            "conductivity_in_query": (
                "|".join(
                    classification_data[
                        "conductivity_in_query"
                    ]
                )
            ),
            "conductivity_in_hit": (
                "|".join(
                    classification_data[
                        "conductivity_in_hit"
                    ]
                )
            ),
            "relation_terms": "|".join(
                classification_data[
                    "relation_terms"
                ]
            ),
            "frequency_terms": "|".join(
                condition_matches[
                    "frequency"
                ]
            ),
            "temperature_terms": "|".join(
                condition_matches[
                    "temperature"
                ]
            ),
            "unit_terms": "|".join(
                condition_matches[
                    "unit"
                ]
            ),
            "value_terms": "|".join(
                condition_matches[
                    "value"
                ]
            ),
            "measurement_terms": "|".join(
                condition_matches[
                    "measurement"
                ]
            ),
            "sample_ids": "|".join(
                sample_ids
            ),
            "response_variables": (
                "|".join(
                    str(variable)
                    for variable
                    in response_variables
                )
            ),
            "binding_count": len(
                bindings
            ),
            "query_characters": len(
                query
            ),
            "query_lines": len(
                query.splitlines()
            ),
            "contains_select": (
                validation[
                    "contains_select"
                ]
            ),
            "contains_where": (
                validation[
                    "contains_where"
                ]
            ),
            "balanced_braces": (
                validation[
                    "balanced_braces"
                ]
            ),
            "response_is_object": (
                validation[
                    "response_is_object"
                ]
            ),
            "query_valid": (
                validation[
                    "all_passed"
                ]
            ),
        }

        if not validation[
            "all_passed"
        ]:
            rejection_reasons = [
                name
                for name, passed
                in validation.items()
                if (
                    name != "all_passed"
                    and not passed
                )
            ]

            rejected_inventory.append(
                {
                    **common_record,
                    "rejection_reasons": (
                        "|".join(
                            rejection_reasons
                        )
                    ),
                    "label_preview": (
                        query[:500]
                    ),
                    "archived_as_evidence": (
                        "not_written_as_sparql"
                    ),
                }
            )

            continue

        classification = (
            scientific_classification(
                classification_data[
                    "relation_terms"
                ],
                condition_matches,
            )
        )

        query_to_save = (
            query.rstrip()
            + "\n"
        )

        query_sha256 = text_sha256(
            query_to_save
        )

        query_filename = (
            f"{position:03d}-"
            f"{safe_filename(hit_id)}-"
            f"{classification}.sparql"
        )

        query_path = (
            OUTPUT_DIR
            / query_filename
        )

        query_path.write_text(
            query_to_save,
            encoding="utf-8",
            newline="\n",
        )

        query_file_sha256 = (
            file_sha256(
                query_path
            )
        )

        valid_record = {
            **common_record,
            "classification": (
                classification
            ),
            "query_file": str(
                query_path
            ),
            "query_sha256": (
                query_sha256
            ),
            "query_file_sha256": (
                query_file_sha256
            ),
            "hash_matches": (
                query_sha256
                == query_file_sha256
            ),
        }

        valid_inventory.append(
            valid_record
        )

        detailed_hits.append(
            {
                **valid_record,
                "query_validation": (
                    validation
                ),
                "query_text": (
                    query_to_save
                ),
                "bindings": (
                    bindings
                ),
            }
        )

        for binding_position, binding in enumerate(
            bindings
        ):
            if not isinstance(
                binding,
                dict,
            ):
                continue

            flat = flatten_binding(
                binding
            )

            flat.update(
                {
                    "_search_position": (
                        position
                    ),
                    "_hit_id": (
                        hit_id
                    ),
                    "_source_date": source.get(
                        "date"
                    ),
                    "_classification": (
                        classification
                    ),
                    "_query_sha256": (
                        query_sha256
                    ),
                    "_binding_position": (
                        binding_position
                    ),
                    "_sample_ids_in_hit": (
                        "|".join(
                            sample_ids
                        )
                    ),
                }
            )

            binding_rows.append(
                flat
            )

    # ========================================================
    # GUARDAR INVENTARIOS
    # ========================================================

    valid_columns = [
        "search_position",
        "index",
        "hit_id",
        "source_date",
        "classification",
        "conductivity_in_query",
        "conductivity_in_hit",
        "relation_terms",
        "frequency_terms",
        "temperature_terms",
        "unit_terms",
        "value_terms",
        "measurement_terms",
        "sample_ids",
        "response_variables",
        "binding_count",
        "query_characters",
        "query_lines",
        "contains_select",
        "contains_where",
        "balanced_braces",
        "response_is_object",
        "query_valid",
        "query_file",
        "query_sha256",
        "query_file_sha256",
        "hash_matches",
    ]

    rejected_columns = [
        "search_position",
        "index",
        "hit_id",
        "source_date",
        "conductivity_in_query",
        "conductivity_in_hit",
        "relation_terms",
        "frequency_terms",
        "temperature_terms",
        "unit_terms",
        "measurement_terms",
        "sample_ids",
        "response_variables",
        "binding_count",
        "query_characters",
        "query_lines",
        "contains_select",
        "contains_where",
        "balanced_braces",
        "response_is_object",
        "query_valid",
        "rejection_reasons",
        "label_preview",
        "archived_as_evidence",
    ]

    write_csv(
        INVENTORY_FILE,
        valid_inventory,
        valid_columns,
    )

    write_csv(
        REJECTED_FILE,
        rejected_inventory,
        rejected_columns,
    )

    binding_columns = [
        "_search_position",
        "_hit_id",
        "_source_date",
        "_classification",
        "_query_sha256",
        "_binding_position",
        "_sample_ids_in_hit",
    ]

    write_csv(
        BINDINGS_FILE,
        binding_rows,
        binding_columns,
    )

    # ========================================================
    # RESUMEN
    # ========================================================

    classification_counts = {}

    for item in valid_inventory:
        name = item[
            "classification"
        ]

        classification_counts[
            name
        ] = (
            classification_counts.get(
                name,
                0,
            )
            + 1
        )

    relation_hits = [
        item
        for item in valid_inventory
        if item[
            "classification"
        ] == (
            "conductivity_with_inRelationTo"
        )
    ]

    frequency_hits = [
        item
        for item in valid_inventory
        if item[
            "frequency_terms"
        ]
    ]

    temperature_hits = [
        item
        for item in valid_inventory
        if item[
            "temperature_terms"
        ]
    ]

    unit_hits = [
        item
        for item in valid_inventory
        if item[
            "unit_terms"
        ]
    ]

    invalid_saved = [
        item
        for item in valid_inventory
        if (
            not item[
                "query_valid"
            ]
            or not item[
                "hash_matches"
            ]
        )
    ]

    result = {
        "generated_at": CHECKED_AT,
        "input_file": str(
            INPUT_FILE
        ),
        "input_sha256": hashlib.sha256(
            raw
        ).hexdigest(),
        "search_hits_total": len(
            hits
        ),
        "textually_relevant_candidates": (
            textually_relevant_count
        ),
        "valid_sparql_queries": len(
            valid_inventory
        ),
        "rejected_candidates": len(
            rejected_inventory
        ),
        "binding_rows": len(
            binding_rows
        ),
        "classification_counts": (
            classification_counts
        ),
        "archived_previous_files": (
            archived_files
        ),
        "valid_queries": (
            detailed_hits
        ),
        "rejected_candidates_detail": (
            rejected_inventory
        ),
        "scientific_interpretation": {
            "conductivity_context_query_found": (
                len(valid_inventory)
                > 0
            ),
            "explicit_inRelationTo_found": (
                len(relation_hits)
                > 0
            ),
            "frequency_context_found": (
                len(frequency_hits)
                > 0
            ),
            "temperature_context_found": (
                len(temperature_hits)
                > 0
            ),
            "unit_context_found": (
                len(unit_hits)
                > 0
            ),
        },
        "notes": [
            (
                "Invalid labels and chart "
                "descriptions were not written "
                "as SPARQL."
            ),
            (
                "Zero valid queries is accepted "
                "as a reproducible negative result."
            ),
            (
                "No units were assumed."
            ),
            (
                "No averaging or modeling "
                "was performed."
            ),
        ],
    }

    RESULT_JSON.write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # LOG
    # ========================================================

    log_lines = [
        (
            "FASE 2 - CONTEXTO HISTORICO "
            "DE CONDUCTIVIDAD L172"
        ),
        "",
        f"Fecha: {CHECKED_AT}",
        f"Entrada: {INPUT_FILE}",
        (
            "SHA256 entrada: "
            f"{result['input_sha256']}"
        ),
        f"Hits totales: {len(hits)}",
        (
            "Candidatos textuales: "
            f"{textually_relevant_count}"
        ),
        (
            "Consultas SPARQL validas: "
            f"{len(valid_inventory)}"
        ),
        (
            "Candidatos rechazados: "
            f"{len(rejected_inventory)}"
        ),
        (
            "Bindings recuperados: "
            f"{len(binding_rows)}"
        ),
        (
            "Consultas con inRelationTo: "
            f"{len(relation_hits)}"
        ),
        (
            "Consultas con frecuencia: "
            f"{len(frequency_hits)}"
        ),
        (
            "Consultas con temperatura: "
            f"{len(temperature_hits)}"
        ),
        (
            "Consultas con unidad: "
            f"{len(unit_hits)}"
        ),
        (
            "Consultas validas con fallo "
            f"de integridad: {len(invalid_saved)}"
        ),
        "",
        "CANDIDATOS RECHAZADOS",
    ]

    if rejected_inventory:
        for item in (
            rejected_inventory
        ):
            log_lines.extend(
                [
                    "",
                    (
                        "Posicion: "
                        f"{item['search_position']}"
                    ),
                    (
                        "Hit: "
                        f"{item['hit_id']}"
                    ),
                    (
                        "Motivos: "
                        f"{item['rejection_reasons']}"
                    ),
                    (
                        "Caracteres: "
                        f"{item['query_characters']}"
                    ),
                    (
                        "Lineas: "
                        f"{item['query_lines']}"
                    ),
                    (
                        "Bindings: "
                        f"{item['binding_count']}"
                    ),
                    (
                        "Vista previa: "
                        f"{item['label_preview']}"
                    ),
                ]
            )
    else:
        log_lines.append(
            "- Ninguno"
        )

    log_lines.extend(
        [
            "",
            "CONSULTAS SPARQL VALIDAS",
        ]
    )

    if valid_inventory:
        for item in valid_inventory:
            log_lines.extend(
                [
                    "",
                    (
                        "Posicion: "
                        f"{item['search_position']}"
                    ),
                    (
                        "Hit: "
                        f"{item['hit_id']}"
                    ),
                    (
                        "Clasificacion: "
                        f"{item['classification']}"
                    ),
                    (
                        "Muestras: "
                        f"{item['sample_ids']}"
                    ),
                    (
                        "Variables: "
                        f"{item['response_variables']}"
                    ),
                    (
                        "Bindings: "
                        f"{item['binding_count']}"
                    ),
                    (
                        "Frecuencia: "
                        f"{item['frequency_terms']}"
                    ),
                    (
                        "Temperatura: "
                        f"{item['temperature_terms']}"
                    ),
                    (
                        "Unidad: "
                        f"{item['unit_terms']}"
                    ),
                    (
                        "Hash coincide: "
                        + (
                            "SI"
                            if item[
                                "hash_matches"
                            ]
                            else "NO"
                        )
                    ),
                    (
                        "Archivo: "
                        f"{item['query_file']}"
                    ),
                ]
            )
    else:
        log_lines.append(
            "- Ninguna"
        )

    log_lines.extend(
        [
            "",
            "CONCLUSION AUTOMATICA",
        ]
    )

    if not valid_inventory:
        log_lines.extend(
            [
                (
                    "- No se localizaron "
                    "consultas SPARQL historicas "
                    "validas que vinculen "
                    "conductividad con frecuencia, "
                    "temperatura o unidad."
                ),
                (
                    "- Los candidatos encontrados "
                    "eran etiquetas o descripciones "
                    "de graficos."
                ),
                (
                    "- Los 235 valores de "
                    "conductividad conservan unidad "
                    "y condiciones no verificadas."
                ),
            ]
        )

    else:
        log_lines.extend(
            [
                (
                    "- Se localizaron consultas "
                    "SPARQL validas para revision."
                ),
                (
                    "- La presencia de terminos "
                    "requiere revisar bindings "
                    "y clausulas WHERE."
                ),
            ]
        )

    log_lines.extend(
        [
            "",
            "ADVERTENCIAS",
            (
                "- Cero consultas validas "
                "es un resultado negativo "
                "aceptable."
            ),
            (
                "- No se ejecutaron consultas "
                "contra el grafo actual."
            ),
            (
                "- No se asumieron unidades."
            ),
            (
                "- No se calcularon medias."
            ),
            (
                "- No se ejecutaron modelos."
            ),
            "",
            f"Inventario valido: {INVENTORY_FILE}",
            f"Rechazados: {REJECTED_FILE}",
            f"Bindings: {BINDINGS_FILE}",
            f"JSON detallado: {RESULT_JSON}",
            (
                "Consultas anteriores archivadas: "
                f"{len(archived_files)}"
            ),
        ]
    )

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    if invalid_saved:
        raise ValueError(
            "Una consulta guardada no supero "
            "la validacion de integridad"
        )

    print("")
    print("EXTRACCION COMPLETADA")
    print(
        "Candidatos textuales:",
        textually_relevant_count,
    )
    print(
        "Consultas SPARQL validas:",
        len(valid_inventory),
    )
    print(
        "Candidatos rechazados:",
        len(rejected_inventory),
    )
    print(
        "Con inRelationTo:",
        len(relation_hits),
    )
    print(
        "Con frecuencia:",
        len(frequency_hits),
    )
    print(
        "Con temperatura:",
        len(temperature_hits),
    )
    print(
        "Con unidad:",
        len(unit_hits),
    )
    print(
        "Bindings:",
        len(binding_rows),
    )
    print(f"Log: {LOG_FILE}")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
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

        print(
            f"Log de error: {ERROR_FILE}"
        )

        sys.exit(1)