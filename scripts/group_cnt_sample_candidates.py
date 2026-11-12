from pathlib import Path
from datetime import datetime
from collections import defaultdict
import csv, hashlib, json, re, sys

ROOT=Path.cwd()
INPUT=ROOT/'data_raw'/'explorer'/'cnt-electrical-conductivity-search-response.json'
OUT=ROOT/'data_interim'/'cnt'; META=ROOT/'metadata'; LOGS=ROOT/'logs'
for d in (OUT,META,LOGS): d.mkdir(parents=True,exist_ok=True)
SAMPLES_OUT=OUT/'cnt-sample-candidates-enriched.csv'
GROUPS_OUT=OUT/'cnt-sample-groups.csv'
ARTICLES_OUT=META/'cnt-article-candidates.csv'
CHARTS_OUT=META/'cnt-chart-candidates.csv'
JSON_OUT=META/'cnt-sample-grouping.json'
LOG_OUT=LOGS/'cnt-sample-grouping.log'; ERROR_OUT=LOGS/'cnt-sample-grouping-error.log'
NOW=datetime.now().astimezone().isoformat(timespec='seconds')
CNT_RE=re.compile(r'(?i)(multi[- ]?walled carbon nanotubes?|single[- ]?walled carbon nanotubes?|double[- ]?walled carbon nanotubes?|carbon nanotubes?|\bmwcnts?\b|\bswcnts?\b|\bdwcnts?\b|\bcnts?\b)')
SAMPLE_RE=re.compile(r'/sample/([^/]+)$',re.I)
STUDY_RE=re.compile(r'^(.*?)-s(\d+)-([^-]+)-(\d{4})$',re.I)
DOI_RE=re.compile(r'10\.\d{4,9}/[-._;()/:A-Z0-9]+',re.I)


def subtype(text):
 low=text.lower()
 if re.search(r'\bmwcnt|multi[- ]?walled',low): return 'MWCNT'
 if re.search(r'\bswcnt|single[- ]?walled',low): return 'SWCNT'
 if re.search(r'\bdwcnt|double[- ]?walled',low): return 'DWCNT'
 return 'CNT_unspecified'
def clean(s): return re.sub(r'\s+',' ',str(s or '')).strip()
def splitter(label):
 # Search labels usually follow "filler in matrix". Preserve original if ambiguous.
 parts=re.split(r'\s+in\s+',label,flags=re.I,maxsplit=1)
 return (clean(parts[0]),clean(parts[1])) if len(parts)==2 else (clean(label),'')
def normalize(s): return clean(s).lower()
def sample_parts(identifier):
 sid=SAMPLE_RE.search(identifier)
 sid=sid.group(1) if sid else identifier.rstrip('/').rsplit('/',1)[-1]
 m=STUDY_RE.match(sid)
 if not m: return sid,'',None,'',''
 prefix,num,author,year=m.groups(); return sid,f'{prefix}-{author}-{year}',int(num),author,year
def write(path,rows,preferred):
 cols=list(preferred)
 for k in sorted({k for r in rows for k in r}):
  if k not in cols: cols.append(k)
 with path.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=cols,extrasaction='ignore');w.writeheader();w.writerows(rows)


