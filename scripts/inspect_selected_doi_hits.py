from pathlib import Path
from datetime import datetime
import json
import sys


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

INPUT_FILE = (
    ROOT
    / "data_interim"
    / "doi-10.1021-acs.jpcc.5b08809-relevant-hits.json"
)

OUTPUT_JSON = (
    ROOT
    / "data_interim"
    / "doi-selected-hits-13-25-26.json"
)

OUTPUT_LOG = (
    ROOT
    / "logs"
    / "doi-selected-hits-13-25-26.log"
)

ERROR_LOG = (
    ROOT
    / "logs"
    / "doi-selected-hits-13-25-26-error.log"
)

# Números humanos del informe, comenzando en 1.
SELECTED_HIT_NUMBERS = [13, 25, 26]

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)

PRIORITY_TERMS = [
    "10.1021/acs.jpcc.5b08809",
    "doi",
    "article",
    "title",
    "author",
    "journal",
    "year",
    "sample",
    "l172",
    "huo",
    "conductivity",
    "electricconductivity",
    "unitofmeasure",
    "unit",
    "frequency",
    "temperature",
    "volumefraction",
    "matrix",
    "filler",
    "poly(vinylidene fluoride)",
    "pvdf",
    "barium titanate",
    "iron oxide",
    "fe3o4",
    "batio3",
    "response",
    "results",
    "bindings",
    "label",
    "description",
]


# ============================================================
# FUNCIONES
# ============================================================

