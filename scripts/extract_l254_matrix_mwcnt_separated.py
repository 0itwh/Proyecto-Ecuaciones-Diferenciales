from pathlib import Path
from datetime import datetime
import json
import re
import sys

import pandas as pd

ROOT = Path.cwd()
COMPONENTS_FILE = ROOT / "data_interim" / "cnt" / "l254_castillo_2011" / "l254-material-components.csv"
COMBINED_FILE = ROOT / "data_processed" / "cnt" / "l254_castillo_2011" / "l254-combined-by-sample.csv"
OUT_DIR = ROOT / "data_processed" / "cnt" / "l254_castillo_2011" / "block_comparison"
META_DIR = ROOT / "metadata"
LOG_DIR = ROOT / "logs"
for folder in (OUT_DIR, META_DIR, LOG_DIR):
    folder.mkdir(parents=True, exist_ok=True)

SAMPLE_ATTRIBUTES_OUT = OUT_DIR / "l254-matrix-mwcnt-attributes-by-sample.csv"
BLOCK_SIGNATURES_OUT = OUT_DIR / "l254-matrix-mwcnt-block-signatures.csv"
MAPPING_STATUS_OUT = OUT_DIR / "l254-block-material-mapping-corrected.csv"
QUALITY_OUT = META_DIR / "l254-matrix-mwcnt-separation-quality.csv"
MANIFEST_OUT = META_DIR / "l254-matrix-mwcnt-separation-manifest.json"
LOG_OUT = LOG_DIR / "l254-matrix-mwcnt-separation.log"
ERROR_OUT = LOG_DIR / "l254-matrix-mwcnt-separation-error.log"
NOW = datetime.now().astimezone().isoformat(timespec="seconds")

BLOCKS = [
    "block_1_s2_s8", "block_2_s9_s15", "block_3_s16_s22",
    "block_4_s23_s29", "block_5_s30_s36",
]


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def numeric(value):
    try:
        return float(clean(value))
    except ValueError:
        return None


def classify_component(row):
    """Clasifica por evidencia especifica, evitando que una etiqueta compuesta
    como 'MWCNT in polycarbonate' asigne el atributo del relleno a la matriz.
    Prioridad: rol explicito, nombre estandar, y solo despues etiqueta completa.
    """
    role = clean(row.get("component_role", "")).lower()
    name = clean(row.get("standard_name", "")).lower()
    label = clean(row.get("full_label", "")).lower()

    # 1. El rol explicito es la evidencia mas fuerte.
    if "filler" in role or "reinforcement" in role:
        return "mwcnt_filler"
    if "matrix" in role or "polymer" in role:
        return "matrix"

    # 2. El nombre estandar identifica el componente al que pertenece la fila.
    if "carbon nanotube" in name or "mwcnt" in name or "multi-wall" in name:
        return "mwcnt_filler"
    if (
        "poly(bisphenol a carbonate)" in name
        or "polycarbonate" in name
        or "makrolon" in name
    ):
        return "matrix"

    # 3. La etiqueta completa es solo respaldo. Si menciona ambos componentes,
    # no se usa para decidir porque seria ambigua.
    label_has_filler = (
        "carbon nanotube" in label
        or "mwcnt" in label
        or "multi-wall" in label
    )
    label_has_matrix = (
        "poly(bisphenol a carbonate)" in label
        or "polycarbonate" in label
        or "makrolon" in label
    )
    if label_has_filler and not label_has_matrix:
        return "mwcnt_filler"
    if label_has_matrix and not label_has_filler:
        return "matrix"

    return "unclassified_component"


def classify_attribute(row):
    text = " ".join([
        clean(row.get("attribute_type", "")), clean(row.get("full_label", ""))
    ]).lower()
    if "density" in text:
        return "density"
    if "aspect ratio" in text or "aspectratio" in text:
        return "aspect_ratio"
    if "diameter" in text or "width" in text:
        return "diameter_or_width"
    if "length" in text:
        return "length"
    if "surface area" in text or "surfacearea" in text:
        return "surface_area"
    if "manufacturer" in text or "supplier" in text:
        return "manufacturer"
    if "trade name" in text or "tradename" in text or "commercial" in text:
        return "commercial_name"
    if re.search(r"mass.?fraction|weight.?fraction|volume.?fraction|loading|concentration", text, re.I):
        return "composition"
    return "other"


