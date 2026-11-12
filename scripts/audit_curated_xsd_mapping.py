from pathlib import Path
from datetime import datetime
import hashlib
import sys

import pandas as pd
from lxml import etree


# ============================================================
# CONFIGURACION
# ============================================================

ROOT = Path.cwd()

XSD_PATH = (
    ROOT
    / "schemas"
    / "nanomine-schema-master"
    / "xml"
    / "PNC_schema_062722.xsd"
)

METADATA_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"

METADATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

NS = {"xs": "http://www.w3.org/2001/XMLSchema"}

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)


# Lista curada para evitar los falsos positivos
# encontrados por la busqueda amplia anterior.

TARGETS = [
    # Materiales
    ("materiales", "matrix", "Matrix"),
    ("materiales", "matrix_component", "MatrixComponent"),
    ("materiales", "polymer_type", "PolymerType"),
    ("materiales", "polymer_class", "PolymerClass"),
    ("materiales", "chemical_name", "ChemicalName"),
    ("materiales", "standard_chemical_name", "StdChemicalName"),
    ("materiales", "trade_name", "TradeName"),
    ("materiales", "abbreviation", "Abbreviation"),
    (
        "materiales",
        "manufacturer_or_source",
        "ManufacturerOrSourceName",
    ),
    ("materiales", "filler", "Filler"),
    ("materiales", "filler_component", "FillerComponent"),
    ("materiales", "particle", "Particle"),
    ("materiales", "particle_type", "ParticleType"),
    (
        "materiales",
        "particle_aspect_ratio",
        "ParticleAspectRatio",
    ),
    (
        "materiales",
        "particle_surface_treatment",
        "ParticleSurfaceTreatment",
    ),
    ("materiales", "surface_treatment", "SurfaceTreatment"),
    (
        "materiales",
        "surface_chemistry_processing",
        "SurfaceChemistryProcessing",
    ),

    # Composicion
    (
        "composicion",
        "filler_composition",
        "FillerComposition",
    ),
    (
        "composicion",
        "filler_component_composition",
        "FillerComponentComposition",
    ),
    (
        "composicion",
        "filler_component_in_composite",
        "FillerComponentInComposite",
    ),
    (
        "composicion",
        "matrix_component_composition",
        "MatrixComponentComposition",
    ),
    ("composicion", "fraction", "Fraction"),
    ("composicion", "mass_fraction_branch", "mass"),
    ("composicion", "volume_fraction_branch", "volume"),

    # Propiedades y condiciones electricas
    (
        "condiciones_electricas",
        "electrical_section",
        "Electrical",
    ),
    (
        "condiciones_electricas",
        "electrical_conductivity",
        "ElectricConductivity",
    ),
    (
        "condiciones_electricas",
        "surface_resistivity",
        "SurfaceResistivity",
    ),
    (
        "condiciones_electricas",
        "volume_resistivity",
        "VolumeResistivity",
    ),
    (
        "condiciones_electricas",
        "frequency_dependence",
        "FrequencyDependence",
    ),
    (
        "condiciones_electricas",
        "frequency_sweep",
        "FrequencySweep",
    ),
    (
        "condiciones_electricas",
        "minimum_frequency",
        "MinFrequency",
    ),
    (
        "condiciones_electricas",
        "maximum_frequency",
        "MaxFrequency",
    ),
    ("condiciones_electricas", "frequency", "frequency"),
    (
        "condiciones_electricas",
        "measurement_method",
        "MeasurementMethod",
    ),
    (
        "condiciones_electricas",
        "measurement_mode",
        "MeasurementMode",
    ),
    (
        "condiciones_electricas",
        "temperature_dependence",
        "TemperatureDependence",
    ),
    (
        "condiciones_electricas",
        "temperature_sweep",
        "TemperatureSweep",
    ),
    (
        "condiciones_electricas",
        "temperature",
        "Temperature",
    ),
    (
        "condiciones_electricas",
        "direction",
        "Direction",
    ),
    (
        "condiciones_electricas",
        "orientation",
        "Orientation",
    ),
    (
        "condiciones_electricas",
        "voltage",
        "Voltage",
    ),
    (
        "condiciones_electricas",
        "amperage",
        "Amperage",
    ),
]


