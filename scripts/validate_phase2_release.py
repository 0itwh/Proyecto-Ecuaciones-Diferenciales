from pathlib import Path
import csv
import hashlib
import json
import sys
import zipfile

BASE = Path('archive/phase2-corpus-release-v1')
ZIP_FILE = Path('archive/phase2-corpus-release-v1.zip')
INVENTORY = BASE / 'sha256-inventory.csv'
MANIFEST = Path('metadata/phase2-corpus-manifest.json')


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    failures = []

    print('VALIDACION DEL CIERRE DE FASE 2')
    print()

    # 1. Inventario SHA-256
    if not INVENTORY.is_file():
        failures.append(f'No existe el inventario: {INVENTORY}')
    else:
        with INVENTORY.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))

        bad_hashes = []
        missing_files = []
        for row in rows:
            path = BASE / row['relative_path']
            if not path.is_file():
                missing_files.append(row['relative_path'])
            elif sha256(path) != row['sha256']:
                bad_hashes.append(row['relative_path'])

        print(f'Archivos inventariados: {len(rows)}')
        print(f'Archivos ausentes: {len(missing_files)}')
        print(f'Hashes incorrectos: {len(bad_hashes)}')
        failures.extend(f'Archivo ausente: {item}' for item in missing_files)
        failures.extend(f'Hash incorrecto: {item}' for item in bad_hashes)

    # 2. Integridad del ZIP
    if not ZIP_FILE.is_file():
        failures.append(f'No existe el ZIP: {ZIP_FILE}')
    else:
        try:
            with zipfile.ZipFile(ZIP_FILE, 'r') as archive:
                bad_member = archive.testzip()
                members = len(archive.namelist())
            print(f'Miembros del ZIP: {members}')
            print(f'Integridad del ZIP: {"CORRECTA" if bad_member is None else "FALLO"}')
            print(f'SHA256 del ZIP: {sha256(ZIP_FILE)}')
            if bad_member is not None:
                failures.append(f'Miembro corrupto del ZIP: {bad_member}')
        except zipfile.BadZipFile:
            failures.append(f'ZIP no valido: {ZIP_FILE}')

    # 3. Cierre formal del manifiesto
    if not MANIFEST.is_file():
        failures.append(f'No existe el manifiesto: {MANIFEST}')
    else:
        data = json.loads(MANIFEST.read_text(encoding='utf-8-sig'))
        print(f"Release: {data.get('release_id', '')}")
        print(f"Fase: {data.get('phase', '')}")
        print(f"Estado: {data.get('phase_status', '')}")
        print(f"Entrada a Fase 3: {data.get('phase3_entry_decision', '')}")
        if data.get('phase_status') != 'closed':
            failures.append('El manifiesto no tiene phase_status=closed')

    print()
    if failures:
        print('VALIDACION FALLIDA')
        for item in failures:
            print(f'- {item}')
        return 1

    print('INVENTARIO VALIDADO')
    print('PAQUETE VALIDADO')
    print('FASE 2 CERRADA')
    return 0


if __name__ == '__main__':
    sys.exit(main())
