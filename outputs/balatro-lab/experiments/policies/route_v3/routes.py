"""Finite route selection from owned components; no seed or future game information."""
import advisor as a

def main_hand(s):
    ks=a.keys(s); hs=s['hands']
    if 'j_baron' in ks:return 'High Card'
    if 'j_obelisk' in ks:
        peak=max(h.get('played',0) for h in hs.values())
        if peak>=10:
            return max((n for n in ('Pair','Two Pair','High Card','Three of a Kind','Flush','Straight') if hs[n].get('played',0)<peak),key=lambda n:hs[n]['level']*3+(n=='Pair'),default='Pair')
    deck=s.get('_belief',{}).get('deck',[])
    if deck:
        from collections import Counter
        ranks=Counter(a.rank(c) for c in deck)
        if max(ranks.values())>=len(deck)*.3:
            for name in ('Flush Five','Five of a Kind','Four of a Kind'):
                if hs[name].get('played',0)>0:return name
    if 'j_trousers' in ks: return 'Two Pair'
    if 'j_four_fingers' in ks:
        return max(('Flush','Straight'),key=lambda n:hs[n]['level']*2+hs[n].get('played',0)*.35+(n=='Flush'))
    if 'j_order' in ks or 'j_runner' in ks: return 'Straight'
    if 'j_tribe' in ks: return 'Flush'
    if 'j_half' in ks or 'j_duo' in ks: return 'Pair'
    if {'j_photograph','j_hanging_chad'} <= ks: return 'Pair'
    if ks & {'j_green_joker','j_ride_the_bus'}:
        return max(('High Card','Pair'),key=lambda n:hs[n]['level']*3+hs[n].get('played',0)*.2)
    # Supernova follows the hand we have actually built; it does not prescribe high card.
    names=('Pair','Two Pair','Three of a Kind','Straight','Flush','Full House','High Card')
    return max(names,key=lambda n:hs[n]['level']*2+hs[n].get('played',0)*.35+(n=='Pair'))

def label(s):
    ks=a.keys(s)
    if {'j_photograph','j_hanging_chad'} <= ks:return '人头重触发'
    if ks & {'j_order','j_runner','j_tribe'}:return '牌型等级与条件乘倍'
    if ks & {'j_green_joker','j_ride_the_bus','j_supernova','j_half','j_trousers'}:return '小牌成长'
    return '过渡保命'