# Rutas que ya demostramos manualmente.

CONFIRMED_COMPOSITE_PATHS = {
    "ElectricConductivity": (
        "PolymerNanocomposite/PROPERTIES/"
        "Electrical/ElectricConductivity"
    ),
    "SurfaceResistivity": (
        "PolymerNanocomposite/PROPERTIES/"
        "Electrical/SurfaceResistivity"
    ),
    "VolumeResistivity": (
        "PolymerNanocomposite/PROPERTIES/"
        "Electrical/VolumeResistivity"
    ),
}


def named_ancestors(element):
    """Obtiene ancestros XSD que tienen atributo name."""

    ancestors = []

    for ancestor in reversed(list(element.iterancestors())):
        name = ancestor.get("name")

        if name:
            ancestors.append(name)

    return ancestors


def find_type(root, type_name):
    """Localiza la definicion de un tipo XSD con nombre."""

    if not type_name or type_name == "anonymous":
        return None

    if ":" in type_name:
        return None

    found = root.xpath(
        (
            './/xs:complexType[@name=$name] | '
            './/xs:simpleType[@name=$name]'
        ),
        namespaces=NS,
        name=type_name,
    )

    return found[0] if found else None


def summarise_type(root, type_name):
    """Genera un resumen corto del tipo XSD."""

    node = find_type(root, type_name)

    if node is None:
        return ""

    kind = etree.QName(node).localname

    restriction = node.find(
        "xs:restriction",
        namespaces=NS,
    )

    if restriction is not None:
        base = restriction.get("base", "")

        enumerations = restriction.xpath(
            "./xs:enumeration/@value",
            namespaces=NS,
        )

        minimum = restriction.xpath(
            "string(./xs:minInclusive/@value)",
            namespaces=NS,
        )

        maximum = restriction.xpath(
            "string(./xs:maxInclusive/@value)",
            namespaces=NS,
        )

        parts = [kind, f"base={base}"]

        if enumerations:
            parts.append(
                "enum=" + "|".join(enumerations)
            )

        if minimum or maximum:
            parts.append(
                f"range={minimum or '?'}..{maximum or '?'}"
            )

        return "; ".join(parts)

    children = node.xpath(
        ".//xs:element[@name]",
        namespaces=NS,
    )

    child_names = [
        child.get("name")
        for child in children[:12]
    ]

    return (
        f"{kind}; children="
        + "|".join(child_names)
    )


