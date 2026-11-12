from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
import csv, hashlib, json, math, re, sys

ROOT=Path.cwd()
INPUT=ROOT/'data_raw'/'explorer'/'cnt-electrical-conductivity-search-response.json'
OUT=ROOT/'data_interim'/'cnt'; META=ROOT/'metadata'; LOGS=ROOT/'logs'
for d in (OUT,META,LOGS): d.mkdir(parents=True,exist_ok=True)
BINDINGS=OUT/'cnt-electrical-bindings-deduplicated.csv'
SERIES=OUT/'cnt-electrical-series-summary.csv'
QUERIES=META/'cnt-electrical-query-inventory.csv'
REJECTED=META/'cnt-electrical-rejected-bindings.csv'
CANDIDATES=META/'cnt-sample-hit-candidates.csv'
DETAIL=META/'cnt-electrical-extraction.json'
LOG=LOGS/'cnt-electrical-extraction.log'; ERROR=LOGS/'cnt-electrical-extraction-error.log'
NOW=datetime.now().astimezone().isoformat(timespec='seconds')

CNT_RE=re.compile(r'(?i)(\bcarbon\s+nanotubes?\b|\bmulti[ -]?walled\s+carbon\s+nanotubes?\b|\bsingle[ -]?walled\s+carbon\s+nanotubes?\b|\bdouble[ -]?walled\s+carbon\s+nanotubes?\b|\bmwcnts?\b|\bswcnts?\b|\bdwcnts?\b|\bcnts?\b)')
PROPERTY_FIELDS={
 'Conductivity':'electrical_conductivity','ElectricConductivity':'electrical_conductivity',
 'VolumeResistivity':'volume_resistivity','SurfaceResistivity':'surface_resistivity',
 'Resistivity':'resistivity_unspecified'}
COMPOSITION_FIELDS={
 'VolumeFraction':'volume_fraction','MassFraction':'mass_fraction',
 'WeightFraction':'mass_fraction','Fraction':'fraction_unspecified',
 'Concentration':'concentration_unspecified','Loading':'loading_unspecified'}
UNIT_FIELDS=['UnitOfMeasure','Unit','Units','unit']


def hbytes(b): return hashlib.sha256(b).hexdigest()
def normq(s): return s.replace('\r\n','\n').replace('\r','\n').strip() if isinstance(s,str) else ''
def val(binding,names):
 for n in names:
  x=binding.get(n)
  if isinstance(x,dict) and x.get('value') not in (None,''): return str(x['value'])
  if x not in (None,'') and not isinstance(x,dict): return str(x)
 return ''
def meta(binding,name,key):
 x=binding.get(name); return x.get(key,'') if isinstance(x,dict) else ''
def sid(uri): return uri.rstrip('/').rsplit('/',1)[-1] if uri else ''
def fnum(x):
 try:
  v=float(str(x)); return v if math.isfinite(v) else None
 except (TypeError,ValueError): return None
def subtype(filler):
 low=filler.lower()
 if re.search(r'\bmwcnt|multi[ -]?walled',low): return 'MWCNT'
 if re.search(r'\bswcnt|single[ -]?walled',low): return 'SWCNT'
 if re.search(r'\bdwcnt|double[ -]?walled',low): return 'DWCNT'
 return 'CNT_unspecified'
def response(hit):
 r=(hit.get('_source') or {}).get('response')
 if not isinstance(r,dict): return [],[]
 return ((r.get('head') or {}).get('vars') or []),((r.get('results') or {}).get('bindings') or [])
def property_info(b):
 for field,name in PROPERTY_FIELDS.items():
  x=val(b,[field])
  if x: return field,name,x
 return '','',''
def composition_info(b):
 for field,basis in COMPOSITION_FIELDS.items():
  x=val(b,[field])
  if x: return field,basis,x
 return '','',''
def write(path,rows,preferred):
 cols=list(preferred)
 for k in sorted({k for r in rows for k in r}):
  if k not in cols: cols.append(k)
 with path.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore'); w.writeheader(); w.writerows(rows)


