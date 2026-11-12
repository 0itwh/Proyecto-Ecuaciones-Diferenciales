from pathlib import Path
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = Path.cwd()
INPUT = ROOT / 'electric-conductivity-search-response.json'
OUT_JSON = ROOT / 'sparql-bindings-deduplicated.json'
OUT_CSV = ROOT / 'sparql-bindings-deduplicated.csv'
SUMMARY = ROOT / 'sparql-extraction-summary.txt'

raw = INPUT.read_bytes()
doc = json.loads(raw.decode('utf-8-sig'))
hits = doc.get('data', {}).get('hits', [])

response_hits = []
all_rows = []
queries = Counter()
response_fingerprints = Counter()

for hit in hits:
    src = hit.get('_source') or {}
    response = src.get('response')
    if not isinstance(response, dict):
        continue
    bindings = (((response.get('results') or {}).get('bindings')) or [])
    if not isinstance(bindings, list):
        continue
    query = src.get('label') if isinstance(src.get('label'), str) else ''
    query_norm = '\n'.join(line.rstrip() for line in query.strip().splitlines())
    queries[hashlib.sha256(query_norm.encode('utf-8')).hexdigest()] += 1
    response_serialized = json.dumps(bindings, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    response_fingerprints[hashlib.sha256(response_serialized.encode('utf-8')).hexdigest()] += 1
    response_hits.append({
        'hit_id': hit.get('_id'),
        'index': hit.get('_index'),
        'date': src.get('date'),
        'query_sha256': hashlib.sha256(query_norm.encode('utf-8')).hexdigest(),
        'response_sha256': hashlib.sha256(response_serialized.encode('utf-8')).hexdigest(),
        'bindings_count': len(bindings),
    })
    for b in bindings:
        row = {}
        for var, cell in b.items():
            if isinstance(cell, dict):
                row[var] = cell.get('value')
                row[f'{var}__type'] = cell.get('type')
                row[f'{var}__datatype'] = cell.get('datatype')
            else:
                row[var] = cell
        row['_source_hit_id'] = hit.get('_id')
        row['_source_date'] = src.get('date')
        row['_query_sha256'] = hashlib.sha256(query_norm.encode('utf-8')).hexdigest()
        row['_response_sha256'] = hashlib.sha256(response_serialized.encode('utf-8')).hexdigest()
        all_rows.append(row)

# Deduplicate scientific observations independently of repeated indexed query copies.
scientific_fields = ['Sample', 'Filler', 'VolumeFraction', 'Matrix', 'Conductivity', 'UnitOfMeasure']
seen = {}
source_occurrences = defaultdict(list)
for row in all_rows:
    key = tuple(row.get(f) for f in scientific_fields)
    if key not in seen:
        seen[key] = row.copy()
    source_occurrences[key].append({
        'hit_id': row.get('_source_hit_id'),
        'date': row.get('_source_date'),
        'query_sha256': row.get('_query_sha256'),
        'response_sha256': row.get('_response_sha256'),
    })

unique_rows = []
for key, row in seen.items():
    sample_uri = row.get('Sample') or ''
    row['sample_id'] = sample_uri.rsplit('/', 1)[-1] if sample_uri else None
    row['source_occurrence_count'] = len(source_occurrences[key])
    row['source_hits'] = source_occurrences[key]
    row['unit_status'] = 'documented' if row.get('UnitOfMeasure') else 'not_verified'
    unique_rows.append(row)

# Stable scientific sort.
def nfloat(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float('inf')

unique_rows.sort(key=lambda r: (r.get('Matrix') or '', r.get('Filler') or '', nfloat(r.get('VolumeFraction')), r.get('Sample') or '', nfloat(r.get('Conductivity'))))

# JSON provenance package
payload = {
    'generated_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    'input_file': INPUT.name,
    'input_sha256': hashlib.sha256(raw).hexdigest(),
    'deduplication_key': scientific_fields,
    'notes': [
        'Repeated indexed knowledge documents were removed using the scientific observation key.',
        'Missing UnitOfMeasure values remain null and are marked not_verified.',
        'No averaging, unit conversion, interpolation, or modeling was performed.'
    ],
    'source_response_hits': response_hits,
    'counts': {
        'search_hits_total': len(hits),
        'hits_with_sparql_response': len(response_hits),
        'raw_bindings_across_hits': len(all_rows),
        'unique_bindings': len(unique_rows),
        'duplicates_removed': len(all_rows) - len(unique_rows),
        'unique_query_fingerprints': len(queries),
        'unique_response_fingerprints': len(response_fingerprints),
    },
    'bindings': unique_rows,
}
OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')

# Flattened CSV
csv_fields = [
    'sample_id', 'Sample', 'Filler', 'VolumeFraction', 'Matrix', 'Conductivity',
    'UnitOfMeasure', 'unit_status', 'Sample__type', 'VolumeFraction__datatype',
    'Conductivity__datatype', 'source_occurrence_count'
]
with OUT_CSV.open('w', encoding='utf-8-sig', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(unique_rows)

sample_counts = Counter(r.get('sample_id') for r in unique_rows)
fractions = sorted({r.get('VolumeFraction') for r in unique_rows}, key=nfloat)
unit_present = sum(1 for r in unique_rows if r.get('UnitOfMeasure'))
summary_lines = [
    'FASE 1 - EXTRACCION Y DEDUPLICACION DE RESPUESTAS SPARQL',
    '',
    f'Entrada: {INPUT.name}',
    f'SHA256 entrada: {hashlib.sha256(raw).hexdigest()}',
    f'Hits de busqueda totales: {len(hits)}',
    f'Hits con respuesta SPARQL: {len(response_hits)}',
    f'Bindings brutos acumulados: {len(all_rows)}',
    f'Bindings unicos: {len(unique_rows)}',
    f'Duplicados eliminados: {len(all_rows) - len(unique_rows)}',
    f'Consultas SPARQL unicas por hash: {len(queries)}',
    f'Respuestas unicas por hash: {len(response_fingerprints)}',
    f'Muestras unicas: {len(sample_counts)}',
    f'Fracciones volumetricas unicas: {", ".join(str(x) for x in fractions)}',
    f'Registros con unidad documentada: {unit_present}/{len(unique_rows)}',
    '',
    'MEDICIONES UNICAS POR MUESTRA',
]
for sample, count in sorted(sample_counts.items()):
    summary_lines.append(f'- {sample}: {count}')
summary_lines += [
    '',
    'REGLA DE DEDUPLICACION',
    'Sample + Filler + VolumeFraction + Matrix + Conductivity + UnitOfMeasure',
    '',
    'ADVERTENCIAS',
    '- No se calcularon medias.',
    '- No se asumieron unidades.',
    '- No se interpretaron los multiples valores por muestra como replicas.',
    '- No se aplicaron transformaciones ni modelos.',
    '',
    f'Salida JSON: {OUT_JSON.name}',
    f'Salida CSV: {OUT_CSV.name}',
]
SUMMARY.write_text('\n'.join(summary_lines) + '\n', encoding='utf-8')

print(json.dumps(payload['counts'], indent=2))
print(f'samples={len(sample_counts)} fractions={fractions} units_present={unit_present}')
print(OUT_JSON)
print(OUT_CSV)
print(SUMMARY)
