"""Independent read-only structural audit of a completed formal campaign export."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding='utf8'))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def public_check(value):
    if isinstance(value, dict):
        for key, child in value.items():
            assert not any(word in key.lower() for word in ('seed', 'rng', 'draw_order')), key
            public_check(child)
    elif isinstance(value, list):
        for child in value:
            public_check(child)


def audit(root):
    protocol = load(root / 'protocol.json')
    summary = load(root / 'summary.json')
    assigned = {row['job_id']: row for row in protocol['jobs']}
    jobs = {row['job_id']: row for row in summary['jobs']}
    assert len(assigned) == protocol['assigned'] == summary['assigned']
    assert assigned.keys() == jobs.keys()
    assert len({row['seed_id'] for row in assigned.values()}) == len(assigned)
    assert summary['campaign_id'] == protocol['campaign_id']
    assert summary['complete'] and all(row['status'] in ('win', 'loss', 'error') for row in jobs.values())
    action_count = 0
    terminal_count = 0
    for job_id, row in jobs.items():
        assert row['seed_id'] == assigned[job_id]['seed_id']
        folder = root / 'jobs' / job_id
        result = load(folder / 'result.json')
        assert result == row['result']
        assert result['status'] == row['status']
        assert result['policy_id'] == protocol['policy_id']
        events = lines(folder / 'transitions.jsonl')
        decisions = lines(folder / 'decisions.jsonl')
        intents = {event['id']: event for event in events if event['event'] == 'intent'}
        outcomes = {event['id']: event for event in events if event['event'] == 'result'}
        assert len(intents) + len(outcomes) == len(events)
        assert outcomes.keys() <= intents.keys()
        starts = [event for event in intents.values() if event['method'] == 'start']
        assert len(starts) == 1
        assert starts[0]['params']['start_commitment'] == assigned[job_id]['commitment']
        initial = outcomes[starts[0]['id']]['after']
        assert (initial['deck'], initial['stake']) == ('BLUE', 'GOLD')
        completed_actions = sum(intents[i]['method'] not in ('start', 'menu') for i in outcomes)
        assert completed_actions == result['actions']
        assert result['actions'] == sum(result['counts'].values())
        if row['status'] != 'error':
            assert intents.keys() == outcomes.keys()
            assert len(decisions) == completed_actions
            final = outcomes[max(outcomes)]['after']
            assert result['terminal']
            assert final.get('state') == 'GAME_OVER' or final.get('overlay') == 'win' or final.get('won')
            if row['status'] == 'win':
                assert final.get('state') != 'GAME_OVER' and final.get('ante_num', 0) >= 8
            terminal_count += 1
        for decision in decisions:
            visible = decision['before']
            public_check(visible)
            # Belief can restore remembered Jokers; filtering must not add a
            # target for anything outside the resulting publicly known set.
            known = {card.get('key') for area in ('jokers', 'shop', 'pack')
                     for card in visible.get(area, {}).get('cards', [])
                     if not card.get('state', {}).get('hidden')}
            assert set(visible.get('_targets', {})) <= known
            assert decision['method'] not in ('start', 'menu', 'skip', 'lab_stop')
        action_count += completed_actions
    wins = sum(row['status'] == 'win' for row in jobs.values())
    assert summary['wins_per_assigned'] == wins / len(jobs)
    assert summary['counts'] == dict(Counter(row['status'] for row in jobs.values()))
    longest = current = 0
    for row in sorted(jobs.values(), key=lambda item: item['seed_id']):
        current = current + 1 if row['status'] == 'win' else 0
        longest = max(longest, current)
    assert summary['longest_streak_in_registered_order'] == longest
    return {'campaign_id': protocol['campaign_id'], 'assigned': len(jobs),
            'true_terminals': terminal_count, 'actions': action_count,
            'wins': wins, 'audit': 'passed',
            'scope': 'structural public artifacts; not full engine or strategic correctness proof',
            'protocol_sha256': hashlib.sha256((root / 'protocol.json').read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.campaign), ensure_ascii=False, indent=2))
