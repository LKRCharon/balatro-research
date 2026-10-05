"""Public collection minus public discard/hand; no hidden identity or future draw order."""
import copy,collections

def base_deck():
    return {su+'_'+r:{'key':su+'_'+r,'value':{'rank':r,'suit':su},'modifier':{},'state':{}}
            for su in 'SHCD' for r in '23456789TJQKA'}

def signature(c):
    return (c['key'],tuple((k,c.get('modifier',{}).get(k)) for k in ('enhancement','edition','seal')),c.get('permanent_bonus',0))

class Belief:
    def __init__(self):self.jokers=[]
    def observe(self,s,context=None,targets=None):
        s=copy.deepcopy(s)
        if context is None:raise ValueError('v2 requires an actual public collection snapshot')
        for item in context.get('visible_hand',[]):
            if item['index']<len(s['hand']['cards']) and not s['hand']['cards'][item['index']].get('state',{}).get('hidden'):
                s['hand']['cards'][item['index']]['permanent_bonus']=item['permanent_bonus']
        for rows in (context['deck_multiset'],context['visible_discard']):
            for row in rows:
                for field in ('modifier','state','value'):row['card'][field]=row['card'].get(field) or {}
        deck=[copy.deepcopy(row['card']) for row in context['deck_multiset'] for _ in range(row['count'])]
        excluded=collections.Counter()
        for row in context['visible_discard']:excluded[signature(row['card'])]+=row['count']
        for c in s.get('hand',{}).get('cards',[]):
            if not c.get('state',{}).get('hidden'):excluded[signature(c)]+=1
        unseen=[]
        for c in deck:
            key=signature(c)
            if excluded[key]>0:excluded[key]-=1
            else:unseen.append(c)
        hidden=any(c.get('state',{}).get('hidden') for c in s['jokers']['cards'])
        if hidden:s['jokers']['cards']=copy.deepcopy(self.jokers);s['_uncertain_jokers']=True
        else:self.jokers=copy.deepcopy(s['jokers']['cards'])
        s['_belief']={'deck':deck,'unseen':unseen,'starting_size':context.get('starting_deck_size',52),
                      'hidden_identity_approximation':any(c.get('state',{}).get('hidden') for c in s.get('hand',{}).get('cards',[]))}
        s['_normal_probability']=context['probability_normal']
        for item in context.get('joker_counters',[]):
            if item['index']<len(s['jokers']['cards']):s['jokers']['cards'][item['index']]['_loyalty_remaining']=item['loyalty_remaining']
        s['_boss_disabled']=context.get('boss_disabled',False);s['_last_consumable']=context.get('last_consumable')
        s['_base_hands']=context.get('base_hands',5);s['_base_discards']=context.get('base_discards',2)
        s['_targets']={t['key']:t for t in (targets or {}).get('targets',[])}
        return s
