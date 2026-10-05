"""Bounded one-purchase shop lookahead, using public information only.

Forecast quantiles are heuristics, not calibrated survival probabilities. Route
witnesses prevent a small random sample from assigning zero value to a reachable
flush/straight upgrade. Witness scores have a fixed 20% ranking weight, never a
claim that those hands are guaranteed. No card category is blacklisted.
"""
import copy
from collections import Counter
import advisor as a
import forecast
from belief import base_deck

PLANETS = dict(zip(('c_pluto','c_mercury','c_uranus','c_venus','c_saturn','c_jupiter',
                   'c_earth','c_mars','c_neptune','c_planet_x','c_ceres','c_eris'), a.NAMES))
MAX_OFFERS = 8
MAX_REPLACEMENTS = 2

def witnesses(s):
    """At most six actual-deck hand witnesses; no future draw order or RNG."""
    deck = copy.deepcopy(s.get('_belief', {}).get('deck') or list(base_deck().values()))
    groups = {}
    for c in deck:
        if not a.st(c).get('hidden'):
            groups.setdefault(a.rank(c), []).append(c)
    ranks = sorted(groups, reverse=True)
    result = [[groups[ranks[0]][0]]] if ranks else []
    pair = next((groups[r][:2] for r in ranks if len(groups[r]) >= 2), [])
    triple = next((groups[r][:3] for r in ranks if len(groups[r]) >= 3), [])
    if pair: result.append(pair)
    pairs = [groups[r][:2] for r in ranks if len(groups[r]) >= 2]
    if len(pairs) >= 2: result.append(pairs[0] + pairs[1])
    if triple: result.append(triple)
    flushes = [[c for c in deck if a.suit(c) == su] for su in ('S','H','C','D')]
    flush = max(flushes, key=len)
    if len(flush) >= 5:
        ordered = sorted(flush, key=a.rank, reverse=True)
        # Avoid turning the ordinary flush witness into a royal flush in a
        # vanilla deck; that would hide Jupiter's improvement entirely.
        result.append([ordered[i] for i in (0, 1, 3, 5, 7)] if len(ordered) >= 8 else ordered[:5])
    for high in range(14, 5, -1):
        run = list(range(high, high - 5, -1))
        if all(r in groups for r in run):
            result.append([groups[r][i % len(groups[r])] for i, r in enumerate(run)]); break
    return result

