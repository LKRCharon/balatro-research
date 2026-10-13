"""Plain-card whole-round common-world search; v10 for other mechanics.

Continuations inspect only each resulting public hand. Sample clear fractions
are rankings, not calibrated probabilities or an optimality certificate.
"""
import time
import combat_candidate_v10 as prior
import plain_combat as plain

a = prior.a
v1 = prior.v1


def play_option(s, opts):
    best = opts[0]
    tied = [o for o in opts if o[0] == best[0] and o[2] == best[2]]
    def rank(o):
        held = [c for i, c in enumerate(s['hand']['cards']) if i not in o[1]]
        suits = prior.Counter(a.suit(c) for c in held if not a.st(c).get('debuff'))
        return len(o[1]) + 3 * (max(suits.values(), default=0) >= 4), len(o[1])
    return max(tied, key=rank)


def roots(s, opts):
    result = [('play', play_option(s, opts)[1])]
    if s['round']['discards_left'] > 0:
        result += [('discard', tuple(r)) for r in prior.cycle.old.discard_roots(s, opts)]
    return list(dict.fromkeys(result))


def continuation(s):
    opts = plain.options(s)
    best = play_option(s, opts)
    need = v1.static.boss(s)['score'] - s['round']['chips']
    if s['round']['discards_left'] > 0 and best[0] < need / max(1, s['round']['hands_left']):
        indices = a.discard(s, best)
        if indices:
            return 'discard', indices
    return 'play', best[1]


def rollout(s, root, world):
    sim, tail = s, world
    method, indices = root
    target = v1.static.boss(s)['score']
    steps = 0
    while sim['round']['hands_left'] > 0 and sim['hand']['cards'] and steps < 20:
        sim, tail, _ = v1.static.transition(sim, method, indices, tail)
        steps += 1
        if sim['round']['chips'] >= target:
            return True, target, sim['round']['hands_left']
        if sim['round']['hands_left'] <= 0 or not sim['hand']['cards']:
            break
        method, indices = continuation(sim)
    return False, min(target, sim['round']['chips']), 0


def choose(state, config=None):
    cfg = v1.config_values(config)
    s = prior.cycle.old.v2.public_state(state)
    if (s.get('state') != 'SELECTING_HAND' or not plain.supported(s) or
        v1.static.support_reason(s) is not None or
        any(a.mod(c) or c.get('permanent_bonus') for c in s['_belief']['unseen'])):
        return prior.choose(state, config)
    opts = plain.options(s)
    target = v1.static.boss(s)['score']
    if opts[0][0] >= target - s['round']['chips']:
        return v1.action_for(s, 'play', opts[0][1], {'mode': 'v11_plain_current_clear', 'optimality_claim': False})
    candidates = roots(s, opts)
    worlds = v1.static.scenarios(s, max(8, cfg['samples']))
    values = [[] for _ in candidates]
    started = time.monotonic()
    for world in worlds:
        batch = [rollout(s, root, world) for root in candidates]
        for row, value in zip(values, batch):
            row.append(value)
        if len(values[0]) >= 8 and time.monotonic() - started >= cfg['time_budget']:
            break
    rows = [{'method': method, 'indices': list(indices), 'samples': len(v),
             'clear_fraction': sum(x[0] for x in v) / len(v),
             'mean_capped_total': sum(x[1] for x in v) / len(v),
             'mean_hands_left': sum(x[2] for x in v) / len(v)}
            for (method, indices), v in zip(candidates, values)]
    allowed = [r for r in rows if not (s['round']['hands_left'] == 1 and
               s['round']['discards_left'] > 0 and r['method'] == 'play')]
    if not allowed:
        return prior.choose(state, config)
    row = max(allowed, key=lambda r: (r['clear_fraction'], r['mean_capped_total'],
                                      r['mean_hands_left'], r['method'] == 'play'))
    return v1.action_for(s, row['method'], row['indices'], {
        'mode': 'v11_plain_common_world_whole_round', 'ranked_candidates': rows,
        'optimality_claim': False, 'future_draw_order_used': False,
        'sample_fraction_is_calibrated_probability': False,
        'continuation_is_greedy': True, 'minimum_complete_batches': 8,
        'time_budget_is_soft': True, 'elapsed_seconds': time.monotonic() - started})
