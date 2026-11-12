from pathlib import Path
from datetime import datetime
import json
import re
import sys

import pandas as pd


ROOT = Path.cwd()

COMPONENTS_FILE = (
    ROOT
    / "data_interim"
    / "cnt"
    / "l254_castillo_2011"
    / "l254-material-components.csv"
)

COMBINED_FILE = (
    ROOT
    / "data_processed"
    / "cnt"
    / "l254_castillo_2011"
    / "l254-combined-by-sample.csv"
)

OUTPUT_DIR = (
    ROOT
    / "data_processed"
    / "cnt"
    / "l254_castillo_2011"
    / "block_comparison"
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

SIGNATURES_FILE = (
    OUTPUT_DIR
    / "l254-mwcnt-block-signatures.csv"
)

ATTRIBUTES_FILE = (
    OUTPUT_DIR
    / "l254-mwcnt-attributes-by-sample.csv"
)

MAPPING_FILE = (
    OUTPUT_DIR
    / "l254-block-material-mapping-status.csv"
)

MANIFEST_FILE = (
    METADATA_DIR
    / "l254-mwcnt-block-signatures-manifest.json"
)

LOG_FILE = (
    LOG_DIR
    / "l254-mwcnt-block-signatures.log"
)

ERROR_FILE = (
    LOG_DIR
    / "l254-mwcnt-block-signatures-error.log"
)

CHECKED_AT = datetime.now().astimezone().isoformat(
    timespec="seconds"
)

DOI = "10.1016/j.polymer.2011.06.018"

BLOCKS = [
    "block_1_s2_s8",
    "block_2_s9_s15",
    "block_3_s16_s22",
    "block_4_s23_s29",
    "block_5_s30_s36",
]


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"No se encontro: {path}"
        )

    return pd.read_csv(
        path,
        dtype=str,
        keep_default_na=False,
    )


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def numeric(value):
    try:
        return float(
            clean(value)
        )

    except ValueError:
        return None


def is_filler(row):
    role = clean(
        row.get(
            "component_role",
            ""
        )
    ).lower()

    name = clean(
        row.get(
            "standard_name",
            ""
        )
    ).lower()

    label = clean(
        row.get(
            "full_label",
            ""
        )
    ).lower()

    return (
        "filler" in role
        or "carbon nanotube" in name
        or "carbon nanotube" in label
        or "mwcnt" in name
        or "mwcnt" in label
    )


def classify_attribute(row):
    text = " ".join(
        [
            clean(
                row.get(
                    "attribute_type",
                    ""
                )
            ),
            clean(
                row.get(
                    "full_label",
                    ""
                )
            ),
        ]
    ).lower()

    if "density" in text:
        return "density"

    if (
        "diameter" in text
        or "width" in text
    ):
        return "diameter_or_width"

    if "length" in text:
        return "length"

    if (
        "aspect ratio" in text
        or "aspectratio" in text
    ):
        return "aspect_ratio"

    if (
        "manufacturer" in text
        or "supplier" in text
        or "trade name" in text
        or "tradename" in text
    ):
        return "commercial_identity"

    if (
        "surface area" in text
        or "surfacearea" in text
    ):
        return "surface_area"

    if (
        "massfraction" in text
        or "mass fraction" in text
        or "volumefraction" in text
        or "volume fraction" in text
    ):
        return "composition"

    return "other_filler_attribute"


def canonical_value(
    category,
    value,
    unit,
):
    number = numeric(value)
    unit_lower = clean(
        unit
    ).lower()

    if number is None:
        return (
            value,
            unit,
            "not_numeric",
        )

    if category == "density":
        if (
            "gram per cubic centimeter"
            in unit_lower
            or "g/cm" in unit_lower
        ):
            return (
                number * 1000.0,
                "kg/m3",
                "g_per_cm3_to_kg_per_m3",
            )

        if (
            "kilogram per cubic meter"
            in unit_lower
            or "kg/m" in unit_lower
        ):
            return (
                number,
                "kg/m3",
                "identity",
            )

    if category in {
        "diameter_or_width",
        "length",
    }:
        if (
            "nanometer"
            in unit_lower
            or unit_lower == "nm"
        ):
            return (
                number,
                "nm",
                "identity",
            )

        if (
            "micrometer"
            in unit_lower
            or unit_lower in {
                "um",
                "µm",
            }
        ):
            return (
                number * 1000.0,
                "nm",
                "um_to_nm",
            )

    return (
        number,
        unit,
        "numeric_parse_only",
    )


def join_unique(values):
    return " | ".join(
        sorted(
            {
                clean(value)
                for value in values
                if clean(value)
            }
        )
    )


