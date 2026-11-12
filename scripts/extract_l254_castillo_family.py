from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
import re
import sys

ROOT = Path.cwd()
INPUT = ROOT / "data_raw" / "explorer" / "cnt-l254-castillo-2011-search-response.json"
OUT = ROOT / "data_interim" / "cnt" / "l254_castillo_2011"
META = ROOT / "metadata"
LOGS = ROOT / "logs"
for folder in (OUT, META, LOGS):
    folder.mkdir(parents=True, exist_ok=True)

SAMPLES_OUT = OUT / "l254-samples.csv"
PROVENANCE_OUT = OUT / "l254-study-provenance.csv"
ATTRIBUTES_OUT = OUT / "l254-sample-attributes.csv"
COMPONENTS_OUT = OUT / "l254-material-components.csv"
PROCESSING_OUT = OUT / "l254-processing-steps.csv"
ELECTRICAL_OUT = OUT / "l254-electrical-attributes.csv"
COMPOSITION_OUT = OUT / "l254-composition.csv"
SERIES_OUT = OUT / "l254-series-candidates.csv"
QUERY_OUT = META / "l254-query-inventory.csv"
MANIFEST_OUT = META / "l254-extraction-manifest.json"
LOG_OUT = LOGS / "l254-extraction.log"
ERROR_OUT = LOGS / "l254-extraction-error.log"
NOW = datetime.now().astimezone().isoformat(timespec="seconds")

SAMPLE_RE = re.compile(r"l254-s\d+-castillo-2011", re.I)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
ELECTRICAL_RE = re.compile(
    r"conductiv|resistiv|impedance|dielectric|permittiv|electric|current|voltage|frequency",
    re.I,
)
COMPOSITION_RE = re.compile(
    r"mass.?fraction|weight.?fraction|volume.?fraction|composition|concentration|loading|wt\.?%|vol\.?%",
    re.I,
)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def normalise_query(value):
    if not isinstance(value, str):
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def value(cell):
    if isinstance(cell, dict):
        return cell.get("value", "")
    return "" if cell is None else cell


def sample_id_from_text(item):
    match = SAMPLE_RE.search(str(item or ""))
    return match.group(0).lower() if match else ""


def safe_float(item):
    try:
        number = float(str(item))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def flatten_binding(binding):
    row = {}
    for variable, cell in binding.items():
        row[variable] = value(cell)
        if isinstance(cell, dict):
            row[f"{variable}__type"] = cell.get("type", "")
            row[f"{variable}__datatype"] = cell.get("datatype", "")
            row[f"{variable}__xml_lang"] = cell.get("xml:lang", "")
    return row


def write_csv(path, rows, preferred):
    columns = list(preferred)
    for key in sorted({key for row in rows for key in row}):
        if key not in columns:
            columns.append(key)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def scientific_key(row, fields):
    return tuple(str(row.get(field, "")) for field in fields)


def deduplicate(rows, fields):
    unique = {}
    occurrences = defaultdict(list)
    for row in rows:
        key = scientific_key(row, fields)
        if key not in unique:
            unique[key] = row.copy()
        occurrences[key].append({
            "hit_id": row.get("source_hit_id", ""),
            "source_date": row.get("source_date", ""),
            "query_sha256": row.get("query_sha256", ""),
            "response_sha256": row.get("response_sha256", ""),
            "binding_position": row.get("binding_position", ""),
        })
    result = []
    for key, row in unique.items():
        row["source_occurrence_count"] = len(occurrences[key])
        row["source_occurrences"] = json.dumps(occurrences[key], ensure_ascii=False)
        result.append(row)
    return result


def classify_attribute(attr_type, unit, label):
    text = " ".join(map(str, [attr_type, unit, label]))
    if COMPOSITION_RE.search(text):
        return "composition"
    if ELECTRICAL_RE.search(text):
        return "electrical"
    return "other"


