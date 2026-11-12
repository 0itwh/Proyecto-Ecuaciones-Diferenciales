from pathlib import Path
from datetime import datetime
import csv
import hashlib
import json
import shutil
import sys
import zipfile

ROOT = Path.cwd()
RELEASE_ID = "phase2-corpus-release-v1"
STAGE = ROOT / "archive" / RELEASE_ID
ZIP_OUT = ROOT / "archive" / f"{RELEASE_ID}.zip"
META = ROOT / "metadata"
LOGS = ROOT / "logs"

L172 = ROOT / "data_processed" / "l172_corpus"
L254 = ROOT / "data_processed" / "l254_corpus"

FINAL_MANIFEST = META / "phase2-corpus-manifest.json"
QUALITY_SUMMARY = META / "phase2-quality-summary.csv"
FINAL_REPORT = LOGS / "phase2-final-quality-report.txt"
DECISION_LOG = LOGS / "phase2-decision-log.csv"
ERROR_LOG = LOGS / "phase2-release-build-error.log"

NOW = datetime.now().astimezone().isoformat(timespec="seconds")

REQUIRED = [
    L172 / "studies.csv",
    L172 / "material_systems.csv",
    L172 / "samples.csv",
    L172 / "sample_composition.csv",
    L172 / "processing_steps.csv",
    L172 / "measurements_unresolved.csv",
    L172 / "provenance.csv",
    L172 / "exclusions.csv",
    L254 / "studies.csv",
    L254 / "material_systems.csv",
    L254 / "filler_variants.csv",
    L254 / "samples.csv",
    L254 / "sample_composition.csv",
    L254 / "processing_steps.csv",
    L254 / "electrical_measurements.csv",
    L254 / "measurement_conditions.csv",
    L254 / "provenance.csv",
    L254 / "exclusions.csv",
    L254 / "curve_inclusion_status.csv",
    META / "l172-corpus-manifest.json",
    META / "l172-corpus-quality-summary.csv",
    META / "l254-corpus-manifest.json",
    META / "l254-corpus-quality-summary.csv",
    LOGS / "l172-corpus-quality-report.txt",
    LOGS / "l254-corpus-quality-report.txt",
]

