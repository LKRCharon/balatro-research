"""Experimental SHOP whole-blind capacity from public deck multisets.
Sample clear fractions are heuristic, not calibrated probabilities. Unsupported
mechanics are frozen/omitted and surfaced, never described as exact simulation.
"""
import copy,functools,hashlib,json,random,time
import combat_candidate_v4 as combat
import copying
import phases
a=combat.a


def reorder_for_combat(s):
    """Same zero-based new-position -> old-index contract as actual rearrange.

    Uses the runtime phase planner's public-hand representative pool; no future
    deck argument and no unconditional assumption that every copier is active.
    """
    action=phases.copy_action(s,'combat')
    if action is None:return s,None
    method,params=action
    if method!='rearrange' or 'jokers' not in params:raise ValueError('Unexpected copy planner action')
    order=params['jokers']
    if sorted(order)!=list(range(len(s['jokers']['cards']))):raise ValueError('Invalid permutation')
    return phases.reordered(s,order),order


def entry_order(s):
    # Burglar modifies the number of hands at entry; copy it before the draw,
    # then permit the independent combat allocation once the hand is public.
    if 'j_burglar' not in a.keys(s) or not a.keys(s)&copying.COPY:return s
    orders=copying.candidate_orders(s)
    legal=[order for order in orders if phases.safe_entry(s,order)]
    if not legal:return s
    best=max(legal,key=lambda order:copying.count(phases.reordered(s,order),'j_burglar'))
    return phases.reordered(s,best)


def canonical(state):
    fields=('ante_num','money','jokers','blinds','hands','_targets','_normal_probability','_base_hands','_base_discards')
    s={k:copy.deepcopy(state[k]) for k in fields if k in state}
    s['hand']={'limit':state.get('hand',{}).get('limit',8)}
    deck=state.get('_belief',{}).get('deck')
    if not deck:return None
    tokens=[]
    for card in deck:
        if a.st(card).get('hidden') or a.st(card).get('face_down') or not card.get('value'):return None
        c={k:copy.deepcopy(card[k]) for k in ('key','value','modifier','permanent_bonus') if k in card}
        c['state']={}
        tokens.append(c)
    tokens.sort(key=lambda c:json.dumps(c,sort_keys=True))
    s['_belief']={'deck':tokens,'starting_size':state.get('_belief',{}).get('starting_size',52)}
    return s


