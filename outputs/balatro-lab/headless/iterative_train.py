"""Versioned full-game TRAIN regression. One start per episode, no action retry."""
import argparse
import importlib
import json
from pathlib import Path
import sys
import time

import hybrid_session as h
import manual_session as manual

SEEDS = (32, 33, 34, 36, 37, 38, 40, 41, 42, 43, 44, 45, 46)


def source_hashes():
    files = manual.source_hashes()
    for folder, pattern in (('headless', 'no_sl_solver*.py'),
                            ('headless', 'iterative_train.py'),
                            ('experiments', 'growth_policy_v*.py'),
                            ('experiments/policies/route_v4', '*.py')):
        files.update({p.relative_to(h.LAB).as_posix(): h.sha(p)
                      for p in (h.LAB / folder).glob(pattern)})
    return files


def prepare(manifest, root, solver, growth, seeds):
    root = Path(root)
    if root.exists():
        raise ValueError('Use a new version directory; completed attempts are immutable')
    if not seeds or len(set(seeds)) != len(seeds) or not set(seeds) <= set(SEEDS):
        raise ValueError('Explicit fixed TRAIN regression seeds required')
    m = manual.verify_engine(manifest)
    protocol = {'schema': 1, 'purpose': 'adaptive_fixed_train_regression',
        'partition': 'train', 'strategy_winrate_eligible': False,
        'solver': solver, 'growth': growth,
        'solver_config': {'samples': 4, 'max_candidates': 10, 'time_budget': 1.0},
        'jobs': [{'seed_id': i, 'seed_commitment': h.training_seed(h.REGISTRY, i)[1]}
                 for i in seeds],
        'source_hashes': source_hashes(), 'engine_input_hashes': m['input_hashes'],
        'engine_manifest_sha256': h.sha(manifest),
        'conditions': {'deck': 'BLUE', 'stake': 'GOLD', 'no_restart_within_episode': True,
                       'no_mutation_retry': True, 'public_information_only': True},
        'limitations': ['Repeated TRAIN seeds with prior knowledge; not independent evaluation.',
                       'Public score and capacity models are approximate.']}
    root.mkdir(parents=True)
    h.atomic(root / 'protocol.json', protocol)
    return protocol


def verify_sources(protocol):
    if source_hashes() != protocol['source_hashes']:
        raise ValueError('Frozen iteration source changed')


