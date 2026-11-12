from pathlib import Path
from datetime import datetime
import json
import re
import sys


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
    / "l172-historical-uri-inventory.json"
)

OUTPUT_LOG = (
    ROOT
    / "logs"
    / "l172-historical-uri-inventory.log"
)

ERROR_LOG = (
    ROOT
    / "logs"
    / "l172-historical-uri-inventory-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)

URI_PATTERN = re.compile(
    r"https?://[^\s\"'<>\\]+"
)

DOI_PATTERN = re.compile(
    r"10\.\d{4,9}/[-._;()/:A-Z0-9]+",
    flags=re.IGNORECASE,
)


def contains_sample(value):
    if isinstance(value, dict):
        return any(
            contains_sample(child)
            for child in value.values()
        )

    if isinstance(value, list):
        return any(
            contains_sample(child)
            for child in value
        )

    if isinstance(value, str):
        return SAMPLE_ID in value

    return False


def collect_strings(value, path="$"):
    records = []

    if isinstance(value, dict):
        for key, child in value.items():
            records.extend(
                collect_strings(
                    child,
                    f"{path}.{key}",
                )
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            records.extend(
                collect_strings(
                    child,
                    f"{path}[{index}]",
                )
            )

    elif isinstance(value, str):
        records.append(
            {
                "json_path": path,
                "text": value,
            }
        )

    return records


def classify_uri(uri):
    lower = uri.lower()

    if "/sample/" in lower:
        return "sample"

    if "doi.org/" in lower:
        return "doi_uri"

    if "/article/" in lower:
        return "article"

    if "/dataset/" in lower:
        return "dataset"

    if "/publication/" in lower:
        return "publication"

    if "materialsmine.org" in lower:
        return "materialsmine_resource"

    if "semanticscience.org" in lower:
        return "ontology_or_predicate"

    if "w3.org" in lower:
        return "standard_vocabulary"

    return "external_or_other"


def main():
    print("EXTRAYENDO URI DE HITS HISTORICOS L172")

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    document = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8-sig"
        )
    )

    hits = document.get(
        "data",
        {},
    ).get(
        "hits",
        [],
    )

    exact_hits = [
        hit
        for hit in hits
        if contains_sample(hit)
    ]

    if not exact_hits:
        raise ValueError(
            "No se encontraron hits con la muestra exacta"
        )

    uri_occurrences = {}
    doi_occurrences = {}
    hit_summaries = []

    for hit_number, hit in enumerate(
        exact_hits,
        start=1,
    ):
        strings = collect_strings(hit)

        hit_uris = set()
        hit_dois = set()

        for record in strings:
            text = record["text"]

            for uri in URI_PATTERN.findall(text):
                cleaned = uri.rstrip(
                    ".,;)]}"
                )

                hit_uris.add(cleaned)

                uri_occurrences.setdefault(
                    cleaned,
                    [],
                ).append(
                    {
                        "hit_number": hit_number,
                        "json_path": record["json_path"],
                    }
                )

            for doi in DOI_PATTERN.findall(text):
                cleaned_doi = doi.rstrip(
                    ".,;)]}"
                )

                hit_dois.add(cleaned_doi)

                doi_occurrences.setdefault(
                    cleaned_doi,
                    [],
                ).append(
                    {
                        "hit_number": hit_number,
                        "json_path": record["json_path"],
                    }
                )

        source = hit.get("_source", {})

        response = source.get(
            "response",
            {},
        )

        bindings = (
            response.get("results", {})
            .get("bindings", [])
            if isinstance(response, dict)
            else []
        )

        hit_summaries.append(
            {
                "hit_number": hit_number,
                "index": hit.get("_index"),
                "hit_id": hit.get("_id"),
                "date": source.get("date"),
                "label_or_query": source.get("label"),
                "response_variables": (
                    response.get("head", {})
                    .get("vars", [])
                    if isinstance(response, dict)
                    else []
                ),
                "binding_count": len(bindings),
                "sample_ids": sorted(
                    {
                        uri.rsplit("/", 1)[-1]
                        for uri in hit_uris
                        if "/sample/" in uri.lower()
                    }
                ),
                "non_sample_uris": sorted(
                    uri
                    for uri in hit_uris
                    if "/sample/" not in uri.lower()
                ),
                "literal_dois": sorted(hit_dois),
            }
        )

    uri_inventory = [
        {
            "uri": uri,
            "classification": classify_uri(uri),
            "occurrence_count": len(occurrences),
            "occurrences": occurrences,
        }
        for uri, occurrences in sorted(
            uri_occurrences.items()
        )
    ]

    non_sample_materialsmine = [
        item
        for item in uri_inventory
        if (
            item["classification"]
            == "materialsmine_resource"
        )
    ]

    output = {
        "generated_at": CHECKED_AT,
        "sample_id": SAMPLE_ID,
        "input_file": str(INPUT_FILE),
        "search_hits_total": len(hits),
        "exact_hits": len(exact_hits),
        "unique_uris": len(uri_inventory),
        "literal_dois": sorted(
            doi_occurrences.keys()
        ),
        "non_sample_materialsmine_resources": (
            non_sample_materialsmine
        ),
        "hit_summaries": hit_summaries,
        "uri_inventory": uri_inventory,
        "notes": [
            (
                "Los URI de ontologias y vocabularios "
                "no son identificadores de registros."
            ),
            (
                "Un recurso MaterialsMine distinto de "
                "sample puede ser candidato a articulo "
                "o dataset y requiere revision."
            ),
            (
                "No se realizaron consultas externas "
                "ni transformaciones."
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
        "FASE 2 - INVENTARIO DE URI HISTORICOS L172",
        "",
        f"Fecha: {CHECKED_AT}",
        f"Muestra: {SAMPLE_ID}",
        f"Entrada: {INPUT_FILE}",
        f"Hits totales: {len(hits)}",
        f"Hits exactos: {len(exact_hits)}",
        f"URI unicos: {len(uri_inventory)}",
        (
            "DOI literales: "
            f"{len(doi_occurrences)}"
        ),
        (
            "Recursos MaterialsMine no muestra: "
            f"{len(non_sample_materialsmine)}"
        ),
        "",
        "RESUMEN DE HITS",
    ]

    for hit in hit_summaries:
        log_lines.extend(
            [
                "",
                f"Hit {hit['hit_number']}",
                f"Indice: {hit['index']}",
                f"ID: {hit['hit_id']}",
                f"Fecha: {hit['date']}",
                (
                    "Variables: "
                    + ", ".join(
                        hit["response_variables"]
                    )
                ),
                (
                    "Bindings: "
                    f"{hit['binding_count']}"
                ),
                (
                    "Muestras: "
                    + ", ".join(
                        hit["sample_ids"]
                    )
                ),
                "URI no muestra:",
            ]
        )

        if hit["non_sample_uris"]:
            log_lines.extend(
                f"- {uri}"
                for uri in hit["non_sample_uris"]
            )
        else:
            log_lines.append("- Ninguno")

        log_lines.append(
            "DOI literales:"
        )

        if hit["literal_dois"]:
            log_lines.extend(
                f"- {doi}"
                for doi in hit["literal_dois"]
            )
        else:
            log_lines.append("- Ninguno")

    log_lines.extend(
        [
            "",
            "RECURSOS MATERIALSMINE NO MUESTRA",
        ]
    )

    if non_sample_materialsmine:
        log_lines.extend(
            (
                f"- {item['uri']} | "
                f"{item['classification']}"
            )
            for item in non_sample_materialsmine
        )
    else:
        log_lines.append("- Ninguno")

    log_lines.extend(
        [
            "",
            "INTERPRETACION",
            (
                "- Si no aparecen recursos MaterialsMine "
                "distintos de sample, la variable ?doi "
                "no fue conservada en los bindings."
            ),
            (
                "- Si aparecen URI de articulo o dataset, "
                "se revisaran antes de consultarlas."
            ),
            (
                "- Los URI de ontologia no son DOI "
                "ni identificadores de registros."
            ),
            "",
            f"JSON detallado: {OUTPUT_JSON}",
        ]
    )

    OUTPUT_LOG.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("EXTRACCION COMPLETADA")
    print(f"Hits exactos: {len(exact_hits)}")
    print(f"URI unicos: {len(uri_inventory)}")
    print(
        "Recursos MaterialsMine no muestra:",
        len(non_sample_materialsmine),
    )
    print(f"DOI literales: {len(doi_occurrences)}")
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