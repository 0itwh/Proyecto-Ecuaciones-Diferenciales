from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
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

OUTPUT_JSON = (
    ROOT
    / "data_interim"
    / "l172-family-bindings-deduplicated.json"
)

OUTPUT_CSV = (
    ROOT
    / "data_interim"
    / "l172-family-bindings-deduplicated.csv"
)

QUERY_INVENTORY = (
    ROOT
    / "metadata"
    / "l172-family-query-inventory.csv"
)

OUTPUT_LOG = (
    ROOT
    / "logs"
    / "l172-family-extraction.log"
)

ERROR_LOG = (
    ROOT
    / "logs"
    / "l172-family-extraction-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)

SAMPLE_PATTERN = re.compile(
    r"l172-s\d+-huo-2015",
    flags=re.IGNORECASE,
)


# ============================================================
# FUNCIONES
# ============================================================

def normalize_query(query):
    if not isinstance(query, str):
        return ""

    return "\n".join(
        line.rstrip()
        for line in query.strip().splitlines()
    )


def query_hash(query):
    normalized = normalize_query(query)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def response_hash(bindings):
    serialized = json.dumps(
        bindings,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def flatten_binding(binding):
    """
    Convierte un binding SPARQL en una fila plana,
    conservando tipo y datatype.
    """

    row = {}

    for variable, cell in binding.items():
        if isinstance(cell, dict):
            row[variable] = cell.get("value")
            row[f"{variable}__type"] = cell.get(
                "type"
            )
            row[f"{variable}__datatype"] = cell.get(
                "datatype"
            )
            row[f"{variable}__xml_lang"] = cell.get(
                "xml:lang"
            )

        else:
            row[variable] = cell

    return row


def sample_ids_in_value(value):
    text = json.dumps(
        value,
        ensure_ascii=False,
    )

    return sorted(
        {
            match.lower()
            for match in SAMPLE_PATTERN.findall(text)
        }
    )


def canonical_sample_id(row):
    """
    Busca una URI o identificador de muestra
    en las variables del binding.
    """

    preferred_fields = [
        "Sample",
        "sample",
        "this",
        "Material",
        "material",
    ]

    for field in preferred_fields:
        value = row.get(field)

        if not isinstance(value, str):
            continue

        matches = SAMPLE_PATTERN.findall(value)

        if matches:
            return matches[0].lower()

    matches = sample_ids_in_value(row)

    return matches[0] if matches else None


def scientific_key(row):
    """
    Genera una clave estable con los valores científicos.

    Se excluyen metadatos de la copia indexada, como
    fecha del hit y hash de respuesta.
    """

    excluded_suffixes = (
        "__type",
        "__datatype",
        "__xml_lang",
    )

    excluded_fields = {
        "_source_hit_id",
        "_source_date",
        "_query_sha256",
        "_response_sha256",
        "_source_index",
        "_binding_position",
        "source_occurrence_count",
        "source_occurrences",
    }

    fields = sorted(
        key
        for key in row.keys()
        if (
            key not in excluded_fields
            and not key.endswith(excluded_suffixes)
        )
    )

    return tuple(
        (field, row.get(field))
        for field in fields
    )


def safe_text(value, limit=300):
    text = str(value).replace(
        "\r",
        " ",
    ).replace(
        "\n",
        " ",
    )

    if len(text) <= limit:
        return text

    return text[:limit] + " ... [TRUNCADO]"


# ============================================================
# EJECUCION
# ============================================================

def main():
    print("EXTRAYENDO FAMILIA L172")

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    raw = INPUT_FILE.read_bytes()

    document = json.loads(
        raw.decode("utf-8-sig")
    )

    data = document.get("data", {})
    hits = data.get("hits", [])

    if not isinstance(hits, list):
        raise ValueError(
            "data.hits no es una lista"
        )

    all_rows = []
    query_records = []

    hits_with_l172 = 0
    hits_with_bindings = 0

    for hit_position, hit in enumerate(hits):
        sample_ids = sample_ids_in_value(hit)

        if not sample_ids:
            continue

        hits_with_l172 += 1

        source = hit.get("_source", {})
        response = source.get("response")

        query = source.get("label")

        if not isinstance(query, str):
            query = ""

        query_sha256 = query_hash(query)

        if not isinstance(response, dict):
            query_records.append(
                {
                    "hit_position": hit_position,
                    "index": hit.get("_index"),
                    "hit_id": hit.get("_id"),
                    "date": source.get("date"),
                    "query_sha256": query_sha256,
                    "response_sha256": "",
                    "variables": "",
                    "binding_count": 0,
                    "sample_ids": "|".join(
                        sample_ids
                    ),
                    "has_response": False,
                    "query_preview": safe_text(
                        query
                    ),
                }
            )

            continue

        head = response.get("head", {})

        variables = head.get(
            "vars",
            [],
        )

        bindings = (
            response.get("results", {})
            .get("bindings", [])
        )

        if not isinstance(bindings, list):
            bindings = []

        if bindings:
            hits_with_bindings += 1

        response_sha256 = response_hash(
            bindings
        )

        query_records.append(
            {
                "hit_position": hit_position,
                "index": hit.get("_index"),
                "hit_id": hit.get("_id"),
                "date": source.get("date"),
                "query_sha256": query_sha256,
                "response_sha256": response_sha256,
                "variables": "|".join(
                    str(variable)
                    for variable in variables
                ),
                "binding_count": len(bindings),
                "sample_ids": "|".join(
                    sample_ids
                ),
                "has_response": True,
                "query_preview": safe_text(
                    query
                ),
            }
        )

        for binding_position, binding in enumerate(
            bindings
        ):
            if not isinstance(binding, dict):
                continue

            row = flatten_binding(
                binding
            )

            row["_source_hit_id"] = hit.get(
                "_id"
            )

            row["_source_index"] = hit.get(
                "_index"
            )

            row["_source_date"] = source.get(
                "date"
            )

            row["_query_sha256"] = (
                query_sha256
            )

            row["_response_sha256"] = (
                response_sha256
            )

            row["_binding_position"] = (
                binding_position
            )

            row["sample_id"] = (
                canonical_sample_id(row)
            )

            all_rows.append(row)

    # ========================================================
    # DEDUPLICACION
    # ========================================================

    unique = {}
    occurrences = defaultdict(list)

    for row in all_rows:
        key = scientific_key(row)

        if key not in unique:
            unique[key] = row.copy()

        occurrences[key].append(
            {
                "hit_id": row.get(
                    "_source_hit_id"
                ),
                "date": row.get(
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
            }
        )

    unique_rows = []

    for key, row in unique.items():
        row["source_occurrence_count"] = len(
            occurrences[key]
        )

        row["source_occurrences"] = (
            occurrences[key]
        )

        unique_rows.append(row)

    unique_rows.sort(
        key=lambda row: (
            row.get("sample_id") or "",
            json.dumps(
                scientific_key(row),
                ensure_ascii=False,
            ),
        )
    )

    # ========================================================
    # RESUMEN DE VARIABLES
    # ========================================================

    scientific_variables = sorted(
        {
            key
            for row in unique_rows
            for key in row.keys()
            if (
                not key.startswith("_")
                and not key.endswith("__type")
                and not key.endswith("__datatype")
                and not key.endswith("__xml_lang")
                and key not in {
                    "source_occurrence_count",
                    "source_occurrences",
                }
            )
        }
    )

    sample_ids = sorted(
        {
            row.get("sample_id")
            for row in unique_rows
            if row.get("sample_id")
        }
    )

    variable_coverage = {}

    for variable in scientific_variables:
        present = sum(
            row.get(variable)
            not in (None, "")
            for row in unique_rows
        )

        variable_coverage[variable] = {
            "present": present,
            "total": len(unique_rows),
            "coverage_fraction": (
                present / len(unique_rows)
                if unique_rows
                else 0
            ),
        }

    query_hash_counts = Counter(
        record["query_sha256"]
        for record in query_records
        if record["query_sha256"]
    )

    response_hash_counts = Counter(
        record["response_sha256"]
        for record in query_records
        if record["response_sha256"]
    )

    output = {
        "generated_at": CHECKED_AT,
        "input_file": str(INPUT_FILE),
        "input_sha256": hashlib.sha256(
            raw
        ).hexdigest(),
        "search_hits_total": len(hits),
        "hits_containing_l172": hits_with_l172,
        "hits_with_sparql_bindings": (
            hits_with_bindings
        ),
        "raw_bindings": len(all_rows),
        "unique_bindings": len(unique_rows),
        "duplicates_removed": (
            len(all_rows) - len(unique_rows)
        ),
        "unique_query_hashes": len(
            query_hash_counts
        ),
        "unique_response_hashes": len(
            response_hash_counts
        ),
        "sample_ids": sample_ids,
        "scientific_variables": (
            scientific_variables
        ),
        "variable_coverage": variable_coverage,
        "query_inventory": query_records,
        "bindings": unique_rows,
        "notes": [
            (
                "Solo se procesaron hits que contienen "
                "identificadores l172-sN-huo-2015."
            ),
            (
                "Las copias indexadas se deduplicaron "
                "por valores científicos del binding."
            ),
            (
                "No se asumieron unidades."
            ),
            (
                "No se calcularon medias ni modelos."
            ),
        ],
    }

    OUTPUT_JSON.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    QUERY_INVENTORY.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_JSON.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # CSV DE BINDINGS
    # ========================================================

    flat_rows = []

    for row in unique_rows:
        flat = {}

        for key, value in row.items():
            if key == "source_occurrences":
                flat[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                )

            elif isinstance(
                value,
                (dict, list),
            ):
                flat[key] = json.dumps(
                    value,
                    ensure_ascii=False,
                )

            else:
                flat[key] = value

        flat_rows.append(flat)

    csv_columns = sorted(
        {
            key
            for row in flat_rows
            for key in row.keys()
        }
    )

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=csv_columns,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(flat_rows)

    # ========================================================
    # INVENTARIO DE CONSULTAS
    # ========================================================

    query_columns = [
        "hit_position",
        "index",
        "hit_id",
        "date",
        "query_sha256",
        "response_sha256",
        "variables",
        "binding_count",
        "sample_ids",
        "has_response",
        "query_preview",
    ]

    with QUERY_INVENTORY.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=query_columns,
        )

        writer.writeheader()
        writer.writerows(query_records)

    # ========================================================
    # LOG
    # ========================================================

    log_lines = [
        "FASE 2 - EXTRACCION DE LA FAMILIA L172",
        "",
        f"Fecha: {CHECKED_AT}",
        f"Entrada: {INPUT_FILE}",
        (
            "SHA256: "
            f"{output['input_sha256']}"
        ),
        f"Hits totales: {len(hits)}",
        (
            "Hits con l172: "
            f"{hits_with_l172}"
        ),
        (
            "Hits con bindings: "
            f"{hits_with_bindings}"
        ),
        f"Bindings brutos: {len(all_rows)}",
        (
            "Bindings unicos: "
            f"{len(unique_rows)}"
        ),
        (
            "Duplicados eliminados: "
            f"{len(all_rows) - len(unique_rows)}"
        ),
        (
            "Consultas unicas por hash: "
            f"{len(query_hash_counts)}"
        ),
        (
            "Respuestas unicas por hash: "
            f"{len(response_hash_counts)}"
        ),
        (
            "Muestras unicas: "
            f"{len(sample_ids)}"
        ),
        "",
        "MUESTRAS",
    ]

    if sample_ids:
        log_lines.extend(
            f"- {sample_id}"
            for sample_id in sample_ids
        )

    else:
        log_lines.append("- Ninguna")

    log_lines.extend(
        [
            "",
            "VARIABLES CIENTIFICAS",
        ]
    )

    for variable in scientific_variables:
        coverage = variable_coverage[
            variable
        ]

        log_lines.append(
            (
                f"- {variable}: "
                f"{coverage['present']}/"
                f"{coverage['total']} "
                f"({coverage['coverage_fraction']:.3f})"
            )
        )

    log_lines.extend(
        [
            "",
            "CONSULTAS ENCONTRADAS",
        ]
    )

    for record in query_records:
        log_lines.extend(
            [
                "",
                (
                    "Hit: "
                    f"{record['hit_position']}"
                ),
                f"Fecha: {record['date']}",
                (
                    "Variables: "
                    f"{record['variables']}"
                ),
                (
                    "Bindings: "
                    f"{record['binding_count']}"
                ),
                (
                    "Muestras: "
                    f"{record['sample_ids']}"
                ),
                (
                    "Consulta: "
                    f"{record['query_preview']}"
                ),
            ]
        )

    log_lines.extend(
        [
            "",
            "ADVERTENCIAS",
            (
                "- La cobertura se calcula sobre "
                "bindings unicos, no necesariamente "
                "sobre muestras."
            ),
            (
                "- Una misma muestra puede tener "
                "varios tipos de binding."
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
            f"JSON: {OUTPUT_JSON}",
            f"CSV: {OUTPUT_CSV}",
            (
                "Inventario de consultas: "
                f"{QUERY_INVENTORY}"
            ),
        ]
    )

    OUTPUT_LOG.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("EXTRACCION COMPLETADA")
    print(f"Hits con l172: {hits_with_l172}")
    print(f"Bindings brutos: {len(all_rows)}")
    print(
        "Bindings unicos:",
        len(unique_rows),
    )
    print(f"Muestras: {len(sample_ids)}")
    print(
        "Variables:",
        len(scientific_variables),
    )
    print(f"Log: {OUTPUT_LOG}")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        ERROR_LOG.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        ERROR_LOG.write_text(
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

        print(f"Log de error: {ERROR_LOG}")

        sys.exit(1)