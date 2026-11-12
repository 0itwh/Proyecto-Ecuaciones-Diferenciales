from pathlib import Path
from datetime import datetime
import hashlib
import json
import sys

import requests


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

URL = "https://materialsmine.org/api/mn/ontology"

OUTPUT_DIR = ROOT / "data_raw" / "ontology"
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

RAW_FILE = (
    OUTPUT_DIR
    / "materialsmine-ontology-response.bin"
)

JSON_FILE = (
    OUTPUT_DIR
    / "materialsmine-ontology-response.json"
)

TEXT_FILE = (
    OUTPUT_DIR
    / "materialsmine-ontology-response.txt"
)

METADATA_FILE = (
    METADATA_DIR
    / "materialsmine-ontology-response-metadata.json"
)

LOG_FILE = (
    LOG_DIR
    / "materialsmine-ontology-access.log"
)

ERROR_FILE = (
    LOG_DIR
    / "materialsmine-ontology-access-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# ============================================================
# FUNCIONES
# ============================================================

def summarise_json(value):
    """
    Resume la estructura JSON sin modificarla.
    """

    summary = {
        "top_level_type": type(value).__name__,
        "top_level_count": None,
        "top_level_keys": [],
        "sample_item_types": [],
    }

    if isinstance(value, dict):
        summary["top_level_count"] = len(value)

        summary["top_level_keys"] = sorted(
            str(key)
            for key in value.keys()
        )

        sample_values = list(value.values())[:20]

        summary["sample_item_types"] = sorted(
            {
                type(item).__name__
                for item in sample_values
            }
        )

    elif isinstance(value, list):
        summary["top_level_count"] = len(value)

        summary["sample_item_types"] = sorted(
            {
                type(item).__name__
                for item in value[:20]
            }
        )

    return summary


def limited_preview(response, limit=1000):
    """
    Devuelve una vista previa limitada de la respuesta.
    """

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    textual = (
        "json",
        "text/",
        "xml",
        "html",
        "javascript",
    )

    if any(
        token in content_type
        for token in textual
    ):
        return response.text[:limit]

    return response.content[:100].hex()


# ============================================================
# EJECUCION
# ============================================================

def main():
    print("CONSULTANDO GET /mn/ontology")
    print(f"URL: {URL}")

    session = requests.Session()

    session.headers.update(
        {
            "Accept": (
                "application/json, "
                "application/xml, "
                "text/plain, "
                "*/*"
            ),
            "User-Agent": (
                "NanoMine-N3-Phase1B-Audit/1.0"
            ),
        }
    )

    response = session.get(
        URL,
        timeout=60,
        allow_redirects=True,
    )

    RAW_FILE.write_bytes(
        response.content
    )

    sha256 = hashlib.sha256(
        response.content
    ).hexdigest()

    content_type = response.headers.get(
        "content-type",
        "",
    )

    content_disposition = (
        response.headers.get(
            "content-disposition"
        )
    )

    redirects = [
        {
            "status_code": item.status_code,
            "url": item.url,
            "location": item.headers.get(
                "location"
            ),
        }
        for item in response.history
    ]

    parsed_json = None
    json_status = "not_json"

    json_summary = {
        "top_level_type": None,
        "top_level_count": None,
        "top_level_keys": [],
        "sample_item_types": [],
    }

    try:
        parsed_json = response.json()
        json_status = "parsed"

        JSON_FILE.write_text(
            json.dumps(
                parsed_json,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        json_summary = summarise_json(
            parsed_json
        )

    except ValueError:
        TEXT_FILE.write_text(
            response.text,
            encoding="utf-8",
        )

    metadata = {
        "checked_at": CHECKED_AT,
        "method": "GET",
        "requested_url": URL,
        "final_url": response.url,
        "status_code": response.status_code,
        "reason": response.reason,
        "content_type": content_type,
        "content_disposition": (
            content_disposition
        ),
        "response_bytes": len(
            response.content
        ),
        "sha256": sha256,
        "redirects": redirects,
        "json_status": json_status,
        **json_summary,
        "authentication_used": False,
        "request_parameters": {},
        "openapi_security_status": (
            "not_declared"
        ),
        "follow_up_requests_executed": 0,
    }

    METADATA_FILE.write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    log_lines = [
        (
            "FASE 1B - ACCESO A "
            "GET /mn/ontology"
        ),
        "",
        f"Fecha: {CHECKED_AT}",
        "Metodo: GET",
        f"URL solicitada: {URL}",
        f"URL final: {response.url}",
        (
            f"HTTP: {response.status_code} "
            f"{response.reason}"
        ),
        f"Tipo: {content_type}",
        (
            "Content-Disposition: "
            f"{content_disposition}"
        ),
        f"Bytes: {len(response.content)}",
        f"SHA256: {sha256}",
        f"Redirecciones: {len(redirects)}",
        f"JSON: {json_status}",
        (
            "Tipo JSON superior: "
            f"{json_summary['top_level_type']}"
        ),
        (
            "Cantidad superior: "
            f"{json_summary['top_level_count']}"
        ),
        (
            "Claves superiores: "
            + ", ".join(
                json_summary["top_level_keys"]
            )
        ),
        (
            "Tipos de muestra: "
            + ", ".join(
                json_summary[
                    "sample_item_types"
                ]
            )
        ),
        "",
        "VISTA PREVIA LIMITADA",
        limited_preview(response),
        "",
        "ADVERTENCIAS",
        (
            "- La ontologia puede describir "
            "vocabulario sin contener registros."
        ),
        (
            "- La presencia de una clase o propiedad "
            "no demuestra observabilidad."
        ),
        (
            "- No se ejecutaron consultas posteriores."
        ),
        (
            "- No se aplicaron transformaciones "
            "ni modelos."
        ),
        "",
        f"Respuesta original: {RAW_FILE}",
        f"Metadatos: {METADATA_FILE}",
    ]

    if parsed_json is not None:
        log_lines.append(
            f"JSON normalizado: {JSON_FILE}"
        )

    else:
        log_lines.append(
            f"Respuesta textual: {TEXT_FILE}"
        )

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("CONSULTA COMPLETADA")
    print(f"HTTP: {response.status_code}")
    print(f"Tipo: {content_type}")
    print(f"Bytes: {len(response.content)}")
    print(f"JSON: {json_status}")
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