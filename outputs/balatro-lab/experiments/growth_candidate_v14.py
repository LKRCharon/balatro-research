"""TRAIN candidate: budgeted growth/economy with visible Boss preparation.

Projected growth is an explicit ranking assumption, not guaranteed capacity.
No future offers, seed or draw order is available to this module.
"""
import copy
import re
import growth_candidate_v6 as prior
import forecast
import policy as legacy
import advisor as a
import routes
import strategy
import round_capacity_v2 as round_capacity
import shop_planning as planets

VERSION = 'growth_candidate_v14'
LAST_DIAGNOSTICS = {}
EARLY_TOOLS = {'j_golden', 'j_rocket', 'j_mail', 'j_riff_raff', 'j_cartomancer',
               'j_burnt', 'j_dna', 'j_trading', 'j_certificate', 'j_hiker',
               'j_wee', 'j_invisible', 'j_perkeo', 'j_chaos'}


def ordered(s):
    t = copy.deepcopy(s)
    if not a.keys(t) & {'j_blueprint', 'j_brainstorm'}:
        t['jokers']['cards'].sort(key=lambda c: int(c['key'] in legacy.XMULT or
                                        a.mod(c).get('edition') == 'POLYCHROME'))
    return t


def outlook(s):
    t = ordered(s)
    def measure(x):
        f = round_capacity.estimate(x,samples=4,budget=2.0)
        if f['available']:
            unknown_boss=any(x.startswith('unmodeled_boss:') for x in f.get('limitations',[]))
            discount=.5 if unknown_boss else 1.0
            LAST_DIAGNOSTICS.setdefault('capacity_evaluations',[]).append({
                'samples':f['samples'],'limitations':f.get('limitations',[]),
                'unknown_boss_risk':unknown_boss,'heuristic_discount':discount,
                'discount_is_calibrated':False,'capacity_is_safety_certificate':False})
            return discount*(.5*f['q25']+.5*f['mean'])/max(1,f['target'])
        fallback = forecast.estimate(x)
        return .7*(.4*fallback['q25']+.6*fallback['median'])*fallback['hands']/max(1,fallback['target'])
    value = measure(t)
    expiry = future_resources(t,1)
    return min(value,measure(expiry)) if expiry != t else value


def future_resources(s, rounds=1):
    """Bound one or more round-end passive losses; does not mutate live state."""
    t=copy.deepcopy(s);remaining=[]
    for c in t['jokers']['cards']:
        life=prior.mod(c).get('perishable')
        if isinstance(life,(int,float)) and not isinstance(life,bool) and life<=rounds:
            c.setdefault('state',{})['debuff']=True
        if c['key']=='j_turtle_bean' and not a.st(c).get('debuff'):
            size=max(0,a.current_number(c)-rounds)
            if size<=0:continue
            c.setdefault('value',{})['effect']='当前 '+str(size)
        remaining.append(c)
    t['jokers']['cards']=remaining
    if 'count' in t['jokers']:t['jokers']['count']=len(remaining)
    return adjust_resources(s,t)



def legacy_grown(s):
    t = ordered(s)
    route = routes.main_hand(t)
    for c in t['jokers']['cards']:
        if a.st(c).get('debuff'): continue
        k = c['key']; value = a.current_number(c)
        extra = {'j_green_joker': 4, 'j_ride_the_bus': 4,
                 'j_runner': 30 if route == 'Straight' else 0,
                 'j_square': 12, 'j_trousers': 4 if route == 'Two Pair' else 0}.get(k, 0)
        if extra: c.setdefault('value', {})['effect'] = '当前 '+str(value + extra)
    if 'j_supernova' in a.keys(t):
        t['hands'][route]['played'] += 4
    return t


