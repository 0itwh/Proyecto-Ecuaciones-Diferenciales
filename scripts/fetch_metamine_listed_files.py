from pathlib import Path
from datetime import datetime
from urllib.parse import quote
import hashlib
import json
import re
import sys

import pandas as pd
import requests


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

CATALOG_FILE = (
    ROOT
    / "data_raw"
    / "metamine"
    / "files-metamine-response.json"
)

OUTPUT_DIR = (
    ROOT
    / "data_raw"
    / "metamine"
    / "downloaded"
)

METADATA_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

METADATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

BASE_URL = (
    "https://materialsmine.org"
    "/api/files/metamine"
)

METADATA_FILE = (
    METADATA_DIR
    / "metamine-downloaded-files.csv"
)

LOG_FILE = (
    LOG_DIR
    / "metamine-downloaded-files.log"
)

ERROR_FILE = (
    LOG_DIR
    / "metamine-downloaded-files-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# ============================================================
# FUNCIONES
# ============================================================

def safe_windows_name(original_name):
    """
    Sustituye caracteres que Windows no permite en nombres.

    El nombre original se conserva en los metadatos.
    """

    return re.sub(
        r'[<>:"/\\|?*]',
        "-",
        original_name,
    )


def inspect_csv(path):
    """
    Inspecciona el CSV sin modificarlo.
    """

    result = {
        "csv_read_status": "not_attempted",
        "csv_rows": None,
        "csv_columns": None,
        "csv_column_names": "",
    }

    try:
        data = pd.read_csv(path)

        result["csv_read_status"] = "parsed"
        result["csv_rows"] = len(data)
        result["csv_columns"] = len(data.columns)
        result["csv_column_names"] = "|".join(
            str(column)
            for column in data.columns
        )

    except Exception as error:
        result["csv_read_status"] = (
            f"error:{type(error).__name__}:{error}"
        )

    return result


# ============================================================
# EJECUCION
# ============================================================

def main():
    print("LEYENDO CATALOGO METAMINE")

    if not CATALOG_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {CATALOG_FILE}"
        )

    catalog = json.loads(
        CATALOG_FILE.read_text(
            encoding="utf-8",
        )
    )

    entries = catalog.get(
        "fetchedNames",
        [],
    )

    if not isinstance(entries, list):
        raise ValueError(
            "fetchedNames no es una lista"
        )

    names = []

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")

        if isinstance(name, str) and name:
            names.append(name)

    names = list(dict.fromkeys(names))

    print(f"Archivos enumerados: {len(names)}")

    if not names:
        raise ValueError(
            "No se encontraron nombres en fetchedNames"
        )

    session = requests.Session()

    session.headers.update(
        {
            "Accept": (
                "text/csv, "
                "application/json, "
                "text/plain, "
                "*/*"
            ),
            "User-Agent": (
                "NanoMine-N3-Phase1B-Audit/1.0"
            ),
        }
    )

    records = []

    for index, original_name in enumerate(
        names,
        start=1,
    ):
        encoded_name = quote(
            original_name,
            safe="",
        )

        url = (
            BASE_URL
            + "/"
            + encoded_name
        )

        print("")
        print(
            f"[{index}/{len(names)}] "
            f"Consultando: {original_name}"
        )

        response = session.get(
            url,
            timeout=60,
            allow_redirects=True,
        )

        local_name = safe_windows_name(
            original_name
        )

        local_path = (
            OUTPUT_DIR
            / local_name
        )

        local_path.write_bytes(
            response.content
        )

        sha256 = hashlib.sha256(
            response.content
        ).hexdigest()

        content_type = response.headers.get(
            "content-type",
            "",
        )

        csv_info = {
            "csv_read_status": "not_applicable",
            "csv_rows": None,
            "csv_columns": None,
            "csv_column_names": "",
        }

        if (
            response.status_code < 400
            and (
                original_name.lower().endswith(
                    ".csv"
                )
                or "csv" in content_type.lower()
            )
        ):
            csv_info = inspect_csv(
                local_path
            )

        records.append(
            {
                "checked_at": CHECKED_AT,
                "catalog_key": next(
                    (
                        entry.get("key")
                        for entry in entries
                        if entry.get("name")
                        == original_name
                    ),
                    None,
                ),
                "bucket_name": next(
                    (
                        entry.get("bucket_name")
                        for entry in entries
                        if entry.get("name")
                        == original_name
                    ),
                    "",
                ),
                "original_file_name": original_name,
                "local_file_name": local_name,
                "requested_url": url,
                "final_url": response.url,
                "http_status": response.status_code,
                "http_reason": response.reason,
                "content_type": content_type,
                "content_disposition": (
                    response.headers.get(
                        "content-disposition"
                    )
                ),
                "response_bytes": len(
                    response.content
                ),
                "sha256": sha256,
                "redirect_count": len(
                    response.history
                ),
                "local_path": str(
                    local_path
                ),
                **csv_info,
                "record_observation_status": (
                    "not_yet_assessed"
                ),
                "series_status": (
                    "not_yet_assessed"
                ),
            }
        )

        print(
            f"HTTP: {response.status_code}"
        )

        print(
            f"Tipo: {content_type}"
        )

        print(
            f"Bytes: {len(response.content)}"
        )

        print(
            "CSV:",
            csv_info[
                "csv_read_status"
            ],
        )

    result = pd.DataFrame(records)

    result.to_csv(
        METADATA_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    log_lines = [
        (
            "FASE 1B - DESCARGA DE ARCHIVOS "
            "ENUMERADOS POR METAMINE"
        ),
        "",
        f"Fecha: {CHECKED_AT}",
        f"Catalogo: {CATALOG_FILE}",
        f"Archivos enumerados: {len(names)}",
        f"Archivos consultados: {len(result)}",
        "",
        result[
            [
                "original_file_name",
                "http_status",
                "content_type",
                "response_bytes",
                "csv_read_status",
                "csv_rows",
                "csv_columns",
                "csv_column_names",
                "sha256",
            ]
        ].to_string(
            index=False,
        ),
        "",
        "ADVERTENCIAS",
        (
            "- Los nombres proceden directamente "
            "de fetchedNames."
        ),
        (
            "- Los dos archivos parecen muestras "
            "de MetaMine por su nombre."
        ),
        (
            "- La descarga no demuestra todavía "
            "series composicion-propiedad."
        ),
        (
            "- No se aplicaron transformaciones "
            "ni modelos."
        ),
        (
            "- Los dos puntos del nombre original "
            "se sustituyen solo en el nombre local "
            "porque Windows no los permite."
        ),
        "",
        f"Metadatos: {METADATA_FILE}",
        f"Directorio: {OUTPUT_DIR}",
    ]

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("DESCARGA COMPLETADA")
    print(f"Archivos: {len(result)}")
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

        print(f"Log de error: {ERROR_FILE}")

        sys.exit(1)