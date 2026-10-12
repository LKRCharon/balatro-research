"""Bounded no-save/load combat search over public card multisets only.

No RPC, engine seed, save, reload, or actual future draw order. Current-hand
scores enumerate advisor-supported subsets/order variants, NOT every permutation.
Forward search is a static-mechanics two-action approximation, not optimal play.
"""
import copy
import importlib.util
import itertools
from pathlib import Path
import sys
import time

LAB=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(LAB/'experiments/policies/route_v3'),str(LAB/'cli')]
import advisor as a
_spec=importlib.util.spec_from_file_location('no_sl_static_model',LAB/'experiments/policies/route_v4/combat.py')
static=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(static)

DEFAULTS={'samples':8,'max_candidates':10,'time_budget':3.0}


def config_values(config):
    cfg=dict(DEFAULTS,**(config or {}))
    if 'candidates' in cfg:cfg['max_candidates']=cfg.pop('candidates')
    if type(cfg['samples']) is not int or not 1<=cfg['samples']<=64:raise ValueError('samples must be 1..64')
    if type(cfg['max_candidates']) is not int or not 1<=cfg['max_candidates']<=32:raise ValueError('max_candidates must be 1..32')
    if not 0<float(cfg['time_budget'])<=60:raise ValueError('time_budget must be positive and <=60')
    return cfg


def continuation(after):
    """Choose using resulting public state only. No scenario-tail argument."""
    if after['round']['hands_left']<=0 or not after['hand']['cards']:return 0
    return max((o[0] for o in a.options(after,optimize_order=True)),default=0)


def transition(state,method,indices,world):
    after,_,scored=static.transition(state,method,indices,world)
    # Wild counts as every suit when evaluating a suit-debuff Boss.
    current=static.boss(state).get('name')
    if current in ('The Club','The Goad','The Window','The Head') and not (state.get('_boss_disabled') or 'j_chicot' in a.keys(state)):
        for card in after['hand']['cards']:
            if a.mod(card).get('enhancement')=='WILD':card.setdefault('state',{})['debuff']=True
    return after,scored


def roots(state,options,limit):
    found=[]
    def add(method,indices):
        item=(method,tuple(indices))
        if item[1] and len(item[1])<=5 and item not in found:found.append(item)
    add('play',options[0][1])
    # A one-card Serpent discard draws three. Reserve it before play variants.
    if state['round']['discards_left']>0 and static.boss(state).get('name')=='The Serpent':
        scored=set(options[0][3]);junk=[i for i in range(len(state['hand']['cards'])) if i not in scored]
        for i in (junk or list(range(len(state['hand']['cards']))))[:2]:add('discard',[i])
    if state['round']['discards_left']>0:
        add('discard',a.discard(state,options[0]))
        add('discard',[i for i in range(len(state['hand']['cards'])) if i not in options[0][3]][:5])
    tied=[o for o in options if o[0]==options[0][0] and o[2]==options[0][2]]
    for option in sorted(tied,key=lambda o:(-len(o[1]),o[1]))[:2]:add('play',option[1])
    categories=set()
    for option in options:
        if option[2] not in categories:
            add('play',option[1]);categories.add(option[2])
        if len(found)>=limit:break
    for option in options:
        if len(found)>=limit:break
        add('play',option[1])
    return found[:limit]


def action_for(state,method,indices,diagnostics):
    indices=list(indices)
    if method=='play' and indices!=sorted(indices):
        order=indices+[i for i in range(len(state['hand']['cards'])) if i not in indices]
        diagnostics['planned_play_order']=indices
        return {'method':'rearrange','params':{'hand':order,'reason':'公开数值搜索选定计分顺序，先在实际手牌中排序；没有模拟读取未来抽牌。'},'diagnostics':diagnostics}
    return {'method':method,'params':{'cards':indices,'reason':'无存读档公开信息战斗搜索；'+diagnostics['mode']+'；只执行当前动作，下一步重新读取实际公开局面。'},'diagnostics':diagnostics}


