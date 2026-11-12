from pathlib import Path
import sys

import pandas as pd


ROOT = Path.cwd()

INPUT_FILE = (
    ROOT
    / "metadata"
    / "historical-xsd-curated-mapping-review.csv"
)

OUTPUT_FILE = (
    ROOT
    / "logs"
    / "historical-xsd-curated-declarations.txt"
)

ERROR_FILE = (
    ROOT
    / "logs"
    / "historical-xsd-curated-declarations-error.txt"
)

COLUMNS = [
    "decision",
    "category",
    "project_variable",
    "xsd_element",
    "xsd_type",
    "min_occurs",
    "max_occurs",
    "semantic_context",
    "decision_reason",
]


def main():
    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro el archivo: {INPUT_FILE}"
        )

    data = pd.read_csv(INPUT_FILE)

    missing_columns = [
        column
        for column in COLUMNS
        if column not in data.columns
    ]

    if missing_columns:
        raise ValueError(
            "Faltan columnas: "
            + ", ".join(missing_columns)
        )

    report = data[COLUMNS].copy()

    report = report.sort_values(
        [
            "decision",
            "category",
            "project_variable",
            "semantic_context",
        ]
    )

    include_count = (
        report["decision"] == "include"
    ).sum()

    ambiguous_count = (
        report["decision"] == "ambiguous"
    ).sum()

    exclude_count = (
        report["decision"] == "exclude"
    ).sum()

    header = [
        "FASE 1B - DECLARACIONES CURADAS DEL XSD HISTORICO",
        "",
        f"Archivo de entrada: {INPUT_FILE}",
        f"Filas totales: {len(report)}",
        f"Include: {include_count}",
        f"Ambiguous: {ambiguous_count}",
        f"Exclude: {exclude_count}",
        "",
        "NOTA:",
        (
            "include significa correspondencia estructural "
            "en el XSD historico."
        ),
        (
            "No significa observabilidad ni cobertura "
            "en registros reales."
        ),
        "",
        "DECLARACIONES",
        "",
    ]

    content = (
        "\n".join(header)
        + report.to_string(index=False)
        + "\n"
    )

    OUTPUT_FILE.write_text(
        content,
        encoding="utf-8",
    )

    print("INFORME GUARDADO")
    print(f"Filas: {len(report)}")
    print(f"Include: {include_count}")
    print(f"Ambiguous: {ambiguous_count}")
    print(f"Exclude: {exclude_count}")
    print(f"Archivo: {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        ERROR_FILE.write_text(
            f"{type(error).__name__}: {error}\n",
            encoding="utf-8",
        )

        print(
            f"ERROR: {type(error).__name__}: {error}"
        )

        print(f"Log de error: {ERROR_FILE}")

        sys.exit(1)