def visible_growth(s):
    """One visible-opportunity window, never assumed future shop contents.

    Existing six growth projections are retained separately. New projections
    share a single spending budget and expose their mechanism/heuristic scope.
    """
    t=legacy_grown(s);keys=a.keys(s);deck=t.get('_belief',{}).get('deck',[])
    notes=[];extra={};cash=max(0,t.get('money',0)-prior.reserve(t))
    def add(key,amount,evidence,heuristic=False):
        if key in keys:
            extra[key]=extra.get(key,0)+amount
            notes.append({'key':key,'gain':amount,'evidence':evidence,'heuristic':heuristic})
    # Planets in inventory are usable public assets. Paid offers are allocated
    # once from the same cash budget, not counted independently for each scaler.
    planet_uses=sum(c.get('set')=='PLANET' or c.get('key') in legacy.PLANETS for c in t.get('consumables',{}).get('cards',[]))
    purchases=[]
    for c in t.get('shop',{}).get('cards',[]):
        price=c.get('cost',{}).get('buy')
        if not isinstance(price,(int,float)) or price<0:continue
        if 'j_constellation' in keys and (c.get('set')=='PLANET' or c.get('key') in legacy.PLANETS):purchases.append((price,'planet',c))
        if 'j_hologram' in keys and c.get('set') in ('DEFAULT','PLAYING_CARD','ENHANCED'):purchases.append((price,'playing_card',c))
    additions=0;spent=0
    for price,kind,c in sorted(purchases,key=lambda x:x[0]):
        if price>cash-spent:continue
        if kind=='planet' and planet_uses<2:planet_uses+=1;spent+=price
        elif kind=='playing_card' and additions<2:additions+=1;spent+=price
    if 'j_constellation' in keys:add('j_constellation',.1*min(2,planet_uses),'at_most_two_owned_or_visible_affordable_planets; planned_cost_paid')
    if 'j_hologram' in keys:
        entry=sum(c['key'] in ('j_certificate','j_marble') and not a.st(c).get('debuff') for c in t['jokers']['cards'])
        add('j_hologram',.25*min(2,additions+entry),'visible_playing_cards_or_existing_entry_generators')
        if 'j_dna' in keys and t.get('_base_hands',5)>=3 and prior.target(t)['name']!='The Needle':
            add('j_hologram',.25,'one_conditional_first_hand_DNA_trigger',True)
    t['money']-=spent
    if spent:notes.append({'planned_visible_spend':spent,'reserve_preserved':prior.reserve(s)})
    if 'j_vampire' in keys and deck:
        eligible=[c for c in deck if a.mod(c).get('enhancement') in ('BONUS','MULT','WILD','GOLD')]
        exposure=min(2,len(eligible)*min(1,t['hand']['limit']/len(deck)))
        # Strip a full exposed enhancement even for fractional encounter credit;
        # never grant growth while pretending the sacrificed enhancement remains.
        for card in eligible[:min(2,len(eligible))]:card['modifier'].pop('enhancement',None)
        add('j_vampire',.1*exposure,'public_enhancement_density; up_to_two_enhancements_removed',True)
    if 'j_madness' in keys:
        others=[c for c in t['jokers']['cards'] if c['key']!='j_madness']
        safe=all(prior.mod(c).get('eternal') for c in others)
        if prior.target(t)['name'] in ('Small Blind','Big Blind') and safe:add('j_madness',.5,'next_visible_nonboss_entry; no_destroyable_companion')
        else:notes.append({'key':'j_madness','gain':0,'evidence':'destruction_cost_or_boss_entry_not_projected','heuristic':False})
    if 'j_wee' in keys and deck:
        twos=sum(a.rank(c)==2 and a.mod(c).get('enhancement')!='STONE' for c in deck)
        seen=min(len(deck),t['hand']['limit']+6)
        triggers=min(2,twos*seen/len(deck))
        repeats=3 if 'j_hanging_chad' in keys else 1
        add('j_wee',8*triggers*repeats,'public_twos_density; two_scoring_opportunities; conditional_Chad',True)
    if 'j_yorick' in keys:
        joker=next(c for c in t['jokers']['cards'] if c['key']=='j_yorick')
        text=joker.get('value',{}).get('effect','')
        match=re.search(r'(?:再弃掉|还需弃掉|剩余弃牌)\s*(\d+)\s*张|(?:remaining|discards remaining)\s*:?\s*(\d+)',text,re.I)
        remaining=int(next(x for x in match.groups() if x is not None)) if match else None
        opportunities=max(0,t.get('_base_discards',2))*4
        if remaining is not None and remaining<=opportunities and not keys&{'j_green_joker','j_banner','j_ramen'} and prior.target(t)['name']!='The Water':
            add('j_yorick',1,'public_remaining_discard_counter_within_bounded_discard_budget',True)
        else:notes.append({'key':'j_yorick','gain':0,'evidence':'counter_unknown_or_trigger_cost_not_supported','heuristic':True})
    for c in t['jokers']['cards']:
        if a.st(c).get('debuff'):continue
        delta=extra.get(c['key'],0)
        if delta:
            current=a.current_number(c,1 if c['key'] in ('j_constellation','j_hologram','j_vampire','j_madness','j_yorick') else 0)
            c.setdefault('value',{})['effect']='当前 '+str(current+delta)
    return t,notes


