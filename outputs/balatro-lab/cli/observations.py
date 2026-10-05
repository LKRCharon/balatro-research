"""Recover public round history; attempted but blocked hands do not unlock The Mouth."""
ZH_TO_EN=dict(zip(['高牌','对子','两对','三条','顺子','同花','葫芦','四条','同花顺','五条','同花葫芦','同花五条'],
                  ['High Card','Pair','Two Pair','Three of a Kind','Straight','Flush','Full House','Four of a Kind','Straight Flush','Five of a Kind','Flush House','Flush Five']))

def enrich(s,previous=None):
    boss=next((b['name'] for b in s.get('blinds',{}).values() if b['status']=='CURRENT'),'')
    if boss!='The Mouth' or not s.get('round',{}).get('hands_played'):return s
    locked=None
    if previous and previous.get('round_num')==s.get('round_num'):
        locked=previous.get('round',{}).get('mouth_hand')
        if not locked:
            prior=[n for n,h in previous.get('hands',{}).items() if h.get('played_this_round',0)]
            if len(prior)==1:locked=prior[0]
    if not locked:
        prior=[n for n,h in s.get('hands',{}).items() if h.get('played_this_round',0)]
        if len(prior)==1:locked=prior[0]
    if locked:s['round']['mouth_hand']=locked
    return s
