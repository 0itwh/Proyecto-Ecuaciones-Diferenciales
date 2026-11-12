from pathlib import Path
import json
import sys


ROOT = Path.cwd()

DOWNLOAD_DIR = (
    ROOT
    / "data_raw"
    / "metamine"
    / "downloaded"
)

OUTPUT_FILE = (
    ROOT
    / "logs"
    / "metamine-download-errors-inspected.log"
)

ERROR_FILE = (
    ROOT
    / "logs"
    / "metamine-download-errors-inspected-error.log"
)


def main():
    print("INSPECCIONANDO RESPUESTAS DESCARGADAS")

    if not DOWNLOAD_DIR.is_dir():
        raise FileNotFoundError(
            f"No existe: {DOWNLOAD_DIR}"
        )

    files = sorted(
        path
        for path in DOWNLOAD_DIR.iterdir()
        if path.is_file()
    )

    if not files:
        raise ValueError(
            "No se encontraron respuestas descargadas"
        )

    lines = [
        "FASE 1B - INSPECCION DE ERRORES METAMINE",
        "",
        f"Directorio: {DOWNLOAD_DIR}",
        f"Archivos inspeccionados: {len(files)}",
        "",
    ]

    for path in files:
        content = path.read_bytes()

        text = content.decode(
            "utf-8",
            errors="replace",
        )

        json_status = "not_json"
        formatted = text

        try:
            parsed = json.loads(text)

            json_status = "parsed"

            formatted = json.dumps(
                parsed,
                indent=2,
                ensure_ascii=False,
            )

        except ValueError:
            pass

        lines.extend(
            [
                f"ARCHIVO: {path.name}",
                f"Bytes: {len(content)}",
                f"JSON: {json_status}",
                "Contenido:",
                formatted,
                "",
            ]
        )

        print("")
        print(f"Archivo: {path.name}")
        print(f"Bytes: {len(content)}")
        print(f"JSON: {json_status}")
        print(f"Contenido: {formatted}")

    OUTPUT_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("INSPECCION COMPLETADA")
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