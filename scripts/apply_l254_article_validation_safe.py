from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile

import pandas as pd

RELEASE = "l254-article-validation-v1"
DOI = "10.1016/j.polymer.2011.06.018"
PDF_DEFAULT = "49-doi10.1016j.polymer.2011.06.018_Castillo.pdf"
BOUNDARY_SIGMA = 1e-7

BLOCK_MAP = {
    "block_1_s2_s8": dict(variant="l254-mwcnt-v1-ar134", commercial_name="Nanocyl NC7000", manufacturer="Nanocyl S.A., Sambreville, Belgium", aspect_ratio=134, diameter_x50_nm=10.0, length_x50_nm=1341, B=6.2e-2, pc=0.28, t=1.3),
    "block_2_s9_s15": dict(variant="l254-mwcnt-v2-ar94", commercial_name="SWeNT SMW-100", manufacturer="SouthWest NanoTechnologies, Inc., Norman, U.S.A.", aspect_ratio=94, diameter_x50_nm=7.8, length_x50_nm=735, B=8.2e-3, pc=0.33, t=2.0),
    "block_3_s16_s22": dict(variant="l254-mwcnt-v3-ar55", commercial_name="Hyperion Masterbatch (15 wt.%)", manufacturer="Hyperion Catalysis International, Inc., Cambridge, U.S.A.", aspect_ratio=55, diameter_x50_nm=6.0, length_x50_nm=332, B=1.4e-2, pc=0.50, t=1.7),
    "block_4_s23_s29": dict(variant="l254-mwcnt-v4-ar73", commercial_name="Baytubes C150P", manufacturer="Bayer MaterialScience AG, Leverkusen, Germany", aspect_ratio=73, diameter_x50_nm=10.5, length_x50_nm=770, B=8.5e-3, pc=0.61, t=2.0),
    "block_5_s30_s36": dict(variant="l254-mwcnt-v5-ar69", commercial_name="Continental Carbon MWNT", manufacturer="Continental Carbon Company, Phoenix, U.S.A.", aspect_ratio=69, diameter_x50_nm=10.5, length_x50_nm=727, B=9.0e-3, pc=0.49, t=1.8),
}

REQUIRED = {
    "samples.csv": {"sample_id", "block_id_inferred", "sample_role", "block_definition_status"},
    "sample_composition.csv": {"composition_id", "sample_id", "basis", "canonical_value"},
    "electrical_measurements.csv": {"measurement_id", "sample_id", "value_numeric", "canonical_unit", "frequency_status", "measurement_status"},
    "measurement_conditions.csv": {"condition_id", "measurement_id", "sample_id", "condition_name", "condition_status"},
    "filler_variants.csv": {"filler_variant_id", "block_id", "aspect_ratio", "commercial_name", "manufacturer", "commercial_identity_status"},
    "curve_inclusion_status.csv": {"curve_id", "block_id", "filler_variant_id", "complete_pair_count", "curve_status", "usable_for_final_modeling"},
    "exclusions.csv": {"exclusion_id", "entity_type", "entity_id", "sample_id", "reason", "status"},
}


def parse_args():
    parser = argparse.ArgumentParser(description="Valida el articulo l254 sin sobrescribir el corpus canonico.")
    parser.add_argument("--root", default=".", help="Raiz del proyecto")
    parser.add_argument("--source-corpus", default="data_processed/l254_corpus")
    parser.add_argument("--output-corpus", default="data_processed/l254_corpus_article_validated")
    parser.add_argument("--pdf", default=PDF_DEFAULT)
    parser.add_argument("--apply", action="store_true", help="Crea el corpus candidato. Sin esta opcion solo audita.")
    parser.add_argument("--replace-output", action="store_true", help="Permite reemplazar solo el directorio candidato, nunca el canonico.")
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_table(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"No se encontro: {path}")
    frame = pd.read_csv(path, keep_default_na=False)
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Columnas faltantes en {path.name}: {missing}")
    return frame


def assert_unique(frame: pd.DataFrame, column: str, table: str):
    if frame[column].astype(str).eq("").any() or frame[column].duplicated().any():
        raise ValueError(f"Clave no unica o vacia: {table}.{column}")


