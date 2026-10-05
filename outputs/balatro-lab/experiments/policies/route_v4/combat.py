"""Bounded public-belief two-action combat search, not a full game simulator.

Root play/discard -> best next play. Static supported mechanics only; mutable or
hidden transitions explicitly fall back. Six shared hypothetical deck shuffles
are scenarios, not calibrated win probabilities or knowledge of future cards.
"""
import copy
import hashlib
import itertools
import json
import random
import time
from collections import defaultdict
import advisor as a

SAMPLES = 6
MAX_CANDIDATES = 10
SAFE_JOKERS = set('j_joker j_greedy_joker j_lusty_joker j_wrathful_joker j_gluttenous_joker j_jolly j_zany j_mad j_crazy j_droll j_sly j_wily j_clever j_devious j_crafty j_half j_stencil j_four_fingers j_mime j_banner j_mystic_summit j_fibonacci j_scary_face j_abstract j_even_steven j_odd_todd j_scholar j_blackboard j_blue_joker j_splash j_shortcut j_baron j_photograph j_juggler j_baseball j_walkie_talkie j_smiley j_acrobat j_sock_and_buskin j_smeared j_hanging_chad j_arrowhead j_onyx_agate j_flower_pot j_blueprint j_brainstorm j_seeing_double j_duo j_trio j_family j_order j_tribe j_stuntman j_shoot_the_moon j_triboulet j_chicot'.split())
SAFE_JOKERS.update({'j_bull','j_bootstraps','j_steel_joker','j_stone','j_erosion','j_drivers_license'})
SAFE_BOSSES = {'Small Blind','Big Blind','The Club','The Goad','The Window','The Head','The Plant',
               'The Psychic','The Wall','The Flint','The Needle','The Manacle','The Water',
               'The Eye','The Mouth','The Serpent','Violet Vessel'}
last_diagnostics = {}

def boss(s):
    return next((b for b in s['blinds'].values() if b['status']=='CURRENT'), {})

def card_token(card):
    return json.dumps({k: card.get(k) for k in ('key','value','modifier','permanent_bonus')}, sort_keys=True, ensure_ascii=False)

def support_reason(s):
    if s.get('state') != 'SELECTING_HAND': return 'not_combat'
    if not s.get('_belief') or 'unseen' not in s['_belief']: return 'missing_public_unseen_multiset'
    if s.get('_uncertain_jokers') or s['_belief'].get('hidden_identity_approximation'): return 'hidden_identity'
    unsupported = a.keys(s) - SAFE_JOKERS
    if unsupported: return 'mutable_or_unmodeled_jokers:' + ','.join(sorted(unsupported))
    if boss(s).get('name') not in SAFE_BOSSES and not (s.get('_boss_disabled') or 'j_chicot' in a.keys(s)):
        return 'unmodeled_boss:' + str(boss(s).get('name'))
    for card in s['hand']['cards'] + s['_belief']['unseen']:
        if a.st(card).get('hidden') or a.st(card).get('face_down'): return 'hidden_card'
        if a.mod(card).get('enhancement') in ('GLASS','LUCKY') or a.mod(card).get('seal') in ('PURPLE','GOLD'):
            return 'random_or_mutating_card_effect'
    if len(s['hand']['cards']) > 10: return 'hand_size_budget'
    return None

def scenarios(s, count=SAMPLES):
    """Permutation-invariant public card multiset; draws consume distinct indices."""
    deck = sorted(copy.deepcopy(s['_belief']['unseen']), key=card_token)
    observed = {'hand':[card_token(c) for c in s['hand']['cards']],
                'deck':[card_token(c) for c in deck],
                'hands':s['round']['hands_left'], 'discards':s['round']['discards_left']}
    seed = int.from_bytes(hashlib.sha256(json.dumps(observed,sort_keys=True).encode()).digest()[:8], 'little')
    rng = random.Random(seed)
    worlds = []
    for _ in range(count):
        world = copy.deepcopy(deck); rng.shuffle(world); worlds.append(world)
    return worlds

def candidates(s, fallback):
    """At most 10 roots, including score-tied junk cycling and discard variants."""
    opts = a.options(s, optimize_order=False)
    roots = []
    def add(method, selected):
        item = (method, tuple(sorted(selected)))
        if item[1] and len(item[1]) <= 5 and item not in roots: roots.append(item)
    if fallback and fallback[0] in ('play','discard'): add(fallback[0],fallback[1]['cards'])
    best = opts[0]
    add('play',best[1])
    # Select score-tied alternatives by actual scoring result, so adding junk
    # never silently turns Half Joker off or changes the relevant hand type.
    tied = [o for o in opts if o[0] == best[0] and o[2] == best[2]]
    for option in sorted(tied,key=lambda o:(-len(o[1]),o[1]))[:3]: add('play',option[1])
    for option in opts:
        if len(roots) >= 6: break
        add('play',option[1])
    if s['round']['discards_left'] > 0:
        add('discard',a.discard(s,best))
        add('discard',[i for i in range(len(s['hand']['cards'])) if i not in best[3]][:5])
        suits = defaultdict(list)
        for i,card in enumerate(s['hand']['cards']): suits[a.suit(card)].append(i)
        for keep in sorted(suits.values(),key=lambda g:(-len(g),g))[:2]:
            add('discard',[i for i in range(len(s['hand']['cards'])) if i not in keep][:5])
    return roots[:MAX_CANDIDATES]

