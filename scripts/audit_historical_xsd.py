from pathlib import Path
from datetime import datetime
import csv
import re
import sys

import pandas as pd
from lxml import etree


PROJECT_ROOT = Path.cwd()
XSD_PATH = (
    PROJECT_ROOT
    / "schemas"
    / "nanomine-schema-master"
    / "xml"
    / "PNC_schema_062722.xsd"
)
OUTPUT_DIR = PROJECT_ROOT / "metadata"
LOG_DIR = PROJECT_ROOT / "logs"

OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

NS = {"xs": "http://www.w3.org/2001/XMLSchema"}

TERMS = {
    "materiales": [
        "Matrix",
        "MatrixComponent",
        "Filler",
        "FillerComponent",
        "ChemicalName",
        "TradeName",
        "Abbreviation",
        "Manufacturer",
        "Grade",
        "SurfaceTreatment",
        "SurfaceModification",
        "Functionalization",
        "Compatibilizer",
    ],
    "condiciones_electricas": [
        "ElectricConductivity",
        "SurfaceResistivity",
        "VolumeResistivity",
        "FrequencyDependence",
        "FrequencySweep",
        "MinFrequency",
        "MaxFrequency",
        "frequency",
        "Temperature",
        "MeasurementMethod",
        "Instrument",
        "Direction",
        "Orientation",
        "Voltage",
        "Amperage",
    ],
    "composicion": [
        "FillerComposition",
        "FillerComponentComposition",
        "FillerComponentInComposite",
        "Fraction",
        "mass",
        "volume",
    ],
}

KEYWORDS = {
    "materiales": [
        "matrix",
        "polymer",
        "filler",
        "particle",
        "chemical",
        "trade",
        "manufacturer",
        "grade",
        "surface",
        "functional",
        "compatibil",
    ],
    "condiciones_electricas": [
        "electric",
        "resist",
        "conduct",
        "frequency",
        "temperature",
        "direction",
        "orientation",
        "voltage",
        "amperage",
        "instrument",
        "measurement",
    ],
    "composicion": [
        "composition",
        "fraction",
        "percentage",
        "mass",
        "volume",
        "loading",
        "concentration",
        "phr",
    ],
}


def semantic_ancestors(element):
    names = []
    for ancestor in element.iterancestors():
        name = ancestor.get("name")
        if name:
            names.append(name)
    return list(reversed(names))


def declaration_record(tree, element, category, query_term, match_type):
    ancestors = semantic_ancestors(element)
    return {
        "category": category,
        "query_term": query_term,
        "match_type": match_type,
        "element_name": element.get("name") or "",
        "element_type": element.get("type") or "anonymous",
        "min_occurs": element.get("minOccurs", "1"),
        "max_occurs": element.get("maxOccurs", "1"),
        "semantic_context": "/".join(ancestors),
        "xsd_internal_path": tree.getpath(element),
        "historical_xsd": XSD_PATH.name,
        "production_status": "not verified",
        "record_observation_status": "not verified",
    }


def main():
    messages = []

    if not XSD_PATH.is_file():
        raise FileNotFoundError(f"No existe el XSD: {XSD_PATH}")

    tree = etree.parse(str(XSD_PATH))
    schema = etree.XMLSchema(tree)
    root = tree.getroot()

    messages.append("XSD compilado correctamente")
    messages.append(f"Errores de compilación: {len(schema.error_log)}")

    all_elements = root.xpath(".//xs:element[@name]", namespaces=NS)
    unique_names = sorted(
        {e.get("name") for e in all_elements if e.get("name")}
    )

    records = []
    seen = set()

    # Coincidencias exactas
    for category, terms in TERMS.items():
        for term in terms:
            matches = tree.xpath(
                './/xs:element[@name=$name]',
                namespaces=NS,
                name=term,
            )
            for element in matches:
                key = (category, term, tree.getpath(element), "exact")
                if key not in seen:
                    records.append(
                        declaration_record(
                            tree, element, category, term, "exact"
                        )
                    )
                    seen.add(key)

    # Coincidencias por palabra clave
    for category, keywords in KEYWORDS.items():
        for name in unique_names:
            lower_name = name.lower()
            matched_keywords = [
                keyword
                for keyword in keywords
                if keyword in lower_name
            ]
            if not matched_keywords:
                continue

            matches = tree.xpath(
                './/xs:element[@name=$name]',
                namespaces=NS,
                name=name,
            )
            for element in matches:
                key = (
                    category,
                    name,
                    tree.getpath(element),
                    "keyword",
                )
                if key not in seen:
                    records.append(
                        declaration_record(
                            tree,
                            element,
                            category,
                            ",".join(matched_keywords),
                            "keyword",
                        )
                    )
                    seen.add(key)

    df = pd.DataFrame(records)

    if df.empty:
        messages.append("ADVERTENCIA: no se encontraron candidatos")
    else:
        df = df.sort_values(
            ["category", "element_name", "xsd_internal_path"]
        )
        output_csv = OUTPUT_DIR / "historical-xsd-priority-audit.csv"
        df.to_csv(output_csv, index=False, encoding="utf-8-sig")

        summary = (
            df.groupby(["category", "match_type"])
            .size()
            .reset_index(name="declarations")
        )
        summary_csv = OUTPUT_DIR / "historical-xsd-priority-summary.csv"
        summary.to_csv(summary_csv, index=False, encoding="utf-8-sig")

        messages.append(f"Declaraciones candidatas: {len(df)}")
        messages.append(
            f"Nombres únicos candidatos: {df['element_name'].nunique()}"
        )
        messages.append(f"Inventario: {output_csv}")
        messages.append(f"Resumen: {summary_csv}")

        messages.append("")
        messages.append("RESUMEN POR CATEGORÍA")
        messages.append(summary.to_string(index=False))

        messages.append("")
        messages.append("NOMBRES CANDIDATOS")
        for category in sorted(df["category"].unique()):
            names = sorted(
                df.loc[
                    df["category"] == category,
                    "element_name",
                ].unique()
            )
            messages.append(f"{category}: {', '.join(names)}")

    root_elements = root.xpath("./xs:element", namespaces=NS)
    messages.append("")
    messages.append(
        "Elementos globales: "
        + ", ".join(
            e.get("name", "")
            for e in root_elements
        )
    )

    log_path = LOG_DIR / "historical-xsd-priority-audit.log"
    log_text = "\n".join(messages) + "\n"
    log_path.write_text(log_text, encoding="utf-8")

    print(log_text)
    print(f"Log: {log_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        error_path = LOG_DIR / "historical-xsd-priority-audit-error.log"
        error_path.write_text(
            f"{type(exc).__name__}: {exc}\n",
            encoding="utf-8",
        )
        print(f"ERROR: {type(exc).__name__}: {exc}")
        print(f"Log de error: {error_path}")
        sys.exit(1)