def main():
 print('EXTRAYENDO SERIES ELECTRICAS CNT')
 if not INPUT.is_file(): raise FileNotFoundError(f'No se encontro: {INPUT}')
 raw=INPUT.read_bytes(); doc=json.loads(raw.decode('utf-8-sig'))
 data=doc.get('data') or {}; hits=data.get('hits') or []; total=data.get('total')
 queries=[]; accepted=[]; rejected=[]; sample_candidates=[]
 qhashes=Counter(); rhashes=Counter()

 for pos,hit in enumerate(hits):
  source=hit.get('_source') or {}; variables,bindings=response(hit)
  # Sample-index candidates are kept separately; never treated as measurements.
  if hit.get('_index')=='samples':
   text=json.dumps(source,ensure_ascii=False)
   if CNT_RE.search(text):
    sample_candidates.append({'search_position':pos,'hit_id':hit.get('_id'),'sample_identifier':source.get('sampleID') or source.get('sampleId') or source.get('id') or '', 'source_keys':'|'.join(sorted(source)),'cnt_terms':'|'.join(sorted(set(m.group(0) for m in CNT_RE.finditer(text))))})
  if not isinstance(bindings,list) or not bindings: continue
  query=normq(source.get('label','')); qh=hbytes(query.encode()); serialized=json.dumps(bindings,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode(); rh=hbytes(serialized)
  qhashes[qh]+=1; rhashes[rh]+=1
  electrical=[v for v in variables if v in PROPERTY_FIELDS]
  queries.append({'search_position':pos,'hit_id':hit.get('_id'),'source_date':source.get('date'),'variables':'|'.join(map(str,variables)),'binding_count':len(bindings),'electrical_variables':'|'.join(electrical),'query_sha256':qh,'response_sha256':rh,'is_electrical_query':bool(electrical)})
  if not electrical: continue
  for bpos,b in enumerate(bindings):
   if not isinstance(b,dict): continue
   filler=val(b,['Filler','filler']); matrix=val(b,['Matrix','matrix']); sample_uri=val(b,['Sample','sample'])
   pf,pname,praw=property_info(b); cf,cbasis,craw=composition_info(b); unit=val(b,UNIT_FIELDS)
   base={'sample_id':sid(sample_uri),'sample_uri':sample_uri,'matrix_original':matrix,'filler_original':filler,'cnt_subtype':subtype(filler) if CNT_RE.search(filler) else '', 'property_field':pf,'property_name':pname,'property_value_original':praw,'property_value_numeric':fnum(praw),'property_unit_original':unit,'composition_field':cf,'composition_basis':cbasis,'composition_value_original':craw,'composition_value_numeric':fnum(craw),'source_hit_id':hit.get('_id'),'source_date':source.get('date'),'query_sha256':qh,'response_sha256':rh,'binding_position':bpos}
   if not CNT_RE.search(filler):
    base['rejection_reason']='filler_not_cnt'; rejected.append(base); continue
   if not pf:
    base['rejection_reason']='electrical_property_missing_in_binding'; rejected.append(base); continue
   accepted.append(base)

 # Dedup scientific observations across repeated historical queries.
 key_fields=['sample_uri','matrix_original','filler_original','property_name','property_value_original','property_unit_original','composition_basis','composition_value_original']
 unique={}; occurrences=defaultdict(list)
 for row in accepted:
  key=tuple(row.get(k,'') for k in key_fields)
  if key not in unique: unique[key]=row.copy()
  occurrences[key].append({'hit_id':row['source_hit_id'],'date':row['source_date'],'query_sha256':row['query_sha256'],'response_sha256':row['response_sha256'],'binding_position':row['binding_position']})
 rows=[]
 for key,row in unique.items():
  row['source_occurrence_count']=len(occurrences[key]); row['source_occurrences']=json.dumps(occurrences[key],ensure_ascii=False); rows.append(row)
 rows.sort(key=lambda r:(r['matrix_original'],r['filler_original'],r['composition_value_numeric'] if r['composition_value_numeric'] is not None else float('inf'),r['sample_id'],r['property_value_numeric'] if r['property_value_numeric'] is not None else float('inf')))

 # Series summary by matrix/filler/property/composition basis/unit.
 groups=defaultdict(list)
 for row in rows:
  key=(row['matrix_original'],row['filler_original'],row['cnt_subtype'],row['property_name'],row['composition_basis'],row['property_unit_original'])
  groups[key].append(row)
 series=[]
 for i,(key,items) in enumerate(sorted(groups.items()),1):
  matrix,filler,st,prop,basis,unit=key
  samples=sorted({x['sample_id'] for x in items if x['sample_id']}); levels=sorted({x['composition_value_numeric'] for x in items if x['composition_value_numeric'] is not None})
  series.append({'series_id':f'cnt-series-{i:03d}','matrix_original':matrix,'filler_original':filler,'cnt_subtype':st,'property_name':prop,'composition_basis':basis,'property_unit_original':unit,'sample_count':len(samples),'measurement_count':len(items),'composition_level_count':len(levels),'composition_levels':'|'.join(map(str,levels)),'unit_present':bool(unit),'candidate_minimum_5_levels':len(levels)>=5,'candidate_status':'candidate_for_review' if len(levels)>=5 and bool(unit) else 'insufficient_or_unit_missing'})

 write(BINDINGS,rows,['sample_id','sample_uri','matrix_original','filler_original','cnt_subtype','property_name','property_value_original','property_value_numeric','property_unit_original','composition_basis','composition_value_original','composition_value_numeric','source_occurrence_count','source_hit_id','source_date','query_sha256','response_sha256','source_occurrences'])
 write(SERIES,series,['series_id','matrix_original','filler_original','cnt_subtype','property_name','composition_basis','property_unit_original','sample_count','measurement_count','composition_level_count','composition_levels','unit_present','candidate_minimum_5_levels','candidate_status'])
 write(QUERIES,queries,['search_position','hit_id','source_date','variables','binding_count','electrical_variables','is_electrical_query','query_sha256','response_sha256'])
 write(REJECTED,rejected,['sample_id','matrix_original','filler_original','property_name','property_value_original','property_unit_original','composition_basis','composition_value_original','rejection_reason','source_hit_id','source_date'])
 write(CANDIDATES,sample_candidates,['search_position','hit_id','sample_identifier','cnt_terms','source_keys'])

 electrical_queries=[q for q in queries if q['is_electrical_query']]
 counts={'search_hits_downloaded':len(hits),'search_total_declared':total,'sparql_hits_with_bindings':len(queries),'electrical_sparql_hits':len(electrical_queries),'raw_cnt_electrical_bindings':len(accepted),'unique_cnt_electrical_bindings':len(rows),'duplicates_removed':len(accepted)-len(rows),'rejected_non_cnt_or_missing_property':len(rejected),'cnt_sample_hit_candidates':len(sample_candidates),'series_groups':len(series),'series_with_5_levels_and_unit':sum(s['candidate_status']=='candidate_for_review' for s in series),'unique_query_hashes':len(qhashes),'unique_response_hashes':len(rhashes)}
 detail={'generated_at':NOW,'input_file':str(INPUT),'input_sha256':hbytes(raw),'counts':counts,'cnt_filter_rule':'CNT terminology must occur in the Filler binding value; search-hit text alone is insufficient.','deduplication_key':key_fields,'series':series,'notes':['Non-electrical SPARQL results were excluded.','Electrical bindings whose filler was not CNT were rejected, including the l172 Fe3O4@BaTiO3 series.','Units were not inferred and resistivity was not converted to conductivity.','Sample-index keyword candidates are metadata only, not measurements.']}
 DETAIL.write_text(json.dumps(detail,indent=2,ensure_ascii=False),encoding='utf-8')

 lines=['FASE 2 - EXTRACCION ESPECIFICA CNT ELECTRICA','',f'Fecha: {NOW}',f'Entrada: {INPUT}',f'SHA256: {hbytes(raw)}','']+[f'{k}: {v}' for k,v in counts.items()]+['','SERIES CANDIDATAS']
 if series:
  for s in series: lines += ['',f"{s['series_id']} | {s['matrix_original']} | {s['filler_original']}",f"Propiedad: {s['property_name']} | Unidad: {s['property_unit_original'] or '[AUSENTE]'}",f"Base: {s['composition_basis'] or '[AUSENTE]'} | Niveles: {s['composition_level_count']} | Muestras: {s['sample_count']} | Mediciones: {s['measurement_count']}",f"Estado: {s['candidate_status']}"]
 else: lines += ['- Ninguna serie electrica CNT encontrada en bindings SPARQL.']
 lines += ['','INTERPRETACION','- La coincidencia CNT se exige en el valor Filler de cada binding.','- Los 235 bindings de l172 se excluyen si el relleno no es CNT.','- Cero series es un resultado negativo reproducible, no un error.','- No se asumieron unidades ni se convirtio resistividad.','- No se ejecutaron modelos.','',f'Bindings: {BINDINGS}',f'Series: {SERIES}',f'Consultas: {QUERIES}',f'Rechazados: {REJECTED}',f'Candidatos de muestras: {CANDIDATES}',f'JSON: {DETAIL}']
 LOG.write_text('\n'.join(lines)+'\n',encoding='utf-8')

 print('EXTRACCION COMPLETADA')
 for k,v in counts.items(): print(f'{k}: {v}')
 print(f'Log: {LOG}')

if __name__=='__main__':
 try: main()
 except Exception as e:
  ERROR.write_text(f'{type(e).__name__}: {e}\n',encoding='utf-8'); print(f'ERROR: {type(e).__name__}: {e}'); print(f'Log de error: {ERROR}'); sys.exit(1)