def grown(s):
    t,notes=visible_growth(s)
    LAST_DIAGNOSTICS.setdefault('growth_opportunities',[]).append(notes)
    return t


def metrics(s):
    now = outlook(s)
    # Rank an assumed four future growth opportunities, with modest weight.
    projected = outlook(grown(s))
    boss = copy.deepcopy(grown(s))
    for k in ('small', 'big'): boss['blinds'][k]['status'] = 'DEFEATED'
    boss['blinds']['boss']['status'] = 'UPCOMING'
    b = outlook(boss)
    return now, projected, b


def legacy_affordable(s, t, offer, now, nxt):
    rescue = False  # Proxy crossing one never waives rent safety; use funded exception.
    if prior.mod(offer).get('rental'):
        total = prior.rent(t)
        # Four dollars per blind is a cash-flow assumption, not guaranteed income.
        deficit = max(0,total-prior.income(t)-4)
        floor = 2*deficit + (10 if prior.target(t)['name']=='The Tooth' else 0)
        if t['money'] < floor and not rescue: return False
        if total > 3 and prior.income(t) < total-3 and not rescue: return False
        if not rescue and nxt < now*1.2: return False
    if prior.mod(offer).get('eternal'):
        if sum(bool(prior.mod(c).get('eternal')) for c in s['jokers']['cards']) >= 3:
            return nxt >= now*1.3 or rescue
    return True


def affordable(s,t,offer,now,nxt):
    regular=legacy_affordable(s,t,offer,now,nxt)
    detail={'regular_gate':regular,'exception':False,'capacity_is_probability':False}
    LAST_DIAGNOSTICS['last_affordability']=detail
    if not prior.mod(offer).get('rental'):
        detail['reason']='regular_nonrental_gate';return regular
    rent=prior.rent(t);income=prior.income(t)
    fee=10 if prior.target(t)['name']=='The Tooth' else 0
    cash=t['money']-fee
    next_net=cash+income-rent
    eternal=bool(prior.mod(offer).get('eternal'))
    detail.update(next_round_net_cash_floor=next_net,rent_per_round=rent,
                  guaranteed_passive_income=income,tooth_fee_allowance=fee)
    if next_net<0:
        detail['reason']='next_round_rent_cash_floor_negative';return False
    if regular:
        detail['reason']='regular_rental_gate';return True
    large_gain=nxt>=max(now*1.8,now+.8)
    two_round_net=cash+2*income-2*rent
    if eternal:
        eligible=large_gain and nxt>=now*2.5 and two_round_net>=0
    else:
        eligible=large_gain and next_net>=0
    detail.update(exception=eligible,two_round_net_cash_floor=two_round_net,
        exit_plan='cannot_sell_eternal; two_round_cash_buffer' if eternal else 'sell_new_rental_at_next_shop_if_needed',
        reason='large_gain_cash_funded_rental_exception' if eligible else 'rental_cash_or_gain_exception_threshold_failed')
    return eligible


