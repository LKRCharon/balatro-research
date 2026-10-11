"""Retrieve archived evidence. Training inputs by default, never a live-game agent."""
import argparse
from collections import Counter
import json
from pathlib import Path

def select(report, *, cohort=None, method=None, joker=None, boss=None, origin=None,
           ante_min=None, ante_max=None, cash_max=None, perishable=False,
           research=False, include_consumed_validation=False, limit=20):
    if include_consumed_validation and not research:
        raise ValueError('Consumed validation requires explicit research mode')
    if not 1<=limit<=1000: raise ValueError('limit must be 1..1000')
    found=[]
    for case in report.get('cases',[]):
        lineage=case.get('lineage',{});features=case.get('input',{});decision=case.get('decision',{})
        partition=lineage.get('partition')
        if not research and case.get('labels',{}).get('action_error') is True:continue
        if partition!='train' and not (include_consumed_validation and partition=='validation_already_consumed'):continue
        if cohort and lineage.get('cohort')!=cohort:continue
        if method and decision.get('method')!=method:continue
        if origin and case.get('controller_origin')!=origin:continue
        lineup=features.get('lineup',[])
        if joker and joker!=decision.get('target_key') and joker not in {c.get('key') for c in lineup}:continue
        if boss and features.get('blind',{}).get('name')!=boss:continue
        ante=features.get('ante');cash=features.get('cash')
        if ante_min is not None and (ante is None or ante<ante_min):continue
        if ante_max is not None and (ante is None or ante>ante_max):continue
        if cash_max is not None and (cash is None or cash>cash_max):continue
        if perishable and not any(c.get('perishable') for c in lineup):continue
        # Explicit projection: labels never leak into default input retrieval.
        result={k:case[k] for k in ('case_id','lineage','controller_origin','plan','input','decision','evidence') if k in case}
        if research:result['labels']=case.get('labels',{})
        found.append(result)
        if len(found)>=limit:break
    return {'mode':'retrospective_research' if research else 'training_evidence_without_outcome_labels',
        'returned':len(found),'limit':limit,'results':found,
        'warning':'Archive cases are correlated demonstrations, not optimal actions. This interface does not inspect current games or recommend an action.'}

def inventory(report):
    cases=report.get('cases',[])
    return {'case_count':len(cases),'cohorts':dict(Counter(c.get('lineage',{}).get('cohort','unknown') for c in cases)),
        'partitions':dict(Counter(c.get('lineage',{}).get('partition','unknown') for c in cases)),
        'origins':dict(Counter(c.get('controller_origin','unknown') for c in cases)),
        'methods':dict(Counter(c.get('decision',{}).get('method','unknown') for c in cases)),
        'plans_explicitly_recorded':sum(bool(c.get('plan',{}).get('recorded')) for c in cases),
        'after_linked':sum(bool(c.get('labels',{}).get('after_linked')) for c in cases),
        'inventory':report.get('inventory',[])}

def select_rules(rulebook,key=None):
    return {'mode':'prospective_mechanism_checklist','rules':[
        {k:rule[k] for k in ('id','keys','condition','check','limit','evidence') if k in rule}
        for rule in rulebook.get('rules',[]) if key is None or key in rule.get('keys',[])],
        'warning':'Mechanism constraints only; no current state, outcome labels or action recommendation.'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('casebook',type=Path,nargs='?')
    parser.add_argument('--rules',type=Path,help='Query a prospective mechanism rulebook instead of archived cases')
    for field in ('cohort','method','joker','boss','origin'):parser.add_argument('--'+field)
    for field in ('ante-min','ante-max','cash-max'):parser.add_argument('--'+field,type=int)
    parser.add_argument('--perishable',action='store_true');parser.add_argument('--research',action='store_true')
    parser.add_argument('--include-consumed-validation',action='store_true');parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--inventory',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.rules:
        result=select_rules(json.loads(args.rules.read_text(encoding='utf-8')),args.joker)
    else:
        if args.casebook is None:parser.error('Provide a casebook file or --rules')
        report=json.loads(args.casebook.read_text(encoding='utf-8'))
        kwargs={k:v for k,v in vars(args).items() if k not in ('casebook','output','inventory','rules')}
        result=inventory(report) if args.inventory else select(report,**kwargs)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    else:print(text)

if __name__=='__main__':main()
