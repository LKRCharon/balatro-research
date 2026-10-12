"""Opt-in public-only combat corrections. Does not change frozen v1 dependencies.

Bounds certify the implemented score model, never the engine. Discard protection
is a conservative heuristic and is not a probability or optimality claim.
"""
import copy
import no_sl_solver as v1

a = v1.a


def public_state(state):
    s = copy.deepcopy(state)
    for i, card in enumerate(s.get('hand', {}).get('cards', [])):
        if a.st(card).get('hidden') or a.st(card).get('face_down'):
            s['hand']['cards'][i] = {'key': 'hidden', 'value': {}, 'modifier': {},
                'state': {'hidden': True, 'highlight': bool(a.st(card).get('highlight'))}}
    return s


def visible_lower_options(state):
    """Anonymous held cards supply no bonuses; unknown predicates are rejected."""
    hidden = {i for i, c in enumerate(state['hand']['cards']) if a.st(c).get('hidden')}
    if not hidden:
        return []
    if (state.get('_uncertain_jokers') or
        a.keys(state) & {'j_blackboard', 'j_space', 'j_bloodstone', 'j_lucky_cat',
                        'j_business', 'j_reserved_parking', 'j_loyalty_card'} or
        v1.static.boss(state).get('name') in {'The Hook', 'The Ox'}):
        return []
    lower = copy.deepcopy(state)
    lower['_normal_probability'] = 0
    # Zero Misprint, including copied ability and its edition: deliberately looser
    # than its actual [0, 23] bonus, while retaining its physical occupied slot.
    for joker in lower['jokers']['cards']:
        if joker['key'] == 'j_misprint':
            joker.setdefault('state', {})['debuff'] = True
    return [o for o in a.options(lower, optimize_order=True) if not hidden.intersection(o[1])]


def protected_indices(state, options):
    """Retain enhanced scoring core and held Steel/Gold; no hidden identities."""
    best = options[0]
    core = set(best[3])
    return {i for i, c in enumerate(state['hand']['cards'])
            if not a.st(c).get('hidden') and not a.st(c).get('debuff') and
            (a.mod(c).get('enhancement') in {'STEEL', 'GOLD'} or
             (i in core and a.mod(c).get('enhancement') in
              {'GLASS', 'MULT', 'BONUS', 'STONE', 'LUCKY', 'WILD'}))}


def choose(state, config=None):
    v1.config_values(config)
    if state.get('state') != 'SELECTING_HAND':
        raise ValueError('Combat state required')
    s = public_state(state)
    need = v1.static.boss(s)['score'] - s['round']['chips']
    for option in visible_lower_options(s):
        if option[0] >= need:
            return v1.action_for(s, 'play', option[1], {
                'mode': 'v2_visible_only_model_clear', 'model_clear_bound': option[0],
                'guaranteed_engine_clear': False, 'no_save_load': True,
                'future_draw_order_used': False, 'forward_supported': False,
                'optimality_claim': False, 'misprint_lower_bound_zero': True,
                'hidden_held_bonuses_omitted': True})
    result = v1.choose(s, config)
    result['diagnostics']['solver_revision'] = 'v2_opt_in'
    if result['method'] != 'discard' or not result['diagnostics'].get('fallback_is_heuristic'):
        return result
    options = a.options(s, optimize_order=True)
    protected = protected_indices(s, options)
    selected = result['params']['cards']
    if not protected.intersection(selected):
        return result
    # Bell's mandatory card takes precedence over heuristic retention.
    forced = {i for i, c in enumerate(s['hand']['cards']) if a.st(c).get('highlight')} if v1.static.boss(s).get('name') == 'Cerulean Bell' else set()
    kept = [i for i in selected if i not in protected or i in forced]
    diag = result['diagnostics']
    diag.update(protected_enhanced_indices=sorted(protected),
                discard_protection_is_heuristic=True,
                heuristic_reason='retain_enhanced_scoring_core')
    if kept:
        return v1.action_for(s, 'discard', kept, diag)
    diag['heuristic_reason'] = 'all_proposed_discards_protected_play_best'
    return v1.action_for(s, 'play', options[0][1], diag)