def classify(element_name, context):
    """
    Clasificacion conservadora.

    include no significa que la variable este observada.
    Solo indica que existe una correspondencia estructural
    historica suficientemente clara.
    """

    context_set = set(context)
    context_text = " ".join(context)

    simulation_tokens = [
        "Abaqus",
        "FEA",
        "Simulation",
        "BoundaryCondition",
    ]

    if any(
        token in context_text
        for token in simulation_tokens
    ):
        return (
            "exclude",
            (
                "Contexto de simulacion o FEA; "
                "no representa directamente la "
                "medicion experimental objetivo"
            ),
        )

    if (
        element_name in CONFIRMED_COMPOSITE_PATHS
        and "DielectricPropertiesType" in context_set
    ):
        return (
            "include",
            (
                "Propiedad electrica confirmada dentro "
                "de DielectricPropertiesType"
            ),
        )

    if (
        element_name in {"mass", "volume"}
        and context_set.intersection(
            {"Percentage", "PercentageWithSource"}
        )
    ):
        return (
            "include",
            (
                "Rama composicional con escala historica "
                "confirmada entre 0 y 1"
            ),
        )

    composition_elements = {
        "FillerComposition",
        "FillerComponentComposition",
        "FillerComponentInComposite",
        "MatrixComponentComposition",
        "Fraction",
    }

    if element_name in composition_elements:
        return (
            "include",
            (
                "Estructura composicional explicita; "
                "el significado final depende del contexto"
            ),
        )

    material_elements = {
        "Matrix",
        "MatrixComponent",
        "PolymerType",
        "PolymerClass",
        "ChemicalName",
        "StdChemicalName",
        "TradeName",
        "Abbreviation",
        "ManufacturerOrSourceName",
        "Filler",
        "FillerComponent",
        "Particle",
        "ParticleType",
        "ParticleAspectRatio",
        "ParticleSurfaceTreatment",
        "SurfaceTreatment",
        "SurfaceChemistryProcessing",
    }

    if element_name in material_elements:
        return (
            "include",
            (
                "Elemento material explicito; debe "
                "conservarse la ruta jerarquica"
            ),
        )

    electrical_candidates = {
        "Electrical",
        "FrequencyDependence",
        "FrequencySweep",
        "MinFrequency",
        "MaxFrequency",
        "frequency",
        "MeasurementMethod",
        "MeasurementMode",
        "TemperatureDependence",
        "TemperatureSweep",
        "Temperature",
        "Direction",
        "Orientation",
        "Voltage",
        "Amperage",
    }

    if element_name in electrical_candidates:
        return (
            "ambiguous",
            (
                "Candidato relevante; el contexto debe "
                "demostrar que corresponde a la medicion "
                "electrica del nanocompuesto"
            ),
        )

    return (
        "ambiguous",
        (
            "Declaracion localizada; correspondencia "
            "cientifica pendiente de revision"
        ),
    )


