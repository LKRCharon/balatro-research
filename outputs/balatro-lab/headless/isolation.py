"""Private source/build/save boundaries for Windows CLI engine instances.

No running training checkout is modified. Staging copies source and dependencies;
each instance builds only in its own checkout. This remains the reference engine,
not a reimplementation of Balatro. Use stop() rather than killing all love.exe.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import urllib.request
import uuid

INPUT_DIRS = ('game', 'assets', 'vendor', 'scripts', 'mods', 'native', 'docs')
EXCLUDED = {'.git', '__pycache__', '.pytest_cache', 'node_modules'}


def stage(source, root, name, port):
    source, root = Path(source).resolve(), Path(root).resolve()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', name):
        raise ValueError('Instance name must be lowercase letters/digits/hyphens')
    if not 1024 <= port <= 65535 or port == 12346:
        raise ValueError('Use an unprivileged private port other than live training port 12346')
    if root == source or source in root.parents:
        raise ValueError('Instance root must not be inside the source checkout')
    for required in ('windows.just', 'justfile', 'scripts/run_agent.py', 'mods/lab_cli/main.lua'):
        if not (source / required).is_file():
            raise ValueError('Missing source prerequisite: ' + required)
    root.mkdir(parents=True, exist_ok=True)
    for existing in root.glob('*/instance.json'):
        if json.loads(existing.read_text(encoding='utf-8')).get('port') == port:
            raise ValueError('Port already allocated to an instance in this root')
    # Exclusive ownership: never overwrite or reuse an existing instance/save.
    target = root / name
    target.mkdir(exist_ok=False)
    checkout = target / 'checkout'
    checkout.mkdir()
    hashes = {}
    for directory in INPUT_DIRS:
        src = source / directory
        if not src.exists():
            continue
        for file in sorted(src.rglob('*')):
            if any(part in EXCLUDED for part in file.relative_to(source).parts):
                continue
            if file.is_symlink():
                raise ValueError('Symlinks are not allowed in staged inputs: ' + str(file))
            if not file.is_file():
                continue
            relative = file.relative_to(source)
            dest = checkout / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file, dest)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            if digest != hashlib.sha256(file.read_bytes()).hexdigest():
                raise RuntimeError('Source changed while staging: ' + str(relative))
            hashes[relative.as_posix()] = digest
    for file in sorted(source.glob('*.just')) + [source / 'justfile']:
        shutil.copy2(file, checkout / file.name)
        hashes[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    for directory in ('logs', 'results'):
        (target / directory).mkdir()
    identity = 'Balatro-Lab-Headless-' + name + '-' + uuid.uuid4().hex[:12]
    version = (checkout / 'game/version.jkr').read_text(encoding='utf-8').splitlines()[0].removesuffix('-FULL')
    manifest = {'schema': 1, 'name': name, 'port': port, 'identity': identity,
                'root': str(target), 'checkout': str(checkout), 'source': str(source),
                'build_version': version + '+isolated',
                'input_hashes': hashes, 'reference_engine': True,
                'save_location': '%APPDATA%/' + identity,
                'mode': {'headless': True, 'audio': False, 'fast': False}}
    (target / 'instance.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def load(path):
    path = Path(path).resolve()
    m = json.loads(path.read_text(encoding='utf-8'))
    if Path(m['root']).resolve() != path.parent or Path(m['checkout']).resolve() != path.parent / 'checkout':
        raise ValueError('Manifest path does not match its owned checkout')
    if not m['identity'].startswith('Balatro-Lab-Headless-') or any(x in m['identity'] for x in '/\\:'):
        raise ValueError('Invalid save identity')
    if m['port'] == 12346 or not 1024 <= m['port'] <= 65535:
        raise ValueError('Invalid isolated port')
    return m


def environment(m, base=None):
    env = dict(os.environ if base is None else base)
    # Do not inherit replay switches or rendering/audio overrides from another job.
    for key in list(env):
        if key.startswith('BALATROBOT_') or key.startswith('BALATRO_SAVE_'):
            env.pop(key)
    env.update(BALATROBOT_PORT=str(m['port']), BALATROBOT_ENABLE='1',
               BALATROBOT_HEADLESS='1', BALATROBOT_AUDIO='0', BALATROBOT_FAST='0',
               BALATROBOT_RECORD='off', BALATROBOT_RENDER_ON_API='0', BALATRO_CLI='1',
               BALATRO_SAVE_IDENTITY=m['identity'], PYTHONIOENCODING='utf-8',
               PYTHONUNBUFFERED='1', PROJECT_BUILD_VERSION=m['build_version'])
    return env


def rpc(m, method):
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': {}}).encode()
    request = urllib.request.Request('http://127.0.0.1:%d' % m['port'], data=body,
                                     headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=10) as response:
        result = json.load(response)
    if 'error' in result:
        raise RuntimeError(result['error'])
    return result['result']


def verify(m):
    info = rpc(m, 'lab_info')
    if info.get('identity') != m['identity']:
        raise RuntimeError('Port belongs to a different engine; refusing action')
    if (not info.get('headless') or info.get('graphics_active') is not False
            or info.get('audio') or info.get('master_volume') != 0):
        raise RuntimeError('Engine did not confirm silent headless mode')
    if not str(info.get('desktop', '')).startswith('BalatroLab-'):
        raise RuntimeError('Engine is not on a verified private desktop')
    save = str(info.get('save_directory', '')).replace('\\', '/').rstrip('/')
    if save.rsplit('/', 1)[-1] != m['identity']:
        raise RuntimeError('Save boundary mismatch')
    return info


def stop(m):
    verify(m)
    return rpc(m, 'lab_stop')


def launch(m, just, python=None):
    if sys.platform != 'win32':
        raise RuntimeError('Private desktop launch requires Windows')
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1', m['port'])) == 0:
            raise RuntimeError('Private port is already occupied')
    root = Path(m['root'])
    # Lock is exclusive and intentionally retained after interrupted launch.
    lock = root / 'launch.lock'
    with lock.open('x', encoding='utf-8') as f:
        f.write(str(os.getpid()))
    env = environment(m)
    env['PATH'] = os.pathsep.join([str(Path(python or sys.executable).parent),
                                  str(Path(just).resolve().parent), r'C:\Program Files\Git\bin',
                                  env.get('PATH', '')])
    try:
        with (root / 'logs/launcher.log').open('ab') as out:
            process = subprocess.Popen([str(just), 'windows', 'run-cli', m['identity']],
                                       cwd=m['checkout'], env=env, stdout=out,
                                       stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            (root / 'launcher.json').write_text(json.dumps({'pid': process.pid}), encoding='utf-8')
            return process.wait()
    finally:
        # Never blanket-kill engine processes or retry an interrupted action.
        if 'process' not in locals() or process.poll() is not None:
            lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('stage')
    p.add_argument('--source', required=True); p.add_argument('--root', required=True)
    p.add_argument('--name', required=True); p.add_argument('--port', type=int, required=True)
    for command in ('launch', 'verify', 'stop'):
        p = sub.add_parser(command); p.add_argument('manifest')
        if command == 'launch':
            p.add_argument('--just', required=True); p.add_argument('--python')
    args = parser.parse_args()
    if args.command == 'stage':
        result = stage(args.source, args.root, args.name, args.port)
        result = {k: v for k, v in result.items() if k != 'input_hashes'}
    else:
        m = load(args.manifest)
        result = launch(m, args.just, args.python) if args.command == 'launch' else globals()[args.command](m)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
