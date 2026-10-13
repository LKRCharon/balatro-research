"""Public-state v6 shop/pack gate. Work candidate, not a proven strategy.
No game calls, files, seeds or hidden state. SHOP never returns None.
"""
import copy
import policy as legacy
import forecast
import shop_planning as planets
import growth_policy_v5 as core

VERSION='growth_candidate_v6'


def mod(c):return c.get('modifier') or {}


def target(s):
    return next((s['blinds'][k] for k in ('small','big','boss') if s['blinds'][k]['status'] not in ('DEFEATED','SKIPPED')),s['blinds']['boss'])


def outlook(s):
    f=forecast.estimate(s)
    # Ranking proxy; no claim q25*hands is a true whole-blind lower bound.
    value=.7*f['coverage']
    soon=copy.deepcopy(s);changed=False
    for c in soon['jokers']['cards']:
        life=mod(c).get('perishable')
        if isinstance(life,(int,float)) and not isinstance(life,bool) and life<=1:
            c.setdefault('state',{})['debuff']=True;changed=True
    if changed:value=min(value,.7*forecast.estimate(soon)['coverage'])
    return value


def income(s):
    total=0
    for c in s['jokers']['cards']:
        if c.get('state',{}).get('debuff'):continue
        if c['key']=='j_golden':total+=4
        # Rocket values and other conditional economy are not guessed.
    return total


def rent(s):return 3*sum(bool(mod(c).get('rental')) for c in s['jokers']['cards'])


def reserve(s):
    blind=target(s)['name']
    # Expected fee budget proxy, not guaranteed cost. Never count unknown income.
    fee=10 if blind=='The Tooth' else 0
    return max(0,2*rent(s)-2*income(s))+fee


def acceptable(before,after,b0,b1,new_card=None):
    rescue=b0<1<=b1
    if b1< b0+.04:return False
    if new_card and mod(new_card).get('eternal') and not rescue and b1-b0<.2:return False
    if after['money']<reserve(after) and not rescue:
        # Ordinary zero-rental purchases can spend under economic floor when
        # materially improving survival. New rentals need a real rescue.
        if new_card and mod(new_card).get('rental'):return False
        if b0>=1 or b1-b0<.25:return False
    return True


def choose_joker(s,pack=False):
    b0=outlook(s);simbase=copy.deepcopy(s)
    if pack:
        simbase['shop']=copy.deepcopy(s.get('pack',{}))
        for c in simbase['shop'].get('cards',[]):c.setdefault('cost',{})['buy']=0
    choices=[]
    for c in core.candidate_states(simbase):
        after=c['state'];b1=outlook(after);offer=simbase['shop']['cards'][c['offer_index']]
        if not acceptable(s,after,b0,b1,offer):continue
        # Preserve safe ongoing growers unless replacement wins convincingly.
        idx=c['replace_index']
        if idx is not None:
            old=s['jokers']['cards'][idx]
            if old['key'] in legacy.GROWTH and not old.get('state',{}).get('debuff') and b0>=1 and b1-b0<.25:continue
        choices.append(((b0<1<=b1,min(b1,1.6)-min(b0,1.6),(b1-b0)/max(1,c['price']+2*rent(after)),after['money']),c,b1))
    if not choices:return None
    _,c,b1=max(choices,key=lambda x:x[0]);reason=f'{VERSION}: capacity proxy {b0:.3f}->{b1:.3f}; observe again after action'
    if c['replace_index'] is not None:return 'sell',{'joker':c['replace_index'],'reason':reason}
    return ('pack' if pack else 'buy'),{'card':c['offer_index'],'reason':reason}


def fallback(s,b0,rerolls):
    cash=s.get('money',0);cost=s.get('round',{}).get('reroll_cost',5)
    if b0<1.25 and rerolls<2 and cost<=6 and cash>=cost+max(6,reserve(s)):
        return 'reroll',{'reason':VERSION+': bounded search with purchase and rental/Boss reserve'}
    return 'next_round',{'reason':VERSION+': no supported affordable improvement; capacity proxy '+str(round(b0,3))}


def action(s,evaluator=None,*,rerolls_this_shop=0):
    phase=s.get('state')
    if phase not in ('SHOP','SMODS_BOOSTER_OPENED'):return None
    if phase=='SMODS_BOOSTER_OPENED':
        cards=s.get('pack',{}).get('cards',[])
        if cards and cards[0].get('set')=='JOKER':
            return choose_joker(s,True) or ('pack',{'skip':True,'reason':VERSION+': no legal beneficial non-debt pack Joker'})
        return legacy.action(s) # revealed planets/Tarot; no cash/rental acquisition
    b0=outlook(s)
    # Preserve legal debuffed sales and ordering, without old acquisition fallback.
    for i,c in enumerate(s['jokers']['cards']):
        if c.get('state',{}).get('debuff') and not mod(c).get('eternal'):
            return 'sell',{'joker':i,'reason':VERSION+': expired component, stop ongoing rent'}
    candidate=choose_joker(s)
    if candidate:return candidate
    # Compare all visible planet upgrades, including off-route synergy.
    upgrades=[]
    for i,c in enumerate(s.get('shop',{}).get('cards',[])):
        price=c.get('cost',{}).get('buy',0)
        if c.get('set')!='PLANET' or price>s['money']:continue
        t=planets.upgraded(s,c,price)
        if t:
            v=outlook(t)
            if acceptable(s,t,b0,v):upgrades.append((v-b0,-price,i))
    if upgrades:
        i=max(upgrades)[2];return 'buy',{'card':i,'use':True,'reason':VERSION+': visible planet improves capacity before unknown packs'}
    proposal=legacy.action(s)
    if proposal is None:return fallback(s,b0,rerolls_this_shop)
    method,params=proposal
    if method in ('rearrange','use'):return proposal
    if method=='buy':
        if 'card' in params:
            c=s['shop']['cards'][params['card']]
            if c.get('key') in ('c_hermit','c_temperance'):return proposal
        elif 'voucher' in params:
            c=s['vouchers']['cards'][params['voucher']];price=c['cost']['buy']
            if b0>=1.35 and s['money']-price>=max(12,reserve(s)):return proposal
        elif 'pack' in params:
            c=s['packs']['cards'][params['pack']];price=c['cost']['buy'];key=c['key']
            free=s['jokers']['limit']-len(s['jokers']['cards'])
            early_buffoon='buffoon' in key and len(s['jokers']['cards'])<=2 and free>0
            # Unknown contents never receive a supposed immediate survival gain.
            if early_buffoon and s['money']>=price:return proposal
            if b0>=1.3 and s['money']-price>=max(10,reserve(s)):return proposal
    # In particular never delegate legacy sells/rerolls/next_round unchecked.
    return fallback(s,b0,rerolls_this_shop)
