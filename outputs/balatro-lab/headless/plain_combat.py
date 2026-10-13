"""Fast plain-card scoring using the already verified hand classifier.

Explicitly declines editions, enhancements, jokers and hidden cards. This is
an optimization of public scoring, not access to the reference engine RNG.
"""
import itertools
import math
import advisor as a


def supported(s):
    return (not s['jokers']['cards'] and all(
        not a.mod(c) and not a.st(c).get('hidden') and
        not a.st(c).get('face_down') and not c.get('permanent_bonus')
        for c in s['hand']['cards']))


def options(s):
    if not supported(s):
        raise ValueError('Plain cards required')
    cards = s['hand']['cards']
    boss = next((b['name'] for b in s['blinds'].values()
                 if b['status'] == 'CURRENT'), '')
    if s.get('_boss_disabled'):
        boss = ''
    forced = {i for i, c in enumerate(cards) if a.st(c).get('highlight')} if boss == 'Cerulean Bell' else set()
    locked = s['round'].get('mouth_hand') or next(
        (n for n, h in s['hands'].items() if h.get('played_this_round', 0)), None)
    result = []
    for n in range(1, min(5, len(cards)) + 1):
        for indices in itertools.combinations(range(len(cards)), n):
            if not forced.issubset(indices):
                continue
            cat, scored, _ = a.classify(cards, indices)
            name = a.NAMES[cat]
            h = s['hands'][name]
            chips, mult = h['chips'], h['mult']
            if boss == 'The Arm' and h['level'] > 1:
                dc, dm = a.LEVEL_DELTA[name]
                chips -= dc
                mult -= dm
            if boss == 'The Flint':
                chips, mult = math.floor(chips / 2 + .5), math.floor(mult / 2 + .5)
            chips += sum(11 if a.rank(cards[i]) == 14 else min(10, a.rank(cards[i]))
                         for i in scored if not a.st(cards[i]).get('debuff'))
            invalid = (boss == 'The Psychic' and n != 5 or
                       boss == 'The Eye' and h.get('played_this_round', 0) > 0 or
                       boss == 'The Mouth' and locked and locked != name)
            value = 0 if invalid else math.floor(chips * mult)
            result.append((value, indices, name, scored))
    return sorted(result, key=lambda x: (-x[0], len(x[1]), x[1]))
