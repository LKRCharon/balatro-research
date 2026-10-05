"""Offline calibration on original Lua and previously observed training trajectories."""
import json, random, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
LAB=HERE.parent
ROOT=LAB.parents[1]
sys.path[:0]=[str(HERE/'policies/route_v1'),str(LAB/'cli'),str(LAB/'scripts')]
import advisor as a
import observations
from lua_bridge import LuaRuntime

def card(i):
    return {'key':'SHCD'[i//13]+'_'+('23456789TJQKA'[i%13]),
            'value':{'rank':'23456789TJQKA'[i%13],'suit':'SHCD'[i//13]},'modifier':{},'state':{}}

def calibrate():
    source=(ROOT/'work/installed-source/functions/misc_functions.lua').read_text(encoding='utf-8')
    def fn(name):
        start=source.index('function '+name+'(');end=source.find('\nfunction ',start+1)
        return source[start:end if end>=0 else len(source)]
    cases=0
    with LuaRuntime(r'D:\download\SteamGame\steamapps\common\Balatro\lua51.dll') as lua:
        lua.execute('four=false; function find_joker(k) if four and k=="Four Fingers" then return {true} else return {} end end')
        for name in ('evaluate_poker_hand','get_flush','get_straight','get_X_same','get_highest'):
            lua.execute(fn(name))
        lua.execute('''function classify(ids, ff)
          four=ff; local hand={};local suits={'Spades','Hearts','Clubs','Diamonds'}
          for i,id in ipairs(ids) do
            local r,suit=id%13+2,suits[math.floor(id/13)+1]
            hand[i]={index=i-1,get_id=function() return r end,get_nominal=function() return r end,
              is_suit=function(_,s) return s==suit end}
          end
          local result=evaluate_poker_hand(hand)
          local names={'High Card','Pair','Two Pair','Three of a Kind','Straight','Flush','Full House',
            'Four of a Kind','Straight Flush','Five of a Kind','Flush House','Flush Five'}
          for k=#names,1,-1 do if next(result[names[k]]) then
            local scored={}; for _,c in ipairs(result[names[k]][1]) do scored[#scored+1]=c.index end
            table.sort(scored);return (k-1)..':'..table.concat(scored,',')
          end end
        end''')
        rng=random.Random(9321)
        hands=[[0,1,2,16,9],[0,1,2,16],[12,0,1,15,9],[9,10,11,25,0],[0,13,26,1,14]]
        hands += [rng.sample(range(52),n) for n in range(1,6) for _ in range(800)]
        for ff in (False,True):
            for ids in hands:
                cards=[card(i) for i in ids];cat,scored,_=a.classify(cards,range(len(cards)),ff)
                actual=lua.execute('return classify({'+','.join(map(str,ids))+'},'+str(ff).lower()+')',result=True)
                expected=str(cat)+':'+','.join(map(str,sorted(scored)))
                assert actual==expected,(ff,ids,actual,expected)
                cases+=1
    checked=[];skipped=[];mismatches=[]
    for rid in range(1,22):
        path=LAB/f'results/cli-runs/run-{rid:02d}.jsonl'
        if not path.exists():continue
        prev=None
        for lineno,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            row=json.loads(line);s=row.get('result',{});observations.enrich(s,prev)
            if row['method']=='play' and not row.get('error') and prev and prev.get('state')=='SELECTING_HAND':
                ident={'run':rid,'line':lineno};actual=s.get('round',{}).get('last_hand',{}).get('total')
                if a.uncertain(prev) or actual is None or a.keys(prev)-a.SUPPORTED:skipped.append(ident)
                else:
                    predicted=a.score(prev,row['params']['cards'])[0]
                    item={**ident,'predicted':predicted,'actual':actual};checked.append(item)
                    if abs(predicted-actual)>1:mismatches.append(item)
            if 'state' in s:prev=s
    report={'lua_classifier_cases':cases,'historical_checked':len(checked),'historical_skipped':len(skipped),
            'exact_matches':sum(c['predicted']==c['actual'] for c in checked),
            'rounding_tolerance':1,'mismatches':mismatches,'cases':checked,
            'scope':'Public deterministic hands from training history; displayed float multipliers tolerate one point; not whole engine parity.'}
    (LAB/'results/route-v1-calibration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
    return report

if __name__=='__main__':
    r=calibrate()
    if r['mismatches']:raise SystemExit(1)