def classify_method(sigma: float) -> dict[str, str]:
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError(f"Conductividad no positiva o no finita: {sigma}")
    if math.isclose(sigma, BOUNDARY_SIGMA, rel_tol=0.0, abs_tol=1e-15):
        return dict(method_group="method_boundary_unresolved", instrument="", fixture="", specimen_geometry="", electrode_geometry="", method_range="sigma = 1e-7 S/cm; article uses strict resistivity inequalities")
    if sigma < BOUNDARY_SIGMA:
        return dict(method_group="high_resistivity_fixture", instrument="Keithley Electrometer 6517A", fixture="Keithley 8009 Resistivity Test Fixture", specimen_geometry="compression molded disc; 60 mm diameter; 0.5 mm thickness", electrode_geometry="fixture geometry not further specified in article", method_range="rho > 1e7 ohm cm; equivalent sigma < 1e-7 S/cm")
    return dict(method_group="four_point_low_resistivity", instrument="Keithley Multimeter DMM 2000", fixture="4-point fixture with gold contact wires", specimen_geometry="strip; 30 x 3 x 0.5 mm", electrode_geometry="source electrodes 16 mm apart; measuring electrodes 10 mm apart", method_range="rho < 1e7 ohm cm; equivalent sigma > 1e-7 S/cm")


def validate_inputs(tables: dict[str, pd.DataFrame]):
    assert_unique(tables["samples.csv"], "sample_id", "samples")
    assert_unique(tables["electrical_measurements.csv"], "measurement_id", "electrical_measurements")
    assert_unique(tables["filler_variants.csv"], "filler_variant_id", "filler_variants")
    assert_unique(tables["curve_inclusion_status.csv"], "curve_id", "curve_inclusion_status")
    if len(tables["samples.csv"]) != 36:
        raise ValueError("Se esperaban 36 muestras")
    if len(tables["electrical_measurements.csv"]) != 29:
        raise ValueError("Se esperaban 29 mediciones electricas")
    if len(tables["filler_variants.csv"]) != 5:
        raise ValueError("Se esperaban cinco variantes")
    blocks = set(tables["filler_variants.csv"]["block_id"])
    if blocks != set(BLOCK_MAP):
        raise ValueError(f"Bloques inesperados: {sorted(blocks)}")
    sample_ids = set(tables["samples.csv"]["sample_id"])
    for table in ("sample_composition.csv", "electrical_measurements.csv", "measurement_conditions.csv", "exclusions.csv"):
        used = set(tables[table]["sample_id"].astype(str)) - {""}
        if not used <= sample_ids:
            raise ValueError(f"{table} contiene sample_id sin padre: {sorted(used-sample_ids)}")


