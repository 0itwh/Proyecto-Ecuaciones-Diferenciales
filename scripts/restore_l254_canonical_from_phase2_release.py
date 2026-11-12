from pathlib import Path
from datetime import datetime
import argparse
import csv
import hashlib
import json
import shutil
import sys
import tempfile

FILES = [
    'studies.csv', 'material_systems.csv', 'filler_variants.csv', 'samples.csv',
    'sample_composition.csv', 'processing_steps.csv',
    'electrical_measurements.csv', 'measurement_conditions.csv',
    'provenance.csv', 'exclusions.csv', 'curve_inclusion_status.csv'
]
EXPECTED_ROWS = {
    'studies.csv': 1,
    'material_systems.csv': 1,
    'filler_variants.csv': 5,
    'samples.csv': 36,
    'sample_composition.csv': 70,
    'processing_steps.csv': 102,
    'electrical_measurements.csv': 29,
    'measurement_conditions.csv': 29,
    'provenance.csv': 632,
    'exclusions.csv': 40,
    'curve_inclusion_status.csv': 5,
}


def parse_args():
    p = argparse.ArgumentParser(description='Restaura l254_corpus desde el release congelado de Fase 2.')
    p.add_argument('--root', default='.')
    p.add_argument('--apply', action='store_true', help='Ejecuta la restauracion. Sin esta opcion solo audita.')
    return p.parse_args()


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return max(sum(1 for _ in csv.reader(stream)) - 1, 0)


def main():
    args = parse_args()
    root = Path(args.root).resolve()
    canonical = root / 'data_processed' / 'l254_corpus'
    frozen = root / 'archive' / 'phase2-corpus-release-v1' / 'data_processed' / 'l254_corpus'
    recovery_root = root / 'archive' / 'recovery'
    stamp = datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%z')
    contaminated_backup = recovery_root / f'l254_corpus_contaminated_{stamp}'
    report_path = recovery_root / f'l254_restore_report_{stamp}.json'

    if not canonical.is_dir():
        raise FileNotFoundError(f'No existe el corpus canonico: {canonical}')
    if not frozen.is_dir():
        raise FileNotFoundError(f'No existe el corpus congelado: {frozen}')

    checks = []
    for name in FILES:
        source = frozen / name
        current = canonical / name
        if not source.is_file():
            raise FileNotFoundError(f'Falta en el release congelado: {source}')
        rows = csv_rows(source)
        expected = EXPECTED_ROWS[name]
        checks.append({
            'file': name,
            'frozen_rows': rows,
            'expected_rows': expected,
            'frozen_rows_ok': rows == expected,
            'canonical_exists': current.is_file(),
            'canonical_sha256': sha256(current) if current.is_file() else '',
            'frozen_sha256': sha256(source),
            'same_before_restore': current.is_file() and sha256(current) == sha256(source),
        })

    failures = [x for x in checks if not x['frozen_rows_ok']]
    print('AUDITORIA DE RESTAURACION L254')
    print(f'Archivos revisados: {len(checks)}')
    print(f'Fallos del release congelado: {len(failures)}')
    print(f'Corpus canonico modificado: NO')
    if failures:
        for item in failures:
            print(f"- {item['file']}: {item['frozen_rows']} filas; esperado {item['expected_rows']}")
        return 1

    if not args.apply:
        print('Modo: DRY-RUN')
        print('El release congelado cumple los conteos esperados.')
        print('Para restaurar use --apply')
        return 0

    recovery_root.mkdir(parents=True, exist_ok=True)
    if contaminated_backup.exists():
        raise FileExistsError(contaminated_backup)
    shutil.copytree(canonical, contaminated_backup)

    temp = Path(tempfile.mkdtemp(prefix='l254_corpus.restore.', dir=canonical.parent))
    try:
        for name in FILES:
            shutil.copy2(frozen / name, temp / name)
        # Copy any additional frozen corpus files without changing the required baseline.
        for source in frozen.iterdir():
            if source.is_file() and not (temp / source.name).exists():
                shutil.copy2(source, temp / source.name)

        post_checks = []
        for name in FILES:
            restored = temp / name
            source = frozen / name
            post_checks.append({
                'file': name,
                'rows': csv_rows(restored),
                'sha256': sha256(restored),
                'matches_frozen': sha256(restored) == sha256(source),
            })
        if not all(x['matches_frozen'] for x in post_checks):
            raise ValueError('La copia temporal no coincide con el release congelado')

        old = canonical.parent / f'l254_corpus.pre_restore_{stamp}'
        canonical.rename(old)
        try:
            temp.rename(canonical)
        except Exception:
            old.rename(canonical)
            raise
        shutil.rmtree(old)

        report = {
            'restored_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'source_release': str(frozen),
            'canonical_path': str(canonical),
            'contaminated_backup': str(contaminated_backup),
            'pre_restore_checks': checks,
            'post_restore_checks': post_checks,
            'status': 'restored_and_verified',
        }
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

    print('RESTAURACION COMPLETADA')
    print(f'Backup del canonico alterado: {contaminated_backup}')
    print(f'Corpus canonico restaurado: {canonical}')
    print(f'Reporte: {report_path}')
    print('Coincidencia con release congelado: SI')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print(f'ERROR: {type(exc).__name__}: {exc}')
        sys.exit(1)