def passive_resources(c):
    if a.st(c).get('debuff'): return 0,0,0
    key=c['key']
    return ({'j_juggler':1,'j_stuntman':-2,'j_troubadour':2,'j_merry_andy':-1}.get(key,a.current_number(c) if key=='j_turtle_bean' else 0),
            -int(key=='j_troubadour'),{'j_drunkard':1,'j_merry_andy':3}.get(key,0))


def adjust_resources(before,after):
    old=[sum(x) for x in zip(*(passive_resources(c) for c in before['jokers']['cards']))] if before['jokers']['cards'] else [0,0,0]
    new=[sum(x) for x in zip(*(passive_resources(c) for c in after['jokers']['cards']))] if after['jokers']['cards'] else [0,0,0]
    after['hand']['limit']=max(1,before['hand']['limit']+new[0]-old[0])
    after['_base_hands']=before.get('_base_hands',5)+new[1]-old[1]
    after['_base_discards']=before.get('_base_discards',2)+new[2]-old[2]
    return after


def choose_joker(s, pack=False):
    base = metrics(s); sim = copy.deepcopy(s); ranked = []
    records=[]
    LAST_DIAGNOSTICS['joker_candidates']=records
    if pack:
        sim['shop'] = copy.deepcopy(s['pack'])
        for c in sim['shop']['cards']: c.setdefault('cost', {})['buy'] = 0
    for c in prior.core.candidate_states(sim):
        offer = sim['shop']['cards'][c['offer_index']]; t = adjust_resources(s,c['state'])
        record={'offer_index':c['offer_index'],'key':offer['key'],'replace_index':c['replace_index'],'accepted':False}
        records.append(record)
        bridge = (c['replace_index'] is None and len(s['jokers']['cards']) < 3 and s['ante_num'] <= 3 and
                  offer['key'] in (legacy.CHIPS | {'j_zany','j_jolly','j_mad','j_crazy','j_droll','j_half','j_fibonacci','j_scholar','j_smiley','j_hanging_chad','j_photograph','j_raised_fist','j_abstract','j_gros_michel','j_mystic_summit'}) and
                  strategy.value(offer,s) >= 45 and prior.rent(t) <= 3)
        permitted=affordable(s,t,offer,base[0],outlook(t))
        record['affordability']=copy.deepcopy(LAST_DIAGNOSTICS.get('last_affordability',{}))
        mandatory_cash_failure=record['affordability'].get('reason')=='next_round_rent_cash_floor_negative'
        if not permitted and (not bridge or mandatory_cash_failure):
            record['reason']='rental_or_eternal_affordability';continue
        m = metrics(t); gain = m[0]-base[0]; future = m[1]-base[1]; boss = m[2]-base[2]
        econ = (offer['key'] in EARLY_TOOLS and s['ante_num'] <= 4 and
                not prior.mod(offer).get('rental') and legacy.utility(offer, s) >= 45)
        old = s['jokers']['cards'][c['replace_index']] if c['replace_index'] is not None else None
        if econ:
            low_cost_start = s['ante_num'] <= 2 and len(s['jokers']['cards']) <= 2 and (c['price']==0 or t['money']>=3)
            econ = m[0] >= min(base[0]*.9, 1.0) and (base[0]>=.8 or low_cost_start)
            if old and (old['key'] in EARLY_TOOLS or old['key'] in legacy.GROWTH): econ = False
        improvement = gain + .35*future + .5*boss
        record.update(immediate_gain=gain,projected_gain=future,boss_gain=boss,weighted_gain=improvement,baseline=base,candidate=m)
        if gain < -.05 and not econ:
            record['reason']='immediate_capacity_regression';continue
        if improvement < .04 and not econ and not bridge:
            record['reason']='insufficient_measured_gain';continue
        if prior.mod(offer).get('eternal') and not econ:
            # Relative improvement avoids rejecting +25% early strength because
            # conservative absolute coverage happens to be below one.
            if m[0] < base[0]*1.12 and improvement < .12 and not bridge:
                record['reason']='eternal_option_value_threshold';continue
        if old and old['key'] in legacy.GROWTH and not a.st(old).get('debuff'):
            if future < .1 and gain < .3:
                record['reason']='retain_existing_growth';continue
        # Coverage crossing is a ranking preference, not certified survival.
        rank = (base[0] < 1 <= m[0], min(m[0], 1.5)-min(base[0], 1.5) +
                .35*(min(m[1], 2)-min(base[1], 2)) + .5*(min(m[2], 1.3)-min(base[2], 1.3)) +
                (.18 if econ else 0) + (.2 if bridge else 0) +
                (.65 if offer['key']=='j_riff_raff' and len(s['jokers']['cards'])<=2 and s['ante_num']<=2 else 0),
                -c['price'] - 2*prior.rent(t))
        record.update(reason='eligible_but_lower_rank',rank=rank)
        ranked.append((rank, c, m, econ, record))
    if not ranked: return None
    _, c, m, econ, record = max(ranked, key=lambda x:x[0])
    record.update(accepted=True,reason='selected_best_visible_candidate')
    reason = f'{VERSION}: immediate {base[0]:.2f}->{m[0]:.2f}; projected growth/Boss ranking, economy={econ}; not survival probability'
    if c['replace_index'] is not None:
        return 'sell', {'joker':c['replace_index'], 'reason':reason}
    return ('pack' if pack else 'buy'), {'card':c['offer_index'], 'reason':reason}


