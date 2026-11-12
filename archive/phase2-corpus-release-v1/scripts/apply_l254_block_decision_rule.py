from pathlib import Path
from datetime import datetime
import json
import re
import sys

import pandas as pd

ROOT = Path.cwd()
BLOCK_DIR = ROOT / "data_processed" / "cnt" / "l254_castillo_2011" / "block_comparison"
META = ROOT / "metadata"
LOGS = ROOT / "logs"

FEATURES_IN = BLOCK_DIR / "l254-normalized-distinguishing-features.csv"
MISSING_PROCESSING_IN = BLOCK_DIR / "l254-samples-missing-processing.csv"
DECISIONS_OUT = BLOCK_DIR / "l254-block-definition-decisions.csv"
BLOCK_STATUS_OUT = BLOCK_DIR / "l254-block-definition-status.csv"
MANIFEST_OUT = META / "l254-block-decision-rule-manifest.json"
LOG_OUT = LOGS / "l254-block-decision-rule.log"
ERROR_OUT = LOGS / "l254-block-decision-rule-error.log"
NOW = datetime.now().astimezone().isoformat(timespec="seconds")

META.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

BLOCKS = [
    "block_1_s2_s8", "block_2_s9_s15", "block_3_s16_s22",
    "block_4_s23_s29", "block_5_s30_s36"
]
MIN_PRESENT = 6
MIN_ABSENT_OTHER_BLOCKS = 4


def read_required(path):
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def parse_counts(text):
    counts = {block: 0 for block in BLOCKS}
    for item in str(text).split("|"):
        if "=" not in item:
            continue
        block, raw = item.rsplit("=", 1)
        if block in counts:
            counts[block] = int(raw)
    return counts


def scientific_assessment(source_type, feature, counts):
    low = feature.lower()
    nonzero = [block for block, count in counts.items() if count > 0]

    if source_type == "processing" and len(nonzero) == 5:
        return (
            "interpretable_common_processing",
            "Common process across all blocks; the lower count in block 5 is explained by missing metadata for s33, not a block-specific condition."
        )

    if "gram per cubic centimeter" in low or "kilogram per cubic meter" in low:
        return (
            "interpretable_unit_representation_only",
            "The feature distinguishes density unit representation (g/cm3 versus kg/m3), not yet a confirmed material or processing difference."
        )

    if "<uri>" in low or "<sample" in low:
        return (
            "contains_normalized_identifier_placeholder",
            "The normalized feature still contains a generic identifier placeholder and cannot define a scientific block by itself."
        )

    return (
        "scientifically_interpretable_candidate",
        "Scientific meaning is readable, but block specificity must still satisfy the numerical rule."
    )


