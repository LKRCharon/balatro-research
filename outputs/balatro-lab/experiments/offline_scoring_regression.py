"""Replay only public observations into a scorer; never contacts a game engine."""
import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import sys


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines() if line.strip()]


def collect(root):
    """Use previously completed episodes only and exclude raw seed/config fields."""
    fixtures=[]
    for session in sorted(Path(root).glob('train-*')):
        result=json.loads((session/'result.json').read_text(encoding='utf8'))
        if not result.get('terminal'):raise ValueError('Regression input must be completed')
        decisions={row['sequence']:row for row in rows(session/'decisions.jsonl')}
        outcomes={row['id']:row['after'] for row in rows(session/'transitions.jsonl') if row['event']=='result'}
        predictions={row['transition_id']:row for row in rows(session/'predictions.jsonl')}
        plays={seq:row for seq,row in decisions.items() if row['method']=='play'}
        if set(plays)!=set(predictions):raise ValueError('Missing or duplicate play coverage')
        for seq,decision in plays.items():
            before=decision['before'];after=outcomes[seq]
            actual=after.get('round',{}).get('last_hand',{}).get('total')
            if before['round']['chips']==after['round']['chips']:actual=0
            if predictions[seq]['actual']!=actual:raise ValueError('Actual score differs from engine journal')
            fixtures.append({'episode':session.name,'sequence':seq,'before':before,
                'cards':decision['params']['cards'],'actual':actual,
                'original_uncertain':predictions[seq]['within_one'] is None})
    return fixtures


def evaluate(fixtures,advisor):
    counts=Counter();failures=[];promoted=[]
    for row in fixtures:
        counts['plays']+=1
        try:
            state=row['before'];predicted=advisor.score(state,row['cards'])[0]
            uncertain=advisor.uncertain(state)
        except Exception as exc:
            counts['scorer_errors']+=1
            failures.append({'episode':row['episode'],'sequence':row['sequence'],'error':type(exc).__name__})
            continue
        if uncertain:counts['uncertain']+=1
        else:
            counts['checkable']+=1
            if row['actual'] is None or abs(predicted-row['actual'])>1:
                counts['mismatches']+=1
                failures.append({'episode':row['episode'],'sequence':row['sequence'],'predicted':predicted,'actual':row['actual']})
        if row['original_uncertain'] and not uncertain:promoted.append({'episode':row['episode'],'sequence':row['sequence']})
        if not row['original_uncertain'] and uncertain:counts['coverage_regressions']+=1
    return {'counts':dict(counts),'failures':failures,'newly_declared_exact':promoted,
        'passed_existing_exact':not failures and not counts['coverage_regressions'],
        'scope':'Historical TRAIN chosen-action regression, not new cross-engine or counterfactual coverage.'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sessions',required=True)
    p.add_argument('--scorer-folder',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    folder=Path(a.scorer_folder).resolve();sys.path[:0]=[str(folder),str(Path(__file__).resolve().parents[1]/'cli')]
    advisor=importlib.import_module('advisor')
    result=evaluate(collect(a.sessions),advisor)
    result['scorer_files']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.glob('*.py')}
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='scorer_files'}))