def strength(s, probes):
    outlook = forecast.estimate(s)
    route_scores = []
    for hand in probes:
        sim = copy.deepcopy(s)
        hand = copy.deepcopy(hand)
        target = next((sim['blinds'][key] for key in ('small','big','boss')
                       if sim['blinds'][key]['status'] not in ('DEFEATED','SKIPPED')), sim['blinds']['boss'])
        for blind in sim['blinds'].values(): blind['status'] = 'UPCOMING'
        target['status'] = 'CURRENT'
        sim['_boss_disabled'] = False
        sim['round'].pop('mouth_hand', None)
        if 'j_chicot' not in a.keys(sim):
            banned = {'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(target['name'])
            for card in hand:
                if a.suit(card) == banned or (target['name'] == 'The Plant' and a.rank(card) in (11,12,13)):
                    card.setdefault('state', {})['debuff'] = True
        sim['hand'] = {'cards': hand, 'count': len(hand), 'limit': s.get('hand', {}).get('limit', 8)}
        sim['round'] = dict(sim['round'], hands_played=0, hands_left=outlook['hands'])
        for level in sim['hands'].values(): level['played_this_round'] = 0
        # These structural witnesses only rank alternatives; they do not inflate
        # the readiness/coverage result or imply those hands will be drawn.
        route_scores.append(a.score(sim, list(range(len(hand))))[0])
    value = .4 * outlook['q25'] + .6 * outlook['median']
    return value + .2 * sum(route_scores) / max(1, len(route_scores)), outlook

def upgraded(s, card, price):
    hand = PLANETS.get(card.get('key'))
    if hand not in s.get('hands', {}): return None
    sim = copy.deepcopy(s)
    chips, mult = a.LEVEL_DELTA[hand]
    sim['hands'][hand]['chips'] += chips
    sim['hands'][hand]['mult'] += mult
    sim['hands'][hand]['level'] = sim['hands'][hand].get('level', 1) + 1
    sim['money'] -= price
    return sim

def choose(s, utility, xmult, *, pack=False):
    """Rank all affordable offers (max 8), at most two replacements per Joker.

    Returns an action or None. Future-value purchases require existing combat
    headroom and an $8 post-purchase reserve; immediate improvements can spend
    below that floor. A pack Joker is already paid for and costs zero here.
    """
    shop = s.get('pack' if pack else 'shop', {}).get('cards', [])
    probes = witnesses(s)
    baseline, outlook = strength(s, probes)
    pressure = outlook['pressure'] or outlook['coverage'] < 1.5
    options = []
    held = s['jokers']['cards']
    free = s['jokers']['limit'] - len(held)
    replace = sorted((utility(c, s), i) for i, c in enumerate(held) if not a.mod(c).get('eternal'))[:MAX_REPLACEMENTS]
    for index, card in enumerate(shop[:MAX_OFFERS]):
        price = 0 if pack else card.get('cost', {}).get('buy', 0)
        candidates = []
        if card.get('set') == 'PLANET':
            if price > s['money']: continue
            sim = upgraded(s, card, price)
            if sim: candidates.append((None, sim, 0))
        elif card.get('set') == 'JOKER':
            targets = [None] if free > 0 or a.mod(card).get('edition') == 'NEGATIVE' else [i for _, i in replace]
            for target in targets:
                sim = copy.deepcopy(s)
                if target is None: sim['jokers']['cards'].append(copy.deepcopy(card))
                else: sim['jokers']['cards'][target] = copy.deepcopy(card)
                sim['jokers']['limit'] += int(a.mod(card).get('edition') == 'NEGATIVE')
                if target is not None:
                    sim['jokers']['limit'] -= int(a.mod(held[target]).get('edition') == 'NEGATIVE')
                if len(sim['jokers']['cards']) > sim['jokers']['limit']: continue
                # Preserve copy-chain geometry; phase policy adjusts it separately.
                if not a.keys(sim) & {'j_blueprint', 'j_brainstorm'}:
                    sim['jokers']['cards'].sort(key=lambda j: int(j['key'] in xmult or a.mod(j).get('edition') == 'POLYCHROME'))
                sim['money'] -= price
                if target is not None: sim['money'] += held[target].get('cost', {}).get('sell', 0)
                if sim['money'] < 0: continue
                candidates.append((target, sim, utility(card, s)))
        for target, sim, prior in candidates:
            value, after = strength(sim, probes)
            gain = value - baseline
            immediate = gain > max(1, baseline * .03)
            # No tier/prior override when the next blind is unsafe. Preserve
            # conditional DNA, generator and economy options when already safe.
            future = (card.get('set') == 'JOKER' and not pressure and not after['pressure']
                      and after['coverage'] >= 1.5 and sim['money'] >= (0 if pack else 8)
                      and value >= baseline * .95 and prior >= 50
                      and (target is None or prior > utility(held[target], s) + 20))
            if not immediate and not future and not (price == 0 and card.get('set') == 'PLANET'): continue
            if immediate and not pressure and not pack and sim['money'] < 5 and gain < baseline * .15: continue
            # Raw score gain takes priority over speculative priors. Cost breaks
            # ties and still matters for cases with similar gains.
            rank = (int(immediate), gain / max(1, baseline), -price, prior)
            options.append((rank, index, target, card, gain))
    if not options: return None
    _, index, target, card, gain = max(options, key=lambda item: item[0])
    if target is not None:
        return 'sell', {'joker': target, 'reason': '比较可负担的完整替代阵容后腾出槽位；新阵容的即时得分或安全余量支持替换。'}
    params = {'card': index, 'reason': f'比较完整阵容与可达牌型升级：{card["key"]} 的即时启发式增益约 {gain:.1f}；危险时不为纯未来收益耗尽现金。'}
    if card.get('set') == 'PLANET' and not pack: params['use'] = True
    return ('pack' if pack else 'buy'), params
