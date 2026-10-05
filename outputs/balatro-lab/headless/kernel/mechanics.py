"""Renderer-free original-Lua mechanism service. No profile or LÖVE access.

This is a mechanism kernel, NOT a complete run environment. Local game source
is loaded at runtime, never copied into this distribution.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import threading

LAB = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB / 'scripts'))
from lua_bridge import LuaRuntime

NAMES = ['High Card', 'Pair', 'Two Pair', 'Three of a Kind', 'Straight',
         'Flush', 'Full House', 'Four of a Kind', 'Straight Flush',
         'Five of a Kind', 'Flush House', 'Flush Five']

def literal(value):
    if value is None: return 'nil'
    if isinstance(value, bool): return str(value).lower()
    if isinstance(value, (int, float)):
        if not math.isfinite(value): raise ValueError('Nonfinite Lua number')
        return repr(value)
    if isinstance(value, str):
        return '"' + ''.join('\\%03d' % b for b in value.encode('utf-8')) + '"'
    if isinstance(value, list): return '{' + ','.join(map(literal, value)) + '}'
    if isinstance(value, dict):
        return '{' + ','.join('['+literal(k)+']='+literal(v) for k,v in value.items()) + '}'
    raise TypeError(type(value))

def extract(source, name):
    match = re.search(r'^function ' + re.escape(name) + r'\(', source, re.M)
    if not match: raise ValueError('Missing original function: '+name)
    following = re.search(r'^function ', source[match.end():], re.M)
    if not following: raise ValueError('Unbounded original function: '+name)
    return source[match.start():match.end()+following.start()]

class Kernel:
    def __init__(self, source, dll):
        self.owner = (os.getpid(), threading.get_ident())
        self.lua = LuaRuntime(dll)
        self.hashes = {}
        self.lua.execute('Card={}; G={jokers={cards={}},consumeables={cards={}},GAME={modifiers={}}}')
        files = {'functions/misc_functions.lua': ['find_joker', 'evaluate_poker_hand',
                 'get_flush','get_straight','get_X_same','get_highest','pseudohash',
                 'pseudoseed','get_blind_amount'],
                 'card.lua': ['Card:get_nominal','Card:get_id','Card:is_suit']}
        try:
            for filename, names in files.items():
                raw = (Path(source)/filename).read_bytes()
                self.hashes[filename] = hashlib.sha256(raw).hexdigest()
                text = raw.decode('utf-8-sig')
                for name in names: self.lua.execute(extract(text,name), name)
            self.reset('KERNEL')
        except Exception:
            self.close()
            raise

    def reset(self, seed):
        self._check_owner()
        if not isinstance(seed,str) or not seed: raise ValueError('Seed must be nonempty text')
        self.lua.execute('G.GAME.pseudorandom={seed='+literal(seed)+'}; G.GAME.pseudorandom.hashed_seed=pseudohash(G.GAME.pseudorandom.seed)')
        return {'source_sha256':self.hashes, 'scope':'mechanisms-only', 'renderer':False}

    def pseudoseed(self, key):
        self._check_owner()
        # key=seed calls unseeded global math.random in original; deliberately excluded.
        if not isinstance(key,str) or not key or key=='seed': raise ValueError('Named deterministic stream required')
        return float(self.lua.execute('return string.format("%.17g",pseudoseed('+literal(key)+'))',result=True))

    def blind_amount(self, ante, scaling=3):
        self._check_owner()
        if type(ante) is not int or not 0 <= ante <= 16 or scaling not in (1,2,3):
            raise ValueError('ante=0..16; scaling=1,2,3')
        self.lua.execute('G.GAME.modifiers.scaling='+str(scaling))
        return float(self.lua.execute('return string.format("%.17g",get_blind_amount('+str(ante)+'))',result=True))

    def classify(self, cards, jokers=None):
        self._check_owner()
        if not 1 <= len(cards) <= 5: raise ValueError('Submit 1..5 cards')
        prepared=[]
        for i,c in enumerate(cards):
            rank, suit = c['rank'],c['suit']
            if type(rank) is not int or not 2 <= rank <= 14 or suit not in ('Spades','Hearts','Clubs','Diamonds'):
                raise ValueError('rank=2..14 and full suit name required')
            # Stone get_id consumes global random values; never silently approximate it.
            if c.get('stone'): raise ValueError('Stone Card requires full engine RNG; unsupported')
            sn={'Diamonds':.01,'Clubs':.02,'Hearts':.03,'Spades':.04}[suit]
            prepared.append({'index':i,'base':{'id':rank,'suit':suit,'nominal':rank if rank<=10 else 11 if rank==14 else 10,
                'face_nominal':(rank-10)/10 if rank>10 else 0,'suit_nominal':sn,
                'suit_nominal_original':c.get('suit_nominal_original',sn/10)},
                'unique_val':c.get('unique_val',i+1),'ability':{'name':'Wild Card' if c.get('wild') else 'Default','effect':'Base'},
                'debuff':bool(c.get('debuff'))})
        js=[]
        for j in jokers or []:
            if isinstance(j,str): j={'name':j}
            if j['name'] not in ('Four Fingers','Shortcut','Smeared Joker'): raise ValueError('Unsupported classifier joker')
            js.append({'ability':{'name':j['name']},'debuff':bool(j.get('debuff'))})
        code='local hand='+literal(prepared)+'; G.jokers.cards='+literal(js)+''';
        for _,c in ipairs(hand) do setmetatable(c,{__index=Card}) end
        local result=evaluate_poker_hand(hand); local names='''+literal(NAMES)+'''
        for i=#names,1,-1 do if next(result[names[i]]) then
          local out={}; for _,c in ipairs(result[names[i]][1]) do out[#out+1]=c.index end
          return names[i]..':'..table.concat(out,',')
        end end'''
        name, indices=self.lua.execute(code,result=True).split(':')
        return {'hand':name,'scoring_indices':[int(x) for x in indices.split(',') if x]}

    def _check_owner(self):
        if self.owner != (os.getpid(), threading.get_ident()):
            raise RuntimeError('Lua kernel cannot cross process or thread boundaries; construct a new worker-local Kernel')
    def __getstate__(self):
        raise TypeError('Live Lua native handles are not serializable; pass source/dll paths to workers')
    def close(self):
        self._check_owner()
        self.lua.close()
    def __enter__(self): return self
    def __exit__(self,*_): self.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--dll',type=Path,required=True)
    args=parser.parse_args()
    with Kernel(args.source,args.dll) as kernel:
        for line in sys.stdin:
            try:
                request=json.loads(line)
                method=request['method']
                if method not in ('reset','classify','pseudoseed','blind_amount'): raise ValueError('Unsupported method')
                result=getattr(kernel,method)(**request.get('params',{}))
                response={'result':result}
            except Exception as exc: response={'error':str(exc)}
            print(json.dumps(response,ensure_ascii=False),flush=True)

if __name__=='__main__': main()