def heuristic_fallback(state,options,need,diagnostics):
    """Public, explicit resource heuristic; not a simulation or optimality claim."""
    best=options[0];method='play';indices=best[1]
    if state['round']['discards_left']>0:
        hidden=[i for i,c in enumerate(state['hand']['cards']) if a.st(c).get('hidden') or a.st(c).get('face_down')]
        discarded=a.discard(state,best)
        capacity=best[0]*state['round']['hands_left']
        expensive=bool(a.keys(state)&{'j_green_joker','j_banner','j_ramen'})
        burnt_pair=next((o for o in options if o[2]=='Pair' and len(o[1])==2),None)
        if hidden:
            method='discard';indices=hidden[:5];diagnostics['heuristic_reason']='replace_hidden_cards'
        elif 'j_burnt' in a.keys(state) and state['round'].get('discards_used',0)==0 and burnt_pair:
            method='discard';indices=burnt_pair[1];diagnostics['heuristic_reason']='burnt_first_discard_pair_upgrade'
        elif (best[0]<need and capacity<need*1.15 and discarded
              and not (expensive and capacity>=need)):
            method='discard';indices=discarded;diagnostics['heuristic_reason']='visible_score_capacity_pressure'
        else:diagnostics['heuristic_reason']='retain_best_visible_play'
    if method=='discard' and static.boss(state).get('name')=='Cerulean Bell':
        forced=[i for i,c in enumerate(state['hand']['cards']) if a.st(c).get('highlight')]
        indices=sorted((forced+[i for i in indices if i not in forced])[:5])
        diagnostics['cerulean_forced_cards_included']=forced
    diagnostics['fallback_is_heuristic']=True
    return action_for(state,method,indices,diagnostics)


def choose(state,config=None):
    cfg=config_values(config);started=time.monotonic()
    if state.get('state')!='SELECTING_HAND':raise ValueError('Combat state required; solver never selects shop actions')
    options=a.options(state,optimize_order=True)
    if not options:raise ValueError('No current-hand scoring candidates')
    boss=static.boss(state);need=boss['score']-state['round']['chips']
    diag={'mode':'deterministic_local_score','no_save_load':True,'future_draw_order_used':False,
          'order_search_exhaustive':False,'order_scope':'advisor subset enumeration plus supported first-card reorder variants',
          'optimality_claim':False,'current_options':len(options),'ranked_candidates':[],
          'samples_requested':cfg['samples'],'forward_supported':False,'model_horizon_actions':2,
          'models_entire_remaining_round':False,
          'horizon_limit':'root play/discard followed by one best visible play; may understate longer-round survival'}
    # A conservative bound certifies only this implemented current-hand model.
    for option in options:
        lower=a.conservative_score(state,option[1],option[0])
        if lower is not None and lower>=need:
            diag.update(mode='current_model_immediate_clear',model_clear_bound=lower,
                        guaranteed_engine_clear=False,elapsed_seconds=time.monotonic()-started)
            return action_for(state,'play',option[1],diag)
    reason=static.support_reason(state)
    if reason:
        diag.update(fallback_reason=reason,uncertain=a.uncertain(state),elapsed_seconds=time.monotonic()-started)
        return heuristic_fallback(state,options,need,diag)
    diag['forward_supported']=True
    candidates=roots(state,options,cfg['max_candidates'])
    worlds=static.scenarios(state,cfg['samples'])
    rows=[];deadline=started+float(cfg['time_budget']);cache={}
    for method,indices in candidates:
        values=[]
        for world in worlds:
            if time.monotonic()>=deadline:break
            after,scored=transition(state,method,indices,world)
            if scored>=need:total=scored
            else:
                # Canonical public state hides the sampled residual permutation;
                # continuation never receives or traverses that permutation.
                key=static.json.dumps({k:after[k] for k in ('hand','jokers','round','hands','blinds','cards','money')},sort_keys=True)
                if key not in cache:cache[key]=continuation(after)
                total=scored+cache[key]
            values.append(min(need,total))
        if len(values)!=len(worlds):break # Never compare uneven/partial sample counts.
        values.sort();clear=sum(x>=need for x in values)/len(values)
        rows.append({'method':method,'indices':list(indices),'sample_clear_fraction':clear,
                     'lower_quartile_score':values[max(0,len(values)//4-1)],'mean_capped_score':sum(values)/len(values),
                     'samples':len(values)})
    rows.sort(key=lambda r:(r['sample_clear_fraction'],r['lower_quartile_score'],r['mean_capped_score'],r['method']=='play'),reverse=True)
    diag.update(mode='approximate_public_belief_two_action',ranked_candidates=rows,
        candidates_requested=len(candidates),candidates_fully_evaluated=len(rows),
        budget_exhausted=len(rows)<len(candidates),time_budget_is_soft=True,
        sample_fraction_is_calibrated_probability=False,elapsed_seconds=time.monotonic()-started)
    if not rows:
        diag['fallback_reason']='time_budget_before_complete_candidate'
        return heuristic_fallback(state,options,need,diag)
    best=rows[0]
    return action_for(state,best['method'],best['indices'],diag)
