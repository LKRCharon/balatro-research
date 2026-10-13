"""Completed TRAIN immediate-score audit; never claims whole-round optimality."""
import argparse
from collections import Counter
import json
from pathlib import Path


def lines(path):
    return [json.loads(row) for row in path.read_text(encoding='utf-8').splitlines() if row.strip()]


def inspect_hand(decision, advisor):
    state = decision['before']
    blind = next((b for b in state.get('blinds', {}).values() if b.get('status') == 'CURRENT'), None)
    if blind is None:
        return {'omitted': 'no_current_blind'}
    options = advisor.options(state, optimize_order=True)
    if not options:
        return {'omitted': 'no_legal_options'}
    best = options[0][0]
    need = blind['score'] - state['round']['chips']
    method = decision['method']
    selected = advisor.score(state, decision['params']['cards'])[0] if method == 'play' else None
    deterministic = not advisor.uncertain(state)
    reason = decision.get('params', {}).get('reason', '')
    growth = any(word in reason for word in ('retained_core_growth', 'safe_model_growth_hand'))
    return {'sequence': decision['sequence'], 'ante': state.get('ante_num'),
        'blind': blind['name'], 'method': method, 'hands_left': state['round']['hands_left'],
        'discards_left': state['round']['discards_left'], 'needed': need,
        'model_best_score': best, 'model_selected_score': selected,
        'deterministic_model': deterministic, 'explicit_growth_play': growth,
        'immediate_score_gap': best - selected if selected is not None else None,
        'passed_available_finish': best >= need and (selected is None or selected < need),
        'final_hand_missed_finish': deterministic and method == 'play' and
            state['round']['hands_left'] == 1 and best >= need and selected < need,
        'spent_final_hand_without_finish_with_discards': method == 'play' and
            state['round']['hands_left'] == 1 and state['round']['discards_left'] > 0 and selected < need,
        'engine_optimality_claim': False}


def analyze(batches, advisor):
    counts = Counter()
    rows = []
    for batch in batches:
        for root in sorted(Path(batch).glob('train-*')):
            result_path = root / 'result.json'
            if not result_path.exists():
                counts['active_episodes_not_read'] += 1
                continue
            result = json.loads(result_path.read_text(encoding='utf-8'))
            if result.get('status') not in ('win', 'loss'):
                counts['nonterminal_episodes_omitted'] += 1
                continue
            counts['completed_episodes'] += 1
            outcomes = {e['id'] for e in lines(root / 'transitions.jsonl') if
                e['event'] == 'result' and e.get('accepted') is not False and not e.get('error')}
            for decision in lines(root / 'decisions.jsonl'):
                if decision['method'] not in ('play', 'discard') or decision.get('before', {}).get('state') != 'SELECTING_HAND':
                    continue
                if decision['sequence'] not in outcomes:
                    counts['unexecuted_actions_omitted'] += 1
                    continue
                try:
                    row = inspect_hand(decision, advisor)
                except ValueError:
                    counts['unsupported_scoring_actions_omitted'] += 1
                    continue
                if 'omitted' in row:
                    counts[row['omitted']] += 1
                    continue
                counts['audited_actions'] += 1
                counts['deterministic_actions' if row['deterministic_model'] else 'uncertain_actions'] += 1
                counts['positive_play_score_gap'] += (row['immediate_score_gap'] or 0) > 0
                for key in ('passed_available_finish', 'final_hand_missed_finish', 'spent_final_hand_without_finish_with_discards', 'explicit_growth_play'):
                    counts[key] += row[key]
                if row['passed_available_finish'] or row['spent_final_hand_without_finish_with_discards'] or (row['immediate_score_gap'] or 0) > 0:
                    rows.append(dict(row, training_id=int(root.name.split('-')[-1]),
                        batch=Path(batch).name, terminal_status=result['status']))
    return {'purpose': 'completed_train_immediate_score_diagnostics', 'counts': dict(counts),
        'flagged_actions': rows, 'strategy_winrate_eligible': False,
        'limitations': ['Score gaps are within the current scoring model; uncertain actions are explicitly labelled.',
            'A lower immediate score can preserve combinations or grow Jokers; this audit does not show a worse whole-round action.',
            'Growth actions may intentionally postpone a finish, and are reported separately.',
            'Boss random effects and hidden cards prevent engine certainty even when a model option scores enough.',
            'Active episode decisions are never opened. Repeated TRAIN seeds are not independent evaluation.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'headless'))
    import hybrid_session
    _, advisor, _, _ = hybrid_session.modules()
    report = analyze(args.batch, advisor)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'purpose': report['purpose'], 'counts': report['counts']}))
