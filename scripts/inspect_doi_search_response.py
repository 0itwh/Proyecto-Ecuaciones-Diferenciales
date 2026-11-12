from pathlib import Path
from datetime import datetime
import hashlib
import json
import sys


ROOT = Path.cwd()

DOI = "10.1021/acs.jpcc.5b08809"
SAMPLE_PREFIX = "l172-"

INPUT_FILE = (
    ROOT
    / "data_raw"
    / "explorer"
    / "doi-10.1021-acs.jpcc.5b08809-search-response.json"
)

OUTPUT_JSON = (
    ROOT
    / "data_interim"
    / "doi-10.1021-acs.jpcc.5b08809-relevant-hits.json"
)

OUTPUT_LOG = (
    ROOT
    / "logs"
    / "doi-10.1021-acs.jpcc.5b08809-inspection.log"
)

ERROR_LOG = (
    ROOT
    / "logs"
    / "doi-10.1021-acs.jpcc.5b08809-inspection-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)

TERMS = [
    DOI.lower(),
    "l172-",
    "huo",
    "conductivity",
    "electricconductivity",
    "unitofmeasure",
    "frequency",
    "temperature",
    "volumefraction",
    "matrix",
    "filler",
    "poly(vinylidene fluoride)",
    "barium titanate",
    "iron oxide",
    "fe3o4",
    "batio3",
    "doi",
    "article",
]


def contains_term(value, term):
    if isinstance(value, dict):
        return any(
            contains_term(child, term)
            for child in value.values()
        )

    if isinstance(value, list):
        return any(
            contains_term(child, term)
            for child in value
        )

    if isinstance(value, str):
        return term in value.lower()

    return False


def collect_scalar_matches(
    value,
    path="$",
    output=None,
):
    if output is None:
        output = []

    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"

            collect_scalar_matches(
                child,
                child_path,
                output,
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{path}[{index}]"

            collect_scalar_matches(
                child,
                child_path,
                output,
            )

    else:
        text = str(value)
        lower = text.lower()

        matched = [
            term
            for term in TERMS
            if (
                term in lower
                or term in path.lower()
            )
        ]

        if matched:
            output.append(
                {
                    "json_path": path,
                    "value": value,
                    "value_type": type(value).__name__,
                    "matched_terms": matched,
                }
            )

    return output


def extract_sample_ids(value):
    text = json.dumps(
        value,
        ensure_ascii=False,
    )

    sample_ids = set()

    marker = "l172-"
    position = 0

    while True:
        position = text.lower().find(
            marker,
            position,
        )

        if position < 0:
            break

        end = position

        while (
            end < len(text)
            and text[end]
            not in '"<> ,;\\n\\t\\\\'
        ):
            end += 1

        candidate = text[position:end]

        if candidate:
            sample_ids.add(candidate)

        position = end

    return sorted(sample_ids)


def main():
    print("INSPECCIONANDO RESPUESTA DEL DOI")

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

    relevant_hits = []

    for position, hit in enumerate(hits):
        matched_terms = [
            term
            for term in TERMS
            if contains_term(hit, term)
        ]

        if not matched_terms:
            continue

        source = hit.get("_source", {})

        relevant_hits.append(
            {
                "position": position,
                "index": hit.get("_index"),
                "hit_id": hit.get("_id"),
                "score": hit.get("_score"),
                "source_keys": sorted(
                    str(key)
                    for key in source.keys()
                ),
                "matched_terms": matched_terms,
                "sample_ids": extract_sample_ids(hit),
                "priority_fields": collect_scalar_matches(
                    hit
                ),
                "original_hit": hit,
            }
        )

    all_sample_ids = sorted(
        {
            sample_id
            for hit in relevant_hits
            for sample_id in hit["sample_ids"]
        }
    )

    term_counts = {
        term: sum(
            term in hit["matched_terms"]
            for hit in relevant_hits
        )
        for term in TERMS
    }

    output = {
        "generated_at": CHECKED_AT,
        "input_file": str(INPUT_FILE),
        "input_sha256": hashlib.sha256(
            raw
        ).hexdigest(),
        "doi_searched": DOI,
        "search_hits_total": len(hits),
        "relevant_hits": len(relevant_hits),
        "sample_ids_found": all_sample_ids,
        "term_hit_counts": term_counts,
        "hits": relevant_hits,
        "notes": [
            (
                "Las coincidencias son candidatos "
                "contextuales y requieren revisión."
            ),
            (
                "No se asumieron unidades."
            ),
            (
                "No se realizaron promedios, "
                "conversiones ni modelos."
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
        "FASE 2 - INSPECCION DE RESPUESTA DEL DOI",
        "",
        f"Fecha: {CHECKED_AT}",
        f"DOI: {DOI}",
        f"Entrada: {INPUT_FILE}",
        (
            "SHA256: "
            f"{output['input_sha256']}"
        ),
        f"Hits totales: {len(hits)}",
        (
            "Hits relevantes: "
            f"{len(relevant_hits)}"
        ),
        (
            "Muestras l172 encontradas: "
            f"{len(all_sample_ids)}"
        ),
        "",
        "MUESTRAS ENCONTRADAS",
    ]

    if all_sample_ids:
        log_lines.extend(
            f"- {sample_id}"
            for sample_id in all_sample_ids
        )

    else:
        log_lines.append(
            "Ninguna"
        )

    log_lines.extend(
        [
            "",
            "CONTEOS POR TERMINO",
        ]
    )

    for term, count in term_counts.items():
        log_lines.append(
            f"- {term}: {count}"
        )

    log_lines.extend(
        [
            "",
            "RESUMEN DE HITS RELEVANTES",
        ]
    )

    for number, hit in enumerate(
        relevant_hits,
        start=1,
    ):
        log_lines.extend(
            [
                "",
                f"Hit {number}",
                f"Posicion: {hit['position']}",
                f"Indice: {hit['index']}",
                f"ID: {hit['hit_id']}",
                (
                    "Terminos: "
                    + ", ".join(
                        hit["matched_terms"]
                    )
                ),
                (
                    "Muestras: "
                    + (
                        ", ".join(hit["sample_ids"])
                        if hit["sample_ids"]
                        else "ninguna"
                    )
                ),
                (
                    "Campos prioritarios: "
                    f"{len(hit['priority_fields'])}"
                ),
            ]
        )

    log_lines.extend(
        [
            "",
            "CLASIFICACION",
            (
                "- DOI en MaterialsMine: "
                + (
                    "documentado en la respuesta"
                    if term_counts[DOI.lower()] > 0
                    else "no localizado"
                )
            ),
            (
                "- Vinculo con muestras l172: "
                + (
                    "candidato confirmado por coincidencia"
                    if all_sample_ids
                    else "no localizado"
                )
            ),
            (
                "- Unidad, frecuencia y temperatura "
                "requieren revisión de rutas concretas."
            ),
            "",
            "ADVERTENCIAS",
            (
                "- Una coincidencia textual no prueba "
                "por si sola una relación experimental."
            ),
            (
                "- No se asumieron unidades."
            ),
            (
                "- No se aplicaron transformaciones "
                "ni modelos."
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
    print("INSPECCION COMPLETADA")
    print(f"Hits totales: {len(hits)}")
    print(
        "Hits relevantes:",
        len(relevant_hits),
    )
    print(
        "Muestras l172:",
        len(all_sample_ids),
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