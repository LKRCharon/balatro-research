"""Completed TRAIN observation aggregates; no causal card-strength claims."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path


def read_lines(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def average(values):
    return round(sum(values) / len(values), 4) if values else None


def analyze(batches):
    offers = defaultdict(Counter)
    actions = Counter()
    rounds = []
    endings = Counter()
    completed = 0
    omitted_idless_observations = 0
    unexecuted_decisions = 0
    for batch in batches:
        for root in sorted(Path(batch).glob('train-*')):
            if not (root / 'result.json').exists():
                continue
            result = json.loads((root / 'result.json').read_text(encoding='utf-8'))
            if result['status'] not in ('win', 'loss'):
                continue
            completed += 1
            endings[result['status']] += 1
            decisions = read_lines(root / 'decisions.jsonl')
            events = read_lines(root / 'transitions.jsonl')
            results = {e['id']: e['after'] for e in events if e['event'] == 'result' and
                       e.get('accepted') is not False and not e.get('error')}
            seen = set()
            shop_number = 0
            reroll_number = 0
            current = None
            for decision in decisions:
                before = decision.get('before')
                if not before:
                    continue
                method = decision['method']
                params = decision.get('params', {})
                after = results.get(decision['sequence'], {})
                executed = decision['sequence'] in results
                if executed:
                    actions[method] += 1
                else:
                    unexecuted_decisions += 1
                if before.get('state') == 'SHOP':
                    for area in ('shop', 'packs', 'vouchers'):
                        for index, card in enumerate(before.get(area, {}).get('cards', [])):
                            card_id = card.get('id')
                            if card_id is None:
                                omitted_idless_observations += 1
                                continue
                            token = (shop_number, area, card_id)
                            if token not in seen:
                                seen.add(token)
                                counts = offers[(area, card['key'])]
                                counts['unique_observed'] += 1
                                price = card.get('cost', {}).get('buy', 0)
                                counts['cash_affordable'] += price <= before['money']
                                counts['rental'] += bool(card.get('modifier', {}).get('rental'))
                                counts['eternal'] += bool(card.get('modifier', {}).get('eternal'))
                    if method == 'buy' and executed:
                        area = 'shop' if 'card' in params else 'packs' if 'pack' in params else 'vouchers' if 'voucher' in params else None
                        if area:
                            key = {'shop': 'card', 'packs': 'pack', 'vouchers': 'voucher'}[area]
                            card = before[area]['cards'][params[key]]
                            offers[(area, card['key'])]['purchases'] += 1
                if not executed:
                    continue
                if method == 'reroll':
                    reroll_number += 1
                if method == 'select':
                    blind = next((b for b in after.get('blinds', {}).values() if b.get('status') == 'CURRENT'), {})
                    jokers = after.get('jokers', {}).get('cards', [])
                    current = {'ante': after.get('ante_num'), 'blind_type': blind.get('type'),
                        'blind_name': blind.get('name'), 'target': blind.get('score', 0),
                        'entry_cash': before.get('money'), 'jokers': len(jokers),
                        'rental_jokers': sum(bool(c.get('modifier', {}).get('rental')) for c in jokers),
                        'entry_hand_limit': after.get('hand', {}).get('limit'),
                        'initial_hands': after.get('round', {}).get('hands_left'),
                        'plays': 0, 'discards': 0, 'scoring_total': 0, 'growth_plays': 0}
                if current and method in ('play', 'discard'):
                    current['plays' if method == 'play' else 'discards'] += 1
                    current['scoring_total'] = after.get('round', {}).get('chips', 0)
                    if 'retained_core_growth' in params.get('reason', '') or 'safe_model_growth_hand' in params.get('reason', ''):
                        current['growth_plays'] += 1
                victory = bool(after.get('won')) or after.get('overlay') == 'win'
                if current and (method == 'cash_out' or after.get('state') == 'GAME_OVER' or victory):
                    current['cleared'] = method == 'cash_out' or victory
                    current['exit_cash'] = after.get('money')
                    current['score_ratio'] = current['scoring_total'] / max(1, current['target'])
                    rounds.append(current)
                    current = None
                if method == 'cash_out':
                    shop_number += 1
                    reroll_number = 0
    grouped = defaultdict(list)
    for row in rounds:
        grouped[row['ante']].append(row)
    stages = []
    for ante, rows in sorted(grouped.items()):
        stages.append({'ante': ante, 'observed_blinds': len(rows),
            'clears': sum(r['cleared'] for r in rows),
            'mean_entry_cash': average([r['entry_cash'] for r in rows]),
            'mean_exit_cash': average([r['exit_cash'] for r in rows]),
            'mean_jokers': average([r['jokers'] for r in rows]),
            'mean_rental_jokers': average([r['rental_jokers'] for r in rows]),
            'mean_plays': average([r['plays'] for r in rows]),
            'mean_discards': average([r['discards'] for r in rows]),
            'mean_score_ratio': average([r['score_ratio'] for r in rows]),
            'growth_plays': sum(r['growth_plays'] for r in rows)})
    return {'purpose': 'completed_train_observations', 'completed': completed,
        'omitted_idless_observation_records': omitted_idless_observations,
        'unexecuted_decisions': unexecuted_decisions,
        'status_counts': dict(endings), 'actions': dict(actions), 'stages': stages,
        'offers': [{'area': area, 'key': key, **dict(counts)} for (area, key), counts in sorted(offers.items())],
        'limitations': ['Later antes include survivors only; never compare them as an unbiased population.',
            'Cash affordability at first sight ignores free slots, stickers and policy budget; it is not purchase feasibility.',
            'Observed purchase frequency is policy-specific exposure data, not causal strength or balance.',
            'Unique offer counts require game-assigned card ids; idless observation records are explicitly omitted.',
            'Pack contents are unknown before opening; only the observed pack offer is counted.',
            'Rounds have equal weight; this differs from action-snapshot-weighted money averages.',
            'Entry rental counts are not a reconstruction of actual fees or net income.',
            'Repeated TRAIN observations are not held-out win-rate evidence.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(args.batch)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('completed', 'status_counts', 'stages')}))