def transition(s, method, selected, world):
    """One supported-model action; returns new public state, unused world, score."""
    sim = copy.deepcopy(s)
    selected = tuple(selected)
    score = 0
    if method == 'play':
        score,name,_ = a.score(s, selected)
        sim['round']['hands_left'] -= 1
        sim['round']['hands_played'] = sim['round'].get('hands_played',0) + 1
        sim['round']['chips'] += score
        sim['hands'][name]['played_this_round'] = sim['hands'][name].get('played_this_round',0) + 1
        sim['hands'][name]['played'] = sim['hands'][name].get('played',0) + 1
        if boss(s).get('name') == 'The Mouth' and not sim['round'].get('mouth_hand'):
            sim['round']['mouth_hand'] = name
    else:
        sim['round']['discards_left'] -= 1
        sim['round']['discards_used'] = sim['round'].get('discards_used',0) + 1
    hand = [c for i,c in enumerate(sim['hand']['cards']) if i not in selected]
    refill = max(0,s['hand']['limit'] - len(hand))
    if boss(s).get('name') == 'The Serpent' and not (s.get('_boss_disabled') or 'j_chicot' in a.keys(s)): refill = 3
    count = min(refill,len(world))
    hand += copy.deepcopy(world[:count])
    boss_name = boss(s).get('name') if not (s.get('_boss_disabled') or 'j_chicot' in a.keys(s)) else ''
    banned = {'The Club':'C','The Goad':'S','The Window':'D','The Head':'H'}.get(boss_name)
    for card in hand:
        if a.suit(card) == banned or (boss_name == 'The Plant' and a.rank(card) in (11,12,13)):
            card.setdefault('state',{})['debuff'] = True
    sim['hand']['cards'] = hand; sim['hand']['count'] = len(hand)
    sim['cards']['count'] = max(0,s['cards']['count'] - count)
    sim['_belief']['unseen'] = sorted(copy.deepcopy(world[count:]), key=card_token)
    return sim, world[count:], score

def scenario_value(s, candidate, world, cache=None):
    method, selected = candidate
    after, _, score = transition(s,method,selected,world)
    need = boss(s)['score'] - s['round']['chips']
    if score >= need: return {'clear':True,'score':need,'hands_used':1,'root_score':score}
    follow = 0
    if after['round']['hands_left'] > 0 and after['hand']['cards']:
        key = json.dumps({k:after[k] for k in ('hand','jokers','round','hands','blinds','cards','money')},sort_keys=True)
        if cache is not None and key in cache: follow = cache[key]
        else:
            follow = a.options(after,optimize_order=False)[0][0]
            if cache is not None: cache[key] = follow
    total = score + follow
    return {'clear':total >= need,'score':min(need,total),'hands_used':int(method=='play')+int(follow>0),'root_score':score}

def choose(s, fallback):
    global last_diagnostics
    begin = time.monotonic()
    reason = support_reason(s)
    last_diagnostics = {'attempted':True,'supported':reason is None,'fallback_reason':reason,'used':False,'action_changed':False,
                        'candidate_count':0,'samples':0,'estimated_two_action_clear_fraction':None}
    def finish(action):
        last_diagnostics['elapsed_seconds'] = time.monotonic()-begin
        if reason and action:
            action = (action[0],dict(action[1]))
            action[1]['reason'] = action[1].get('reason','') + ' [v4沿用v3: '+reason+']'
        return action
    if reason: return finish(fallback)
    if not fallback or fallback[0] not in ('play','discard'):
        last_diagnostics['fallback_reason']='preserve_special_action'; return finish(fallback)
    need = boss(s)['score'] - s['round']['chips']
    if fallback[0]=='play' and a.score(s,fallback[1]['cards'])[0] >= need:
        last_diagnostics['fallback_reason']='already_winning'; return finish(fallback)
    roots = candidates(s,fallback); worlds = scenarios(s); cache = {}; ranked = []
    for index,root in enumerate(roots):
        values = [scenario_value(s,root,world,cache) for world in worlds]
        scores = sorted(v['score'] for v in values)
        clears = sum(v['clear'] for v in values)/len(values)
        # First sample clear rate, then lower-tail progress, then mean progress;
        # preserve hands on ties. These are scenario rankings, not probabilities.
        rank = (clears, scores[max(0,len(scores)//4-1)],sum(scores)/len(scores),
                -sum(v['hands_used'] for v in values)/len(values), -int(root[0]=='discard'),-index)
        ranked.append((rank,root))
    rank,(method,selected) = max(ranked)
    last_diagnostics.update(candidate_count=len(roots),samples=len(worlds),
        estimated_two_action_clear_fraction=rank[0],selected_method=method,
        selected_cards=list(selected),score_cache_entries=len(cache),used=True,
        action_changed=(method != fallback[0] or list(selected) != fallback[1].get('cards')))
    return finish((method,{'cards':list(selected),'reason':f'v4公开牌组两动作抽样：{len(roots)}个候选、{len(worlds)}种假想补牌，样本过关比例{rank[0]:.2f}；优先生存与低分尾部，再比较手数。该比例不是校准胜率。'}))
