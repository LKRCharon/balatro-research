"""Check the current scoring model against already completed real-engine trajectories."""
import json
import advisor as a
import balatro_cli as cli
import observations

def main():
    checked=[];skipped=[];mismatches=[]
    for p in sorted(cli.RUNS.glob('run-??-outcome.json')):
        rid=cli.read(p)['run'];previous=None
        for lineno,line in enumerate((cli.RUNS/f'run-{rid:02d}.jsonl').read_text(encoding='utf-8').splitlines(),1):
            row=json.loads(line);s=row.get('result',{});observations.enrich(s,previous)
            if row['method']=='play' and not row.get('error') and previous and previous.get('state')=='SELECTING_HAND':
                ident={'run':rid,'line':lineno}
                actual=s.get('round',{}).get('last_hand',{}).get('total')
                if a.uncertain(previous) or actual is None:
                    skipped.append({**ident,'reason':'random, hidden, or no scoring result'})
                elif a.keys(previous)-a.SUPPORTED:
                    skipped.append({**ident,'reason':'unsupported scoring mechanic'})
                else:
                    predicted=a.score(previous,row['params']['cards'])[0]
                    result={**ident,'predicted':predicted,'actual':actual}
                    checked.append(result)
                    if predicted!=actual:mismatches.append(result)
            if 'state' in s:previous=s
    result={'checked':len(checked),'matched':len(checked)-len(mismatches),'skipped':len(skipped),
            'mismatches':mismatches,'cases':checked,'excluded':skipped,
            'scope':'Recorded visible deterministic play decisions only; not whole-engine parity.'}
    cli.write(cli.LAB/'results/cli-replay-validation.json',result)
    print(json.dumps({k:result[k] for k in ('checked','matched','skipped','mismatches')},ensure_ascii=False))
    if mismatches:raise SystemExit(1)

if __name__=='__main__':main()