def immediate_cash_action(s):
    """Execute one known strictly positive buy-and-use transaction, then observe.

    Hermit and Temperance require no targets or newly generated card slots.
    The runtime buy endpoint explicitly permits use=True with full consumables.
    Explicit public cannot-use flags and overlays still block this shortcut.
    """
    if s.get('state')!='SHOP' or s.get('overlay') or s.get('won'):return None
    cash=s.get('money',0);transactions=[]
    for i,c in enumerate(s.get('shop',{}).get('cards',[])):
        if c.get('key') not in ('c_hermit','c_temperance') or c.get('set')!='TAROT':continue
        price=c.get('cost',{}).get('buy')
        if type(price) not in (int,float) or price<0 or price>cash:continue
        if c.get('can_use') is False or a.st(c).get('can_use') is False or a.st(c).get('debuff'):continue
        if c['key']=='c_hermit':gain=min(20,max(0,cash-price))
        else:gain=min(50,sum(max(0,j.get('cost',{}).get('sell',0)) for j in s['jokers']['cards']))
        net=gain-price
        if net>0:transactions.append((c['key']=='c_temperance',net,i,price,gain))
    if not transactions:return None
    _,net,i,price,gain=max(transactions)
    LAST_DIAGNOSTICS['cash_priority']={
        'offer_index':i,'key':s['shop']['cards'][i]['key'],'cash_before':cash,
        'purchase_cost':price,'known_effect_gain':gain,'net_cash_gain':net,
        'cash_after_if_executed':cash-price+gain,'future_income_borrowed':False,
        'must_reobserve_after_action':True,'consumable_slot_required':False,
        'reason':'realize_strictly_positive_public_cash_transaction_before_spending_principal'}
    return 'buy',{'card':i,'use':True,'reason':VERSION+
        f': realize known net cash +{net} before other purchases; buy cost {price}, effect +{gain}; reobserve before spending proceeds'}


