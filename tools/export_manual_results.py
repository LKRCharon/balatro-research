"""Publish aggregate results from an audited completed manual cohort; no raw states."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--lab',type=Path,required=True);parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args();source=args.lab/'results/manual-ten-002';target=Path(__file__).resolve().parents[1]/'results/manual-ten-002';target.mkdir(parents=True,exist_ok=True)
    audit=read(source/'integrity.json')
    if audit.get('audit')!='passed' or audit.get('completed')!=10 or not audit.get('complete'):raise ValueError('Final passed 10-run audit required')
    table=[]
    for entry in audit['sessions']:
        run=entry['seed_id'];path=args.work/f'experiments/manual-ten-002/train-{run}/transitions.jsonl'
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        end=next(row for row in reversed(rows) if row.get('event')=='result' and row.get('accepted') is not False and row.get('applied') is not False and row.get('after',{}).get('state')!='MENU')
        before=next(row['before'] for row in rows if row.get('event')=='intent' and row.get('id')==end['id'])
        blind=next((b for b in before.get('blinds',{}).values() if b.get('status')=='CURRENT'),{})
        table.append({'training_seed_id':run,'status':entry['status'],'ante':before.get('ante_num'),'terminal_ante':entry['ante'],
            'last_blind':blind.get('name'),'score':end['after'].get('round',{}).get('chips'),'target':blind.get('score'),
            'win_mechanism':'mr_bones_insurance' if run==35 else 'natural_score_clear' if run==39 else None,
            'first_attempt_in_this_cohort_loss':entry['status']=='loss','proven_unwinnable_seed':False,
            'controller_decisions':entry['controller_decisions'],'successful_gameplay_actions':entry['gameplay_actions'],
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    summary={'purpose':'adaptive_root_controlled_training_demonstrations','partition':'train','frozen_policy_evaluation':False,
        'assigned':10,'completed':10,'outcomes':audit['status_counts'],'controller_decisions':audit['controller_decisions'],
        'successful_gameplay_actions':audit['gameplay_actions'],'script_decisions':audit['script_decisions'],
        'rejected_no_mutation_attempts':audit['rejected_no_mutation_attempts'],'post_terminal_cleanup_actions':audit['post_terminal_cleanup_actions'],
        'prediction_checks':audit['prediction_checks'],'prediction_mismatches':audit['prediction_mismatches'],
        'uncertain_predictions':audit['uncertain_or_unavailable_predictions'],'games':table,
        'limitations':audit['limitations']+['Loss tags refer to first attempts in this cohort, not proof of globally new or unwinnable seeds.',
            'Run35 was a genuine insurance-triggered win below normal target; run39 exceeded normal target. Do not conflate scoring mechanisms.']}
    write(target/'summary.json',summary);write(source/'summary.json',summary)
    full=read(source/'telemetry.json');offers=Counter();rarity=Counter();selection=Counter();compact=[]
    for job in full['jobs']:
        offers.update(job['offer_counts_by_area']);rarity.update(job['observed_shop_joker_rarity_counts']);selection.update(job['selection_counts'])
        compact.append({k:job[k] for k in ('job_id','status','offer_counts_by_area','observed_shop_joker_rarity_counts','observed_shop_joker_offer_denominator','selection_counts','fingerprint_identity_exposures','unresolved_intents','actions_without_explicit_origin')})
    write(target/'telemetry.json',{'schema':1,'public_export':'aggregate_only','jobs':compact,'offers_by_area':dict(offers),
        'shop_joker_rarity_counts':dict(rarity),'resolved_selection_counts':dict(selection),
        'rarity_catalog':full.get('rarity_catalog'),'caveats':full['caveats'],
        'private_full_telemetry_sha256':hashlib.sha256((source/'telemetry.json').read_bytes()).hexdigest()})
    print(json.dumps({'games':len(table),'offers':sum(offers.values())}))

if __name__=='__main__':main()
