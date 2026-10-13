"""TRAIN candidate: budgeted growth/economy with visible Boss preparation.

Projected growth is an explicit ranking assumption, not guaranteed capacity.
No future offers, seed or draw order is available to this module.
"""
import copy
import growth_candidate_v6 as prior
import forecast
import policy as legacy
import advisor as a
import routes
import shop_planning as planets

VERSION = 'growth_candidate_v8'
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
    return prior.outlook(ordered(s))


def grown(s):
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


def metrics(s):
    now = outlook(s)
    # Rank an assumed four future growth opportunities, with modest weight.
    projected = outlook(grown(s))
    boss = copy.deepcopy(grown(s))
    for k in ('small', 'big'): boss['blinds'][k]['status'] = 'DEFEATED'
    boss['blinds']['boss']['status'] = 'UPCOMING'
    b = outlook(boss)
    return now, projected, b


def affordable(s, t, offer, now, nxt):
    rescue = now < 1 <= nxt
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


def choose_joker(s, pack=False):
    base = metrics(s); sim = copy.deepcopy(s); ranked = []
    if pack:
        sim['shop'] = copy.deepcopy(s['pack'])
        for c in sim['shop']['cards']: c.setdefault('cost', {})['buy'] = 0
    for c in prior.core.candidate_states(sim):
        offer = sim['shop']['cards'][c['offer_index']]; t = c['state']
        if not affordable(s, t, offer, base[0], outlook(t)): continue
        m = metrics(t); gain = m[0]-base[0]; future = m[1]-base[1]; boss = m[2]-base[2]
        econ = (offer['key'] in EARLY_TOOLS and s['ante_num'] <= 4 and
                not prior.mod(offer).get('rental') and legacy.utility(offer, s) >= 45)
        old = s['jokers']['cards'][c['replace_index']] if c['replace_index'] is not None else None
        if econ:
            low_cost_start = s['ante_num'] <= 2 and len(s['jokers']['cards']) <= 2 and (c['price']==0 or t['money']>=3)
            econ = m[0] >= min(base[0]*.9, 1.0) and (base[0]>=.8 or low_cost_start)
            if old and (old['key'] in EARLY_TOOLS or old['key'] in legacy.GROWTH): econ = False
        improvement = gain + .35*future + .5*boss
        if gain < -.05 and not econ: continue
        if improvement < .04 and not econ: continue
        if prior.mod(offer).get('eternal') and not econ:
            # Relative improvement avoids rejecting +25% early strength because
            # conservative absolute coverage happens to be below one.
            if m[0] < base[0]*1.12 and improvement < .12: continue
        if old and old['key'] in legacy.GROWTH and not a.st(old).get('debuff'):
            if future < .1 and gain < .3: continue
        # Immediate rescue wins; future tools compete only after survival.
        rank = (base[0] < 1 <= m[0], min(m[0], 1.5)-min(base[0], 1.5) +
                .35*(min(m[1], 2)-min(base[1], 2)) + .5*(min(m[2], 1.3)-min(base[2], 1.3)) +
                (.18 if econ else 0), -c['price'] - 2*prior.rent(t))
        ranked.append((rank, c, m, econ))
    if not ranked: return None
    _, c, m, econ = max(ranked, key=lambda x:x[0])
    reason = f'{VERSION}: immediate {base[0]:.2f}->{m[0]:.2f}; projected growth/Boss ranking, economy={econ}; not survival probability'
    if c['replace_index'] is not None:
        return 'sell', {'joker':c['replace_index'], 'reason':reason}
    return ('pack' if pack else 'buy'), {'card':c['offer_index'], 'reason':reason}


def action(s, evaluator=None, *, rerolls_this_shop=0):
    phase = s.get('state')
    if phase not in ('SHOP', 'SMODS_BOOSTER_OPENED'): return None
    if phase == 'SMODS_BOOSTER_OPENED':
        cs = s.get('pack', {}).get('cards', [])
        if cs and cs[0].get('set') == 'JOKER':
            return choose_joker(s, True) or ('pack', {'skip':True, 'reason':VERSION+': no affordable useful Joker'})
        return legacy.action(s)
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
