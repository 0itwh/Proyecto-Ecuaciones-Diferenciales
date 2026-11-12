from pathlib import Path
from datetime import datetime
import hashlib
import json
import sys


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

SAMPLE_ID = "l172-s13-huo-2015"

INPUT_FILE = (
    ROOT
    / "data_raw"
    / "explorer"
    / "l172-s13-huo-2015-search-response.json"
)

OUTPUT_JSON = (
    ROOT
    / "data_interim"
    / "l172-s13-huo-2015-exact-context.json"
)

OUTPUT_LOG = (
    ROOT
    / "logs"
    / "l172-s13-huo-2015-exact-context.log"
)

ERROR_LOG = (
    ROOT
    / "logs"
    / "l172-s13-huo-2015-exact-context-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)

SEARCH_TERMS = [
    "unitofmeasure",
    "unit",
    "frequency",
    "temperature",
    "doi",
    "controlid",
    "curationid",
    "fileid",
    "xml",
    "sample",
    "conductivity",
    "volumefraction",
    "matrix",
    "filler",
    "article",
    "reference",
    "title",
]


# ============================================================
# FUNCIONES
# ============================================================

def contains_exact_sample(value):
    """
    Comprueba recursivamente si un objeto contiene
    exactamente el identificador de muestra.
    """

    if isinstance(value, dict):
        return any(
            contains_exact_sample(child)
            for child in value.values()
        )

    if isinstance(value, list):
        return any(
            contains_exact_sample(child)
            for child in value
        )

    if isinstance(value, str):
        return SAMPLE_ID in value

    return False


def walk(value, path="$"):
    """
    Recorre recursivamente un objeto JSON y devuelve
    ruta, valor y tipo.
    """

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"

            yield from walk(
                child,
                child_path,
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"

            yield from walk(
                child,
                child_path,
            )

    else:
        yield {
            "json_path": path,
            "value": value,
            "value_type": type(value).__name__,
        }


def matched_fields(value):
    """
    Extrae campos escalares relacionados con las
    variables prioritarias.
    """

    matches = []

    for item in walk(value):
        path_lower = item["json_path"].lower()

        value_text = str(
            item["value"]
        ).lower()

        matched_terms = [
            term
            for term in SEARCH_TERMS
            if (
                term in path_lower
                or term in value_text
            )
        ]

        if matched_terms:
            matches.append(
                {
                    **item,
                    "matched_terms": matched_terms,
                }
            )

    return matches


def compact_preview(value, limit=1500):
    """
    Genera una vista previa limitada para el log.
    """

    text = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
    )

    if len(text) <= limit:
        return text

    return (
        text[:limit]
        + "\n... VISTA PREVIA TRUNCADA ..."
    )


# ============================================================
# EJECUCION
# ============================================================

def main():
    print("EXTRAYENDO CONTEXTO DE MUESTRA")
    print(f"Muestra: {SAMPLE_ID}")

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

    data = document.get(
        "data",
        {},
    )

    hits = data.get(
        "hits",
        [],
    )

    if not isinstance(hits, list):
        raise ValueError(
            "data.hits no es una lista"
        )

    exact_hits = []

    for position, hit in enumerate(hits):
        if not contains_exact_sample(hit):
            continue

        source = hit.get(
            "_source",
            {},
        )

        fields = matched_fields(
            hit
        )

        exact_hits.append(
            {
                "position_in_search_results": position,
                "index": hit.get("_index"),
                "hit_id": hit.get("_id"),
                "score": hit.get("_score"),
                "source_keys": sorted(
                    str(key)
                    for key in source.keys()
                ),
                "title": (
                    source.get("title")
                    or source.get("name")
                    or ""
                ),
                "date": source.get("date"),
                "label": source.get("label"),
                "matched_fields": fields,
                "original_hit": hit,
            }
        )

    unique_values = {
        term: []
        for term in SEARCH_TERMS
    }

    for hit in exact_hits:
        for field in hit["matched_fields"]:
            value = field["value"]

            if isinstance(
                value,
                (str, int, float, bool),
            ):
                value_text = str(value)

                for term in field["matched_terms"]:
                    if (
                        value_text
                        not in unique_values[term]
                    ):
                        unique_values[term].append(
                            value_text
                        )

    output = {
        "generated_at": CHECKED_AT,
        "input_file": str(INPUT_FILE),
        "input_sha256": hashlib.sha256(
            raw
        ).hexdigest(),
        "sample_id": SAMPLE_ID,
        "search_hits_total": len(hits),
        "exact_hits_found": len(exact_hits),
        "search_terms": SEARCH_TERMS,
        "unique_priority_values": unique_values,
        "exact_hits": exact_hits,
        "evidence_status": {
            "sample_identifier": "confirmed",
            "unit": "not_verified",
            "frequency": "not_verified",
            "temperature": "not_verified",
            "doi": "not_verified",
            "control_id": "not_verified",
            "curation_id": "not_verified",
            "file_id": "not_verified",
        },
        "notes": [
            (
                "Solo se conservaron hits que contienen "
                "el identificador exacto de muestra."
            ),
            (
                "Las coincidencias de frecuencia, "
                "temperatura o DOI deben revisarse "
                "en su contexto antes de aceptarse."
            ),
            (
                "No se aplicaron conversiones, "
                "promedios ni modelos."
            ),
        ],
    }

    OUTPUT_JSON.parent.mkdir(
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

    log_lines = [
        (
            "FASE 2 - EXTRACCION DE CONTEXTO "
            "DE MUESTRA"
        ),
        "",
        f"Fecha: {CHECKED_AT}",
        f"Muestra: {SAMPLE_ID}",
        f"Entrada: {INPUT_FILE}",
        (
            "SHA256 entrada: "
            f"{output['input_sha256']}"
        ),
        f"Hits totales: {len(hits)}",
        (
            "Hits con identificador exacto: "
            f"{len(exact_hits)}"
        ),
        "",
        "HITS EXACTOS",
    ]

    for number, hit in enumerate(
        exact_hits,
        start=1,
    ):
        log_lines.extend(
            [
                "",
                f"Hit {number}",
                (
                    "Posicion: "
                    f"{hit['position_in_search_results']}"
                ),
                f"Indice: {hit['index']}",
                f"ID del hit: {hit['hit_id']}",
                f"Titulo: {hit['title']}",
                f"Fecha: {hit['date']}",
                (
                    "Claves principales: "
                    + ", ".join(
                        hit["source_keys"]
                    )
                ),
                (
                    "Campos prioritarios encontrados: "
                    f"{len(hit['matched_fields'])}"
                ),
                "Vista previa:",
                compact_preview(
                    hit["original_hit"]
                ),
            ]
        )

    log_lines.extend(
        [
            "",
            "CONTEOS DE VALORES PRIORITARIOS",
        ]
    )

    for term in SEARCH_TERMS:
        log_lines.append(
            (
                f"{term}: "
                f"{len(unique_values[term])}"
            )
        )

    log_lines.extend(
        [
            "",
            "ADVERTENCIAS",
            (
                "- Una coincidencia textual no "
                "demuestra automáticamente su "
                "relación experimental."
            ),
            (
                "- No se asumieron unidades."
            ),
            (
                "- No se interpretaron frecuencia "
                "o temperatura sin ruta contextual."
            ),
            (
                "- No se ejecutaron modelos."
            ),
            "",
            f"JSON extraído: {OUTPUT_JSON}",
        ]
    )

    OUTPUT_LOG.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("EXTRACCION COMPLETADA")
    print(f"Hits totales: {len(hits)}")
    print(
        "Hits exactos:",
        len(exact_hits),
    )
    print(f"JSON: {OUTPUT_JSON}")
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