def worlds_for(deck,count):
    encoded=json.dumps(deck,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(encoded.encode()).hexdigest()
    worlds=[]
    for i in range(count):
        rng=random.Random(int(hashlib.sha256(f'{digest}:{i}'.encode()).hexdigest(),16))
        world=copy.deepcopy(deck);rng.shuffle(world);worlds.append(world)
    return digest,worlds


def apply_debuff(s):
    if 'j_chicot' in a.keys(s):return
    name=combat.v1.static.boss(s).get('name')
    suit={'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(name)
    for c in s['hand']['cards']:
        if (suit and (a.suit(c)==suit or a.mod(c).get('enhancement')=='WILD')) or (name=='The Plant' and (a.rank(c) in (11,12,13) or 'j_pareidolia' in a.keys(s))):
            c.setdefault('state',{})['debuff']=True


def prepare(s,world):
    s=entry_order(copy.deepcopy(s))
    target=next((s['blinds'][k] for k in ('small','big','boss') if k in s['blinds'] and s['blinds'][k].get('status') not in ('DEFEATED','SKIPPED')),None)
    if target is None:raise ValueError('No upcoming blind')
    for b in s['blinds'].values():b['status']='UPCOMING'
    target['status']='CURRENT';name=target['name'];disabled='j_chicot' in a.keys(s)
    burglar=copying.count(s,'j_burglar')
    hands=s.get('_base_hands',5)+3*burglar;discards=0 if burglar else s.get('_base_discards',2)
    if not disabled:
        if name=='The Needle':hands=1
        if name=='The Water':discards=0
    size=int(s['hand']['limit'])-(name=='The Manacle' and not disabled)
    size=max(1,min(size,len(world)))
    s['state']='SELECTING_HAND';s['round']={'hands_left':hands,'discards_left':discards,'hands_played':0,'discards_used':0,'chips':0}
    s['hand']={'cards':copy.deepcopy(world[:size]),'limit':size,'count':size}
    s['cards']={'count':len(world)-size,'limit':len(world)}
    for h in s['hands'].values():h['played_this_round']=0
    s['_belief']['unseen']=sorted(copy.deepcopy(world[size:]),key=combat.v1.static.card_token)
    apply_debuff(s)
    return s,world[size:]


def actor(s):
    options=a.options(s,optimize_order=True);best=options[0]
    need=combat.v1.static.boss(s)['score']-s['round']['chips']
    clear=[o for o in options if (a.conservative_score(s,o[1],o[0]) or 0)>=need]
    if clear:return 'play',clear[0][1]
    quota=need/max(1,s['round']['hands_left'])
    if s['round']['discards_left']>0 and best[0]<quota:
        cards=s['hand']['cards'];protected=combat.old.v2.protected_indices(s,options)
        ranks={r:[i for i,c in enumerate(cards) if a.rank(c)==r] for r in {a.rank(c) for c in cards}}
        suits={su:[i for i,c in enumerate(cards) if a.suit(c)==su] for su in 'SHCD'}
        suit=max(suits.values(),key=len);rank=max(ranks.values(),key=lambda g:(len(g),a.rank(cards[g[0]])))
        keep=suit if len(suit)>=4 and len(rank)<3 else rank if len(rank)>=2 else None
        indices=[i for i in range(len(cards)) if i not in keep and i not in protected][:5] if keep is not None else [i for i in a.discard(s,best) if i not in protected]
        if indices:return 'discard',indices
    return 'play',combat.play_option(s)[1]


def simulate(s,world):
    sim,tail=prepare(s,world);actions=0
    while sim['round']['hands_left']>0 and sim['hand']['cards'] and actions<20:
        sim,_=reorder_for_combat(sim)
        method,indices=actor(sim)
        try:sim,tail,_=combat.transition(sim,method,indices,tail)
        except ValueError:
            # Unsupported destruction transition (e.g. Ramen expiry): play the
            # current best instead, and retain the approximate diagnostic.
            method,indices='play',a.options(sim,optimize_order=True)[0][1]
            sim,tail,_=combat.transition(sim,method,indices,tail)
        apply_debuff(sim);actions+=1
        if sim['round']['chips']>=combat.v1.static.boss(sim)['score']:break
    return sim['round']['chips'],actions


@functools.lru_cache(maxsize=256)
def _estimate(encoded,samples,budget):
    s=json.loads(encoded);started=time.monotonic()
    deck=s['_belief']['deck'];digest,worlds=worlds_for(deck,samples)
    prepared,_=prepare(s,worlds[0]);target=combat.v1.static.boss(prepared)
    unknown=sorted(a.keys(s)-(combat.v1.static.SAFE_JOKERS|combat.GROWTH|{'j_burglar'}))
    limits=[]
    if unknown:limits.append('unmodeled_mutable_jokers:'+','.join(unknown))
    if target['name'] not in combat.v1.static.SAFE_BOSSES:limits.append('unmodeled_boss:'+target['name'])
    if any(a.mod(c).get('enhancement') in ('GLASS','LUCKY') or a.mod(c).get('seal') in ('PURPLE','GOLD') for c in deck):limits.append('random_or_mutating_cards_approximated')
    scores=[];actions=[]
    for world in worlds:
        if len(scores)>=4 and time.monotonic()-started>=budget:break
        score,count=simulate(s,world);scores.append(score);actions.append(count)
    ordered=sorted(scores);target_score=target['score']
    return {'available':True,'samples':len(scores),'requested_samples':samples,
        'clear_fraction':sum(x>=target_score for x in scores)/len(scores),
        'mean':sum(scores)/len(scores),'q25':ordered[max(0,(len(scores)-1)//4)],
        'target':target_score,'hands':prepared['round']['hands_left'],'discards':prepared['round']['discards_left'],
        'scores':scores,'world_ids':list(range(len(scores))),'public_deck_hash':digest,
        'limitations':limits,'approximation':True,'calibrated_probability':False,
        'optimality_claim':False,'future_draw_order_used':False,'common_worlds_across_lineups':True,
        'actor_uses_only_resulting_public_hand':True,
        'copy_allocation':'runtime phases.copy_action on each visible hand; entry Burglar allocation',
        'copy_search_scope':'all permutations through 5 jokers; heuristic candidates above 5; representative hand subsets',
        'execution_parity':'same rearrange zero-based new-position-to-old-index contract; no engine replay','mean_actions':sum(actions)/len(actions),
        'budget_seconds':budget,'elapsed_seconds':time.monotonic()-started,
        'budget_is_soft_minimum_four_worlds':True}


def estimate(state,samples=4,budget=2.0):
    if type(samples) is not int or not 4<=samples<=8:raise ValueError('samples must be 4..8')
    if budget<=0:raise ValueError('budget must be positive')
    s=canonical(state)
    if s is None:return {'available':False,'reason':'public_actual_deck_multiset_missing_or_hidden','approximation':True,'calibrated_probability':False}
    return copy.deepcopy(_estimate(json.dumps(s,sort_keys=True),samples,float(budget)))
