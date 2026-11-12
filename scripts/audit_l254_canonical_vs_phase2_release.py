from pathlib import Path
import csv
import hashlib
import json
import sys

ROOT = Path.cwd()
CANON = ROOT / 'data_processed' / 'l254_corpus'
CANDIDATE = ROOT / 'data_processed' / 'l254_corpus_article_validated'
FROZEN = ROOT / 'archive' / 'phase2-corpus-release-v1' / 'data_processed' / 'l254_corpus'
INVENTORY = ROOT / 'archive' / 'phase2-corpus-release-v1' / 'sha256-inventory.csv'

FILES = [
    'samples.csv', 'sample_composition.csv', 'electrical_measurements.csv',
    'measurement_conditions.csv', 'filler_variants.csv',
    'curve_inclusion_status.csv', 'exclusions.csv'
]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return max(sum(1 for _ in csv.reader(f)) - 1, 0)


def main():
    print('AUDITORIA CANONICO VS RELEASE CONGELADO DE FASE 2')
    print()
    if not FROZEN.is_dir():
        print(f'ERROR: no existe el corpus congelado: {FROZEN}')
        return 1

    differences = []
    for name in FILES:
        c = CANON / name
        f = FROZEN / name
        if not c.is_file() or not f.is_file():
            differences.append((name, 'archivo_ausente', c.is_file(), f.is_file()))
            continue
        same = sha256(c) == sha256(f)
        print(f'{name}: canon={csv_rows(c)} filas | frozen={csv_rows(f)} filas | hash_igual={same}')
        if not same:
            differences.append((name, 'hash_diferente', sha256(c), sha256(f)))

    print()
    print(f'Archivos diferentes: {len(differences)}')
    for item in differences:
        print('-', item[0], item[1])

    # Critical baseline assertions from the validated Phase 2 report.
    comp = CANON / 'sample_composition.csv'
    excl = CANON / 'exclusions.csv'
    if comp.is_file():
        print(f'Composicion canonica actual: {csv_rows(comp)} filas (baseline Fase 2 esperado: 70)')
    if excl.is_file():
        print(f'Exclusiones canonicas actuales: {csv_rows(excl)} filas (baseline Fase 2 esperado: 40)')

    if differences:
        print()
        print('DICTAMEN: EL CORPUS CANONICO DIFIERE DEL RELEASE CONGELADO.')
        print('No promueva el candidato. Restaure primero el canonico desde el release congelado.')
        return 2

    print()
    print('DICTAMEN: EL CORPUS CANONICO COINCIDE CON EL RELEASE CONGELADO.')
    print('El candidato puede evaluarse como una transformacion separada.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
