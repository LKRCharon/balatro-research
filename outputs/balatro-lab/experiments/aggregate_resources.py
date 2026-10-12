"""Aggregate completed resource reports without raw states, seeds or causal claims."""
import argparse
from collections import Counter
import json
from pathlib import Path


def aggregate(reports):
    groups={};seen=set()
    for report in reports:
        for run in report['runs']:
            n=run['run_id']
            if n in seen:raise ValueError('Duplicate run id')
            seen.add(n)
            if run.get('status') not in ('win','loss'):raise ValueError('Terminal result required')
            group='hindsight_replay' if n in (32,33,34,36,37,38,40,41) else 'new_train' if n in range(42,47) else None
            if group is None:raise ValueError('Run outside campaign allowlist')
            g=groups.setdefault(group,{'completed':0,'outcomes':Counter(),'quoted_costs':Counter(),'exposures_by_area':Counter(),'cash_covered_exposures_by_area':Counter(),'resource_actions':Counter(),'selected_keys':Counter()})
            g['completed']+=1;g['outcomes'][run['status']]+=1;g['quoted_costs'].update(run['quoted_acquisition_costs'])
            for offer in run['offer_exposures']:
                g['exposures_by_area'][offer['area']]+=1
                if offer['cash_covers_price_when_first_seen']:g['cash_covered_exposures_by_area'][offer['area']]+=1
            for e in run['resource_events']:
                g['resource_actions'][e['method']]+=1
                if e['target_key'] and e['method'] in ('buy','pack','use'):g['selected_keys'][e['target_key']]+=1
    return {'schema':1,'purpose':'training_campaign_resource_aggregates','formal_winrate_claim':False,'groups':groups,
        'limitations':['Exposure identity deduplicated within run/area, not independent shop draws.','Selection counts include buys and later use; not unique purchases.','Cash coverage ignores credit and slot legality.','Quoted costs exclude rental and triggered income; not net expenditure.','Adaptive mixed controller/script policy; cohorts are not frozen evaluation.']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    reports=[json.loads((a.root/f'train-{n}-resources.json').read_text(encoding='utf-8')) for n in (32,33,34,36,37,38,40,41,42,43,44,45,46)]
    a.output.write_text(json.dumps(aggregate(reports),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':main()