def main():
    if not XSD_PATH.is_file():
        raise FileNotFoundError(
            f"No se encontro el XSD: {XSD_PATH}"
        )

    tree = etree.parse(str(XSD_PATH))
    root = tree.getroot()

    schema = etree.XMLSchema(tree)

    xsd_hash = hashlib.sha256(
        XSD_PATH.read_bytes()
    ).hexdigest()

    records = []
    missing = []

    for category, project_variable, xsd_element in TARGETS:
        matches = tree.xpath(
            './/xs:element[@name=$name]',
            namespaces=NS,
            name=xsd_element,
        )

        if not matches:
            missing.append(
                {
                    "category": category,
                    "project_variable": project_variable,
                    "xsd_element": xsd_element,
                    "status": (
                        "not_found_in_historical_xsd"
                    ),
                }
            )

            continue

        for occurrence, element in enumerate(
            matches,
            start=1,
        ):
            context = named_ancestors(element)

            xsd_type = (
                element.get("type")
                or "anonymous"
            )

            decision, reason = classify(
                xsd_element,
                context,
            )

            semantic_context = "/".join(context)

            if (
                xsd_element
                in CONFIRMED_COMPOSITE_PATHS
                and "DielectricPropertiesType" in context
            ):
                historical_path = (
                    CONFIRMED_COMPOSITE_PATHS[
                        xsd_element
                    ]
                )

            else:
                historical_path = "/".join(
                    context + [xsd_element]
                )

            records.append(
                {
                    "category": category,
                    "project_variable": project_variable,
                    "xsd_element": xsd_element,
                    "occurrence_index": occurrence,
                    "xsd_type": xsd_type,
                    "type_summary": summarise_type(
                        root,
                        xsd_type,
                    ),
                    "min_occurs": element.get(
                        "minOccurs",
                        "1",
                    ),
                    "max_occurs": element.get(
                        "maxOccurs",
                        "1",
                    ),
                    "semantic_context": semantic_context,
                    "historical_xml_path_candidate": (
                        historical_path
                    ),
                    "xsd_internal_path": tree.getpath(
                        element
                    ),
                    "decision": decision,
                    "decision_reason": reason,
                    "historical_xsd": XSD_PATH.name,
                    "historical_xsd_sha256": xsd_hash,
                    "historical_xsd_status": (
                        "confirmed_in_historical_copy"
                    ),
                    "production_xsd_status": (
                        "not_verified_endpoint_http_500"
                    ),
                    "record_observation_status": (
                        "not_verified"
                    ),
                    "coverage_status": "not_assessed",
                    "checked_at": CHECKED_AT,
                }
            )

    detail = pd.DataFrame(records)
    missing_df = pd.DataFrame(missing)

    if not detail.empty:
        detail = detail.sort_values(
            [
                "category",
                "decision",
                "project_variable",
                "semantic_context",
                "occurrence_index",
            ]
        )

    detail_path = (
        METADATA_DIR
        / "historical-xsd-curated-mapping-review.csv"
    )

    summary_path = (
        METADATA_DIR
        / "historical-xsd-curated-mapping-summary.csv"
    )

    missing_path = (
        METADATA_DIR
        / "historical-xsd-curated-missing.csv"
    )

    log_path = (
        LOG_DIR
        / "historical-xsd-curated-mapping-review.log"
    )

    detail.to_csv(
        detail_path,
        index=False,
        encoding="utf-8-sig",
    )

    missing_df.to_csv(
        missing_path,
        index=False,
        encoding="utf-8-sig",
    )

    if detail.empty:
        summary = pd.DataFrame(
            columns=[
                "category",
                "decision",
                "declarations",
            ]
        )

    else:
        summary = (
            detail.groupby(
                ["category", "decision"]
            )
            .size()
            .reset_index(
                name="declarations"
            )
        )

    summary.to_csv(
        summary_path,
        index=False,
        encoding="utf-8-sig",
    )

    lines = [
        "FASE 1B - REVISION CURADA DEL XSD HISTORICO",
        f"Fecha: {CHECKED_AT}",
        f"XSD: {XSD_PATH}",
        f"SHA256: {xsd_hash}",
        (
            "Compilacion XSD: correcta; "
            f"errores={len(schema.error_log)}"
        ),
        f"Objetivos curados: {len(TARGETS)}",
        (
            "Declaraciones encontradas: "
            f"{len(detail)}"
        ),
        (
            "Objetivos no encontrados: "
            f"{len(missing_df)}"
        ),
        "",
        "RESUMEN POR CATEGORIA Y DECISION",
        (
            summary.to_string(index=False)
            if not summary.empty
            else "Sin resultados"
        ),
        "",
        "NO ENCONTRADOS",
        (
            missing_df.to_string(index=False)
            if not missing_df.empty
            else "Ninguno"
        ),
        "",
        "ADVERTENCIAS METODOLOGICAS",
        (
            "- include significa correspondencia "
            "estructural historica, no observabilidad."
        ),
        (
            "- ambiguous exige revision contextual "
            "antes de actualizar el inventario."
        ),
        (
            "- El XSD de produccion sigue no verificado "
            "porque /api/curate/schema devolvio HTTP 500."
        ),
        (
            "- Observabilidad y cobertura permanecen "
            "no verificadas."
        ),
        "",
        f"Detalle: {detail_path}",
        f"Resumen: {summary_path}",
        f"Ausentes: {missing_path}",
    ]

    log_text = "\n".join(lines) + "\n"

    log_path.write_text(
        log_text,
        encoding="utf-8",
    )

    print(log_text)
    print(f"Log: {log_path}")


if __name__ == "__main__":
    try:
        main()

    except Exception as error:
        error_path = (
            LOG_DIR
            / "historical-xsd-curated-mapping-review-error.log"
        )

        error_path.write_text(
            f"{type(error).__name__}: {error}\n",
            encoding="utf-8",
        )

        print(
            f"ERROR: {type(error).__name__}: {error}"
        )

        print(f"Log de error: {error_path}")

        sys.exit(1)