def main():
 print('AGRUPANDO CANDIDATOS DE MUESTRAS CNT')
 if not INPUT.is_file(): raise FileNotFoundError(f'No se encontro: {INPUT}')
 raw=INPUT.read_bytes();doc=json.loads(raw.decode('utf-8-sig'));hits=(doc.get('data') or {}).get('hits') or []
 samples=[]; articles=[]; charts=[]
 for pos,h in enumerate(hits):
  src=h.get('_source') or {}; text=json.dumps(src,ensure_ascii=False); idx=h.get('_index')
  if not CNT_RE.search(text): continue
  if idx=='samples':
   identifier=clean(src.get('identifier'));label=clean(src.get('label'));filler,matrix=splitter(label);sid,study,num,author,year=sample_parts(identifier)
   samples.append({'search_position':pos,'hit_id':h.get('_id'),'sample_id':sid,'sample_uri':identifier,'study_code_inferred':study,'sample_number_inferred':num if num is not None else '', 'author_token_inferred':author,'year_inferred':year,'label_original':label,'filler_label_inferred':filler,'matrix_label_inferred':matrix,'cnt_subtype':subtype(filler),'thumbnail':clean(src.get('thumbnail')),'doi':'','doi_status':'not_present_in_sample_hit','inference_note':'filler/matrix split from label pattern X in Y; study code parsed from sample identifier'})
  elif idx=='articles':
   title=clean(src.get('title') or src.get('label') or src.get('name')); dois=sorted(set(DOI_RE.findall(text)))
   articles.append({'search_position':pos,'hit_id':h.get('_id'),'title':title,'doi_values':'|'.join(dois),'source_keys':'|'.join(sorted(src)),'cnt_terms':'|'.join(sorted(set(m.group(0) for m in CNT_RE.finditer(text))))})
  elif idx=='charts':
   title=clean(src.get('title') or src.get('label') or src.get('name'));dois=sorted(set(DOI_RE.findall(text)))
   charts.append({'search_position':pos,'hit_id':h.get('_id'),'title':title,'doi_values':'|'.join(dois),'source_keys':'|'.join(sorted(src)),'cnt_terms':'|'.join(sorted(set(m.group(0) for m in CNT_RE.finditer(text))))})

 groups=defaultdict(list)
 for r in samples:
  key=(r['study_code_inferred'],normalize(r['filler_label_inferred']),normalize(r['matrix_label_inferred']),r['cnt_subtype'])
  groups[key].append(r)
 summary=[]
 for i,(key,items) in enumerate(sorted(groups.items()),1):
  study,fill_norm,matrix_norm,st=key; nums=sorted({x['sample_number_inferred'] for x in items if x['sample_number_inferred']!=''}); ids=sorted({x['sample_id'] for x in items})
  summary.append({'group_id':f'cnt-group-{i:03d}','study_code_inferred':study,'filler_label_normalized':fill_norm,'matrix_label_normalized':matrix_norm,'cnt_subtype':st,'sample_count':len(ids),'sample_numbers':'|'.join(map(str,nums)),'sample_ids':'|'.join(ids),'doi':'','doi_status':'not_available_in_sample_hits','composition_levels_status':'not_available_in_sample_hits','electrical_property_status':'not_available_in_sample_hits','candidate_priority':'high' if len(ids)>=5 else ('medium' if len(ids)>=3 else 'low'),'next_action':'search exact study_code or representative sample_id in MM Explorer'})

 write(SAMPLES_OUT,samples,['search_position','hit_id','sample_id','sample_uri','study_code_inferred','sample_number_inferred','author_token_inferred','year_inferred','label_original','filler_label_inferred','matrix_label_inferred','cnt_subtype','doi','doi_status','thumbnail','inference_note'])
 write(GROUPS_OUT,summary,['group_id','study_code_inferred','filler_label_normalized','matrix_label_normalized','cnt_subtype','sample_count','sample_numbers','sample_ids','doi','doi_status','composition_levels_status','electrical_property_status','candidate_priority','next_action'])
 write(ARTICLES_OUT,articles,['search_position','hit_id','title','doi_values','cnt_terms','source_keys'])
 write(CHARTS_OUT,charts,['search_position','hit_id','title','doi_values','cnt_terms','source_keys'])
 high=[g for g in summary if g['candidate_priority']=='high']
 payload={'generated_at':NOW,'input_file':str(INPUT),'input_sha256':hashlib.sha256(raw).hexdigest(),'counts':{'search_hits':len(hits),'cnt_sample_candidates':len(samples),'unique_sample_ids':len({x['sample_id'] for x in samples}),'groups':len(summary),'high_priority_groups_5plus_samples':len(high),'article_candidates':len(articles),'chart_candidates':len(charts)},'important_limitations':['Matrix and filler are inferred only by splitting the sample label at " in ".','Study code, author token, year, and sample number are inferred from identifier syntax.','No DOI, composition, or electrical property is assigned from a sample hit unless explicitly present.','Groups are discovery candidates, not validated electrical series.'],'high_priority_groups':high}
 JSON_OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
 lines=['FASE 2 - AGRUPACION DE CANDIDATOS CNT','',f'Fecha: {NOW}',f'Entrada: {INPUT}',f'SHA256: {payload["input_sha256"]}','']+[f'{k}: {v}' for k,v in payload['counts'].items()]+['','GRUPOS DE ALTA PRIORIDAD (>=5 MUESTRAS)']
 if high:
  for g in sorted(high,key=lambda x:(-x['sample_count'],x['study_code_inferred'])):
   lines += ['',f"{g['group_id']} | {g['study_code_inferred']} | {g['cnt_subtype']}",f"Relleno inferido: {g['filler_label_normalized']}",f"Matriz inferida: {g['matrix_label_normalized']}",f"Muestras: {g['sample_count']} | Numeros: {g['sample_numbers']}",f"DOI: {g['doi_status']} | Composicion: {g['composition_levels_status']} | Propiedad electrica: {g['electrical_property_status']}"]
 else: lines.append('- Ninguno')
 lines += ['','ADVERTENCIAS','- La agrupacion usa metadatos de hits de muestras, no mediciones.','- Filler y matriz son inferidos desde la etiqueta X in Y.','- No se asignaron DOI, composiciones, unidades ni propiedades electricas.','- Los grupos de alta prioridad deben buscarse individualmente en MM Explorer.','',f'Muestras enriquecidas: {SAMPLES_OUT}',f'Grupos: {GROUPS_OUT}',f'Articulos candidatos: {ARTICLES_OUT}',f'Graficos candidatos: {CHARTS_OUT}',f'JSON: {JSON_OUT}']
 LOG_OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print('AGRUPACION COMPLETADA')
 for k,v in payload['counts'].items(): print(f'{k}: {v}')
 print(f'Log: {LOG_OUT}')

if __name__=='__main__':
 try: main()
 except Exception as e:
  ERROR_OUT.write_text(f'{type(e).__name__}: {e}\n',encoding='utf-8');print(f'ERROR: {type(e).__name__}: {e}');print(f'Log de error: {ERROR_OUT}');sys.exit(1)
