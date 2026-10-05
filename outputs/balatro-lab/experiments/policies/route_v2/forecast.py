"""Conservative next-blind pressure estimate, with a documented vanilla-deck approximation.

Samples hypothetical unordered 52-card hands using Python's private RNG, never game RNG.
Does not claim independent future hands or a calibrated win probability.
"""
import copy, functools, json, random
import advisor as a
import copying
from belief import base_deck

@functools.lru_cache(maxsize=512)
def _estimate(encoded):
    s=json.loads(encoded)
    target=next((s['blinds'][k] for k in ('small','big','boss') if s['blinds'][k]['status'] not in ('DEFEATED','SKIPPED')),s['blinds']['boss'])
    for b in s['blinds'].values(): b['status']='UPCOMING'
    target['status']='CURRENT'
    for h in s['hands'].values():h['played_this_round']=0
    size=max(5,min(12,int(s.get('hand',{}).get('limit',8))))
    deck=s.get('_belief',{}).get('deck',list(base_deck().values()))
    s['round'].pop('mouth_hand',None)
    s['_boss_disabled']=False
    s['round']['hands_played']=0
    s['round']['hands_left']=s.get('_base_hands',5)+3*copying.count(s,'j_burglar')
    s['round']['discards_left']=0 if copying.count(s,'j_burglar') else s.get('_base_discards',2)
    rng=random.Random(20261004)
    scores=[]
    for _ in range(16):
        hand=copy.deepcopy(rng.sample(deck,size))
        banned={'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(target['name'])
        for c in hand:
            if c['value']['suit']==banned or (target['name']=='The Plant' and c['value']['rank'] in ('J','Q','K')):c['state']['debuff']=True
        s['hand']={'cards':hand,'count':size,'limit':size};s['cards']={'count':max(0,len(deck)-size),'limit':len(deck)}
        opts=a.options(s);value=opts[0][0]
        if a.keys(s)&copying.COPY:
            for order in copying.candidate_orders(s)[1:]:
                sim=copy.deepcopy(s);sim['jokers']['cards']=[s['jokers']['cards'][i] for i in order]
                value=max(value,max(a.score(sim,o[1])[0] for o in opts[:4]))
        scores.append(value)
    scores.sort(); q25=scores[3];median=(scores[7]+scores[8])/2
    hands=1 if target['name']=='The Needle' else s['round']['hands_left']
    capacity=q25*hands
    return {'samples':16,'q25':q25,'median':median,'target':target['score'],'hands':hands,
            'coverage':capacity/max(1,target['score']),'pressure':capacity<1.25*target['score'],
            'assumption':'public actual deck multiset and visible modifiers; no discards; heuristic, not win probability'}

def estimate(s):
    reduced={k:s[k] for k in ('ante_num','money','jokers','blinds','hands','round','hand','_belief','_normal_probability','_targets','_base_hands','_base_discards','_boss_disabled') if k in s}
    reduced['round']={k:v for k,v in reduced['round'].items() if k!='last_hand'}
    return _estimate(json.dumps(reduced,ensure_ascii=False,sort_keys=True))