def build_candidate(tables: dict[str, pd.DataFrame], pdf_name: str):
    out = {name: frame.copy(deep=True) for name, frame in tables.items()}

    fillers = out["filler_variants.csv"]
    for block, info in BLOCK_MAP.items():
        mask = fillers["block_id"] == block
        current_ar = int(float(fillers.loc[mask, "aspect_ratio"].iloc[0]))
        if current_ar != info["aspect_ratio"]:
            raise ValueError(f"Relacion de aspecto incompatible en {block}: {current_ar}")
        fillers.loc[mask, "commercial_name"] = info["commercial_name"]
        fillers.loc[mask, "manufacturer"] = info["manufacturer"]
        fillers.loc[mask, "commercial_identity_status"] = "documented_in_article_pages_8_and_12"
        fillers.loc[mask, "diameter_x50_nm"] = info["diameter_x50_nm"]
        fillers.loc[mask, "length_x50_nm"] = info["length_x50_nm"]
        fillers.loc[mask, "article_mapping_basis"] = "unique exact aspect-ratio match to Table 2"

    measurements = out["electrical_measurements.csv"]
    measurements["frequency_status"] = "not_reported_for_electrical_method; 1_Hz_is_DMA_only"
    measurements["measurement_status"] = "documented_value_unit_and_resistivity_method_verified"
    measurements["electrical_method_page"] = 10
    measurements["current_type_status"] = "not_explicitly_stated"
    measurements["modeling_block_reason"] = "frequency_block_removed; independent fit reproduction and missing-point sensitivity remain"

    condition_rows = []
    for _, row in measurements.iterrows():
        method = classify_method(float(row["value_numeric"]))
        base = dict(measurement_id=row["measurement_id"], sample_id=row["sample_id"], source_document=pdf_name, source_page=10, source_section="Characterization", evidence_status="documented_global_method_with_range_based_assignment")
        fields = {
            "electrical_quantity_measured": "volume_resistivity",
            "reported_quantity": "volume_conductivity_calculated_from_resistivity",
            "electrical_frequency": "not_reported_for_electrical_method",
            "current_type": "not_explicitly_stated",
            "method_group": method["method_group"],
            "instrument": method["instrument"],
            "fixture": method["fixture"],
            "method_range": method["method_range"],
            "specimen_geometry": method["specimen_geometry"],
            "electrode_geometry": method["electrode_geometry"],
        }
        for key, value in fields.items():
            condition_rows.append(dict(condition_id=f"cond-{row['measurement_id']}-{key}", **base, condition_name=key, value_original=value, value_numeric="", unit_original="", canonical_value=value, canonical_unit="", condition_status="documented" if value else "not_reported", method_group=method["method_group"]))
    out["measurement_conditions.csv"] = pd.DataFrame(condition_rows)

    samples = out["samples.csv"]
    s1 = "l254-s1-castillo-2011"
    samples.loc[samples["sample_id"] == s1, "sample_role"] = "pure_polycarbonate_control_candidate"
    samples.loc[samples["sample_id"] == s1, "block_definition_status"] = "inferred_from_unassigned_sample_and_figure_2_zero_wt_percent"

    exclusions = out["exclusions.csv"]
    exclusions["article_validation_disposition"] = exclusions["reason"].map(lambda x: "superseded_by_article_method_validation" if x == "measurement_frequency_not_verified" else "retained")
    exclusions["active_after_article_validation"] = exclusions["reason"] != "measurement_frequency_not_verified"

    curves = out["curve_inclusion_status.csv"]
    curves["frequency_documented_count"] = 0
    curves["electrical_method_status"] = "verified_from_article_page_10"
    curves["curve_status"] = curves["complete_pair_count"].astype(int).map(lambda n: "phase3_fit_reproduction_candidate_complete" if n == 7 else "phase3_fit_reproduction_candidate_incomplete")
    curves["usable_for_final_modeling"] = False
    curves["decision_reason"] = "published fit may be reproduced; final release requires independent residual and sensitivity analysis"

    control_proposal = pd.DataFrame([
        dict(sample_id=s1, proposed_mass_fraction=0.0, proposed_volume_fraction=0.0, evidence="Figure 2 includes pure PC at 0 wt%; sample-to-point identity inferred from corpus integration", evidence_status="inferred_not_applied", required_next_check="verify exact pure-PC conductivity against source figure or structured provenance")
    ])

    mapping = pd.DataFrame([dict(block_id=b, filler_variant_id=i["variant"], commercial_name=i["commercial_name"], manufacturer=i["manufacturer"], aspect_ratio=i["aspect_ratio"], diameter_x50_nm=i["diameter_x50_nm"], length_x50_nm=i["length_x50_nm"], source_pages="8|12", evidence_status="confirmed_unique_match") for b, i in BLOCK_MAP.items()])
    benchmarks = pd.DataFrame([dict(block_id=b, filler_variant_id=i["variant"], commercial_name=i["commercial_name"], published_B_s_per_cm=i["B"], published_pc_wt_percent=i["pc"], published_critical_exponent_t=i["t"], source_page=16, status="published_benchmark_not_project_fit") for b, i in BLOCK_MAP.items()])
    return out, control_proposal, mapping, benchmarks


def quality_checks(source: dict[str, pd.DataFrame], candidate: dict[str, pd.DataFrame], mapping: pd.DataFrame, benchmarks: pd.DataFrame):
    checks = []
    def add(cid, passed, description, observed, expected):
        checks.append(dict(check_id=cid, passed=bool(passed), description=description, observed=str(observed), expected=str(expected)))
    add("Q001", len(candidate["samples.csv"]) == 36, "sample count preserved", len(candidate["samples.csv"]), 36)
    add("Q002", len(candidate["electrical_measurements.csv"]) == 29, "measurement count preserved", len(candidate["electrical_measurements.csv"]), 29)
    add("Q003", len(mapping) == 5 and mapping["commercial_name"].nunique() == 5, "five unique commercial mappings", mapping["commercial_name"].nunique(), 5)
    add("Q004", set(mapping["aspect_ratio"]) == {134,94,55,73,69}, "aspect ratios preserved", sorted(mapping["aspect_ratio"]), "55,69,73,94,134")
    add("Q005", len(candidate["measurement_conditions.csv"]) == 290, "ten method fields per measurement", len(candidate["measurement_conditions.csv"]), 290)
    freq = candidate["measurement_conditions.csv"].query("condition_name == 'electrical_frequency'")
    add("Q006", len(freq) == 29 and freq["canonical_value"].eq("not_reported_for_electrical_method").all(), "electrical frequency not fabricated", len(freq), 29)
    add("Q007", len(benchmarks) == 5, "five published benchmarks", len(benchmarks), 5)
    add("Q008", len(candidate["sample_composition.csv"]) == len(source["sample_composition.csv"]), "no composition imputed", len(candidate["sample_composition.csv"]), len(source["sample_composition.csv"]))
    add("Q009", candidate["exclusions.csv"]["reason"].eq("measurement_frequency_not_verified").sum() == source["exclusions.csv"]["reason"].eq("measurement_frequency_not_verified").sum(), "historical exclusions retained with disposition", candidate["exclusions.csv"]["reason"].eq("measurement_frequency_not_verified").sum(), source["exclusions.csv"]["reason"].eq("measurement_frequency_not_verified").sum())
    add("Q010", not candidate["curve_inclusion_status.csv"]["usable_for_final_modeling"].astype(str).str.lower().eq("true").any(), "no automatic final-model release", "checked", True)
    return pd.DataFrame(checks)


