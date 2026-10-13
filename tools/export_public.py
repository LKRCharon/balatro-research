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
    parser.add_argument('--candidates', type=Path, help='Explicit work candidate directory; only explicitly allowlisted completed combat/growth modules')
    parser.add_argument('--extra-candidate', action='append', default=[], choices=['combat_candidate_v9.py', 'combat_candidate_v10.py', 'growth_candidate_v10.py', 'growth_candidate_v11.py', 'round_capacity.py', 'round_capacity_v2.py', 'combat_candidate_v11.py', 'combat_candidate_v12.py', 'growth_candidate_v13.py', 'plain_combat.py'], help='Opt-in only after the corresponding iteration is complete and audited; never exports active candidates by default')
    args = parser.parse_args()
    if args.extra_candidate and not args.candidates:
        parser.error('--extra-candidate requires --candidates')
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
        if folder.is_dir() and (folder.name in ('route_v2', 'route_v3', 'route_v4') or folder.name.startswith('formal_public_route_v2_')):
            files.extend(folder.glob('*.py'))
            files.extend(folder.glob('joker_specs.json'))
    manifest = []
    for path in sorted(files):
        rel = path.relative_to(source)
        content = path.read_bytes()
        exported = content
        transform = None
        if path.name == 'joker_specs.json' and path.parent.name == 'route_v2':
            spec = json.loads(content)
            spec = {k: {field: v[field] for field in ('blueprint_compat', 'rarity', 'config') if field in v} for k, v in spec.items()}
            exported = (json.dumps(spec, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
            transform = 'retain factual mechanics only; remove localized names/descriptions'
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(exported)
        manifest.append({'path': rel.as_posix(), 'source_sha256': digest(content), 'export_sha256': digest(exported), 'transformation': transform})
    if args.candidates:
        allowed = {'combat_candidate_v4.py': 'headless', 'combat_candidate_v5.py': 'headless', 'growth_candidate_v6.py': 'experiments', 'growth_candidate_v7.py': 'experiments', 'combat_candidate_v6.py': 'headless', 'growth_candidate_v8.py': 'experiments'}
        for name in args.extra_candidate:
            allowed[name] = 'experiments' if name.startswith('growth_') else 'headless'
        for name, folder in allowed.items():
            content = (args.candidates / name).read_bytes()
            rel = Path(folder) / name
            (target / rel).write_bytes(content)
            manifest.append({'path': rel.as_posix(), 'source_sha256': digest(content), 'export_sha256': digest(content), 'transformation': None, 'source_kind': 'explicit_completed_work_candidate'})
    (root / 'export-manifest.json').write_text(json.dumps({'files': manifest, 'excluded': ['game source/assets/binaries', 'backend patches', 'saves', 'raw seeds', 'registry databases', 'raw results', 'third-party code']}, indent=2) + '\n', encoding='utf-8')
    print(f'Exported {len(manifest)} allowlisted files')

if __name__ == '__main__':
    main()
