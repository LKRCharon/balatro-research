"""Fixed-action ability ablations on audited completed TRAIN plays.

This measures conditional scoring interactions including editions, not sale
value, total utility, causal card strength or balance. Resources stay fixed.
"""
import argparse
from collections import defaultdict, Counter
import copy
import json
from pathlib import Path
from audit_combat_regret import lines


def ablate(state, selected, advisor):
    baseline = advisor.score(state, selected)[0]
    result = []
    for index, joker in enumerate(state['jokers']['cards']):
        if advisor.st(joker).get('debuff'):
            continue
        changed = copy.deepcopy(state)
        changed['jokers']['cards'][index].setdefault('state', {})['debuff'] = True
        without = advisor.score(changed, selected)[0]
        result.append({'key': joker['key'], 'index': index, 'baseline': baseline,
            'disabled_score': without, 'difference': baseline - without,
            'relative_difference': (baseline - without) / baseline if baseline else None,
            'sticker_rental': bool(advisor.mod(joker).get('rental')),
            'sticker_eternal': bool(advisor.mod(joker).get('eternal')),
            'edition': advisor.mod(joker).get('edition') or 'NONE',
            'sell_recommendation': False})
    return result


def analyze(batches, advisor):
    counts = Counter()
    by_key = defaultdict(list)
    for batch in batches:
        for root in sorted(Path(batch).glob('train-*')):
            if not (root / 'result.json').exists():
                counts['active_episodes_not_read'] += 1
                continue
            terminal = json.loads((root / 'result.json').read_text(encoding='utf-8'))
            if terminal.get('status') not in ('win', 'loss'):
                continue
            counts['completed_episodes'] += 1
            audited = {p['transition_id']: p for p in lines(root / 'predictions.jsonl')}
            for d in lines(root / 'decisions.jsonl'):
                if d['method'] != 'play':
                    continue
                prediction = audited.get(d['sequence'])
                if not prediction or prediction.get('uncertain') or prediction.get('within_one') is not True:
                    counts['unaudited_or_uncertain_plays_omitted'] += 1
                    continue
                state = d['before']
                modeled = advisor.score(state, d['params']['cards'])[0]
                if abs(modeled - prediction['actual']) > 1:
                    counts['current_model_disagrees_omitted'] += 1
                    continue
                counts['audited_plays'] += 1
                for row in ablate(state, d['params']['cards'], advisor):
                    row.update(training_id=int(root.name.split('-')[-1]), batch=Path(batch).name,
                        sequence=d['sequence'], ante=state['ante_num'])
                    by_key[row['key']].append(row)
    cards = []
    for key, rows in sorted(by_key.items()):
        relative = [r['relative_difference'] for r in rows if r['relative_difference'] is not None]
        cards.append({'key': key, 'audited_play_appearances': len(rows),
            'edition_play_appearances': dict(Counter(r['edition'] for r in rows)),
            'episodes': len({(r['batch'], r['training_id']) for r in rows}),
            'positive_scoring_ablations': sum(r['difference'] > 0 for r in rows),
            'negative_scoring_ablations': sum(r['difference'] < 0 for r in rows),
            'zero_scoring_ablations': sum(r['difference'] == 0 for r in rows),
            'mean_relative_scoring_difference': sum(relative) / len(relative) if relative else None,
            'mean_absolute_scoring_difference': sum(r['difference'] for r in rows) / len(rows)})
    return {'purpose': 'conditional_fixed_action_joker_ability_ablation', 'counts': dict(counts),
        'cards': cards, 'strategy_winrate_eligible': False,
        'limitations': ['Only deterministic plays matched to real engine scores are included; mismatches and uncertain plays are omitted.',
            'Abilities are disabled in place: slots, money, hand resources and selected action are fixed; this is not a sale simulation.',
            'Copy chains and combinations can attribute the same interaction to several cards; contributions do not add up.',
            'Debuffing also suppresses edition scoring; edition appearances are listed to prevent attributing Foil/Holographic/Polychrome effects to the base ability.',
            'Zero score contribution does not mean weak: economy, insurance, future growth, draw resources and pack effects are excluded.',
            'Means weight audited play appearances, not independent episodes. Selection and survivor bias prevent causal strength claims.',
            'Repeated TRAIN episodes are development data; final TEST remains separate.']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--batch', action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'headless'))
    import hybrid_session
    _, advisor, _, _ = hybrid_session.modules()
    report = analyze(args.batch, advisor)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'counts': report['counts'], 'cards': report['cards']}))
