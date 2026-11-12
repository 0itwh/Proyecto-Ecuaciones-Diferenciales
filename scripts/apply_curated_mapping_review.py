from pathlib import Path
from datetime import datetime
import sys

import pandas as pd


# ============================================================
# RUTAS DEL PROYECTO
# ============================================================

ROOT = Path.cwd()

INPUT_FILE = (
    ROOT
    / "metadata"
    / "historical-xsd-curated-mapping-review.csv"
)

OUTPUT_FILE = (
    ROOT
    / "metadata"
    / "historical-xsd-curated-mapping-reviewed.csv"
)

SUMMARY_FILE = (
    ROOT
    / "metadata"
    / "historical-xsd-curated-mapping-reviewed-summary.csv"
)

CHANGES_FILE = (
    ROOT
    / "metadata"
    / "historical-xsd-curated-mapping-review-changes.csv"
)

LOG_FILE = (
    ROOT
    / "logs"
    / "historical-xsd-curated-mapping-reviewed.log"
)

ERROR_FILE = (
    ROOT
    / "logs"
    / "historical-xsd-curated-mapping-reviewed-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# ============================================================
# REGLAS: CAMBIAR A INCLUDE
# ============================================================

INCLUDE_RULES = {
    (
        "Electrical",
        "PropertiesType",
    ): (
        "Bloque electrico general dentro de "
        "PropertiesType"
    ),

    (
        "FrequencyDependence",
        "DDDependenceType",
    ): (
        "Dependencia en frecuencia dentro de la "
        "estructura dielectrica historica"
    ),

    (
        "TemperatureDependence",
        "DDDependenceType",
    ): (
        "Dependencia en temperatura dentro de la "
        "estructura dielectrica historica"
    ),
}


# ============================================================
# REGLAS: CAMBIAR A EXCLUDE
# ============================================================

EXCLUDE_RULES = {
    (
        "Amperage",
        "ExtruderOutput",
    ): (
        "Corriente asociada a la extrusora, no a una "
        "medicion electrica del nanocompuesto"
    ),

    (
        "Voltage",
        "ExtruderOutput",
    ): (
        "Tension asociada a la extrusora, no a una "
        "medicion electrica del nanocompuesto"
    ),

    (
        "frequency",
        "DMAStrainSweepTypeType",
    ): (
        "Frecuencia de ensayo DMA"
    ),

    (
        "frequency",
        "DMATemperatureType",
    ): (
        "Frecuencia utilizada en un ensayo DMA"
    ),

    (
        "FrequencySweep",
        "DMAMethodType",
    ): (
        "Barrido de frecuencia perteneciente a DMA"
    ),

    (
        "MeasurementMethod",
        "DMAType",
    ): (
        "Metodo de medicion viscoelastica DMA"
    ),

    (
        "MeasurementMethod",
        "ThermalType",
    ): (
        "Metodo de medicion termica"
    ),

    (
        "MeasurementMode",
        "DMAType",
    ): (
        "Modo de medicion perteneciente a DMA"
    ),

    (
        "TemperatureSweep",
        "DMAMethodType",
    ): (
        "Barrido de temperatura perteneciente a DMA"
    ),

    (
        "Temperature",
        "ProcessingParameterMixing",
    ): (
        "Temperatura de procesamiento o mezclado"
    ),

    (
        "Direction",
        "FEALoadingConditionsGeneralType",
    ): (
        "Direccion de carga de un analisis FEA"
    ),

    (
        "MinFrequency",
        "AbaqusModelConfigurationType",
    ): (
        "Frecuencia minima de configuracion Abaqus"
    ),

    (
        "MaxFrequency",
        "AbaqusModelConfigurationType",
    ): (
        "Frecuencia maxima de configuracion Abaqus"
    ),

    (
        "Orientation",
        "FEAMicrostructureGenerationType",
    ): (
        "Orientacion usada en generacion "
        "microestructural FEA"
    ),

    (
        "PolymerType",
        "ProcessingType",
    ): (
        "En ProcessingType, PolymerType describe un "
        "metodo de procesamiento y no la identidad "
        "de la matriz"
    ),
}


# ============================================================
# REGLAS: CONSERVAR COMO AMBIGUOUS
# ============================================================

AMBIGUOUS_RULES = {
    (
        "frequency",
        "DDTemperatureConditionType",
    ): (
        "Posible condicion de frecuencia dielectrica; "
        "la ruta en registros reales no esta verificada"
    ),

    (
        "Temperature",
        "GeneralConditionsType",
    ): (
        "Condicion general de temperatura no vinculada "
        "exclusivamente a una medicion electrica"
    ),
}


# ============================================================
# FUNCIONES
# ============================================================

def context_contains(context, expected_context):
    """
    Comprueba si el contexto esperado aparece como un nivel
    completo dentro de semantic_context.
    """

    if pd.isna(context):
        return False

    levels = str(context).split("/")

    return expected_context in levels


def find_rule(element, context, rules):
    """
    Busca una regla por nombre del elemento y contexto.
    """

    for (
        expected_element,
        expected_context,
    ), reason in rules.items():

        if (
            element == expected_element
            and context_contains(
                context,
                expected_context,
            )
        ):
            return reason

    return None


def review_row(row):
    """
    Revisa una declaración.

    Si ninguna regla explícita coincide, conserva la
    decisión inicial.
    """

    element = row["xsd_element"]
    context = row["semantic_context"]

    reason = find_rule(
        element,
        context,
        INCLUDE_RULES,
    )

    if reason is not None:
        return pd.Series(
            {
                "reviewed_decision": "include",
                "reviewed_reason": reason,
                "review_rule": (
                    "electrical_context_include"
                ),
            }
        )

    reason = find_rule(
        element,
        context,
        EXCLUDE_RULES,
    )

    if reason is not None:
        return pd.Series(
            {
                "reviewed_decision": "exclude",
                "reviewed_reason": reason,
                "review_rule": (
                    "non_target_context_exclude"
                ),
            }
        )

    reason = find_rule(
        element,
        context,
        AMBIGUOUS_RULES,
    )

    if reason is not None:
        return pd.Series(
            {
                "reviewed_decision": "ambiguous",
                "reviewed_reason": reason,
                "review_rule": (
                    "unresolved_context_ambiguous"
                ),
            }
        )

    return pd.Series(
        {
            "reviewed_decision": row["decision"],
            "reviewed_reason": row["decision_reason"],
            "review_rule": "original_decision_retained",
        }
    )


def main():
    print("INICIANDO RECLASIFICACION")

    if not INPUT_FILE.is_file():
        raise FileNotFoundError(
            f"No se encontro: {INPUT_FILE}"
        )

    data = pd.read_csv(INPUT_FILE)

    print(f"Archivo de entrada: {INPUT_FILE}")
    print(f"Filas leidas: {len(data)}")

    required_columns = {
        "category",
        "project_variable",
        "xsd_element",
        "semantic_context",
        "decision",
        "decision_reason",
    }

    missing_columns = sorted(
        required_columns - set(data.columns)
    )

    if missing_columns:
        raise ValueError(
            "Faltan columnas: "
            + ", ".join(missing_columns)
        )

    if len(data) != 59:
        raise ValueError(
            "Se esperaban 59 declaraciones, "
            f"pero se encontraron {len(data)}"
        )

    reviewed_columns = data.apply(
        review_row,
        axis=1,
    )

    result = pd.concat(
        [
            data,
            reviewed_columns,
        ],
        axis=1,
    )

    result["decision_changed"] = (
        result["decision"]
        != result["reviewed_decision"]
    )

    result["reviewed_at"] = CHECKED_AT

    result["review_status"] = (
        "contextually_reviewed_historical_xsd"
    )

    result["production_xsd_status"] = (
        "not_verified_endpoint_http_500"
    )

    result["record_observation_status"] = (
        "not_verified"
    )

    result["coverage_status"] = (
        "not_assessed"
    )

    counts = (
        result["reviewed_decision"]
        .value_counts()
        .to_dict()
    )

    include_count = counts.get(
        "include",
        0,
    )

    ambiguous_count = counts.get(
        "ambiguous",
        0,
    )

    exclude_count = counts.get(
        "exclude",
        0,
    )

    total_count = (
        include_count
        + ambiguous_count
        + exclude_count
    )

    changed = result[
        result["decision_changed"]
    ].copy()

    print("RECUENTOS CALCULADOS")
    print(f"Include: {include_count}")
    print(f"Ambiguous: {ambiguous_count}")
    print(f"Exclude: {exclude_count}")
    print(f"Total: {total_count}")
    print(f"Cambios: {len(changed)}")

    if include_count != 42:
        raise ValueError(
            "Se esperaban 42 include, "
            f"pero se obtuvieron {include_count}"
        )

    if ambiguous_count != 2:
        raise ValueError(
            "Se esperaban 2 ambiguous, "
            f"pero se obtuvieron {ambiguous_count}"
        )

    if exclude_count != 15:
        raise ValueError(
            "Se esperaban 15 exclude, "
            f"pero se obtuvieron {exclude_count}"
        )

    if total_count != 59:
        raise ValueError(
            "La suma de decisiones no es 59"
        )

    if len(changed) != 14:
        raise ValueError(
            "Se esperaban 14 cambios, "
            f"pero se obtuvieron {len(changed)}"
        )

    result = result.sort_values(
        [
            "reviewed_decision",
            "category",
            "project_variable",
            "semantic_context",
        ]
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    changed.to_csv(
        CHANGES_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    summary = (
        result.groupby(
            [
                "category",
                "reviewed_decision",
            ]
        )
        .size()
        .reset_index(
            name="declarations"
        )
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    ambiguous_rows = result[
        result["reviewed_decision"]
        == "ambiguous"
    ][
        [
            "project_variable",
            "xsd_element",
            "semantic_context",
            "reviewed_reason",
        ]
    ]

    log_lines = [
        (
            "FASE 1B - MAPEO CURADO REVISADO "
            "DEL XSD HISTORICO"
        ),
        "",
        f"Fecha: {CHECKED_AT}",
        f"Entrada: {INPUT_FILE}",
        f"Salida: {OUTPUT_FILE}",
        "",
        f"Declaraciones revisadas: {len(result)}",
        f"Include: {include_count}",
        f"Ambiguous: {ambiguous_count}",
        f"Exclude: {exclude_count}",
        f"Decisiones modificadas: {len(changed)}",
        "",
        "RESUMEN POR CATEGORIA",
        summary.to_string(index=False),
        "",
        "DECLARACIONES AMBIGUAS",
        ambiguous_rows.to_string(index=False),
        "",
        "ADVERTENCIAS",
        (
            "- Include representa correspondencia "
            "estructural en el XSD historico."
        ),
        (
            "- No demuestra observabilidad ni cobertura "
            "en registros reales."
        ),
        (
            "- El XSD de produccion continua no "
            "verificado por el error HTTP 500."
        ),
        (
            "- VARIABLEINVENTORY.csv no fue modificado."
        ),
        "",
        f"Detalle revisado: {OUTPUT_FILE}",
        f"Resumen: {SUMMARY_FILE}",
        f"Cambios: {CHANGES_FILE}",
    ]

    LOG_FILE.write_text(
        "\n".join(log_lines) + "\n",
        encoding="utf-8",
    )

    print("")
    print("RECLASIFICACION COMPLETADA")
    print(f"Filas: {len(result)}")
    print(f"Include: {include_count}")
    print(f"Ambiguous: {ambiguous_count}")
    print(f"Exclude: {exclude_count}")
    print(f"Cambios: {len(changed)}")
    print(f"Archivo: {OUTPUT_FILE}")
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