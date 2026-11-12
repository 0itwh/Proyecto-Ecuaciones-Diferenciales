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

URL = (
    "https://materialsmine.org"
    "/api/files/metamine"
)

RAW_DIR = ROOT / "data_raw" / "metamine"
LOG_DIR = ROOT / "logs"
METADATA_DIR = ROOT / "metadata"

RAW_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

LOG_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

METADATA_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESPONSE_FILE = (
    RAW_DIR
    / "files-metamine-response.bin"
)

JSON_FILE = (
    RAW_DIR
    / "files-metamine-response.json"
)

TEXT_FILE = (
    RAW_DIR
    / "files-metamine-response.txt"
)

LOG_FILE = (
    LOG_DIR
    / "files-metamine-access.log"
)

METADATA_FILE = (
    METADATA_DIR
    / "files-metamine-response-metadata.json"
)

ERROR_FILE = (
    LOG_DIR
    / "files-metamine-access-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# ============================================================
# FUNCIONES
# ============================================================

def safe_preview(response, limit=500):
    """
    Devuelve una vista previa limitada.

    No imprime respuestas completas ni contenido binario.
    """

    content_type = (
        response.headers.get(
            "content-type",
            "",
        )
        .lower()
    )

    textual_types = (
        "json",
        "text/",
        "xml",
        "javascript",
        "html",
    )

    if any(
        value in content_type
        for value in textual_types
    ):
        return response.text[:limit]

    return response.content[:80].hex()


def describe_json(value):
    """
    Resume la estructura JSON sin ejecutar nuevas consultas.
    """

    result = {
        "json_top_level_type": type(value).__name__,
        "json_item_count": None,
        "json_top_level_keys": [],
        "candidate_file_names": [],
    }

    if isinstance(value, list):
        result["json_item_count"] = len(value)

        candidate_names = []

        for item in value[:500]:
            if isinstance(item, str):
                candidate_names.append(item)

            elif isinstance(item, dict):
                for key in (
                    "fileName",
                    "filename",
                    "name",
                    "file",
                    "path",
                    "key",
                ):
                    candidate = item.get(key)

                    if isinstance(candidate, str):
                        candidate_names.append(candidate)
                        break

        result["candidate_file_names"] = (
            candidate_names[:100]
        )

    elif isinstance(value, dict):
        result["json_top_level_keys"] = sorted(
            str(key)
            for key in value.keys()
        )

        result["json_item_count"] = len(value)

        candidate_names = []

        for key in (
            "files",
            "data",
            "results",
            "items",
        ):
            collection = value.get(key)

            if not isinstance(collection, list):
                continue

            for item in collection[:500]:
                if isinstance(item, str):
                    candidate_names.append(item)

                elif isinstance(item, dict):
                    for name_key in (
                        "fileName",
                        "filename",
                        "name",
                        "file",
                        "path",
                        "key",
                    ):
                        candidate = item.get(
                            name_key
                        )

                        if isinstance(
                            candidate,
                            str,
                        ):
                            candidate_names.append(
                                candidate
                            )
                            break

        result["candidate_file_names"] = (
            candidate_names[:100]
        )

    return result


# ============================================================
# EJECUCION
# ============================================================

def main():
    print("CONSULTANDO GET /files/metamine")
    print(f"URL: {URL}")

    session = requests.Session()

    session.headers.update(
        {
            "Accept": (
                "application/json, "
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

    RESPONSE_FILE.write_bytes(
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
            "status_code": previous.status_code,
            "url": previous.url,
            "location": previous.headers.get(
                "location"
            ),
        }
        for previous in response.history
    ]

    json_status = "not_attempted"
    json_summary = {
        "json_top_level_type": None,
        "json_item_count": None,
        "json_top_level_keys": [],
        "candidate_file_names": [],
    }

    parsed_json = None

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

        json_summary = describe_json(
            parsed_json
        )

    except ValueError:
        json_status = "not_json"

        if (
            "text/" in content_type.lower()
            or "xml" in content_type.lower()
            or "html" in content_type.lower()
        ):
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
        "operation_scope": (
            "read_only_catalog_probe"
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

    candidate_names = json_summary.get(
        "candidate_file_names",
        [],
    )

    log_lines = [
        (
            "FASE 1B - ACCESO A "
            "GET /files/metamine"
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
            f"{json_summary.get('json_top_level_type')}"
        ),
        (
            "Elementos JSON: "
            f"{json_summary.get('json_item_count')}"
        ),
        (
            "Claves superiores: "
            + ", ".join(
                json_summary.get(
                    "json_top_level_keys",
                    [],
                )
            )
        ),
        (
            "Nombres candidatos detectados: "
            f"{len(candidate_names)}"
        ),
        "",
        "NOMBRES CANDIDATOS",
        (
            "\n".join(candidate_names)
            if candidate_names
            else "Ninguno detectado automaticamente"
        ),
        "",
        "VISTA PREVIA LIMITADA",
        safe_preview(response),
        "",
        "INTERPRETACION AUTOMATICA",
        (
            "Respuesta recibida correctamente."
            if response.status_code < 400
            else (
                "La API devolvio un codigo de error; "
                "se conserva la respuesta original."
            )
        ),
        (
            "No se ejecutaron consultas posteriores "
            "a rutas con fileName."
        ),
        (
            "La presencia de nombres no demuestra "
            "todavia series composicion-propiedad."
        ),
        "",
        f"Respuesta original: {RESPONSE_FILE}",
        f"Metadatos: {METADATA_FILE}",
    ]

    if parsed_json is not None:
        log_lines.append(
            f"JSON normalizado: {JSON_FILE}"
        )

    elif TEXT_FILE.is_file():
        log_lines.append(
            f"Texto recibido: {TEXT_FILE}"
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
    print(
        "Nombres candidatos:",
        len(candidate_names),
    )
    print(f"Log: {LOG_FILE}")

    # No se considera fallo técnico recibir 4xx o 5xx.
    # La respuesta se conserva como evidencia.
    # Solo los errores de ejecución activan except.


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