def main():
    print("EXTRAYENDO FAMILIA L254-CASTILLO-2011")
    if not INPUT.is_file():
        raise FileNotFoundError(f"No se encontro: {INPUT}")

    raw = INPUT.read_bytes()
    document = json.loads(raw.decode("utf-8-sig"))
    data = document.get("data", {})
    hits = data.get("hits", [])
    total = data.get("total")
    if not isinstance(hits, list):
        raise ValueError("data.hits no es una lista")

    query_inventory = []
    samples_raw = []
    provenance_raw = []
    attributes_raw = []
    components_raw = []
    processing_raw = []

    for position, hit in enumerate(hits):
        source = hit.get("_source", {}) or {}
        response = source.get("response", {})
        if not isinstance(response, dict):
            continue
        variables = (response.get("head", {}) or {}).get("vars", []) or []
        bindings = (response.get("results", {}) or {}).get("bindings", []) or []
        if not isinstance(bindings, list):
            continue

        query = normalise_query(source.get("label", ""))
        query_hash = sha256_bytes(query.encode("utf-8"))
        response_hash = sha256_bytes(
            json.dumps(bindings, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        signature = "|".join(map(str, variables))
        query_inventory.append({
            "search_position": position,
            "hit_id": hit.get("_id", ""),
            "source_date": source.get("date", ""),
            "variable_signature": signature,
            "binding_count": len(bindings),
            "query_sha256": query_hash,
            "response_sha256": response_hash,
        })

        for binding_position, binding in enumerate(bindings):
            if not isinstance(binding, dict):
                continue
            flat = flatten_binding(binding)
            trace = {
                "source_hit_id": hit.get("_id", ""),
                "source_date": source.get("date", ""),
                "query_sha256": query_hash,
                "response_sha256": response_hash,
                "binding_position": binding_position,
            }

            if variables == ["sample"]:
                sample_uri = str(flat.get("sample", ""))
                sample_id = sample_id_from_text(sample_uri)
                if sample_id:
                    samples_raw.append({"sample_id": sample_id, "sample_uri": sample_uri, **trace})

            elif set(["DOI", "sample_label", "process_label"]).issubset(variables):
                sample_id = sample_id_from_text(query + " " + json.dumps(flat, ensure_ascii=False))
                doi = str(flat.get("DOI", ""))
                provenance_raw.append({
                    "sample_id": sample_id,
                    "doi_or_resource": doi,
                    "sample_label": flat.get("sample_label", ""),
                    "process_label": flat.get("process_label", ""),
                    **trace,
                })

            elif set(["AttrType", "value", "Units"]).issubset(variables):
                sample_id = sample_id_from_text(query)
                attr_type = str(flat.get("AttrType", ""))
                attr_value = flat.get("value", "")
                unit = str(flat.get("Units", ""))
                category = classify_attribute(attr_type, unit, "")
                attributes_raw.append({
                    "sample_id": sample_id,
                    "attribute_type": attr_type,
                    "attribute_value_original": attr_value,
                    "attribute_value_numeric": safe_float(attr_value),
                    "attribute_unit_original": unit,
                    "attribute_category": category,
                    **trace,
                })

            elif set(["std_name", "role", "attrType", "attrValue", "attrUnits", "fullLabel"]).issubset(variables):
                sample_id = sample_id_from_text(query)
                row = {
                    "sample_id": sample_id,
                    "standard_name": flat.get("std_name", ""),
                    "component_role": flat.get("role", ""),
                    "attribute_type": flat.get("attrType", ""),
                    "attribute_value_original": flat.get("attrValue", ""),
                    "attribute_value_numeric": safe_float(flat.get("attrValue", "")),
                    "attribute_unit_original": flat.get("attrUnits", ""),
                    "full_label": flat.get("fullLabel", ""),
                    **trace,
                }
                components_raw.append(row)

            elif set(["step", "param_label", "Descr"]).issubset(variables):
                sample_id = sample_id_from_text(str(flat.get("step", "")) + " " + query)
                processing_raw.append({
                    "sample_id": sample_id,
                    "processing_step": flat.get("step", ""),
                    "parameter_label": flat.get("param_label", ""),
                    "description_original": flat.get("Descr", ""),
                    **trace,
                })

    samples = deduplicate(samples_raw, ["sample_id", "sample_uri"])
    provenance = deduplicate(provenance_raw, ["sample_id", "doi_or_resource", "sample_label", "process_label"])
    attributes = deduplicate(attributes_raw, ["sample_id", "attribute_type", "attribute_value_original", "attribute_unit_original"])
    components = deduplicate(components_raw, ["sample_id", "standard_name", "component_role", "attribute_type", "attribute_value_original", "attribute_unit_original", "full_label"])
    processing = deduplicate(processing_raw, ["sample_id", "processing_step", "parameter_label", "description_original"])

    # Add DOI literals found exactly in provenance or, secondarily, in the raw hit text.
    doi_values = sorted({str(row["doi_or_resource"]).strip() for row in provenance if DOI_RE.fullmatch(str(row["doi_or_resource"]).strip())})
    if not doi_values:
        doi_values = sorted(set(DOI_RE.findall(raw.decode("utf-8-sig"))))

    # Derive composition and electrical subsets only from explicit metadata labels/types.
    composition = []
    electrical = []
    for row in attributes:
        if row["attribute_category"] == "composition":
            composition.append(row.copy())
        if row["attribute_category"] == "electrical":
            electrical.append(row.copy())
    for row in components:
        category = classify_attribute(row["attribute_type"], row["attribute_unit_original"], row["full_label"])
        enriched = row.copy()
        enriched["attribute_category"] = category
        if category == "composition":
            composition.append(enriched)
        if category == "electrical":
            electrical.append(enriched)

    composition = deduplicate(composition, ["sample_id", "attribute_type", "attribute_value_original", "attribute_unit_original", "full_label"])
    electrical = deduplicate(electrical, ["sample_id", "attribute_type", "attribute_value_original", "attribute_unit_original", "full_label"])

    # Summarize candidate series conservatively.
    by_key = defaultdict(list)
    for row in electrical:
        key = (row.get("attribute_type", ""), row.get("attribute_unit_original", ""))
        by_key[key].append(row)
    series = []
    for index, ((attr_type, unit), rows) in enumerate(sorted(by_key.items()), start=1):
        sample_ids = sorted({row.get("sample_id", "") for row in rows if row.get("sample_id", "")})
        values = sorted({row.get("attribute_value_numeric") for row in rows if row.get("attribute_value_numeric") is not None})
        series.append({
            "series_id": f"l254-series-{index:03d}",
            "attribute_type": attr_type,
            "unit_original": unit,
            "sample_count": len(sample_ids),
            "measurement_count": len(rows),
            "unique_value_count": len(values),
            "sample_ids": "|".join(sample_ids),
            "status": "candidate_for_manual_review" if rows else "none",
        })

    write_csv(SAMPLES_OUT, samples, ["sample_id", "sample_uri", "source_occurrence_count", "source_hit_id", "source_date", "query_sha256", "response_sha256", "source_occurrences"])
    write_csv(PROVENANCE_OUT, provenance, ["sample_id", "doi_or_resource", "sample_label", "process_label", "source_occurrence_count", "source_hit_id", "source_date", "query_sha256", "response_sha256", "source_occurrences"])
    write_csv(ATTRIBUTES_OUT, attributes, ["sample_id", "attribute_category", "attribute_type", "attribute_value_original", "attribute_value_numeric", "attribute_unit_original", "source_occurrence_count", "source_hit_id", "source_date", "query_sha256", "response_sha256", "source_occurrences"])
    write_csv(COMPONENTS_OUT, components, ["sample_id", "standard_name", "component_role", "attribute_type", "attribute_value_original", "attribute_value_numeric", "attribute_unit_original", "full_label", "source_occurrence_count", "source_hit_id", "source_date", "query_sha256", "response_sha256", "source_occurrences"])
    write_csv(PROCESSING_OUT, processing, ["sample_id", "processing_step", "parameter_label", "description_original", "source_occurrence_count", "source_hit_id", "source_date", "query_sha256", "response_sha256", "source_occurrences"])
    write_csv(ELECTRICAL_OUT, electrical, ["sample_id", "attribute_category", "attribute_type", "attribute_value_original", "attribute_value_numeric", "attribute_unit_original", "standard_name", "component_role", "full_label", "source_occurrence_count", "source_hit_id", "source_date", "query_sha256", "response_sha256", "source_occurrences"])
    write_csv(COMPOSITION_OUT, composition, ["sample_id", "attribute_category", "attribute_type", "attribute_value_original", "attribute_value_numeric", "attribute_unit_original", "standard_name", "component_role", "full_label", "source_occurrence_count", "source_hit_id", "source_date", "query_sha256", "response_sha256", "source_occurrences"])
    write_csv(SERIES_OUT, series, ["series_id", "attribute_type", "unit_original", "sample_count", "measurement_count", "unique_value_count", "sample_ids", "status"])
    write_csv(QUERY_OUT, query_inventory, ["search_position", "hit_id", "source_date", "variable_signature", "binding_count", "query_sha256", "response_sha256"])

    sample_ids = sorted({row["sample_id"] for row in samples})
    signature_counts = Counter(row["variable_signature"] for row in query_inventory)
    counts = {
        "search_hits_downloaded": len(hits),
        "search_total_declared": total,
        "unique_samples": len(sample_ids),
        "provenance_rows": len(provenance),
        "attribute_rows": len(attributes),
        "component_rows": len(components),
        "processing_rows": len(processing),
        "composition_rows_explicitly_classified": len(composition),
        "electrical_rows_explicitly_classified": len(electrical),
        "candidate_series": len(series),
        "doi_values": len(doi_values),
    }

    manifest = {
        "generated_at": NOW,
        "input_file": str(INPUT),
        "input_sha256": sha256_bytes(raw),
        "counts": counts,
        "doi_values": doi_values,
        "sample_ids": sample_ids,
        "query_signature_counts": dict(signature_counts),
        "classification_rule": "Electrical and composition rows require explicit terminology in attribute type, unit, or full label; values are not classified from search terms alone.",
        "notes": [
            "Historical duplicates were collapsed by scientific keys while preserving occurrence metadata.",
            "No unit was inferred and no resistivity-to-conductivity conversion was performed.",
            "A zero electrical-row result is accepted as reproducible evidence.",
            "The response contains only the first 400 of 728 declared hits.",
        ],
    }
    MANIFEST_OUT.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "FASE 2 - EXTRACCION DE LA FAMILIA L254-CASTILLO-2011",
        "",
        f"Fecha: {NOW}",
        f"Entrada: {INPUT}",
        f"SHA256: {sha256_bytes(raw)}",
        "",
    ]
    lines.extend(f"{key}: {item}" for key, item in counts.items())
    lines.extend(["", "DOI/RECURSOS LITERALES"])
    lines.extend([f"- {item}" for item in doi_values] or ["- Ninguno"])
    lines.extend(["", "FIRMAS DE CONSULTA"])
    for signature, count in sorted(signature_counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {signature}: {count}")
    lines.extend(["", "INTERPRETACION"])
    if electrical:
        lines.append("- Se localizaron atributos explicitamente electricos para revision.")
    else:
        lines.append("- No se localizaron atributos explicitamente electricos en los 400 hits descargados.")
    if composition:
        lines.append("- Se localizaron atributos de composicion explicitamente etiquetados.")
    else:
        lines.append("- No se localizaron atributos de composicion clasificables sin inferencia adicional.")
    lines.extend([
        "- Los resultados no se consideran aptos para modelado hasta verificar propiedad, unidad y composicion por muestra.",
        "- No se ejecutaron conversiones, promedios ni modelos.",
        "",
        f"Muestras: {SAMPLES_OUT}",
        f"Procedencia: {PROVENANCE_OUT}",
        f"Atributos: {ATTRIBUTES_OUT}",
        f"Componentes: {COMPONENTS_OUT}",
        f"Procesamiento: {PROCESSING_OUT}",
        f"Electricos: {ELECTRICAL_OUT}",
        f"Composicion: {COMPOSITION_OUT}",
        f"Series: {SERIES_OUT}",
        f"Consultas: {QUERY_OUT}",
        f"Manifiesto: {MANIFEST_OUT}",
    ])
    LOG_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("EXTRACCION COMPLETADA")
    for key, item in counts.items():
        print(f"{key}: {item}")
    print(f"Log: {LOG_OUT}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        ERROR_OUT.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
        print(f"ERROR: {type(error).__name__}: {error}")
        print(f"Log de error: {ERROR_OUT}")
        sys.exit(1)
