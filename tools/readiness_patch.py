"""Install original readiness barrier only into a newly staged private instance."""
import argparse
import hashlib
import json
from pathlib import Path


def install(manifest, version=3):
    if version not in (2, 3):raise ValueError('Unknown readiness version')
    path = Path(manifest).resolve()
    m = json.loads(path.read_text(encoding='utf-8'))
    root = path.parent
    checkout = root / 'checkout'
    if Path(m['root']).resolve() != root or Path(m['checkout']).resolve() != checkout:
        raise ValueError('Invalid isolated manifest paths')
    if not m['identity'].startswith('Balatro-Lab-Headless-'):
        raise ValueError('Not an isolated save identity')
    if (root/'launch.lock').exists() or (root/'launcher.json').exists() or (checkout/'dist').exists():
        raise ValueError('Only a never-launched staging instance can be patched')
    if m.get('readiness_patch'):
        raise ValueError('Already patched')
    main = checkout/'mods/lab_cli/main.lua'
    relative = 'mods/lab_cli/main.lua'
    before = hashlib.sha256(main.read_bytes()).hexdigest()
    if before != m['input_hashes'].get(relative):
        raise ValueError('Staged main.lua differs from manifest')
    helper_name = f'readiness_v{version}.lua'
    helper = Path(__file__).with_name(helper_name).read_bytes()
    target = main.with_name(helper_name)
    if target.exists():
        raise ValueError('Unexpected existing helper')
    target.write_bytes(helper)
    with main.open('ab') as out:
        out.write(f"\nassert(SMODS.load_file('{helper_name}'))()\n".encode())
    m['readiness_patch'] = {'version':version,'original_main_sha256':before,
        'main_sha256':hashlib.sha256(main.read_bytes()).hexdigest(),
        'helper_sha256':hashlib.sha256(helper).hexdigest()}
    m['input_hashes'][relative] = m['readiness_patch']['main_sha256']
    m['input_hashes']['mods/lab_cli/'+helper_name] = m['readiness_patch']['helper_sha256']
    path.write_text(json.dumps(m,indent=2),encoding='utf-8')
    return m['readiness_patch']

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest')
    p.add_argument('--version',type=int,choices=(2,3),default=3)
    args=p.parse_args()
    print(json.dumps(install(args.manifest,args.version),indent=2))