def main():
    print("APLICANDO REGLA DE DECISION A BLOQUES L254")
    features = read_required(FEATURES_IN)
    missing = read_required(MISSING_PROCESSING_IN)

    missing_samples = set(missing["sample_id"]) if "sample_id" in missing.columns else set()
    decisions = []

    for feature_index, row in features.iterrows():
        source_type = row["source_type"]
        feature = row["normalized_feature"]
        counts = parse_counts(row["block_sample_counts"])
        assessment, scientific_note = scientific_assessment(source_type, feature, counts)

        not_composition = not bool(re.search(
            r"mass.?fraction|volume.?fraction|weight.?fraction|loading|concentration|composition",
            feature, re.I
        ))
        not_identifier_derived = not bool(re.search(
            r"l254[-_]s\d+|https?://|<sample_id>|<sample_uri>", feature, re.I
        ))

        for target_block in BLOCKS:
            present_count = counts[target_block]
            other_blocks = [block for block in BLOCKS if block != target_block]
            absent_other_blocks = sum(counts[block] == 0 for block in other_blocks)
            present_rule = present_count >= MIN_PRESENT
            absent_rule = absent_other_blocks >= MIN_ABSENT_OTHER_BLOCKS
            interpretable_rule = assessment == "scientifically_interpretable_candidate"

            passes = all([
                present_rule, absent_rule, interpretable_rule,
                not_composition, not_identifier_derived
            ])

            reasons = []
            if not present_rule:
                reasons.append(f"present_in_{present_count}_of_7")
            if not absent_rule:
                reasons.append(f"absent_in_{absent_other_blocks}_of_4_other_blocks")
            if not interpretable_rule:
                reasons.append(assessment)
            if not not_composition:
                reasons.append("composition_derived")
            if not not_identifier_derived:
                reasons.append("identifier_derived")

            decisions.append({
                "feature_id": f"feature-{feature_index + 1:02d}",
                "target_block": target_block,
                "source_type": source_type,
                "normalized_feature": feature,
                "present_count_in_target_block": present_count,
                "absent_count_in_other_blocks": absent_other_blocks,
                "rule_present_6_of_7": present_rule,
                "rule_absent_4_other_blocks": absent_rule,
                "rule_scientifically_interpretable": interpretable_rule,
                "rule_not_composition_derived": not_composition,
                "rule_not_identifier_derived": not_identifier_derived,
                "passes_block_definition_rule": passes,
                "decision_reasons": "|".join(reasons) if reasons else "all_rules_passed",
                "scientific_assessment": assessment,
                "scientific_note": scientific_note,
            })

    decision_frame = pd.DataFrame(decisions)
    decision_frame.to_csv(DECISIONS_OUT, index=False, encoding="utf-8-sig")

    block_rows = []
    for block in BLOCKS:
        subset = decision_frame[
            (decision_frame["target_block"] == block)
            & (decision_frame["passes_block_definition_rule"] == True)
        ]
        coherent_count = len(subset)
        block_rows.append({
            "block_id": block,
            "qualifying_feature_count": coherent_count,
            "requires_two_coherent_features": True,
            "block_definition_confirmed": coherent_count >= 2,
            "block_definition_status": (
                "supported_by_two_or_more_coherent_features"
                if coherent_count >= 2
                else "not_supported_by_strict_rule"
            ),
            "qualifying_feature_ids": "|".join(subset["feature_id"].tolist()),
            "recommended_label": block,
            "recommended_action": "retain_numeric_block_id_and_do_not_merge_blocks",
        })
    block_status = pd.DataFrame(block_rows)
    block_status.to_csv(BLOCK_STATUS_OUT, index=False, encoding="utf-8-sig")

    passing = decision_frame[decision_frame["passes_block_definition_rule"] == True]
    manifest = {
        "generated_at": NOW,
        "decision_rule": {
            "present_in_target_block": ">=6 of 7 samples",
            "absent_in_other_blocks": "all 4 other blocks",
            "scientifically_interpretable": True,
            "not_composition_derived": True,
            "not_identifier_derived": True,
            "block_confirmation": ">=2 coherent qualifying features",
        },
        "counts": {
            "normalized_features_reviewed": len(features),
            "feature_block_evaluations": len(decision_frame),
            "qualifying_feature_block_pairs": len(passing),
            "blocks_confirmed": int(block_status["block_definition_confirmed"].sum()),
            "blocks_not_confirmed": int((~block_status["block_definition_confirmed"]).sum()),
        },
        "missing_processing_samples": sorted(missing_samples),
        "scientific_conclusion": (
            "No normalized feature satisfies the strict block-definition rule. "
            "The two component features separate density unit representation, while the three processing features are common to all blocks and are missing only for s33 in block 5."
        ),
        "outputs": [str(DECISIONS_OUT), str(BLOCK_STATUS_OUT)],
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - REGLA DE DECISION PARA BLOQUES L254",
        "",
        f"Fecha: {NOW}",
        "",
        "REGLA",
        "- Presente en al menos 6 de 7 muestras del bloque.",
        "- Ausente en los 4 bloques restantes.",
        "- Significado cientifico interpretable.",
        "- No derivado de composicion.",
        "- No derivado de identificadores.",
        "- Se requieren al menos 2 rasgos coherentes para confirmar un bloque.",
        "",
        "RESULTADOS",
    ]
    for key, value in manifest["counts"].items():
        lines.append(f"- {key}: {value}")

    lines.extend([
        "",
        "EVALUACION DE LOS CINCO RASGOS",
        "- Los dos rasgos de componente separan unidades de densidad: g/cm3 en bloques 3 y 5; kg/m3 en bloques 1, 2 y 4.",
        "- Ninguno esta ausente en los cuatro bloques restantes, porque cada rasgo aparece en dos o tres bloques.",
        "- La unidad por si sola no demuestra una variante material; puede ser una diferencia de representacion del metadato.",
        "- Los tres rasgos de procesamiento aparecen en los cinco bloques.",
        "- En el bloque 5 aparecen en 6 de 7 muestras debido a la ausencia de metadatos de s33.",
        "- El patron de s33 no se interpreta como condicion experimental distintiva.",
        "",
        "DECISION",
        "- Cero rasgos cumplen la regla estricta para definir un bloque.",
        "- Cero bloques quedan confirmados por dos rasgos coherentes.",
        "- Se conservan los nombres numericos block_1 a block_5.",
        "- Los cinco bloques no deben combinarse en una sola curva.",
        "- La variable experimental que distingue los bloques permanece no verificada.",
        "- s33 se conserva con processing_metadata_status=missing_in_extracted_bindings.",
        "",
        f"Decisiones por rasgo y bloque: {DECISIONS_OUT}",
        f"Estado por bloque: {BLOCK_STATUS_OUT}",
        f"Manifiesto: {MANIFEST_OUT}",
    ])
    LOG_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("REGLA APLICADA")
    for key, value in manifest["counts"].items():
        print(f"{key}: {value}")
    print(f"Log: {LOG_OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_OUT.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_OUT}")
        sys.exit(1)