def action(s, evaluator=None, *, rerolls_this_shop=0):
    phase = s.get('state')
    if phase not in ('SHOP', 'SMODS_BOOSTER_OPENED'): return None
    if phase == 'SMODS_BOOSTER_OPENED':
        cs = s.get('pack', {}).get('cards', [])
        if cs and cs[0].get('set') == 'JOKER':
            choice=choose_joker(s,True)
            if choice:return choice
            free=s['jokers']['limit']-len(s['jokers']['cards'])
            resale=[(c.get('cost',{}).get('sell',0),i) for i,c in enumerate(cs) if not prior.mod(c).get('eternal') and not prior.mod(c).get('rental')]
            if free>0 and resale:
                return 'pack',{'card':max(resale)[1],'reason':VERSION+': free reversible Joker has resale value; no paid unknown purchase implied'}
            return 'pack', {'skip':True, 'reason':VERSION+': no affordable useful Joker'}
        return legacy.action(s)
    cash_pick=immediate_cash_action(s)
    if cash_pick:return cash_pick
    for i, c in enumerate(s['jokers']['cards']):
        if a.st(c).get('debuff') and not prior.mod(c).get('eternal'):
            return 'sell', {'joker':i, 'reason':VERSION+': expired component and rental cost'}
    pick = choose_joker(s)
    if pick: return pick
    now, future, boss = metrics(s)
    # Free a low-value generated card before Riff Raff's next activation.
    if 'j_riff_raff' in a.keys(s) and len(s['jokers']['cards']) >= s['jokers']['limit'] and now >= 1.2 and s['ante_num'] <= 3:
        for i,c in sorted(enumerate(s['jokers']['cards']), key=lambda x:legacy.utility(x[1],s)):
            if c['key'] == 'j_riff_raff' or prior.mod(c).get('eternal') or c['key'] in legacy.GROWTH: continue
            t = copy.deepcopy(s); t['jokers']['cards'].pop(i)
            t['jokers']['count'] -= 1; t['money'] += c['cost']['sell']
            t=adjust_resources(s,t)
            if outlook(t) >= 1.1 and legacy.utility(c,s) < 55:
                return 'sell', {'joker':i, 'reason':VERSION+': clear generated low-value slot for next Riff activation'}
    upgrades = []
    for i,c in enumerate(s.get('shop',{}).get('cards',[])):
        if c.get('set') != 'PLANET' or c['cost']['buy'] > s['money']: continue
        t = planets.upgraded(s,c,c['cost']['buy'])
        if t:
            m = metrics(t); gain = (m[0]-now)+.35*(m[1]-future)+.5*(m[2]-boss)
            if gain > .04: upgrades.append((gain, i))
    if upgrades:
        return 'buy', {'card':max(upgrades)[1], 'use':True, 'reason':VERSION+': visible permanent planet gain including known Boss'}
    # Evaluate remaining categories directly: a rejected legacy card proposal
    # must not prevent inspecting other affordable offers in the same shop.
    cash=s['money']; reserve=prior.reserve(s)
    for i,c in enumerate(s.get('shop',{}).get('cards',[])):
        price=c['cost']['buy']
        gain=min(20,max(0,cash-price)) if c['key']=='c_hermit' else min(50,sum(j['cost']['sell'] for j in s['jokers']['cards'])) if c['key']=='c_temperance' else 0
        if price<=cash and gain>price:
            return 'buy',{'card':i,'use':True,'reason':VERSION+': known positive immediate cash gain'}
    free=s['jokers']['limit']-len(s['jokers']['cards'])
    packs=s.get('packs',{}).get('cards',[])
    buffoons=[(c['cost']['buy'],i) for i,c in enumerate(packs) if 'buffoon' in c['key'] and c['cost']['buy']<=cash and
              (free>0 or cash>=20) and (len(s['jokers']['cards'])<4 or now<1.2)]
    if buffoons:
        price,i=min(buffoons)
        if cash-price>=reserve or not prior.rent(s):
            return 'buy',{'pack':i,'reason':VERSION+': budgeted unknown Buffoon options; rejected card does not hide pack'}
    route=routes.main_hand(s)
    for i,c in enumerate(s.get('shop',{}).get('cards',[])):
        if c.get('set')=='PLANET' and legacy.PLANETS.get(c['key'])==route and cash-c['cost']['buy']>=max(4,reserve):
            return 'buy',{'card':i,'use':True,'reason':VERSION+': permanent current-route level, sampled q25 is not sole criterion'}
    for i,c in enumerate(s.get('vouchers',{}).get('cards',[])):
        if c['key'] in ('v_grabber','v_nacho_tong','v_paint_brush','v_palette','v_telescope') and cash-c['cost']['buy']>=max(8,reserve) and now>=1.1:
            return 'buy',{'voucher':i,'reason':VERSION+': known additional resource with survival reserve'}
    for i,c in sorted(enumerate(packs),key=lambda x:x[1]['cost']['buy']):
        after=cash-c['cost']['buy'];key=c['key']
        if 'celestial' in key and after>=max(4,reserve) and (now<1.5 or boss<1.2 or s['hands'][route]['level']<=3):
            return 'buy',{'pack':i,'reason':VERSION+': budgeted level options, no guaranteed rescue claim'}
        if 'arcana' in key and after>=max(12,reserve):
            return 'buy',{'pack':i,'reason':VERSION+': budgeted economy/deck improvement options'}
    proposal = legacy.action(s)
    if proposal:
        method,params = proposal
        if method in ('rearrange','use'): return proposal
        if method == 'buy':
            if 'card' in params and s['shop']['cards'][params['card']]['key'] in ('c_hermit','c_temperance'): return proposal
            if 'voucher' in params:
                v = s['vouchers']['cards'][params['voucher']]
                if s['money']-v['cost']['buy'] >= max(10,prior.reserve(s)) and now >= 1.1: return proposal
            if 'pack' in params:
                c = s['packs']['cards'][params['pack']]; cost = c['cost']['buy']; key = c['key']
                cash = s['money']-cost
                if 'buffoon' in key and cash >= prior.reserve(s) and (len(s['jokers']['cards']) < 4 or now < 1.2): return proposal
                if 'celestial' in key and cash >= max(4, prior.reserve(s)) and (now < 1.5 or boss < 1.2): return proposal
                if 'arcana' in key and cash >= max(12,prior.reserve(s)): return proposal
                if cash >= max(15,prior.reserve(s)) and now >= 1.3: return proposal
    cost = s['round'].get('reroll_cost',5)
    if (now < 1.25 or boss < .8) and rerolls_this_shop < 2 and cost <= 6 and s['money'] >= cost+max(5,prior.reserve(s)):
        return 'reroll', {'reason':VERSION+': visible next-blind/Boss pressure, reserve purchase cash'}
    return 'next_round', {'reason':VERSION+': retain cash; no supported improvement'}


