"""Opt-in v3: bounded discard opportunity search before v2 combat.

Only public unordered unseen cards are sampled. One-draw estimates are heuristic,
not win probabilities or an entire round simulator. Preserves frozen v1/v2.
"""
import copy
import time
import no_sl_solver_v2 as v2
v1=v2.v1
a=v1.a


def discard_roots(s, options):
    cards=s['hand']['cards']; roots=[]
    protected=v2.protected_indices(s,options)
    def add(indices):
        ids=tuple(i for i in indices if i not in protected)[:5]
        if ids and ids not in roots: roots.append(ids)
    add(a.discard(s,options[0]))
    add(i for i in range(len(cards)) if i not in options[0][3])
    # Hold the most populated ranks; Trio/Duo/Family need an explicit draw route.
    groups={r:[i for i,c in enumerate(cards) if a.rank(c)==r] for r in {a.rank(c) for c in cards}}
    for group in sorted(groups.values(),key=lambda g:(len(g),max(a.rank(cards[i]) for i in g)),reverse=True)[:2]:
        add(i for i in range(len(cards)) if i not in group)
    if 'j_blackboard' in a.keys(s):
        add(i for i,c in enumerate(cards) if a.suit(c) in ('H','D'))
    # Preserve the strongest suit even if rank heuristic chased a straight.
    suits={su:[i for i,c in enumerate(cards) if a.suit(c)==su] for su in 'SHCD'}
    group=max(suits.values(),key=len)
    add(i for i in range(len(cards)) if i not in group)
    return roots


def after_discard(s,indices,world):
    after,_=v1.transition(s,'discard',indices,world)
    # Explicit known immediate discard costs; current values remain public.
    for j in after['jokers']['cards']:
        if a.st(j).get('debuff'):continue
        if j['key']=='j_green_joker':value=max(0,a.current_number(j)-1)
        elif j['key']=='j_ramen':
            value=a.current_number(j,1)-.01*len(indices)
            if value<=1:raise ValueError('ramen extinction requires slot transition')
        else:continue
        j.setdefault('value',{})['effect']=f'当前 {value}'
    return after


def choose(state,config=None):
    cfg=v1.config_values(config);s=v2.public_state(state)
    if s.get('state')!='SELECTING_HAND':raise ValueError('Combat state required')
    options=a.options(s,optimize_order=True);best=options[0][0]
    need=v1.static.boss(s)['score']-s['round']['chips']
    lower=a.conservative_score(s,options[0][1],best)
    hidden=any(a.st(c).get('hidden') for c in s['hand']['cards'])
    # Unknown boss draw/discard mutations and hidden identities remain v2 scope.
    allowed_boss=v1.static.boss(s).get('name') in v1.static.SAFE_BOSSES
    uncertain_discard=a.keys(s)&{'j_castle','j_hit_the_road','j_trading','j_burnt','j_yorick'}
    if (s['round']['discards_left']<=0 or (lower is not None and lower>=need) or hidden or
        not allowed_boss or uncertain_discard or not s.get('_belief',{}).get('unseen') or
        s.get('_belief',{}).get('hidden_identity_approximation')):
        return v2.choose(s,config)
    worlds=v1.static.scenarios(s,min(cfg['samples'],4));rows=[]
    deadline=time.monotonic()+cfg['time_budget']
    for indices in discard_roots(s,options):
        values=[]
        for world in worlds:
            if time.monotonic()>deadline:break
            try:after=after_discard(s,indices,world)
            except ValueError:break
            values.append(min(need,a.options(after,optimize_order=True)[0][0]))
        if len(values)!=len(worlds):break
        values.sort()
        rows.append({'cards':list(indices),'mean':sum(values)/len(values),
            'minimum':min(values),'improve_fraction':sum(x>best for x in values)/len(values),
            'clear_fraction':sum(x>=need for x in values)/len(values)})
    # Compare one scoring opportunity against one scoring opportunity, not the
    # unequal play+play versus discard+play horizon in the old search.
    pressure=best*s['round']['hands_left']<need
    eligible=[r for r in rows if r['mean']>min(need,best)*1.25 and
        (r['improve_fraction']>=.5 or pressure and r['clear_fraction']>0)]
    if eligible:
        row=max(eligible,key=lambda r:(r['clear_fraction'],r['mean'],r['minimum']))
        return v1.action_for(s,'discard',row['cards'],{
            'mode':'v3_discard_opportunity','no_save_load':True,'future_draw_order_used':False,
            'optimality_claim':False,'sample_fraction_is_calibrated_probability':False,
            'mutable_play_growth_frozen':True,'model_horizon_actions':1,
            'current_best_score':best,'capacity_pressure':pressure,'discard_candidates':rows,
            'samples':len(worlds),'heuristic_gain_threshold':1.25})
    return v2.choose(s,config)

# Keep the opportunity search independently testable; final action guard applies
# equally to its early v2 fallbacks (including hidden-card fallback states).
_choose_opportunity = choose


def choose(state, config=None):
    result = _choose_opportunity(state, config)
    s = v2.public_state(state)
    if result['method'] == 'rearrange' and result['params'].get('hand') == list(range(len(s['hand']['cards']))):
        options = a.options(s, optimize_order=True)
        diag = dict(result['diagnostics'], noop_rearrangement_avoided=True)
        result = v1.action_for(s, 'play', sorted(options[0][1]), diag)
    if (s['round']['hands_left'] != 1 or s['round']['discards_left'] <= 0 or
        result['method'] not in ('play', 'rearrange')):
        return result
    options = a.options(s, optimize_order=True)
    need = v1.static.boss(s)['score'] - s['round']['chips']
    # Below-target *expected* scores are not proof of certain death for random
    # mechanics, so diagnostics deliberately say model shortfall, not certainty.
    if options[0][0] >= need:
        return result
    hidden = [i for i,c in enumerate(s['hand']['cards']) if a.st(c).get('hidden')]
    rows = result['diagnostics'].get('discard_candidates', [])
    roots = discard_roots(s, options)
    if hidden:
        indices = hidden[:5]
    elif rows:
        indices = max(rows, key=lambda r:(r['clear_fraction'],r['mean'],r['minimum']))['cards']
    elif roots:
        indices = list(roots[0])
    else:
        # Protection is a preference, never a reason to spend a losing final
        # hand. Replace one weakest visible card when every root was protected.
        indices = [min(range(len(s['hand']['cards'])), key=lambda i:a.rank(s['hand']['cards'][i]))]
    if v1.static.boss(s).get('name') == 'Cerulean Bell':
        forced = [i for i,c in enumerate(s['hand']['cards']) if a.st(c).get('highlight')]
        indices = (forced + [i for i in indices if i not in forced])[:5]
    diag = dict(result['diagnostics'], mode='v3_last_hand_preserve_redraw',
        last_hand_model_shortfall=True, current_best_score=options[0][0],
        remaining_target=need, zero_sample_clears_do_not_prove_impossibility=True,
        fallback_is_heuristic=True)
    return v1.action_for(s, 'discard', indices, diag)
