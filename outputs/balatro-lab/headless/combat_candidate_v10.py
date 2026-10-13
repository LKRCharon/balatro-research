"""Public candidate: preserve Bus scaling and cycle score-neutral extra cards.

Uses v6 discard pacing and cautious growth. Preserves conservative model clears. Greedy current-hand ranking is an
approximation; no complete-round optimality or win probability is claimed.
"""
import combat_candidate_v6 as prior
import combat_candidate_v4 as cycle
from collections import Counter
a=cycle.a
v1=cycle.v1


def playable(s):
    options=a.options(s,optimize_order=True)
    need=v1.static.boss(s)['score']-s['round']['chips']
    # An expected-score winner must never displace a conservative current clear.
    # Restrict cycling too: equal expectation does not imply equal lower bound.
    clears=[]
    for option in options:
        bound=a.conservative_score(s,option[1],option[0])
        if bound is not None and bound>=need:clears.append(option)
    if clears:options=clears
    best=options[0]
    if 'j_ride_the_bus' in a.keys(s) and best[0]<need:
        safe=[o for o in options if not any(a.rank(s['hand']['cards'][i]) in (11,12,13) or
                   'j_pareidolia' in a.keys(s) for i in o[3])]
        if safe and safe[0][0]>=best[0]*.7: best=safe[0]
    economy={i for i,c in enumerate(s['hand']['cards']) if a.mod(c).get('enhancement')=='GOLD' or a.mod(c).get('seal')=='BLUE'}
    tied=[o for o in options if o[0]==best[0] and o[2]==best[2] and
          not (set(o[1])-set(best[1]))&economy]
    if 'j_ride_the_bus' in a.keys(s):
        safe_tied=[o for o in tied if not any(a.rank(s['hand']['cards'][i]) in (11,12,13) or
                    'j_pareidolia' in a.keys(s) for i in o[3])]
        if safe_tied: tied=safe_tied
    def cycling_value(option):
        held=[c for i,c in enumerate(s['hand']['cards']) if i not in option[1]]
        suits=Counter(a.suit(c) for c in held if not a.st(c).get('debuff'))
        ranks=Counter(a.rank(c) for c in held if not a.st(c).get('debuff'))
        near_flush=max(suits.values(),default=0)>=4
        pair=max(ranks.values(),default=0)>=2
        # Retain a near-complete new scoring core when two more junk cards
        # would break it. Only score-neutral, same-hand options are compared.
        return len(option[1])+3*near_flush+pair,len(option[1])
    return max(tied,key=cycling_value)


def choose(state,config=None):
    result=prior.choose(state,config)
    rows=result.get('diagnostics',{}).get('discard_candidates',[])
    if result['method']=='discard' and rows and state['round']['hands_left']>1 and all('mean' in r and 'minimum' in r for r in rows):
        row=max(rows,key=lambda r:(.8*r['mean']+.2*r['minimum'],r.get('quota_fraction',0)))
        result=v1.action_for(state,'discard',row['cards'],dict(result['diagnostics'],
                mode='v10_discard_mean_and_lower_tail',discard_ranking_not_win_probability=True))
    if result['method'] not in ('play','rearrange'): return result
    if result['diagnostics'].get('mode')=='v6_one_safe_model_growth_hand': return result
    s=cycle.old.v2.public_state(state)
    if any(a.st(c).get('hidden') for c in s['hand']['cards']): return result
    best=playable(s)
    return v1.action_for(s,'play',best[1],dict(result['diagnostics'],
            mode='v10_preserve_model_clear_and_cycle',previous_mode=result['diagnostics']['mode'],
            selected_conservative_bound=a.conservative_score(s,best[1],best[0]),
            guaranteed_engine_clear=False,bus_scaling_preference=True,score_neutral_cycle=True,optimality_claim=False))
