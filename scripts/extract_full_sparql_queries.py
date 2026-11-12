from pathlib import Path
from datetime import datetime
import hashlib
import json
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
    / "sparql_queries"
)

METADATA_FILE = (
    ROOT
    / "metadata"
    / "l172-full-sparql-queries.json"
)

LOG_FILE = (
    ROOT
    / "logs"
    / "l172-full-sparql-queries.log"
)

ERROR_FILE = (
    ROOT
    / "logs"
    / "l172-full-sparql-queries-error.log"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

METADATA_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# Hits que contienen los atributos 19.5 y 25.0 °C.

TARGETS = {
    "IKTKTZIBGO0wWaevBNFi": {
        "short_name": "attribute-19_5",
        "expected_value": "19.5",
        "expected_unit": None,
        "expected_type": "file:///apps/whyis/nan",
    },
    "eIs225cBqjuXg29aIbPm": {
        "short_name": "temperature-25C",
        "expected_value": "25.0",
        "expected_unit": "Celsius",
        "expected_type": "obo:PATO_0000146",
    },
}


# ============================================================
# FUNCIONES
# ============================================================

def sha256_text(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def sha256_file(path):
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def normalize_query(query):
    """
    Normaliza únicamente finales de línea.

    No modifica espacios internos, nombres de variables,
    URI ni sintaxis SPARQL.
    """

    return query.replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).strip() + "\n"


def extract_bindings(hit):
    source = hit.get(
        "_source",
        {},
    )

    response = source.get(
        "response",
        {},
    )

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

    return bindings if isinstance(
        bindings,
        list,
    ) else []


def binding_summary(binding):
    """
    Conserva valores, tipos y unidades sin transformarlos.
    """

    summary = {}

    for variable, cell in binding.items():
        if isinstance(cell, dict):
            summary[variable] = {
                "value": cell.get("value"),
                "type": cell.get("type"),
                "datatype": cell.get("datatype"),
                "xml_lang": cell.get("xml:lang"),
            }

        else:
            summary[variable] = {
                "value": cell,
                "type": type(cell).__name__,
                "datatype": None,
                "xml_lang": None,
            }

    return summary


def validate_query(query):
    """
    Validaciones mínimas de integridad.

    No ejecuta la consulta contra MaterialsMine.
    """

    upper = query.upper()

    checks = {
        "not_empty": bool(query.strip()),
        "contains_select": "SELECT" in upper,
        "contains_where": "WHERE" in upper,
        "contains_prefix": "PREFIX" in upper,
        "balanced_braces": (
            query.count("{")
            == query.count("}")
        ),
        "no_truncation_marker": (
            "[TRUNCADO]" not in query
            and "... [TRUNCADO]" not in query
        ),
    }

    checks["all_passed"] = all(
        checks.values()
    )

    return checks


# ============================================================
# EJECUCION
# ============================================================

def main():
    print("RECUPERANDO CONSULTAS SPARQL COMPLETAS")

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    raw = INPUT_FILE.read_bytes()

    document = json.loads(
        raw.decode("utf-8-sig")
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

    hits_by_id = {
        str(hit.get("_id")): hit
        for hit in hits
        if hit.get("_id") is not None
    }

    missing_hits = sorted(
        set(TARGETS)
        - set(hits_by_id)
    )

    if missing_hits:
        raise ValueError(
            "No se encontraron los hits: "
            + ", ".join(missing_hits)
        )

    records = []

    for hit_id, target in TARGETS.items():
        hit = hits_by_id[hit_id]

        source = hit.get(
            "_source",
            {},
        )

        query = source.get(
            "label"
        )

        if not isinstance(query, str):
            raise ValueError(
                f"El hit {hit_id} no contiene "
                "una consulta en _source.label"
            )

        query = normalize_query(
            query
        )

        checks = validate_query(
            query
        )

        output_path = (
            OUTPUT_DIR
            / (
                target["short_name"]
                + "-"
                + hit_id
                + ".sparql"
            )
        )

        output_path.write_text(
            query,
            encoding="utf-8",
            newline="\n",
        )

        bindings = extract_bindings(
            hit
        )

        records.append(
            {
                "hit_id": hit_id,
                "short_name": (
                    target["short_name"]
                ),
                "expected_value": (
                    target["expected_value"]
                ),
                "expected_unit": (
                    target["expected_unit"]
                ),
                "expected_type": (
                    target["expected_type"]
                ),
                "index": hit.get("_index"),
                "score": hit.get("_score"),
                "source_date": source.get(
                    "date"
                ),
                "source_keys": sorted(
                    str(key)
                    for key in source.keys()
                ),
                "query_file": str(
                    output_path
                ),
                "query_sha256": sha256_text(
                    query
                ),
                "query_file_sha256": (
                    sha256_file(output_path)
                ),
                "query_characters": len(
                    query
                ),
                "query_lines": len(
                    query.splitlines()
                ),
                "query_validation": checks,
                "response_variables": (
                    source.get(
                        "response",
                        {},
                    )
                    .get(
                        "head",
                        {},
                    )
                    .get(
                        "vars",
                        [],
                    )
                    if isinstance(
                        source.get("response"),
                        dict,
                    )
                    else []
                ),
                "binding_count": len(
                    bindings
                ),
                "bindings": [
                    binding_summary(binding)
                    for binding in bindings
                    if isinstance(binding, dict)
                ],
            }
        )

    metadata = {
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
        "target_hit_count": len(
            TARGETS
        ),
        "queries": records,
        "notes": [
            (
                "Las consultas se copiaron directamente "
                "desde _source.label del JSON bruto."
            ),
            (
                "Solo se normalizaron los finales de línea."
            ),
            (
                "Las consultas no se ejecutaron contra "
                "el grafo SPARQL actual."
            ),
            (
                "Los bindings se conservaron sin "
                "transformación."
            ),
        ],
    }

    METADATA_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    log_lines = [
        (
            "FASE 2 - CONSULTAS SPARQL "
            "COMPLETAS L172"
        ),
        "",
        f"Fecha: {CHECKED_AT}",
        f"Entrada: {INPUT_FILE}",
        (
            "SHA256 entrada: "
            f"{metadata['input_sha256']}"
        ),
        f"Hits totales: {len(hits)}",
        (
            "Hits objetivo encontrados: "
            f"{len(records)}"
        ),
        "",
    ]

    all_valid = True

    for record in records:
        checks = record[
            "query_validation"
        ]

        all_valid = (
            all_valid
            and checks["all_passed"]
        )

        log_lines.extend(
            [
                "=" * 72,
                (
                    "HIT: "
                    f"{record['hit_id']}"
                ),
                "=" * 72,
                (
                    "Nombre: "
                    f"{record['short_name']}"
                ),
                (
                    "Valor esperado: "
                    f"{record['expected_value']}"
                ),
                (
                    "Unidad esperada: "
                    f"{record['expected_unit']}"
                ),
                (
                    "Tipo esperado: "
                    f"{record['expected_type']}"
                ),
                (
                    "Fecha de la fuente: "
                    f"{record['source_date']}"
                ),
                (
                    "Variables de respuesta: "
                    + ", ".join(
                        str(value)
                        for value
                        in record[
                            "response_variables"
                        ]
                    )
                ),
                (
                    "Bindings: "
                    f"{record['binding_count']}"
                ),
                (
                    "Caracteres de consulta: "
                    f"{record['query_characters']}"
                ),
                (
                    "Lineas de consulta: "
                    f"{record['query_lines']}"
                ),
                (
                    "SHA256 consulta: "
                    f"{record['query_sha256']}"
                ),
                (
                    "SHA256 archivo: "
                    f"{record['query_file_sha256']}"
                ),
                (
                    "Hash coincide: "
                    + (
                        "SI"
                        if (
                            record["query_sha256"]
                            == record[
                                "query_file_sha256"
                            ]
                        )
                        else "NO"
                    )
                ),
                (
                    "SELECT presente: "
                    + (
                        "SI"
                        if checks[
                            "contains_select"
                        ]
                        else "NO"
                    )
                ),
                (
                    "WHERE presente: "
                    + (
                        "SI"
                        if checks[
                            "contains_where"
                        ]
                        else "NO"
                    )
                ),
                (
                    "PREFIX presente: "
                    + (
                        "SI"
                        if checks[
                            "contains_prefix"
                        ]
                        else "NO"
                    )
                ),
                (
                    "Llaves equilibradas: "
                    + (
                        "SI"
                        if checks[
                            "balanced_braces"
                        ]
                        else "NO"
                    )
                ),
                (
                    "Sin marcador truncado: "
                    + (
                        "SI"
                        if checks[
                            "no_truncation_marker"
                        ]
                        else "NO"
                    )
                ),
                (
                    "Validacion completa: "
                    + (
                        "SI"
                        if checks[
                            "all_passed"
                        ]
                        else "NO"
                    )
                ),
                (
                    "Archivo: "
                    f"{record['query_file']}"
                ),
                "",
            ]
        )

    log_lines.extend(
        [
            "VALIDACION GLOBAL",
            (
                "Consultas completas guardadas: "
                + (
                    "SI"
                    if all_valid
                    else "NO"
                )
            ),
            (
                "Cantidad esperada: "
                f"{len(TARGETS)}"
            ),
            (
                "Cantidad guardada: "
                f"{len(records)}"
            ),
            "",
            "ADVERTENCIAS",
            (
                "- La integridad sintactica minima "
                "no confirma que el grafo actual "
                "reproduzca los resultados."
            ),
            (
                "- Los archivos .sparql conservan "
                "el texto histórico indexado."
            ),
            (
                "- No se modificaron URI, variables "
                "ni filtros."
            ),
            (
                "- No se ejecutaron conversiones, "
                "medias ni modelos."
            ),
            "",
            f"Metadatos: {METADATA_FILE}",
            f"Directorio SPARQL: {OUTPUT_DIR}",
        ]
    )

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    if len(records) != len(TARGETS):
        raise ValueError(
            "No se guardaron las dos consultas"
        )

    if not all_valid:
        raise ValueError(
            "Una o más consultas no superaron "
            "la validación mínima"
        )

    print("")
    print("EXTRACCION COMPLETADA")
    print(
        "Consultas guardadas:",
        len(records),
    )

    for record in records:
        print(
            record["short_name"],
            "| lineas:",
            record["query_lines"],
            "| caracteres:",
            record["query_characters"],
            "| hash:",
            record["query_sha256"],
        )

    print(f"Metadatos: {METADATA_FILE}")
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