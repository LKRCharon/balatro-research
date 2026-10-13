"""Pure public-state shop candidate planner. No RPC, seed access or frozen edits.
Evaluator contract: {capacity: number, target: number, verified: bool}; capacity
must come from a whole-blind resource model, not best-hand times hands.
"""
import copy
import math


def mod(c):return c.get('modifier') or {}


def candidate_states(s):
    held=s['jokers']['cards']
    for index,offer in enumerate(s.get('shop',{}).get('cards',[])):
        if offer.get('set')!='JOKER':continue
        price=offer.get('cost',{}).get('buy')
        if not isinstance(price,(int,float)):continue
        for target in [None]+[i for i,c in enumerate(held) if not mod(c).get('eternal')]:
            t=copy.deepcopy(s);sale=0
            if target is not None:
                old=t['jokers']['cards'].pop(target);sale=old.get('cost',{}).get('sell',0)
                t['jokers']['limit']-=int(mod(old).get('edition')=='NEGATIVE')
            t['jokers']['cards'].insert(len(t['jokers']['cards']) if target is None else target,copy.deepcopy(offer))
            t['jokers']['limit']+=int(mod(offer).get('edition')=='NEGATIVE')
            t['jokers']['count']=len(t['jokers']['cards']);t['money']=s.get('money',0)+sale-price
            if t['money']<0 or t['jokers']['count']>t['jokers']['limit']:continue
            yield {'state':t,'offer_index':index,'replace_index':target,'price':price,'key':offer['key']}


def expiring_state(s):
    t=copy.deepcopy(s)
    for c in t['jokers']['cards']:
        life=mod(c).get('perishable')
        if isinstance(life,(int,float)) and not isinstance(life,bool) and life<=1:
            c.setdefault('state',{})['debuff']=True
    return t


def rental(s):return 3*sum(bool(mod(c).get('rental')) for c in s['jokers']['cards'])


def evaluate(s,evaluator):
    now=evaluator(copy.deepcopy(s));later=evaluator(expiring_state(s))
    valid=lambda v: v.get('verified') is True and all(isinstance(v.get(k),(int,float)) and math.isfinite(v[k]) for k in ('capacity','target')) and v['target']>0
    if not valid(now) or not valid(later):return None
    # Expiry scenario shares target; it is a stress case, not next-round forecast.
    return min(now['capacity']/now['target'],later['capacity']/later['target'])


def choose(s,evaluator,*,rerolls_this_shop=0):
    """Return one action and diagnostics, reobserve before the next call.

    For replacement this returns only sell. All sale-trigger dynamics require a
    fresh subsequent state; callers must never blindly queue the purchase.
    """
    base=evaluate(s,evaluator)
    if base is None:return {'action':None,'reason':'unverified_capacity','requires_review':True}
    ranked=[]
    for c in candidate_states(s):
        after=evaluate(c['state'],evaluator)
        if after is None:continue
        improvement=after-base
        if improvement<=.03:continue
        rent_delta=rental(c['state'])-rental(s)
        # Reject unsustainable marginal rental gains; accept actual rescue even
        # with low reserves. Eternal allocation must buy substantial capacity.
        offer=s['shop']['cards'][c['offer_index']]
        rescue=base<1<=after
        if rent_delta>0 and c['state']['money']<2*rent_delta and not rescue and improvement<.4:continue
        if mod(offer).get('eternal') and improvement<.15 and not rescue:continue
        rank=(rescue,min(after,1.5)-min(base,1.5),improvement/max(1,c['price']+max(0,rent_delta)*2),-c['price'])
        ranked.append((rank,c,after))
    if ranked:
        _,c,after=max(ranked,key=lambda v:v[0]);target=c['replace_index']
        method='sell' if target is not None else 'buy';params={'joker':target} if target is not None else {'card':c['offer_index']}
        return {'action':(method,params),'reason':'whole_blind_capacity_gain','baseline_coverage':base,'candidate_coverage':after,'candidate_key':c['key'],'must_reobserve':True}
    cash=s.get('money',0);cost=s.get('round',{}).get('reroll_cost',5)
    # Preserve ability to buy a discovered ordinary Joker; bounded search avoids
    # repeated refreshes exhausting all money. No unknown pack contents valued.
    if base<1.25 and rerolls_this_shop<2 and cash>=cost+6 and cost<=6:
        return {'action':('reroll',{}),'reason':'unsafe_search_with_purchase_reserve','baseline_coverage':base,'must_reobserve':True}
    return {'action':None,'reason':'no_supported_improvement','baseline_coverage':base,'requires_review':base<1}

def action(publicstate, evaluator=None, *, rerolls_this_shop=0):
    """Harness adapter: one SHOP action or None to delegate.

    An explicitly supplied evaluator is preferred. Default uses frozen route_v3
    forecast only as an uncalibrated ranking proxy with 0.7 capacity haircut;
    this does NOT certify whole-blind survival. No combat actions are emitted.
    """
    if publicstate.get('state')!='SHOP':return None
    if evaluator is None:
        import forecast
        def evaluator(s):
            f=forecast.estimate(s)
            return {'capacity':.7*f['q25']*f['hands'],'target':f['target'],'verified':True}
    result=choose(publicstate,evaluator,rerolls_this_shop=rerolls_this_shop)
    return result['action']