_action = action


def action(s, evaluator=None, *, rerolls_this_shop=0):
    """Compatible action result; diagnostics are available separately."""
    LAST_DIAGNOSTICS.clear()
    LAST_DIAGNOSTICS.update(version=VERSION,approximation=True,calibrated_probability=False)
    result=_action(s,evaluator,rerolls_this_shop=rerolls_this_shop)
    LAST_DIAGNOSTICS['selected_action']=copy.deepcopy(result)
    offers=[]
    method,params=result if result else (None,{})
    area='pack' if s.get('state')=='SMODS_BOOSTER_OPENED' else 'shop'
    for container,param in ((area,'card'),('packs','pack'),('vouchers','voucher')):
        for i,card in enumerate(s.get(container,{}).get('cards',[])):
            picked=method in ('buy','pack') and params.get(param)==i and not params.get('skip')
            evidence=[r for r in LAST_DIAGNOSTICS.get('joker_candidates',[]) if container==area and r['offer_index']==i]
            reason=params.get('reason') if picked else (';'.join(dict.fromkeys(r['reason'] for r in evidence)) if evidence else
                'unaffordable' if card.get('cost',{}).get('buy',0)>s.get('money',0) else 'not_selected_by_visible_policy')
            offers.append({'area':container,'index':i,'key':card.get('key'),'accepted':picked,'reason':reason})
    LAST_DIAGNOSTICS['offers']=offers
    return result


def diagnostics():
    return copy.deepcopy(LAST_DIAGNOSTICS)
