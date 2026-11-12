from pathlib import Path
import sys

import pandas as pd


ROOT = Path.cwd()

INPUT_FILE = (
    ROOT
    / "metadata"
    / "l172-conductivity-context-query-inventory.csv"
)

OUTPUT_FILE = (
    ROOT
    / "logs"
    / "l172-conductivity-context-invalid-queries.log"
)

ERROR_FILE = (
    ROOT
    / "logs"
    / "l172-conductivity-context-diagnostic-error.log"
)


def as_boolean(series):
    return (
        series
        .astype(str)
        .str.strip()
        .str.lower()
        .map(
            {
                "true": True,
                "false": False,
                "1": True,
                "0": False,
            }
        )
        .fillna(False)
        .astype(bool)
    )


def main():
    print("DIAGNOSTICANDO CONSULTAS CANDIDATAS")

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    data = pd.read_csv(
        INPUT_FILE,
        keep_default_na=False,
    )

    required = {
        "search_position",
        "hit_id",
        "source_date",
        "classification",
        "response_variables",
        "binding_count",
        "query_file",
        "query_characters",
        "query_lines",
        "query_sha256",
        "query_file_sha256",
        "hash_matches",
        "query_valid",
    }

    missing = sorted(
        required - set(data.columns)
    )

    if missing:
        raise ValueError(
            "Faltan columnas: "
            + ", ".join(missing)
        )

    data["query_valid_bool"] = as_boolean(
        data["query_valid"]
    )

    data["hash_matches_bool"] = as_boolean(
        data["hash_matches"]
    )

    invalid = data[
        ~data["query_valid_bool"]
        | ~data["hash_matches_bool"]
    ].copy()

    valid = data[
        data["query_valid_bool"]
        & data["hash_matches_bool"]
    ].copy()

    columns = [
        "search_position",
        "hit_id",
        "source_date",
        "classification",
        "conductivity_terms",
        "relation_terms",
        "frequency_terms",
        "temperature_terms",
        "unit_terms",
        "measurement_terms",
        "response_variables",
        "binding_count",
        "query_characters",
        "query_lines",
        "query_valid",
        "hash_matches",
        "query_file",
    ]

    columns = [
        column
        for column in columns
        if column in data.columns
    ]

    lines = [
        (
            "FASE 2 - DIAGNOSTICO DE CONSULTAS "
            "DE CONDUCTIVIDAD"
        ),
        "",
        f"Entrada: {INPUT_FILE}",
        f"Consultas candidatas: {len(data)}",
        f"Consultas validas: {len(valid)}",
        f"Consultas invalidas: {len(invalid)}",
        "",
        "CONSULTAS INVALIDAS",
        "",
    ]

    if invalid.empty:
        lines.append(
            "Ninguna. Revisar conversion booleana "
            "del script principal."
        )

    else:
        lines.append(
            invalid[columns].to_string(
                index=False
            )
        )

    lines.extend(
        [
            "",
            "CONSULTAS VALIDAS",
            "",
        ]
    )

    if valid.empty:
        lines.append("Ninguna")

    else:
        lines.append(
            valid[columns].to_string(
                index=False
            )
        )

    OUTPUT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("DIAGNOSTICO COMPLETADO")
    print(f"Candidatas: {len(data)}")
    print(f"Validas: {len(valid)}")
    print(f"Invalidas: {len(invalid)}")
    print(f"Log: {OUTPUT_FILE}")


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

        print(f"Log de error: {ERROR_FILE}")

        sys.exit(1)