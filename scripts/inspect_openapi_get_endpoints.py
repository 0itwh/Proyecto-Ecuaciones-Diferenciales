from pathlib import Path
import json
import sys

import pandas as pd


ROOT = Path.cwd()

OPENAPI_FILE = (
    ROOT
    / "api_docs"
    / "materialsmine-openapi.json"
)

OUTPUT_FILE = (
    ROOT
    / "metadata"
    / "materialsmine-get-endpoints.csv"
)

LOG_FILE = (
    ROOT
    / "logs"
    / "materialsmine-get-endpoints.log"
)

ERROR_FILE = (
    ROOT
    / "logs"
    / "materialsmine-get-endpoints-error.log"
)


def parameter_text(parameters):
    results = []

    for parameter in parameters:
        name = parameter.get("name", "")
        location = parameter.get("in", "")
        required = parameter.get("required", False)

        schema = parameter.get(
            "schema",
            {},
        )

        data_type = schema.get(
            "type",
            "",
        )

        results.append(
            (
                f"{name}"
                f"|in={location}"
                f"|required={required}"
                f"|type={data_type}"
            )
        )

    return "; ".join(results)


def security_text(operation, document):
    security = operation.get("security")

    if security is None:
        security = document.get("security")

    if security is None:
        return "not_declared"

    if security == []:
        return "none_declared"

    return json.dumps(
        security,
        ensure_ascii=False,
    )


def main():
    print("INSPECCIONANDO OPENAPI LOCAL")

    if not OPENAPI_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {OPENAPI_FILE}"
        )

    document = json.loads(
        OPENAPI_FILE.read_text(
            encoding="utf-8",
        )
    )

    servers = document.get(
        "servers",
        [],
    )

    production_server = ""

    for server in servers:
        url = server.get("url", "")

        if url == "https://materialsmine.org/api":
            production_server = url

    records = []

    for path, path_item in document.get(
        "paths",
        {},
    ).items():

        if "get" not in path_item:
            continue

        operation = path_item["get"]

        parameters = []

        parameters.extend(
            path_item.get(
                "parameters",
                [],
            )
        )

        parameters.extend(
            operation.get(
                "parameters",
                [],
            )
        )

        required_parameters = [
            parameter.get("name", "")
            for parameter in parameters
            if parameter.get("required", False)
        ]

        responses = operation.get(
            "responses",
            {},
        )

        records.append(
            {
                "method": "GET",
                "path": path,
                "operation_id": operation.get(
                    "operationId",
                    "",
                ),
                "summary": (
                    operation.get("summary")
                    or operation.get("description")
                    or ""
                ).replace(
                    "\n",
                    " ",
                ),
                "parameters": parameter_text(
                    parameters
                ),
                "required_parameters": ";".join(
                    required_parameters
                ),
                "required_parameter_count": len(
                    required_parameters
                ),
                "security": security_text(
                    operation,
                    document,
                ),
                "response_codes": ";".join(
                    responses.keys()
                ),
                "production_url_candidate": (
                    production_server + path
                    if production_server
                    else ""
                ),
                "execution_status": (
                    "not_executed"
                ),
            }
        )

    data = pd.DataFrame(records)

    if data.empty:
        raise ValueError(
            "No se encontraron operaciones GET"
        )

    data = data.sort_values(
        [
            "required_parameter_count",
            "path",
        ]
    )

    data.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    safe_candidates = data[
        data["required_parameter_count"] == 0
    ]

    lines = [
        "FASE 1B - OPERACIONES GET DOCUMENTADAS",
        "",
        (
            "Titulo: "
            + document.get(
                "info",
                {},
            ).get(
                "title",
                "",
            )
        ),
        (
            "Version OpenAPI: "
            + document.get(
                "openapi",
                "",
            )
        ),
        (
            "Version API: "
            + document.get(
                "info",
                {},
            ).get(
                "version",
                "",
            )
        ),
        (
            "Servidor de produccion: "
            + (
                production_server
                or "NO IDENTIFICADO"
            )
        ),
        f"Operaciones GET: {len(data)}",
        (
            "GET sin parametros obligatorios: "
            f"{len(safe_candidates)}"
        ),
        "",
        "TODAS LAS OPERACIONES GET",
        data[
            [
                "path",
                "operation_id",
                "required_parameters",
                "security",
                "response_codes",
            ]
        ].to_string(
            index=False,
        ),
        "",
        "CANDIDATOS SIN PARAMETROS OBLIGATORIOS",
        safe_candidates[
            [
                "path",
                "operation_id",
                "summary",
                "security",
            ]
        ].to_string(
            index=False,
        ),
        "",
        "NOTA:",
        (
            "Este script solo inspecciona la "
            "especificacion OpenAPI local."
        ),
        (
            "No ejecuta llamadas a la API ni "
            "descarga registros."
        ),
    ]

    LOG_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("INSPECCION COMPLETADA")
    print(f"Operaciones GET: {len(data)}")
    print(
        "Sin parametros obligatorios:",
        len(safe_candidates),
    )
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