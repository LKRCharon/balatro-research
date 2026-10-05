"""Verify published candidate bytes against the preregistered source hashes."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument('--protocol', type=Path, default=root / 'results/formal-validation-001/protocol.json')
    parser.add_argument('--source', type=Path, default=root / 'outputs/balatro-lab/experiments/policies/formal_public_route_v2_bfec46182700')
    args = parser.parse_args()
    hashes = json.loads(args.protocol.read_text(encoding='utf-8'))['source_files']
    actual = {p.relative_to(args.source).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in args.source.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    differences = sorted(name for name in hashes.keys() | actual.keys() if hashes.get(name) != actual.get(name))
    if differences:
        raise SystemExit('Frozen candidate mismatch: ' + ', '.join(differences))
    print(f'Verified {len(hashes)} frozen source files; private engine is outside this check.')


if __name__ == '__main__':
    main()