def walk(value, path="$"):
    """
    Recorre recursivamente un objeto JSON.
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


def priority_matches(value):
    """
    Conserva solamente valores escalares relacionados
    con los términos prioritarios.
    """

    matches = []

    for item in walk(value):
        path_lower = item["json_path"].lower()
        value_text = str(item["value"])
        value_lower = value_text.lower()

        matched_terms = [
            term
            for term in PRIORITY_TERMS
            if (
                term in path_lower
                or term in value_lower
            )
        ]

        if not matched_terms:
            continue

        matches.append(
            {
                "json_path": item["json_path"],
                "value": item["value"],
                "value_type": item["value_type"],
                "matched_terms": matched_terms,
            }
        )

    return matches


def find_exact_values(matches, term):
    """
    Recupera valores únicos vinculados a un término.
    """

    values = []

    for match in matches:
        if term not in match["matched_terms"]:
            continue

        value = match["value"]

        if not isinstance(
            value,
            (str, int, float, bool),
        ):
            continue

        value_text = str(value)

        if value_text not in values:
            values.append(value_text)

    return values


def compact_text(value, limit=400):
    """
    Evita que una sola celda o consulta gigantesca
    vuelva ilegible el informe.
    """

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


def main():
    print("INSPECCIONANDO HITS 13, 25 Y 26")

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
        "hits",
        [],
    )

    if not isinstance(hits, list):
        raise ValueError(
            "El campo hits no es una lista"
        )

    print(f"Hits relevantes disponibles: {len(hits)}")

    selected = []

    for human_number in SELECTED_HIT_NUMBERS:
        array_index = human_number - 1

        if array_index < 0 or array_index >= len(hits):
            raise IndexError(
                f"El hit {human_number} no existe. "
                f"Solo hay {len(hits)} hits."
            )

        hit = hits[array_index]

        original_hit = hit.get(
            "original_hit",
            {},
        )

        source = original_hit.get(
            "_source",
            {},
        )

        matches = priority_matches(
            original_hit
        )

        selected.append(
            {
                "human_hit_number": human_number,
                "array_index": array_index,
                "search_position": hit.get("position"),
                "index_name": hit.get("index"),
                "hit_id": hit.get("hit_id"),
                "matched_terms_from_previous_scan": (
                    hit.get("matched_terms", [])
                ),
                "source_keys": sorted(
                    str(key)
                    for key in source.keys()
                ),
                "title": (
                    source.get("title")
                    or source.get("name")
                    or ""
                ),
                "label": source.get("label"),
                "description": source.get(
                    "description"
                ),
                "date": source.get("date"),
                "priority_matches": matches,
                "doi_values": find_exact_values(
                    matches,
                    "doi",
                ),
                "sample_values": find_exact_values(
                    matches,
                    "sample",
                ),
                "conductivity_values": find_exact_values(
                    matches,
                    "conductivity",
                ),
                "unit_values": find_exact_values(
                    matches,
                    "unitofmeasure",
                ),
                "frequency_values": find_exact_values(
                    matches,
                    "frequency",
                ),
                "temperature_values": find_exact_values(
                    matches,
                    "temperature",
                ),
                "matrix_values": find_exact_values(
                    matches,
                    "matrix",
                ),
                "filler_values": find_exact_values(
                    matches,
                    "filler",
                ),
                "original_hit": original_hit,
            }
        )

    output = {
        "generated_at": CHECKED_AT,
        "input_file": str(INPUT_FILE),
        "selected_hit_numbers": SELECTED_HIT_NUMBERS,
        "selected_hit_count": len(selected),
        "hits": selected,
        "warnings": [
            (
                "Las coincidencias de texto no confirman "
                "una relación con la serie l172."
            ),
            (
                "Los valores doi pueden incluir nombres "
                "de variables y no DOI literales."
            ),
            (
                "No se asumieron unidades ni condiciones."
            ),
            (
                "No se realizaron conversiones, "
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
        "FASE 2 - INSPECCION DE HITS 13, 25 Y 26",
        "",
        f"Fecha: {CHECKED_AT}",
        f"Entrada: {INPUT_FILE}",
        (
            "Hits seleccionados: "
            + ", ".join(
                str(number)
                for number in SELECTED_HIT_NUMBERS
            )
        ),
        "",
    ]

    for selected_hit in selected:
        log_lines.extend(
            [
                "=" * 72,
                (
                    "HIT "
                    f"{selected_hit['human_hit_number']}"
                ),
                "=" * 72,
                (
                    "Posicion original: "
                    f"{selected_hit['search_position']}"
                ),
                (
                    "Indice: "
                    f"{selected_hit['index_name']}"
                ),
                (
                    "ID: "
                    f"{selected_hit['hit_id']}"
                ),
                (
                    "Claves de _source: "
                    + ", ".join(
                        selected_hit["source_keys"]
                    )
                ),
                (
                    "Titulo: "
                    + compact_text(
                        selected_hit["title"]
                    )
                ),
                (
                    "Fecha: "
                    f"{selected_hit['date']}"
                ),
                (
                    "Terminos previos: "
                    + ", ".join(
                        selected_hit[
                            "matched_terms_from_previous_scan"
                        ]
                    )
                ),
                (
                    "Coincidencias prioritarias: "
                    f"{len(selected_hit['priority_matches'])}"
                ),
                "",
                "ETIQUETA O CONSULTA:",
                compact_text(
                    selected_hit["label"],
                    limit=2000,
                ),
                "",
                "DESCRIPCION:",
                compact_text(
                    selected_hit["description"],
                    limit=1000,
                ),
                "",
                "CONTEOS ESPECIFICOS:",
                (
                    "DOI: "
                    f"{len(selected_hit['doi_values'])}"
                ),
                (
                    "Muestras: "
                    f"{len(selected_hit['sample_values'])}"
                ),
                (
                    "Conductividad: "
                    f"{len(selected_hit['conductivity_values'])}"
                ),
                (
                    "Unidades: "
                    f"{len(selected_hit['unit_values'])}"
                ),
                (
                    "Frecuencia: "
                    f"{len(selected_hit['frequency_values'])}"
                ),
                (
                    "Temperatura: "
                    f"{len(selected_hit['temperature_values'])}"
                ),
                (
                    "Matriz: "
                    f"{len(selected_hit['matrix_values'])}"
                ),
                (
                    "Relleno: "
                    f"{len(selected_hit['filler_values'])}"
                ),
                "",
                "VALORES DOI CANDIDATOS:",
            ]
        )

        if selected_hit["doi_values"]:
            log_lines.extend(
                "- " + compact_text(value)
                for value in selected_hit["doi_values"]
            )
        else:
            log_lines.append("- Ninguno")

        log_lines.append("")
        log_lines.append(
            "VALORES DE MUESTRA CANDIDATOS:"
        )

        if selected_hit["sample_values"]:
            log_lines.extend(
                "- " + compact_text(value)
                for value in selected_hit["sample_values"]
            )
        else:
            log_lines.append("- Ninguno")

        log_lines.append("")
        log_lines.append(
            "PRIMERAS 30 COINCIDENCIAS PRIORITARIAS:"
        )

        for match in selected_hit[
            "priority_matches"
        ][:30]:
            log_lines.append(
                (
                    f"- {match['json_path']} | "
                    f"{compact_text(match['value'])} | "
                    + ",".join(
                        match["matched_terms"]
                    )
                )
            )

        if len(
            selected_hit["priority_matches"]
        ) > 30:
            log_lines.append(
                (
                    "- ... "
                    f"{len(selected_hit['priority_matches']) - 30} "
                    "coincidencias adicionales en el JSON detallado"
                )
            )

        log_lines.append("")

    log_lines.extend(
        [
            "ADVERTENCIAS",
            (
                "- El nombre doi puede ser una variable "
                "SPARQL y no un DOI bibliografico."
            ),
            (
                "- Una coincidencia de frecuencia o "
                "temperatura debe conservar su ruta."
            ),
            (
                "- No se asumieron unidades."
            ),
            (
                "- No se ejecutaron modelos."
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
    print(f"Hits inspeccionados: {len(selected)}")
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