"""Allowlisted source export. Run with --source /path/to/private/balatro-lab.

Results are deliberately separate: review them before copying into results/.
No game source, player data, raw seeds, database or arbitrary JSON is copied.
"""
import argparse
import hashlib
import json
from pathlib import Path

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    root = Path(__file__).resolve().parents[1]
    target = root / 'outputs/balatro-lab'
    files = []
    for folder in ('cli', 'headless', 'experiments'):
        files.extend((source / folder).glob('*.py'))
    files = [f for f in files if f.name not in ('test_route_v1.py', 'check_all.py')]
    files.extend((source / 'headless/kernel').glob('*.py'))
    files.append(source / 'scripts/lua_bridge.py')
    for folder in (source / 'experiments/policies').iterdir():
        if folder.is_dir() and (folder.name == 'route_v2' or folder.name.startswith('formal_public_route_v2_')):
            files.extend(folder.glob('*.py'))
            files.extend(folder.glob('joker_specs.json'))
    manifest = []
    for path in sorted(files):
        rel = path.relative_to(source)
        content = path.read_bytes()
        exported = content
        transform = None
        if path.name == 'joker_specs.json' and not path.parent.name.startswith('formal_public_'):
            spec = json.loads(content)
            spec = {k: {field: v[field] for field in ('blueprint_compat', 'rarity', 'config') if field in v} for k, v in spec.items()}
            exported = (json.dumps(spec, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            transform = 'retain factual mechanics only; remove localized names/descriptions'
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(exported)
        manifest.append({'path': rel.as_posix(), 'source_sha256': digest(content), 'export_sha256': digest(exported), 'transformation': transform})
    (root / 'export-manifest.json').write_text(json.dumps({'files': manifest, 'excluded': ['game source/assets/binaries', 'backend patches', 'saves', 'raw seeds', 'registry databases', 'raw results', 'third-party code']}, indent=2) + '\n', encoding='utf-8')
    print(f'Exported {len(manifest)} allowlisted files')

if __name__ == '__main__':
    main()
