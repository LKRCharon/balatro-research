"""Opt-in conservative one-hand growth before an existing model clear.
Does not claim engine certainty. Pays one hand-dollar only when public model
shows useful persistent growth while retaining an unchanged winning card core.
"""
import copy
import combat_candidate_v5 as previous
prior=previous.prior
v1=previous.v1
a=previous.a
GROWERS={'j_green_joker','j_ride_the_bus','j_supernova'}
# No held-card, random, copy, cash-sensitive, destruction, or shape-changing
# abilities: the retained scoring core must remain independently meaningful.
ALLOWED=GROWERS|{'j_joker','j_abstract','j_half','j_banner','j_blue_joker','j_stuntman','j_gros_michel','j_popcorn','j_swashbuckler','j_fibonacci','j_odd_todd','j_even_steven','j_scholar','j_scary_face','j_smiley','j_sly','j_jolly','j_zany','j_wily','j_duo','j_trio','j_family'}
BOSSES={'Small Blind','Big Blind','The Wall','Violet Vessel'}


def growth_action(state):
    if state.get('state')!='SELECTING_HAND':return None
    s=previous.old.v2.public_state(state);keys=a.keys(s)
    if (not keys&GROWERS or keys-ALLOWED or s['round']['hands_left']<3 or
        s['round'].get('hands_played',0)!=0 or s.get('money',0)<15 or
        s.get('ante_num',8)>=8 or v1.static.boss(s).get('name') not in BOSSES or
        a.uncertain(s) or any(a.st(c).get('hidden') or a.mod(c).get('enhancement') or a.mod(c).get('seal') for c in s['hand']['cards'])):
        return None
    options=a.options(s,optimize_order=True);need=v1.static.boss(s)['score']-s['round']['chips']
    winning=[o for o in options if (a.conservative_score(s,o[1],o[0]) or 0)>=need]
    if not winning:return None
    # A smaller independently winning core leaves the greatest room for junk.
    core=min(winning,key=lambda o:(len(o[1]),-o[0]));held=set(core[1])
    candidates=[]
    for option in options:
        if set(option[1])&held or option[0]>=need:continue
        if 'j_ride_the_bus' in keys and any(a.rank(s['hand']['cards'][i]) in (11,12,13) for i in option[3]):continue
        # Playing another type does not train the winning Supernova route.
        if keys&GROWERS=={'j_supernova'} and option[2]!=core[2]:continue
        after,_,points=prior.transition(s,'play',option[1],[])
        remaining=[i for i in range(len(s['hand']['cards'])) if i not in option[1]]
        retained=[remaining.index(i) for i in core[1]]
        reserve=a.conservative_score(after,retained)
        baseline=copy.deepcopy(after)
        baseline['jokers']=copy.deepcopy(s['jokers'])
        baseline['hands']=copy.deepcopy(s['hands'])
        baseline_score=a.conservative_score(baseline,retained)
        if reserve is None or baseline_score is None or reserve<need-points:continue
        gain=reserve-baseline_score
        relative=gain/max(1,baseline_score)
        threshold=.03 if s['money']>=25 else .08
        if gain<=0 or relative<threshold:continue
        candidates.append((relative,gain,option,core,reserve,points))
    if not candidates:return None
    relative,gain,option,core,reserve,points=max(candidates,key=lambda x:(x[0],x[1],-len(x[2][1])))
    return v1.action_for(s,'play',option[1],{
        'mode':'v6_one_safe_model_growth_hand','optimality_claim':False,
        'guaranteed_engine_clear':False,'no_save_load':True,'future_draw_order_used':False,
        'retained_winning_indices':core[1],'retained_model_clear_bound':reserve,
        'remaining_target_after_growth_play':need-points,
        'persistent_route_score_gain':gain,'persistent_relative_gain':relative,
        'foregone_hand_income':1,'income_tradeoff_is_heuristic':True,
        'at_most_one_growth_play_per_blind':True})


def choose(state,config=None):
    v1.config_values(config)
    return growth_action(state) or previous.choose(state,config)
