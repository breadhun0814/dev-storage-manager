"""Check the local package manifest and Windows GUI subsystem without launching it."""
import hashlib
import json
from pathlib import Path
import tomllib


def main():
    root = Path(__file__).resolve().parents[1]
    version = tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    bundle = root/'outputs'/f'DevStorageManager-{version}-preview'
    manifest = json.loads((bundle/'SHA256.json').read_text(encoding='utf-8'))
    for relative, expected in manifest.items():
        path = bundle/relative
        if not path.resolve().is_relative_to(bundle.resolve()):
            raise RuntimeError('Manifest path leaves package boundary')
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Package content mismatch: {relative}')
    binary = (bundle/'DevStorageManager.exe').read_bytes()
    pe = int.from_bytes(binary[60:64], 'little')
    if binary[pe:pe+4] != b'PE\0\0':
        raise RuntimeError('Invalid Windows executable')
    subsystem = int.from_bytes(binary[pe+24+68:pe+24+70], 'little')
    if subsystem != 2:
        raise RuntimeError('The executable is not a Windows GUI application')
    print(json.dumps({'version':version, 'verified_files':len(manifest), 'gui_subsystem':subsystem}))


if __name__ == '__main__':
    main()
