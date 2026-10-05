"""Isolated development games on registered training seeds only; no win-rate claim."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import closing
import hashlib
import importlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from environment import Environment, terminal
from isolation import load

LAB = Path(__file__).resolve().parents[1]
REGISTRY = LAB.parents[1] / 'work/experiments/registry.sqlite'


def hashes(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}


def training_seed(registry, seed_id):
    with closing(sqlite3.connect(f'file:{Path(registry).resolve().as_posix()}?mode=ro', uri=True)) as db:
        row = db.execute("SELECT seed,commitment FROM seeds WHERE id=? AND partition='train'", (seed_id,)).fetchone()
    if row is None:
        raise ValueError('Only registered training seeds are accepted')
    return row


def append(path, value):
    with path.open('a', encoding='utf8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + '\n')


def run(manifest_path, seed_id, policy_name='route_v3', max_actions=800):
    if policy_name not in ('route_v2', 'route_v3'):
        raise ValueError('Explicit development policy required')
    seed, commitment = training_seed(REGISTRY, seed_id)
    manifest = load(manifest_path)
    source = LAB / 'experiments/policies' / policy_name
    frozen = hashes(source)
    if not frozen:
        raise ValueError('Policy source missing')
    for name, expected in manifest['input_hashes'].items():
        if hashlib.sha256((Path(manifest['checkout']) / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Staged engine fingerprint mismatch')
    output = Path(manifest['root']) / 'train-smoke'
    output.mkdir(exist_ok=False)
    sys.path[:0] = [str(source), str(LAB / 'cli')]
    policy = importlib.import_module('policy')
    advisor = importlib.import_module('advisor')
    memory = importlib.import_module('belief').Belief()
    validate = importlib.import_module('execution').validate
    started = time.monotonic()
    counts = Counter()
    errors = []
    checks = []
    s = {}
    status = 'truncated'
    try:
        with Environment(manifest['port'], manifest['identity'], output, registry=REGISTRY) as env:
            s = env.reset(seed)
            if (s.get('deck'), s.get('stake')) != ('BLUE', 'GOLD'):
                raise ValueError('Wrong game conditions')
            for index in range(max_actions):
                if terminal(s):
                    break
                context = env.context()
                known = {card.get('key') for area in ('jokers', 'shop', 'pack')
                         for card in s.get(area, {}).get('cards', []) if not card.get('state', {}).get('hidden')}
                context['targets']['targets'] = [t for t in context['targets'].get('targets', []) if t.get('key') in known]
                visible = memory.observe(s, context['collection'], context['targets'])
                before_time = time.monotonic()
                chosen = policy.action(visible)
                if not chosen:
                    raise ValueError('Policy returned no action before terminal')
                method, params = chosen
                if method in ('start', 'menu', 'lab_stop', 'skip'):
                    raise ValueError('Disallowed development action')
                validate(s, method, params)
                predicted = advisor.score(visible, params['cards'])[0] if method == 'play' else None
                uncertain = advisor.uncertain(visible) if method == 'play' else None
                append(output / 'decisions.jsonl', {'action': index + 1, 'before': visible,
                       'method': method, 'params': params, 'predicted': predicted,
                       'uncertain': uncertain, 'decision_seconds': time.monotonic() - before_time})
                before = s
                s = env.step(method, params)
                counts[method] += 1
                if method == 'play' and not uncertain:
                    actual = s.get('round', {}).get('last_hand', {}).get('total')
                    if s.get('round', {}).get('chips') == before.get('round', {}).get('chips'):
                        actual = 0
                    if actual is not None:
                        checks.append({'action': index + 1, 'predicted': predicted, 'actual': actual,
                                       'within_one': abs(predicted - actual) <= 1})
                (output / 'progress.json').write_text(json.dumps({'action': index + 1,
                    'ante': s.get('ante_num'), 'phase': s.get('state'), 'seconds': time.monotonic() - started}), encoding='utf8')
            if terminal(s):
                status = 'loss' if s.get('state') == 'GAME_OVER' else 'win' if s.get('ante_num', 0) >= 8 else 'error'
                if status == 'error':
                    errors.append({'type': 'InvalidTerminal', 'message': 'Early win flag'})
    except Exception as exc:
        status = 'error'
        errors.append({'type': type(exc).__name__, 'message': str(exc).replace(seed, '[private seed]')})
    if hashes(source) != frozen:
        status = 'error'
        errors.append({'type': 'IntegrityError', 'message': 'Policy source changed during run'})
    result = {'purpose': 'engineering_train_only', 'strategy_winrate_eligible': False,
              'seed_id': seed_id, 'commitment': commitment, 'policy': policy_name,
              'policy_files': frozen, 'engine_input_hashes': manifest['input_hashes'],
              'status': status, 'terminal': terminal(s), 'ante': s.get('ante_num'),
              'actions': sum(counts.values()), 'counts': dict(counts), 'errors': errors,
              'seconds': time.monotonic() - started, 'prediction_checks': len(checks),
              'prediction_mismatches': [x for x in checks if not x['within_one']]}
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--seed-id', type=int, required=True)
    parser.add_argument('--policy', choices=['route_v2', 'route_v3'], default='route_v3')
    parser.add_argument('--max-actions', type=int, default=800)
    args = parser.parse_args()
    if not 1 <= args.max_actions <= 10000:
        parser.error('max-actions must be 1..10000')
    result = run(args.manifest, args.seed_id, args.policy, args.max_actions)
    print(json.dumps({k: v for k, v in result.items() if k not in ('policy_files', 'engine_input_hashes')}))
    raise SystemExit(1 if result['status'] == 'error' else 0)