def run_episode(manifest, batch, protocol, seed_id):
    verify_sources(protocol)
    root = batch / f'train-{seed_id}'
    if root.exists():
        raise ValueError('Episode already exists; no restart')
    m = manual.verify_engine(manifest, protocol['engine_manifest_sha256'])
    seed, commitment = h.training_seed(h.REGISTRY, seed_id)
    assigned = next(j for j in protocol['jobs'] if j['seed_id'] == seed_id)
    if commitment != assigned['seed_commitment']:
        raise ValueError('Seed commitment mismatch')
    root.mkdir()
    h.atomic(root / 'session.json', {'purpose': protocol['purpose'], 'seed_id': seed_id,
        'seed_commitment': commitment, 'source_hashes': protocol['source_hashes'],
        'manifest_sha256': protocol['engine_manifest_sha256'], 'solver': protocol['solver'],
        'growth': protocol['growth'], 'strategy_winrate_eligible': False})
    policy, advisor, belief, execution = h.modules()
    sys.path.insert(0, str(h.LAB / 'experiments'))
    solver = importlib.import_module(protocol['solver'])
    growth = importlib.import_module(protocol['growth'])
    memory = belief.Belief()
    started = time.monotonic()
    counts = {}; rerolls = 0; actions = 0; state = {}
    try:
        with h.Environment(m['port'], m['identity'], root, registry=h.REGISTRY) as env:
            current = env.observe()
            if current['state'] != 'MENU' and not h.terminal(current):
                raise ValueError('Unfinished episode must not be reset')
            manual.claim_seed(h.REGISTRY, batch / 'protocol.json', seed_id, root)
            env.reset(seed)
            state = env.state
            h.append(root / 'decisions.jsonl', {'sequence': env.sequence, 'method': 'start',
                'origin': 'script', 'seed_commitment': commitment})
            for actions in range(1, 1001):
                if h.terminal(env.state):
                    break
                verify_sources(protocol)
                visible = h.visible(env, memory)
                phase = visible['state']
                decision = None
                if phase == 'SELECTING_HAND':
                    import consumables, phases
                    decision = consumables.held_action(visible) or phases.before(visible)
                    if decision is None:
                        choice = solver.choose(visible, protocol['solver_config'])
                        h.append(root / 'solver.jsonl', dict(choice, transition_id=env.sequence + 1))
                        decision = choice['method'], choice['params']
                elif phase == 'SHOP':
                    import consumables, phases
                    decision = consumables.held_action(visible) or phases.before(visible)
                    if decision is None:
                        decision = growth.action(visible, rerolls_this_shop=rerolls)
                if decision is None:
                    decision = policy.action(visible)
                if not decision:
                    raise ValueError('No action before terminal')
                method, params = decision
                params = dict(params)
                params.setdefault('reason', 'Versioned public-state TRAIN strategy; reobserve after one action.')
                if method in ('start', 'menu', 'lab_stop', 'skip'):
                    raise ValueError('Disallowed policy method')
                if method == 'reroll': rerolls += 1
                if method == 'next_round': rerolls = 0
                h.perform(root, env, memory, execution, advisor, method, params, 'script')
                state = env.state
                counts[method] = counts.get(method, 0) + 1
                h.atomic(root / 'progress.json', {'seed_id': seed_id, 'actions': actions,
                    'ante': state.get('ante_num'), 'phase': state['state'], 'money': state.get('money'),
                    'seconds': time.monotonic() - started})
                if method == 'cash_out':
                    print(json.dumps({'seed_id': seed_id, 'ante': state.get('ante_num'),
                        'money': state.get('money'), 'actions': actions}), flush=True)
            status = 'loss' if state.get('state') == 'GAME_OVER' else 'win' if h.terminal(state) else 'truncated'
    except Exception as exc:
        result = {'seed_id': seed_id, 'status': 'error', 'terminal': h.terminal(state),
                  'error_type': type(exc).__name__, 'error': str(exc).replace(seed, '[private]')}
        h.atomic(root / 'result.json', result)
        raise
    verify_sources(protocol)
    result = {'seed_id': seed_id, 'status': status, 'terminal': h.terminal(state),
        'ante': state.get('ante_num'), 'money': state.get('money'), 'chips': state.get('round', {}).get('chips'),
        'blind': next((b.get('name') for b in state.get('blinds', {}).values() if b.get('status') == 'CURRENT'), None),
        'actions': sum(counts.values()), 'counts': counts, 'seconds': time.monotonic() - started,
        'strategy_winrate_eligible': False, 'source_hashes_unchanged': True}
    h.atomic(root / 'result.json', result)
    print(json.dumps(result), flush=True)
    if not result['terminal']:
        raise ValueError('Truncated episode requires investigation, never reset')
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--solver', default='no_sl_solver_v3')
    p.add_argument('--growth', default='growth_policy_v5')
    p.add_argument('--seeds', type=int, nargs='+', default=SEEDS)
    args = p.parse_args()
    protocol = prepare(args.manifest, args.output, args.solver, args.growth, args.seeds)
    results = []
    for seed_id in args.seeds:
        results.append(run_episode(args.manifest, args.output, protocol, seed_id))
        h.atomic(args.output / 'summary.json', {'purpose': protocol['purpose'], 'completed': len(results),
            'wins': sum(r['status'] == 'win' for r in results), 'results': results,
            'strategy_winrate_eligible': False})


if __name__ == '__main__':
    main()
