"""Candidate v4: public hypothetical whole-blind greedy continuation.
Approximation only; mutable effects not listed below delegate to v3.
"""
import copy,time
import no_sl_solver_v3 as old
v1=old.v1
a=old.a
GROWTH={'j_green_joker','j_ride_the_bus','j_runner','j_square','j_trousers','j_supernova','j_ice_cream','j_popcorn','j_gros_michel','j_swashbuckler','j_fortune_teller','j_red_card','j_flash','j_ceremonial','j_campfire','j_constellation','j_throwback','j_madness','j_ramen'}


def transition(s,method,indices,world):
    if method=='discard':
        after=old.after_discard(s,indices,world)
        drawn=s['cards']['count']-after['cards']['count']
        return after,world[drawn:],0
    score,name,scored=a.score(s,indices)
    after,tail,_=v1.static.transition(s,method,indices,world)
    for j in after['jokers']['cards']:
        if a.st(j).get('debuff'):continue
        k=j['key'];val=a.current_number(j)
        if k=='j_green_joker':val+=1
        elif k=='j_runner':val+=15*(name in ('Straight','Straight Flush'))
        elif k=='j_square':val+=4*(len(indices)==4)
        elif k=='j_trousers':
            _,_,counts=a.classify(s['hand']['cards'],indices)
            val+=2*(sum(v>=2 for v in counts.values())>=2)
        elif k=='j_ride_the_bus':
            face=any(a.rank(s['hand']['cards'][i]) in (11,12,13) or 'j_pareidolia' in a.keys(s) for i in scored)
            val=0 if face else val+1
        elif k=='j_ice_cream':val=max(0,val-5)
        else:continue
        j.setdefault('value',{})['effect']=f'当前 {val}'
    return after,tail,score


def play_option(s):
    options=a.options(s,optimize_order=True)
    best=options[0]
    # Cycle score-neutral junk within actual Half/Blackboard constraints, instead
    # of repeatedly playing only one card and seeing only one replacement.
    held_economy={i for i,c in enumerate(s['hand']['cards']) if a.mod(c).get('enhancement')=='GOLD' or a.mod(c).get('seal')=='BLUE'}
    tied=[o for o in options if o[0]==best[0] and o[2]==best[2] and not (set(o[1])-set(best[1]))&held_economy]
    return max(tied,key=lambda o:len(o[1]))


def rollout(s,method,indices,world,deadline):
    total=0;sim=s;tail=world;steps=0
    while sim['round']['hands_left']>0:
        if time.monotonic()>deadline:return None
        sim,tail,points=transition(sim,method,indices,tail)
        total+=points;steps+=1
        if total>=v1.static.boss(s)['score']-s['round']['chips']:return total
        if not sim['round']['hands_left'] or not sim['hand']['cards']:break
        best=play_option(sim)
        method,indices='play',best[1]
        # Continuation sees resulting hand only. Retain a pair for a Trio route
        # only on the last hand when its current score demonstrably falls short.
        if sim['round']['hands_left']==1 and sim['round']['discards_left']>0 and best[0]<v1.static.boss(s)['score']-s['round']['chips']-total:
            roots=old.discard_roots(sim,[best])
            if roots:method,indices='discard',roots[0]
        if steps>12:break
    return total


def choose(state,config=None):
    cfg=v1.config_values(config);s=old.v2.public_state(state)
    keys=a.keys(s)
    if (s.get('state')!='SELECTING_HAND' or keys-(v1.static.SAFE_JOKERS|GROWTH) or
        any(a.st(c).get('hidden') for c in s['hand']['cards']) or
        s.get('_belief',{}).get('hidden_identity_approximation') or
        not s.get('_belief',{}).get('unseen') or
        v1.static.boss(s).get('name') not in v1.static.SAFE_BOSSES or a.uncertain(s) or
        any(a.mod(c).get('enhancement') in ('GLASS','LUCKY') or a.mod(c).get('seal') in ('PURPLE','GOLD') for c in s['hand']['cards']+s.get('_belief',{}).get('unseen',[]))):
        return old.choose(s,config)
    options=a.options(s,optimize_order=True);best=options[0]
    need=v1.static.boss(s)['score']-s['round']['chips']
    if best[0]>=need:return v1.action_for(s,'play',best[1],{'mode':'v4_immediate_model_clear','optimality_claim':False})
    roots=[('play',play_option(s)[1])]
    if s['round']['discards_left']>0:
        roots += [('discard',r) for r in old.discard_roots(s,options)]
    worlds=v1.static.scenarios(s,min(3,cfg['samples']));rows=[]
    deadline=time.monotonic()+cfg['time_budget']
    for method,indices in roots:
        vals=[]
        for world in worlds:
            try:value=rollout(s,method,indices,world,deadline)
            except ValueError:value=None
            if value is None:break
            vals.append(min(need,value))
        if len(vals)!=len(worlds):break
        rows.append({'method':method,'indices':list(indices),'clear_fraction':sum(x>=need for x in vals)/len(vals),'minimum':min(vals),'mean':sum(vals)/len(vals)})
    if len(rows)<2:return old.choose(s,config)
    allowed=[r for r in rows if not (s['round']['hands_left']==1 and s['round']['discards_left']>0 and r['method']=='play' and best[0]<need)]
    if not allowed:return old.choose(s,config)
    row=max(allowed,key=lambda r:(r['clear_fraction'],r['minimum'],r['mean'],r['method']=='play'))
    return v1.action_for(s,row['method'],row['indices'],{'mode':'v4_whole_blind_greedy_public_rollout','optimality_claim':False,'future_draw_order_used':False,'scenario_future_is_hypothetical':True,'no_save_load':True,'ranked_candidates':rows,'samples':len(worlds),'sample_fraction_is_calibrated_probability':False,'greedy_continuation_not_optimal':True})
