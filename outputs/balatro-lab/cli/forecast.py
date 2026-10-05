"""Conservative next-blind pressure estimate, with a documented vanilla-deck approximation.

Samples hypothetical unordered 52-card hands using Python's private RNG, never game RNG.
Does not claim independent future hands or a calibrated win probability.
"""
import copy, functools, json, random
import advisor as a

@functools.lru_cache(maxsize=512)
def _estimate(encoded):
    s=json.loads(encoded)
    target=next((s['blinds'][k] for k in ('small','big','boss') if s['blinds'][k]['status'] not in ('DEFEATED','SKIPPED')),s['blinds']['boss'])
    for b in s['blinds'].values(): b['status']='UPCOMING'
    target['status']='CURRENT'
    for h in s['hands'].values():h['played_this_round']=0
    size=max(5,min(12,int(s.get('hand',{}).get('limit',8))))
    deck=[{'key':su+'_'+r,'value':{'rank':r,'suit':su},'modifier':{},'state':{}}
          for su in ('S','H','C','D') for r in ('2','3','4','5','6','7','8','9','T','J','Q','K','A')]
    rng=random.Random(20261004)
    scores=[]
    for _ in range(16):
        hand=copy.deepcopy(rng.sample(deck,size))
        banned={'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(target['name'])
        for c in hand:
            if c['value']['suit']==banned or (target['name']=='The Plant' and c['value']['rank'] in ('J','Q','K')):c['state']['debuff']=True
        s['hand']={'cards':hand,'count':size,'limit':size};s['cards']={'count':52-size,'limit':52}
        scores.append(a.options(s)[0][0])
    scores.sort(); q25=scores[3];median=(scores[7]+scores[8])/2
    hands=1 if target['name']=='The Needle' else s['round']['hands_left']
    capacity=q25*hands
    return {'samples':16,'q25':q25,'median':median,'target':target['score'],'hands':hands,
            'coverage':capacity/max(1,target['score']),'pressure':capacity<1.25*target['score'],
            'assumption':'unmodified 52-card deck, no discards; heuristic coverage, not a survival probability'}

def estimate(s):
    reduced={k:s[k] for k in ('ante_num','money','jokers','blinds','hands','round','hand') if k in s}
    reduced['round']={k:v for k,v in reduced['round'].items() if k!='last_hand'}
    return _estimate(json.dumps(reduced,ensure_ascii=False,sort_keys=True))
