"""Independent original-Lua classification plus historical training-score residuals."""
import json,random,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;LAB=HERE.parent;ROOT=LAB.parents[1]
sys.path[:0]=[str(HERE/'policies/route_v2'),str(LAB/'cli'),str(LAB/'scripts')]
import advisor as a
import balatro_cli as cli
import observations
from lua_bridge import LuaRuntime

def main():
    source=(ROOT/'work/installed-source/functions/misc_functions.lua').read_text(encoding='utf-8')
    def fn(name):
        start=source.index('function '+name+'(');end=source.find('\nfunction ',start+1);return source[start:end]
    cases=0;rng=random.Random(939)
    with LuaRuntime(r'D:\download\SteamGame\steamapps\common\Balatro\lua51.dll') as lua:
        lua.execute("flags={};function find_joker(name) return flags[name] and {true} or {} end")
        for name in ('evaluate_poker_hand','get_flush','get_straight','get_X_same','get_highest'):lua.execute(fn(name))
        lua.execute('''function check(ids,ff,shortcut,smeared)
          flags={['Four Fingers']=ff,['Shortcut']=shortcut,['Smeared Joker']=smeared};local cards={}
          local suits={'Spades','Hearts','Clubs','Diamonds'}
          for i,id in ipairs(ids) do
            local r=id%13+2;local s=suits[math.floor(id/13)+1]
            cards[i]={index=i-1,get_id=function() return r end,get_nominal=function() return r end,
              is_suit=function(_,su) return s==su or (smeared and ((s=='Hearts' or s=='Diamonds')==(su=='Hearts' or su=='Diamonds'))) end}
          end
          local names={'High Card','Pair','Two Pair','Three of a Kind','Straight','Flush','Full House','Four of a Kind','Straight Flush','Five of a Kind','Flush House','Flush Five'}
          local result=evaluate_poker_hand(cards)
          for k=#names,1,-1 do if next(result[names[k]]) then
            local out={};for _,c in ipairs(result[names[k]][1]) do out[#out+1]=c.index end;table.sort(out)
            return (k-1)..':'..table.concat(out,',')
          end end
        end''')
        for ff in (False,True):
            for shortcut in (False,True):
                for smeared in (False,True):
                    for _ in range(1000):
                        ids=rng.sample(range(52),rng.randint(1,5))
                        cards=[{'value':{'rank':'23456789TJQKA'[i%13],'suit':'SHCD'[i//13]},'modifier':{},'state':{}} for i in ids]
                        cat,scored,_=a.classify(cards,range(len(cards)),ff,shortcut,smeared)
                        got=lua.execute('return check({'+','.join(map(str,ids))+'},'+','.join(str(x).lower() for x in (ff,shortcut,smeared))+')',result=True)
                        expected=str(cat)+':'+','.join(map(str,sorted(scored)))
                        assert got==expected,(ids,ff,shortcut,smeared,got,expected)
                        cases+=1
    checks=[];skips=0
    # Only previous training trajectories. Never consult held-out trajectories or seeds.
    for rid in range(1,27):
        path=LAB/f'results/cli-runs/run-{rid:02d}.jsonl'
        if not path.exists():continue
        prev=None
        for n,line in enumerate(path.read_text(encoding='utf-8').splitlines(),1):
            row=json.loads(line);s=cli.sanitize(row.get('result',{}));observations.enrich(s,prev)
            if row['method']=='play' and not row.get('error') and prev and prev.get('state')=='SELECTING_HAND':
                actual=s.get('round',{}).get('last_hand',{}).get('total')
                # Old logs lack the public joint deck snapshot / variable rank-suit targets.
                unavailable=a.keys(prev)&{'j_ancient','j_idol','j_drivers_license','j_stone','j_erosion','j_steel_joker','j_hiker'}
                if a.uncertain(prev) or actual is None or unavailable:skips+=1
                else:
                    predicted=a.score(prev,row['params']['cards'])[0]
                    checks.append({'run':rid,'line':n,'predicted':predicted,'actual':actual,'within_one':abs(predicted-actual)<=1})
            if 'state' in s:prev=s
    result={'classifier_cases':cases,'score_checks':len(checks),'skipped':skips,
            'exact':sum(x['predicted']==x['actual'] for x in checks),'within_one':sum(x['within_one'] for x in checks),
            'mismatches':[x for x in checks if not x['within_one']],'cases':checks}
    (LAB/'results/route-v2-calibration.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='cases'}))

if __name__=='__main__':main()