def write_atomic(candidate_dir: Path, tables, control_proposal, mapping, benchmarks, quality, source_dir: Path, pdf: Path):
    parent = candidate_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=candidate_dir.name + ".tmp.", dir=parent))
    try:
        for name, frame in tables.items():
            frame.to_csv(temp / name, index=False, encoding="utf-8-sig")
        evidence = temp / "article_validation"
        evidence.mkdir()
        control_proposal.to_csv(evidence / "pure_pc_control_composition_proposal.csv", index=False, encoding="utf-8-sig")
        mapping.to_csv(evidence / "block_commercial_mapping.csv", index=False, encoding="utf-8-sig")
        benchmarks.to_csv(evidence / "published_percolation_benchmarks.csv", index=False, encoding="utf-8-sig")
        quality.to_csv(evidence / "quality_checks.csv", index=False, encoding="utf-8-sig")
        manifest = {
            "release": RELEASE,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source_corpus": str(source_dir),
            "source_files": {name: sha256(source_dir / name) for name in REQUIRED},
            "source_pdf": str(pdf),
            "source_pdf_sha256": sha256(pdf),
            "decisions": [
                "1 Hz is documented for DMA only and is not an electrical-conductivity condition.",
                "Electrical frequency and current type are not explicitly stated in the article.",
                "Two resistivity methods are documented and assigned by strict conductivity ranges.",
                "Pure-PC zero composition is proposed but not applied automatically.",
                "Published B, pc, and t are benchmarks, not project-generated fits.",
                "Canonical corpus was not overwritten.",
            ],
            "quality_passed": bool(quality["passed"].all()),
        }
        (temp / "article_validation_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        if candidate_dir.exists():
            shutil.rmtree(candidate_dir)
        temp.rename(candidate_dir)
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise


def main():
    args = parse_args()
    root = Path(args.root).resolve()
    source_dir = (root / args.source_corpus).resolve()
    candidate_dir = (root / args.output_corpus).resolve()
    pdf = (root / args.pdf).resolve()
    if source_dir == candidate_dir:
        raise ValueError("El directorio de salida no puede ser el corpus canonico")
    if not pdf.is_file():
        raise FileNotFoundError(f"No se encontro el PDF: {pdf}")
    tables = {name: read_table(source_dir / name, cols) for name, cols in REQUIRED.items()}
    validate_inputs(tables)
    candidate, control_proposal, mapping, benchmarks = build_candidate(tables, pdf.name)
    quality = quality_checks(tables, candidate, mapping, benchmarks)
    failed = quality[quality["passed"] != True]

    print("AUDITORIA PREVIA COMPLETADA")
    print(f"PDF SHA256: {sha256(pdf)}")
    print(f"Corpus fuente: {source_dir}")
    print(f"Controles: {len(quality)}")
    print(f"Fallos: {len(failed)}")
    print("Corpus canonico modificado: NO")
    if not failed.empty:
        print(failed.to_string(index=False))
        return 1
    if not args.apply:
        print("Modo: DRY-RUN")
        print("Para crear el corpus candidato use --apply")
        return 0
    if candidate_dir.exists() and not args.replace_output:
        raise FileExistsError(f"La salida ya existe: {candidate_dir}. Use --replace-output para reemplazar solo la copia candidata.")
    write_atomic(candidate_dir, candidate, control_proposal, mapping, benchmarks, quality, source_dir, pdf)
    print("Modo: APPLY SEGURO")
    print(f"Corpus candidato creado: {candidate_dir}")
    print("Corpus canonico modificado: NO")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        sys.exit(1)