def main():
    print(
        "EXTRAYENDO FIRMAS DE LOS "
        "CINCO MWCNT DE L254"
    )

    components = read_required(
        COMPONENTS_FILE
    )

    combined = read_required(
        COMBINED_FILE
    )

    sample_to_block = dict(
        zip(
            combined["sample_id"],
            combined[
                "block_id_inferred"
            ],
        )
    )

    filler = components[
        components.apply(
            is_filler,
            axis=1,
        )
    ].copy()

    filler[
        "block_id_inferred"
    ] = (
        filler["sample_id"]
        .map(sample_to_block)
        .fillna("")
    )

    filler[
        "attribute_category"
    ] = filler.apply(
        classify_attribute,
        axis=1,
    )

    canonical_values = []

    for _, row in filler.iterrows():
        canonical_values.append(
            canonical_value(
                row[
                    "attribute_category"
                ],
                row[
                    "attribute_value_original"
                ],
                row[
                    "attribute_unit_original"
                ],
            )
        )

    filler[
        "canonical_value"
    ] = [
        item[0]
        for item in canonical_values
    ]

    filler[
        "canonical_unit"
    ] = [
        item[1]
        for item in canonical_values
    ]

    filler[
        "transformation"
    ] = [
        item[2]
        for item in canonical_values
    ]

    filler.to_csv(
        ATTRIBUTES_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    records = []

    for block in BLOCKS:
        block_rows = filler[
            filler[
                "block_id_inferred"
            ]
            == block
        ]

        samples = combined[
            combined[
                "block_id_inferred"
            ]
            == block
        ]

        record = {
            "block_id": block,
            "sample_count": len(
                samples
            ),
            "samples_with_filler_metadata": (
                block_rows[
                    "sample_id"
                ].nunique()
            ),
            "standard_names": join_unique(
                block_rows[
                    "standard_name"
                ]
            ),
            "density_original_values": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == "density"
                    ][
                        "attribute_value_original"
                    ]
                )
            ),
            "density_original_units": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == "density"
                    ][
                        "attribute_unit_original"
                    ]
                )
            ),
            "density_canonical_kg_m3": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == "density"
                    ][
                        "canonical_value"
                    ]
                )
            ),
            "diameter_or_width_nm": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == (
                            "diameter_or_width"
                        )
                    ][
                        "canonical_value"
                    ]
                )
            ),
            "length_nm": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == "length"
                    ][
                        "canonical_value"
                    ]
                )
            ),
            "aspect_ratio": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == "aspect_ratio"
                    ][
                        "canonical_value"
                    ]
                )
            ),
            "surface_area": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == "surface_area"
                    ][
                        "attribute_value_original"
                    ]
                )
            ),
            "commercial_identity": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == (
                            "commercial_identity"
                        )
                    ][
                        "attribute_value_original"
                    ]
                )
            ),
            "other_filler_attributes": (
                join_unique(
                    block_rows[
                        block_rows[
                            "attribute_category"
                        ]
                        == (
                            "other_filler_attribute"
                        )
                    ][
                        "full_label"
                    ]
                )
            ),
            "study_level_interpretation": (
                "one_of_five_commercial_mwcnt_types"
            ),
            "mapping_status": (
                "commercial_name_not_verified"
            ),
        }

        records.append(
            record
        )

    signatures = pd.DataFrame(
        records
    )

    signatures.to_csv(
        SIGNATURES_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    mapping = signatures[
        [
            "block_id",
            "sample_count",
            "standard_names",
            "density_canonical_kg_m3",
            "diameter_or_width_nm",
            "length_nm",
            "aspect_ratio",
            "surface_area",
            "commercial_identity",
            "study_level_interpretation",
            "mapping_status",
        ]
    ].copy()

    mapping[
        "block_definition_status"
    ] = (
        "supported_as_distinct_commercial_mwcnt_type"
    )

    mapping[
        "block_identity_status"
    ] = mapping[
        "commercial_identity"
    ].map(
        lambda value: (
            "commercial_identity_documented"
            if clean(value)
            else "commercial_identity_not_verified"
        )
    )

    mapping[
        "recommended_action"
    ] = (
        "retain_separate_block_and_map_to_article_table"
    )

    mapping.to_csv(
        MAPPING_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    distinct_signatures = (
        signatures[
            [
                "density_canonical_kg_m3",
                "diameter_or_width_nm",
                "length_nm",
                "aspect_ratio",
                "surface_area",
                "commercial_identity",
            ]
        ]
        .astype(str)
        .drop_duplicates()
    )

    manifest = {
        "generated_at": CHECKED_AT,
        "doi": DOI,
        "study_evidence": {
            "documented_material_design": (
                "five commercially available "
                "multi-walled carbon nanotubes "
                "with different characteristics"
            ),
            "documented_loading_range": (
                "0.25 to 3.0 weight percent"
            ),
            "documented_matrix": (
                "polycarbonate"
            ),
            "documented_processing": (
                "melt mixing in twin-screw "
                "micro compounder"
            ),
        },
        "counts": {
            "blocks": len(
                signatures
            ),
            "filler_attribute_rows": len(
                filler
            ),
            "distinct_material_signatures": len(
                distinct_signatures
            ),
            "blocks_with_commercial_identity": int(
                signatures[
                    "commercial_identity"
                ]
                .astype(str)
                .str.strip()
                .ne("")
                .sum()
            ),
        },
        "interpretation": {
            "block_definition_status": (
                "supported_as_five_distinct_"
                "commercial_mwcnt_types"
            ),
            "exact_block_mapping_status": (
                "pending_article_table_mapping"
            ),
            "blocks_can_be_merged": False,
        },
        "notes": [
            (
                "Density conversions are explicit "
                "and stored with transformation."
            ),
            (
                "No commercial name is inferred "
                "from density or dimensions."
            ),
            (
                "The five blocks remain separate."
            ),
            (
                "No model was fitted."
            ),
        ],
    }

    MANIFEST_FILE.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        (
            "FASE 2 - FIRMAS DE LOS "
            "CINCO MWCNT DE L254"
        ),
        "",
        f"Fecha: {CHECKED_AT}",
        f"DOI: {DOI}",
        "",
        "EVIDENCIA DEL ARTICULO",
        (
            "- Cinco MWCNT comerciales "
            "con caracteristicas diferentes."
        ),
        (
            "- Matriz de policarbonato."
        ),
        (
            "- Cargas entre 0.25 y "
            "3.0 por ciento en masa."
        ),
        (
            "- Mezclado en fundido en "
            "microcompounder de doble tornillo."
        ),
        "",
        "RESULTADOS",
        (
            "- Bloques analizados: "
            f"{len(signatures)}"
        ),
        (
            "- Filas de atributos del relleno: "
            f"{len(filler)}"
        ),
        (
            "- Firmas materiales distintas: "
            f"{len(distinct_signatures)}"
        ),
        (
            "- Bloques con identidad comercial: "
            f"{manifest['counts']['blocks_with_commercial_identity']}"
        ),
        "",
    ]

    for _, row in signatures.iterrows():
        lines.extend(
            [
                (
                    f"{row['block_id']}"
                ),
                (
                    "  densidad kg/m3: "
                    f"{row['density_canonical_kg_m3'] or '[NO DISPONIBLE]'}"
                ),
                (
                    "  diametro/anchura nm: "
                    f"{row['diameter_or_width_nm'] or '[NO DISPONIBLE]'}"
                ),
                (
                    "  longitud nm: "
                    f"{row['length_nm'] or '[NO DISPONIBLE]'}"
                ),
                (
                    "  relacion de aspecto: "
                    f"{row['aspect_ratio'] or '[NO DISPONIBLE]'}"
                ),
                (
                    "  identidad comercial: "
                    f"{row['commercial_identity'] or '[NO VERIFICADA]'}"
                ),
                "",
            ]
        )

    lines.extend(
        [
            "DECISION",
            (
                "- Los cinco bloques quedan "
                "respaldados como cinco tipos "
                "comerciales distintos de MWCNT."
            ),
            (
                "- La correspondencia bloque-producto "
                "permanece pendiente de la tabla "
                "de materiales del articulo."
            ),
            (
                "- Los bloques no deben combinarse."
            ),
            (
                "- No se ejecutaron modelos."
            ),
            "",
            f"Firmas: {SIGNATURES_FILE}",
            f"Mapeo: {MAPPING_FILE}",
            f"Atributos: {ATTRIBUTES_FILE}",
            f"Manifiesto: {MANIFEST_FILE}",
        ]
    )

    LOG_FILE.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    print(
        "FIRMAS DE MWCNT GENERADAS"
    )
    print(
        "Bloques:",
        len(signatures),
    )
    print(
        "Firmas distintas:",
        len(distinct_signatures),
    )
    print(
        "Identidades comerciales:",
        manifest[
            "counts"
        ][
            "blocks_with_commercial_identity"
        ],
    )
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
        print(
            f"Log de error: {ERROR_FILE}"
        )
        sys.exit(1)