def canonical_density(value, unit):
    number = numeric(value)
    lower = clean(unit).lower()
    if number is None:
        return "", "", "not_numeric"
    if "gram per cubic centimeter" in lower or "g/cm" in lower:
        return number * 1000.0, "kg/m3", "g_per_cm3_to_kg_per_m3"
    if "kilogram per cubic meter" in lower or "kg/m" in lower:
        return number, "kg/m3", "identity"
    return number, clean(unit), "numeric_parse_only"


def canonical_length_nm(value, unit):
    number = numeric(value)
    lower = clean(unit).lower()
    if number is None:
        return "", "", "not_numeric"
    if "nanometer" in lower or lower == "nm":
        return number, "nm", "identity"
    if "micrometer" in lower or lower in {"um", "µm"}:
        return number * 1000.0, "nm", "um_to_nm"
    return number, clean(unit), "numeric_parse_only"


def join_unique(values):
    return " | ".join(sorted({clean(value) for value in values if clean(value)}))


def values_for(frame, component_class, category, column):
    rows = frame[(frame["component_class"] == component_class) & (frame["attribute_category"] == category)]
    return join_unique(rows[column])


def main():
    print("SEPARANDO MATRIZ Y MWCNT EN L254")
    components = read_required(COMPONENTS_FILE)
    combined = read_required(COMBINED_FILE)
    sample_to_block = dict(zip(combined["sample_id"], combined["block_id_inferred"]))

    components["component_class"] = components.apply(classify_component, axis=1)
    components["attribute_category"] = components.apply(classify_attribute, axis=1)
    components["block_id_inferred"] = components["sample_id"].map(sample_to_block).fillna("")

    canonical_values, canonical_units, transformations = [], [], []
    for _, row in components.iterrows():
        category = row["attribute_category"]
        if category == "density":
            value, unit, transformation = canonical_density(
                row.get("attribute_value_original", ""), row.get("attribute_unit_original", "")
            )
        elif category in {"diameter_or_width", "length"}:
            value, unit, transformation = canonical_length_nm(
                row.get("attribute_value_original", ""), row.get("attribute_unit_original", "")
            )
        else:
            parsed = numeric(row.get("attribute_value_original", ""))
            value = parsed if parsed is not None else clean(row.get("attribute_value_original", ""))
            unit = clean(row.get("attribute_unit_original", ""))
            transformation = "numeric_parse_only" if parsed is not None else "text_preserved"
        canonical_values.append(value)
        canonical_units.append(unit)
        transformations.append(transformation)

    components["canonical_value"] = canonical_values
    components["canonical_unit"] = canonical_units
    components["transformation"] = transformations
    components.to_csv(SAMPLE_ATTRIBUTES_OUT, index=False, encoding="utf-8-sig")

    signatures = []
    for block in BLOCKS:
        block_rows = components[components["block_id_inferred"] == block]
        matrix = block_rows[block_rows["component_class"] == "matrix"]
        filler = block_rows[block_rows["component_class"] == "mwcnt_filler"]
        signatures.append({
            "block_id": block,
            "sample_count": int((combined["block_id_inferred"] == block).sum()),
            "samples_with_matrix_metadata": matrix["sample_id"].nunique(),
            "samples_with_mwcnt_metadata": filler["sample_id"].nunique(),
            "matrix_name": join_unique(matrix["standard_name"]),
            "matrix_density_original": values_for(matrix, "matrix", "density", "attribute_value_original"),
            "matrix_density_unit_original": values_for(matrix, "matrix", "density", "attribute_unit_original"),
            "matrix_density_kg_m3": values_for(matrix, "matrix", "density", "canonical_value"),
            "matrix_product": values_for(matrix, "matrix", "commercial_name", "attribute_value_original"),
            "matrix_manufacturer": values_for(matrix, "matrix", "manufacturer", "attribute_value_original"),
            "mwcnt_name": join_unique(filler["standard_name"]),
            "mwcnt_density_original": values_for(filler, "mwcnt_filler", "density", "attribute_value_original"),
            "mwcnt_density_unit_original": values_for(filler, "mwcnt_filler", "density", "attribute_unit_original"),
            "mwcnt_density_canonical_kg_m3": values_for(filler, "mwcnt_filler", "density", "canonical_value"),
            "mwcnt_density_semantic_status": "documented_value_density_kind_not_verified",
            "mwcnt_aspect_ratio": values_for(filler, "mwcnt_filler", "aspect_ratio", "canonical_value"),
            "mwcnt_diameter_or_width_nm": values_for(filler, "mwcnt_filler", "diameter_or_width", "canonical_value"),
            "mwcnt_length_nm": values_for(filler, "mwcnt_filler", "length", "canonical_value"),
            "mwcnt_surface_area": values_for(filler, "mwcnt_filler", "surface_area", "attribute_value_original"),
            "mwcnt_commercial_name": values_for(filler, "mwcnt_filler", "commercial_name", "attribute_value_original"),
            "mwcnt_manufacturer": values_for(filler, "mwcnt_filler", "manufacturer", "attribute_value_original"),
            "mwcnt_identity_status": "documented" if (
                values_for(filler, "mwcnt_filler", "commercial_name", "attribute_value_original")
                or values_for(filler, "mwcnt_filler", "manufacturer", "attribute_value_original")
            ) else "not_verified",
            "block_definition_status": "confirmed_as_distinct_mwcnt_variant_by_aspect_ratio_and_study_design",
        })

    signatures_frame = pd.DataFrame(signatures)
    signatures_frame.to_csv(BLOCK_SIGNATURES_OUT, index=False, encoding="utf-8-sig")

    mapping = signatures_frame[[
        "block_id", "matrix_name", "matrix_product", "matrix_manufacturer",
        "mwcnt_name", "mwcnt_density_original", "mwcnt_density_unit_original",
        "mwcnt_density_canonical_kg_m3", "mwcnt_density_semantic_status",
        "mwcnt_aspect_ratio", "mwcnt_commercial_name", "mwcnt_manufacturer",
        "mwcnt_identity_status", "block_definition_status",
    ]].copy()
    mapping["recommended_action"] = "retain_separate_curve_and_seek_article_material_table_mapping"
    mapping.to_csv(MAPPING_STATUS_OUT, index=False, encoding="utf-8-sig")

    matrix_products = {clean(v) for v in signatures_frame["matrix_product"] if clean(v)}
    matrix_manufacturers = {clean(v) for v in signatures_frame["matrix_manufacturer"] if clean(v)}
    mwcnt_names = {clean(v) for v in signatures_frame["mwcnt_commercial_name"] if clean(v)}
    mwcnt_manufacturers = {clean(v) for v in signatures_frame["mwcnt_manufacturer"] if clean(v)}
    aspect_ratios = [clean(v) for v in signatures_frame["mwcnt_aspect_ratio"]]
    aspect_rows = components[components["attribute_category"] == "aspect_ratio"]
    aspect_rows_filler = aspect_rows[aspect_rows["component_class"] == "mwcnt_filler"]

    checks = [
        ("Q001", "Five blocks generated", len(signatures_frame) == 5, len(signatures_frame), 5),
        ("Q002", "Matrix product is common across blocks", len(matrix_products) == 1 and "Makrolon 2600" in matrix_products, sorted(matrix_products), "Makrolon 2600"),
        ("Q003", "Matrix manufacturer is common across blocks", len(matrix_manufacturers) == 1 and any("Bayer MaterialScience" in item for item in matrix_manufacturers), sorted(matrix_manufacturers), "Bayer MaterialScience"),
        ("Q004", "Matrix product is not assigned to MWCNT", "Makrolon 2600" not in mwcnt_names, sorted(mwcnt_names), "Makrolon absent"),
        ("Q005", "Matrix manufacturer is not assigned to MWCNT", not any("Bayer MaterialScience" in item for item in mwcnt_manufacturers), sorted(mwcnt_manufacturers), "Bayer absent"),
        ("Q006", "Five distinct non-empty aspect ratios", len(set(aspect_ratios)) == 5 and all(aspect_ratios), aspect_ratios, "5 distinct values"),
        ("Q007", "Aspect-ratio rows belong to MWCNT filler", len(aspect_rows) > 0 and len(aspect_rows) == len(aspect_rows_filler), f"all={len(aspect_rows)}, filler={len(aspect_rows_filler)}", "all aspect-ratio rows classified as mwcnt_filler"),
    ]
    quality = pd.DataFrame(checks, columns=["check_id", "description", "passed", "observed", "expected"])
    quality.to_csv(QUALITY_OUT, index=False, encoding="utf-8-sig")

    manifest = {
        "generated_at": NOW,
        "input_files": [str(COMPONENTS_FILE), str(COMBINED_FILE)],
        "outputs": [str(SAMPLE_ATTRIBUTES_OUT), str(BLOCK_SIGNATURES_OUT), str(MAPPING_STATUS_OUT), str(QUALITY_OUT)],
        "counts": {
            "blocks": len(signatures_frame),
            "component_rows": len(components),
            "matrix_rows": int((components["component_class"] == "matrix").sum()),
            "mwcnt_filler_rows": int((components["component_class"] == "mwcnt_filler").sum()),
            "unclassified_component_rows": int((components["component_class"] == "unclassified_component").sum()),
            "blocks_with_verified_mwcnt_identity": int((signatures_frame["mwcnt_identity_status"] == "documented").sum()),
        },
        "scientific_status": {
            "matrix_identity": "documented_as_bayer_makrolon_2600",
            "mwcnt_commercial_identity": "not_verified" if not mwcnt_names and not mwcnt_manufacturers else "partially_documented",
            "block_definition": "confirmed_as_five_distinct_mwcnt_variants",
            "mapping_basis": "aspect_ratio_and_density_metadata",
            "recommended_action": "retain_five_separate_curves",
        },
        "methodological_notes": [
            "Matrix and filler rows are classified separately before aggregating attributes.",
            "Makrolon 2600 and Bayer MaterialScience are accepted only from matrix-classified rows.",
            "MWCNT commercial identity is not inferred from density or aspect ratio.",
            "Density unit conversion is explicit, but density semantic kind (bulk/apparent/solid) remains unverified.",
            "No model was fitted.",
        ],
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - SEPARACION CORREGIDA V2 DE MATRIZ Y MWCNT L254",
        "",
        f"Fecha: {NOW}",
        "",
        "ESTADO",
        "- Matriz: Poly(bisphenol A carbonate), producto Makrolon 2600, Bayer MaterialScience.",
        "- Relleno: Multi-wall carbon nanotubes.",
        "- Makrolon 2600 y Bayer no se asignan al MWCNT.",
        "- La identidad comercial de cada MWCNT permanece no verificada salvo evidencia explicita en filas de relleno.",
        "",
        "FIRMAS POR BLOQUE",
    ]
    for _, row in signatures_frame.iterrows():
        lines.extend([
            f"{row['block_id']}",
            f"  matriz: {row['matrix_name'] or '[NO DISPONIBLE]'}",
            f"  producto matriz: {row['matrix_product'] or '[NO DISPONIBLE]'}",
            f"  fabricante matriz: {row['matrix_manufacturer'] or '[NO DISPONIBLE]'}",
            f"  MWCNT: {row['mwcnt_name'] or '[NO DISPONIBLE]'}",
            f"  densidad MWCNT original: {row['mwcnt_density_original'] or '[NO DISPONIBLE]'} {row['mwcnt_density_unit_original']}",
            f"  densidad MWCNT canonica: {row['mwcnt_density_canonical_kg_m3'] or '[NO DISPONIBLE]'} kg/m3",
            f"  estado semantico densidad: {row['mwcnt_density_semantic_status']}",
            f"  relacion de aspecto: {row['mwcnt_aspect_ratio'] or '[NO DISPONIBLE]'}",
            f"  nombre comercial MWCNT: {row['mwcnt_commercial_name'] or '[NO VERIFICADO]'}",
            f"  fabricante MWCNT: {row['mwcnt_manufacturer'] or '[NO VERIFICADO]'}",
            "",
        ])
    lines.extend([
        "DECISION",
        "- Los cinco bloques se conservan como cinco curvas separadas.",
        "- La matriz queda identificada como Makrolon 2600 de Bayer MaterialScience.",
        "- Los nombres comerciales de MWCNT no se completan sin evidencia explicita.",
        "- No se homogenizan densidades hasta verificar si representan densidad aparente, bulk o solida.",
        "- No se ejecutaron modelos.",
        "",
        f"Firmas corregidas: {BLOCK_SIGNATURES_OUT}",
        f"Mapeo corregido: {MAPPING_STATUS_OUT}",
        f"Atributos separados: {SAMPLE_ATTRIBUTES_OUT}",
        f"Calidad: {QUALITY_OUT}",
        f"Manifiesto: {MANIFEST_OUT}",
    ])
    LOG_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("SEPARACION COMPLETADA")
    for key, val in manifest["counts"].items():
        print(f"{key}: {val}")
    print(f"Log: {LOG_OUT}")

    if not quality["passed"].astype(bool).all():
        raise ValueError("Uno o mas controles de separacion fallaron")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_OUT.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_OUT}")
        sys.exit(1)