OPTIONAL = [
    ROOT / "scripts" / "build_l172_relational_corpus.py",
    ROOT / "scripts" / "build_l254_relational_corpus.py",
    ROOT / "scripts" / "extract_l254_castillo_family.py",
    ROOT / "scripts" / "build_l254_combined_sample_table.py",
    ROOT / "scripts" / "compare_l254_blocks.py",
    ROOT / "scripts" / "normalize_l254_block_features.py",
    ROOT / "scripts" / "apply_l254_block_decision_rule.py",
    ROOT / "scripts" / "extract_l254_matrix_mwcnt_separated.py",
    META / "l254-matrix-mwcnt-separation-manifest.json",
    META / "l254-matrix-mwcnt-separation-quality.csv",
    LOGS / "l254-matrix-mwcnt-separation.log",
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def relative_destination(path):
    return path.relative_to(ROOT)


def copy_into_stage(path):
    destination = STAGE / relative_destination(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    return destination


def count_csv_rows(path):
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream)
        return max(sum(1 for _ in reader) - 1, 0)


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    print("CONSTRUYENDO PAQUETE REPRODUCIBLE DE CIERRE DE FASE 2")

    missing = [str(path) for path in REQUIRED if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Faltan archivos requeridos:\n- " + "\n- ".join(missing)
        )

    l172_manifest = read_json(META / "l172-corpus-manifest.json")
    l254_manifest = read_json(META / "l254-corpus-manifest.json")

    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    META.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    quality_rows = [
        {
            "corpus_id": "l172-corpus-v1",
            "scientific_role": "auxiliary_quarantine",
            "samples": l172_manifest.get("counts", {}).get("samples", 18),
            "composition_rows": l172_manifest.get("counts", {}).get("sample_composition", 5),
            "electrical_measurements": l172_manifest.get("counts", {}).get("measurements_unresolved", 235),
            "curves": 0,
            "unit_status": "not_verified",
            "condition_status": "not_verified",
            "usable_for_final_modeling": "false",
            "decision": "retain_as_auxiliary_quarantine",
        },
        {
            "corpus_id": "l254-corpus-v1",
            "scientific_role": "primary_candidate",
            "samples": l254_manifest.get("counts", {}).get("samples", 36),
            "composition_rows": l254_manifest.get("counts", {}).get("sample_composition", 70),
            "electrical_measurements": l254_manifest.get("counts", {}).get("electrical_measurements", 29),
            "curves": l254_manifest.get("counts", {}).get("curves", 5),
            "unit_status": "documented_S_per_cm",
            "condition_status": "partial_4_frequencies_documented",
            "usable_for_final_modeling": "false",
            "decision": "retain_as_primary_candidate_for_phase3_exploration",
        },
    ]
    write_csv(
        QUALITY_SUMMARY,
        quality_rows,
        [
            "corpus_id", "scientific_role", "samples", "composition_rows",
            "electrical_measurements", "curves", "unit_status",
            "condition_status", "usable_for_final_modeling", "decision",
        ],
    )

    decisions = [
        {
            "decision_id": "P2-D001",
            "entity": "l172-corpus-v1",
            "evidence_state": "confirmed",
            "decision": "auxiliary_quarantine",
            "reason": "235 conductivity values lack verified unit and measurement conditions",
        },
        {
            "decision_id": "P2-D002",
            "entity": "l254-corpus-v1",
            "evidence_state": "confirmed",
            "decision": "primary_candidate",
            "reason": "composition, S/cm conductivity, DOI, processing, and five MWCNT variants are linked by sample",
        },
        {
            "decision_id": "P2-D003",
            "entity": "l254-five-curves",
            "evidence_state": "confirmed",
            "decision": "retain_separately",
            "reason": "five distinct aspect ratios and study design support five distinct MWCNT variants",
        },
        {
            "decision_id": "P2-D004",
            "entity": "l254-measurement-conditions",
            "evidence_state": "documented_partial",
            "decision": "block_final_modeling",
            "reason": "frequency is documented for only four samples; other electrical conditions remain incomplete",
        },
        {
            "decision_id": "P2-D005",
            "entity": "phase3-scope",
            "evidence_state": "authorized_next_phase",
            "decision": "exploratory_analysis_only",
            "reason": "begin visualization and coverage analysis without percolation fitting",
        },
    ]
    write_csv(
        DECISION_LOG,
        decisions,
        ["decision_id", "entity", "evidence_state", "decision", "reason"],
    )

    report_lines = [
        "FASE 2 - INFORME FINAL DE CIERRE",
        "",
        f"Fecha de congelacion: {NOW}",
        f"Release: {RELEASE_ID}",
        "",
        "RESULTADO",
        "- Fase 2 cerrada: adquisicion y curacion del corpus completadas.",
        "- l172-corpus-v1 queda como corpus auxiliar en cuarentena.",
        "- l254-corpus-v1 queda como corpus principal candidato para analisis exploratorio.",
        "- Las cinco variantes MWCNT de l254 se conservan como cinco curvas independientes.",
        "- Ninguna curva queda liberada para modelado final por condiciones de medicion incompletas.",
        "- No se imputaron unidades, frecuencias, conductividades, procesamiento ni identidades comerciales.",
        "- No se ejecutaron ajustes de percolacion, regresiones ni modelos.",
        "",
        "CORPUS L172",
        "- 18 muestras.",
        "- 5 registros de composicion.",
        "- 235 mediciones de conductividad bloqueadas.",
        "- Unidad y condiciones electricas no verificadas.",
        "",
        "CORPUS L254",
        "- 36 muestras.",
        "- 70 registros de composicion.",
        "- 29 mediciones electricas en S/cm.",
        "- 28 pares completos composicion-conductividad.",
        "- 5 variantes MWCNT con relaciones de aspecto 134, 94, 55, 73 y 69.",
        "- 4 frecuencias documentadas; 25 condiciones de frecuencia no verificadas entre las mediciones.",
        "- Bloque AR134: 7 pares completos, candidato principal para Fase 3.",
        "",
        "ESTADO DE EVIDENCIA",
        "- Confirmado: estructura relacional, conteos, claves, unidades de l254, cinco variantes y controles de calidad.",
        "- Documentado: DOI, matriz Makrolon 2600, fabricante Bayer MaterialScience, procesamiento y frecuencias disponibles.",
        "- Inferido: ninguna condicion ausente fue completada; los identificadores internos de variantes no son nombres comerciales.",
        "- No verificado: identidades comerciales MWCNT, semantica de densidad y condiciones electricas completas.",
        "",
        "SIGUIENTE FASE AUTORIZADA",
        "- Fase 3: analisis exploratorio por curva.",
        "- Permitido: cobertura, faltantes, visualizacion logaritmica, monotonia, rangos y comparacion descriptiva.",
        "- Fuera de alcance hasta nueva autorizacion: ajuste de percolacion y modelado final.",
    ]
    FINAL_REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    combined_manifest = {
        "release_id": RELEASE_ID,
        "generated_at": NOW,
        "phase": "2_acquisition_and_curation",
        "phase_status": "closed",
        "corpora": [
            {
                "corpus_id": "l172-corpus-v1",
                "path": "data_processed/l172_corpus",
                "role": "auxiliary_quarantine",
                "modeling_status": "blocked_missing_unit_and_conditions",
            },
            {
                "corpus_id": "l254-corpus-v1",
                "path": "data_processed/l254_corpus",
                "role": "primary_candidate",
                "modeling_status": "blocked_pending_measurement_condition_validation",
            },
        ],
        "phase3_entry_decision": "approved_for_exploratory_analysis_without_percolation_fitting",
        "source_manifests": {
            "l172": l172_manifest,
            "l254": l254_manifest,
        },
    }
    FINAL_MANIFEST.write_text(
        json.dumps(combined_manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    files_to_copy = REQUIRED + [path for path in OPTIONAL if path.is_file()] + [
        FINAL_MANIFEST, QUALITY_SUMMARY, FINAL_REPORT, DECISION_LOG,
    ]
    copied = []
    for path in files_to_copy:
        if path.is_file():
            copied.append(copy_into_stage(path))

    # README for durable reuse.
    readme = STAGE / "README_PHASE2_RELEASE.txt"
    readme.write_text(
        "\n".join([
            "PHASE 2 CORPUS RELEASE V1",
            "",
            "Contents:",
            "- data_processed/l172_corpus: auxiliary quarantine corpus",
            "- data_processed/l254_corpus: primary candidate corpus",
            "- metadata: manifests and quality summaries",
            "- logs: final reports and decision records",
            "- scripts: reproducible builders when available",
            "",
            "Reproduction order:",
            "1. Run scripts/build_l172_relational_corpus.py",
            "2. Run scripts/build_l254_relational_corpus.py",
            "3. Run scripts/build_phase2_release_package.py",
            "",
            "Scientific restriction:",
            "Phase 3 may perform exploratory analysis only. Do not fit percolation models until measurement-condition decisions are explicitly updated.",
        ]) + "\n",
        encoding="utf-8",
    )
    copied.append(readme)

    inventory_path = STAGE / "sha256-inventory.csv"
    inventory_rows = []
    for path in sorted(p for p in STAGE.rglob("*") if p.is_file() and p != inventory_path):
        inventory_rows.append({
            "relative_path": path.relative_to(STAGE).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    write_csv(inventory_path, inventory_rows, ["relative_path", "bytes", "sha256"])

    # Validate inventory before zipping.
    for row in inventory_rows:
        path = STAGE / row["relative_path"]
        if sha256(path) != row["sha256"]:
            raise ValueError(f"Hash inconsistente: {path}")

    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    with zipfile.ZipFile(ZIP_OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in STAGE.rglob("*") if p.is_file()):
            archive.write(path, arcname=f"{RELEASE_ID}/{path.relative_to(STAGE).as_posix()}")

    # Verify ZIP integrity.
    with zipfile.ZipFile(ZIP_OUT, "r") as archive:
        bad = archive.testzip()
        if bad is not None:
            raise ValueError(f"Archivo corrupto dentro del ZIP: {bad}")
        zip_members = len(archive.namelist())

    release_summary = {
        "release_id": RELEASE_ID,
        "generated_at": NOW,
        "stage_directory": str(STAGE),
        "zip_file": str(ZIP_OUT),
        "zip_bytes": ZIP_OUT.stat().st_size,
        "zip_sha256": sha256(ZIP_OUT),
        "inventory_entries": len(inventory_rows),
        "zip_members": zip_members,
        "required_files_missing": 0,
        "phase_status": "closed",
    }
    (STAGE / "release-summary.json").write_text(
        json.dumps(release_summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    # Rebuild zip with release summary included and verify one final time.
    ZIP_OUT.unlink()
    with zipfile.ZipFile(ZIP_OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(p for p in STAGE.rglob("*") if p.is_file()):
            archive.write(path, arcname=f"{RELEASE_ID}/{path.relative_to(STAGE).as_posix()}")
    with zipfile.ZipFile(ZIP_OUT, "r") as archive:
        if archive.testzip() is not None:
            raise ValueError("Fallo de integridad en ZIP final")

    print("PAQUETE DE FASE 2 GENERADO")
    print(f"Release: {RELEASE_ID}")
    print(f"Archivos inventariados: {len(inventory_rows)}")
    print(f"ZIP: {ZIP_OUT}")
    print(f"SHA256 ZIP: {sha256(ZIP_OUT)}")
    print("Estado de Fase 2: closed")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        ERROR_LOG.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_LOG}")
        sys.exit(1)
