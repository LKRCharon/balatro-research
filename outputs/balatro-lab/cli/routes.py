"""Finite route selection from owned components; no seed or future game information."""
import advisor as a

def main_hand(s):
    ks=a.keys(s); hs=s['hands']
    if 'j_trousers' in ks: return 'Two Pair'
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
