"""Repeat deterministic retained-core growth while two hands remain.

Spends a hand-dollar on model-verified persistent growth; requires an unchanged
winning core after the junk play. No engine certainty or optimality is claimed.
"""
import copy
import combat_candidate_v11 as prior
import combat_candidate_v6 as grow


def growth_action(state):
    if state.get('state') != 'SELECTING_HAND':
        return None
    s = prior.prior.cycle.old.v2.public_state(state)
    a, v1 = grow.a, grow.v1
    keys = a.keys(s)
    if (not keys & grow.GROWERS or keys - grow.ALLOWED or
        s['round']['hands_left'] < 2 or s.get('money', 0) < 5 or
        s.get('ante_num', 8) >= 8 or
        v1.static.boss(s).get('name') not in grow.BOSSES or a.uncertain(s) or
        any(a.st(c).get('hidden') or a.mod(c).get('enhancement') or
            a.mod(c).get('seal') for c in s['hand']['cards'])):
        return None
    options = a.options(s, optimize_order=True)
    need = v1.static.boss(s)['score'] - s['round']['chips']
    winning = [o for o in options if (a.conservative_score(s, o[1], o[0]) or 0) >= need]
    if not winning:
        return None
    core = min(winning, key=lambda o: (len(o[1]), -o[0]))
    choices = []
    for option in options:
        if set(option[1]) & set(core[1]) or option[0] >= need:
            continue
        if 'j_ride_the_bus' in keys and any(a.rank(s['hand']['cards'][i]) in (11, 12, 13) for i in option[3]):
            continue
        if keys & grow.GROWERS == {'j_supernova'} and option[2] != core[2]:
            continue
        after, _, points = grow.prior.transition(s, 'play', option[1], [])
        # Ignore unknown refill identities, but not their public deck-count cost:
        # Blue Joker loses two chips for every card drawn before the next hand.
        refill_count = min(s['cards']['count'], max(0, s['hand']['limit'] - len(after['hand']['cards'])))
        after['cards']['count'] = max(0, s['cards']['count'] - refill_count)
        remaining = [i for i in range(len(s['hand']['cards'])) if i not in option[1]]
        retained = [remaining.index(i) for i in core[1]]
        bound = a.conservative_score(after, retained)
        baseline = copy.deepcopy(after)
        baseline['jokers'] = copy.deepcopy(s['jokers'])
        baseline['hands'] = copy.deepcopy(s['hands'])
        old_bound = a.conservative_score(baseline, retained)
        if bound is None or old_bound is None or bound < need - points:
            continue
        gain = bound - old_bound
        relative = gain / max(1, old_bound)
        if relative >= .02:
            choices.append((relative, gain, option, bound, refill_count))
    if not choices:
        return None
    relative, gain, option, bound, refill_count = max(choices, key=lambda x: (x[0], x[1], -len(x[2][1])))
    return v1.action_for(s, 'play', option[1], {
        'mode': 'v12_retained_core_growth', 'optimality_claim': False,
        'future_draw_order_used': False, 'guaranteed_engine_clear': False,
        'retained_winning_indices': core[1], 'retained_model_clear_bound': bound,
        'persistent_relative_gain': relative, 'persistent_route_score_gain': gain,
        'foregone_hand_income': 1, 'income_tradeoff_is_heuristic': True,
        'minimum_relative_growth_gain': .02, 'retained_core_refill_identities_ignored': True,
        'refill_deck_count_cost': refill_count})


def choose(state, config=None):
    grow.v1.config_values(config)
    return growth_action(state) or prior.choose(state, config)
