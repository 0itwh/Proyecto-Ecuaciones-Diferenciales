from pathlib import Path
import json
import sys

import pandas as pd


ROOT = Path.cwd()

INPUT_FILE = (
    ROOT
    / "data_raw"
    / "ontology"
    / "materialsmine-ontology-response.json"
)

OUTPUT_FILE = (
    ROOT
    / "metadata"
    / "materialsmine-ontology-priority-matches.csv"
)

SUMMARY_FILE = (
    ROOT
    / "metadata"
    / "materialsmine-ontology-priority-summary.csv"
)

LOG_FILE = (
    ROOT
    / "logs"
    / "materialsmine-ontology-priority-inspection.log"
)

ERROR_FILE = (
    ROOT
    / "logs"
    / "materialsmine-ontology-priority-inspection-error.log"
)


SEARCH_GROUPS = {
    "propiedades_electricas": [
        "electric conductivity",
        "conductivity",
        "surface resistivity",
        "volume resistivity",
        "resistivity",
        "dielectric",
        "frequency",
    ],
    "composicion": [
        "mass fraction",
        "volume fraction",
        "weight fraction",
        "filler composition",
        "composition",
        "concentration",
        "loading",
    ],
    "materiales": [
        "matrix",
        "filler",
        "polymer",
        "particle",
        "nanoparticle",
        "interphase",
    ],
    "familias_candidatas": [
        "carbon nanotube",
        "cnt",
        "graphene",
        "graphite nanoplatelet",
        "gnp",
        "carbon black",
    ],
    "identificadores": [
        "controlid",
        "control id",
        "curationid",
        "sample id",
        "dataset",
        "file id",
    ],
}


def walk(value, json_path="$"):
    """
    Recorre recursivamente dictados y listas del JSON.
    """

    if isinstance(value, dict):
        yield json_path, value

        for key, child in value.items():
            child_path = f"{json_path}.{key}"
            yield from walk(child, child_path)

    elif isinstance(value, list):
        for index, child in enumerate(value):
            child_path = f"{json_path}[{index}]"
            yield from walk(child, child_path)


def searchable_text(item):
    """
    Convierte los campos escalares de un objeto en texto.
    """

    parts = []

    for key, value in item.items():
        if isinstance(
            value,
            (str, int, float, bool),
        ):
            parts.append(str(key))
            parts.append(str(value))

    return " ".join(parts).lower()


def first_value(item, keys):
    for key in keys:
        value = item.get(key)

        if value is not None:
            return value

    return ""


def main():
    print("INSPECCIONANDO ONTOLOGIA LOCAL")

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    document = json.loads(
        INPUT_FILE.read_text(
            encoding="utf-8",
        )
    )

    records = []
    seen = set()

    for json_path, item in walk(document):
        text = searchable_text(item)

        if not text:
            continue

        for group, terms in SEARCH_GROUPS.items():
            matched = [
                term
                for term in terms
                if term in text
            ]

            if not matched:
                continue

            ontology_id = first_value(
                item,
                [
                    "ID",
                    "id",
                    "@id",
                    "iri",
                    "IRI",
                ],
            )

            preferred_name = first_value(
                item,
                [
                    "Preferred Name",
                    "prefLabel",
                    "Label",
                    "label",
                    "name",
                ],
            )

            key = (
                group,
                json_path,
                str(ontology_id),
                str(preferred_name),
            )

            if key in seen:
                continue

            seen.add(key)

            records.append(
                {
                    "search_group": group,
                    "matched_terms": "|".join(
                        matched
                    ),
                    "preferred_name": preferred_name,
                    "ontology_id": ontology_id,
                    "prefix_iri": first_value(
                        item,
                        [
                            "prefixIRI",
                            "prefix_iri",
                        ],
                    ),
                    "json_path": json_path,
                    "item_keys": "|".join(
                        sorted(
                            str(key)
                            for key in item.keys()
                        )
                    ),
                    "evidence_status": (
                        "documented_in_public_ontology"
                    ),
                    "record_observation_status": (
                        "not_verified"
                    ),
                }
            )

    result = pd.DataFrame(records)

    if result.empty:
        result = pd.DataFrame(
            columns=[
                "search_group",
                "matched_terms",
                "preferred_name",
                "ontology_id",
                "prefix_iri",
                "json_path",
                "item_keys",
                "evidence_status",
                "record_observation_status",
            ]
        )

    else:
        result = result.sort_values(
            [
                "search_group",
                "preferred_name",
                "json_path",
            ]
        )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    if result.empty:
        summary = pd.DataFrame(
            columns=[
                "search_group",
                "matches",
            ]
        )

    else:
        summary = (
            result.groupby("search_group")
            .size()
            .reset_index(name="matches")
        )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    log_lines = [
        (
            "FASE 1B - INSPECCION PRIORITARIA "
            "DE LA ONTOLOGIA"
        ),
        "",
        f"Entrada: {INPUT_FILE}",
        f"Coincidencias: {len(result)}",
        "",
        "RESUMEN",
        (
            summary.to_string(index=False)
            if not summary.empty
            else "Sin coincidencias"
        ),
        "",
        "NOMBRES ENCONTRADOS",
    ]

    if result.empty:
        log_lines.append("Ninguno")

    else:
        for group in sorted(
            result["search_group"].unique()
        ):
            names = sorted(
                {
                    str(value)
                    for value in result.loc[
                        result["search_group"]
                        == group,
                        "preferred_name",
                    ]
                    if str(value).strip()
                }
            )

            log_lines.append("")
            log_lines.append(
                f"{group}:"
            )

            log_lines.extend(
                f"- {name}"
                for name in names
            )

    log_lines.extend(
        [
            "",
            "ADVERTENCIAS",
            (
                "- Las coincidencias describen "
                "vocabulario de la ontologia."
            ),
            (
                "- No demuestran presencia ni "
                "cobertura en registros."
            ),
            (
                "- Una coincidencia textual puede "
                "requerir revision contextual."
            ),
            (
                "- No se realizaron nuevas "
                "consultas a Internet."
            ),
            "",
            f"Detalle: {OUTPUT_FILE}",
            f"Resumen: {SUMMARY_FILE}",
        ]
    )

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("INSPECCION COMPLETADA")
    print(f"Coincidencias: {len(result)}")
    print(f"CSV: {OUTPUT_FILE}")
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

        print(
            f"ERROR: {type(error).__name__}: "
            f"{error}"
        )

        print(f"Log de error: {ERROR_FILE}")

        sys.exit(1)