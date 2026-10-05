"""Posthoc observed-state telemetry. Never exports raw states, seeds or prose."""
import argparse
from collections import Counter
import json
from pathlib import Path

def cards(state, area):
    return state.get(area, {}).get('cards', [])

def summarize_job(events, rarity, result=None):
    seen = set()
    offers, purchases, rarities = Counter(), Counter(), Counter()
    money, blind_curve = [], []
    pending = {}
    visit = None
    generation = 0
    ambiguous = 0
    last = {}
    active_blind = {}
    last_money = None
    def observe(state, event_id):
        nonlocal visit, generation, ambiguous, last, active_blind, last_money
        if not state or state.get('state') == 'MENU':
            return
        last = state
        current = next((b for b in state.get('blinds', {}).values() if b.get('status') == 'CURRENT'), None)
        if current:
            active_blind = {k: current.get(k) for k in ('name', 'type', 'score')}
        point = (state.get('ante_num'), state.get('round_num'), state.get('state'), state.get('money'))
        if point != last_money:
            money.append(dict(zip(('ante', 'round', 'phase', 'money'), point), event_id=event_id))
            last_money = point
        if state.get('state') != 'SHOP':
            return
        observed_visit = (state.get('ante_num'), state.get('round_num'))
        if observed_visit != visit:
            visit = observed_visit
            generation = 0
        for area in ('shop', 'vouchers', 'packs'):
            occurrences = Counter()
            for card in cards(state, area):
                if card.get('state', {}).get('hidden'):
                    continue
                key = card.get('key', 'unknown')
                kind = str(card.get('set', 'UNKNOWN')).upper()
                ident = card.get('id')
                fallback = ident is None
                if fallback:
                    fingerprint = (key, kind, json.dumps(card.get('modifier', {}), sort_keys=True))
                    occurrences[fingerprint] += 1
                    ident = (fingerprint, occurrences[fingerprint])
                token = (visit, area, generation if area == 'shop' else 0, ident)
                if token in seen:
                    continue
                seen.add(token)
                ambiguous += int(fallback)
                offers[area + ':' + key] += 1
                if area == 'shop' and kind == 'JOKER':
                    rarities[str(rarity.get(key, 'unknown'))] += 1

    for event in events:
        event_id = event.get('id')
        if event.get('event') == 'intent':
            pending[event_id] = event
            observe(event.get('before', {}), event_id)
            continue
        if event.get('event') != 'result':
            continue
        intent = pending.pop(event_id, {})
        method, params = intent.get('method'), intent.get('params', {})
        before, after = intent.get('before', {}), event.get('after', {})
        if method == 'reroll':
            generation += 1
        if method == 'buy':
            for param, area in (('card', 'shop'), ('voucher', 'vouchers'), ('pack', 'packs')):
                idx = params.get(param)
                available = cards(before, area)
                if type(idx) is int and 0 <= idx < len(available):
                    purchases[area + ':' + available[idx].get('key', 'unknown')] += 1
                    break
        observe(after, event_id)
        if method in ('select', 'cash_out'):
            blind_curve.append({'event_id': event_id, 'event': method, 'ante': after.get('ante_num'),
                                'round': after.get('round_num'), 'money': after.get('money')})
    final = result or {}
    failure = None
    if final.get('status') == 'loss' or last.get('state') == 'GAME_OVER':
        failure = {'ante': last.get('ante_num'), 'round': last.get('round_num'),
                   'blind': active_blind.get('name'), 'blind_type': active_blind.get('type'),
                   'target': active_blind.get('score'), 'score': last.get('round', {}).get('chips')}
    return {'status': final.get('status', 'incomplete'), 'money_curve': money,
            'blind_boundary_money': blind_curve, 'shop_joker_rarity_offers': dict(rarities),
            'shop_joker_offer_denominator': sum(rarities.values()), 'offers_by_area_key': dict(offers),
            'resolved_buy_actions_by_area_key': dict(purchases), 'fallback_identity_exposures': ambiguous,
            'unresolved_intents': len(pending), 'failure': failure}

def build(source, specs):
    protocol = json.loads((source / 'protocol.json').read_text(encoding='utf-8'))
    rarity = {k: v.get('rarity', 'unknown') for k, v in specs.items()}
    jobs = []
    for assignment in protocol['jobs']:
        directory = source / 'jobs' / assignment['job_id']
        path = directory / 'transitions.jsonl'
        events = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
        path = directory / 'result.json'
        result = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        jobs.append({'job_id': assignment['job_id'], **summarize_job(events, rarity, result)})
    counts = Counter()
    for job in jobs:
        counts.update(job['shop_joker_rarity_offers'])
    return {'schema': 1, 'campaign_id': protocol['campaign_id'], 'assigned_jobs': len(jobs),
            'complete': all(j['status'] in ('win', 'loss', 'error') for j in jobs),
            'method': 'posthoc paired transition intents/results; only observable snapshots; no raw states exported',
            'caveats': [
                'Rarity denominator is deduplicated observed SHOP Joker offers, not theoretical spawn probabilities.',
                'Shop identity uses ante/round visit, reroll generation and stable card id; missing ids use fingerprint multiplicity and may merge indistinguishable replacements.',
                'Voucher/pack offers count distinct observed card ids per shop visit; a persistent voucher seen in another visit counts again.',
                'Resolved buy actions count returned engine actions targeting an observed offer, not independent inventory-diff verification.',
                'Only visited shops are observed; survival and policy choices bias exposure. Pack contents are not shop offers.',
                'Money curve retains phase or money changes; blind_boundary_money offers compact round checkpoints.',
                'No raw seeds, card descriptions, decision prose or complete game states are exported.'
            ], 'shop_joker_rarity_offers': dict(counts), 'shop_joker_offer_denominator': sum(counts.values()), 'jobs': jobs}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--specs', type=Path, required=True)
    args = parser.parse_args()
    report = build(args.source, json.loads(args.specs.read_text(encoding='utf-8')))
    if not report['complete']:
        raise SystemExit('Refusing final telemetry export: assigned jobs remain incomplete')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'jobs': len(report['jobs']), 'observed_shop_jokers': report['shop_joker_offer_denominator']}))

if __name__ == '__main__':
    main()
