"""Join recorded shop calculations to public decision states without an engine."""
import argparse
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path


def commitment(state):
    # Match train_shard_v4 exactly: sorted compact JSON, default ensure_ascii=True.
    # Do not use environment.canonical_state, which removes additional fields.
    return hashlib.sha256(json.dumps(state,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def read_rows(path):
    data=path.read_bytes() if path.exists() else b''
    rows=[];partial=False
    for number,line in enumerate(data.splitlines()):
        if not line.strip():continue
        try:rows.append(json.loads(line))
        except (ValueError,UnicodeDecodeError):
            if number==len(data.splitlines())-1 and not data.endswith(b'\n'):partial=True
            else:raise
    return rows,partial


def selected_matches(selected,decision):
    if not isinstance(selected,(list,tuple)) or len(selected)!=2:return False
    method,params=selected
    actual=decision['params']
    # iterative_train adds a generic reason only if the policy omitted it.
    return method==decision['method'] and all(actual.get(k)==v for k,v in params.items()) and set(actual)-set(params)<={'reason'}


def audit_rows(records,decisions,complete=False):
    by_hash=defaultdict(list)
    for d in decisions:
        if 'before' in d and d['before'].get('state') in ('SHOP','SMODS_BOOSTER_OPENED'):
            by_hash[commitment(d['before'])].append(d)
    assert [r['call'] for r in records]==list(range(1,len(records)+1)), 'Missing, duplicate or reordered call'
    matches=[];unresolved=[];last_sequence=-1;reasons=Counter();selected_sequences=set()
    for r in records:
        assert r['strategy_winrate_eligible'] is False
        selected=r['selected_action'];diag=r['diagnostics']
        assert diag['selected_action']==selected, 'Trace and diagnostic selections differ'
        candidates=[d for d in by_hash[r['public_state_commitment']] if d['sequence']>=last_sequence and d['before']['state']==r['phase']]
        if selected is not None:candidates=[d for d in candidates if d['sequence'] not in selected_sequences and selected_matches(selected,d)]
        if not candidates:
            unresolved.append(r['call']);continue
        d=min(candidates,key=lambda d:d['sequence']);last_sequence=d['sequence']
        if selected is not None:selected_sequences.add(d['sequence'])
        matches.append({'call':r['call'],'decision_sequence':d['sequence'],
            'selected_action_matches':selected is not None,'policy_fallthrough':selected is None})
        for offer in diag.get('offers',[]):
            # Only fixed categories are exported, never freeform text/card identity.
            reason=offer.get('reason','')
            reasons['selected' if offer.get('accepted') else 'unaffordable' if reason=='unaffordable' else 'other_rejection_or_not_selected']+=1
    if complete:assert not unresolved, 'Unmatched diagnostic calls in completed episode'
    return {'audit':'passed' if not unresolved else 'partial_pending_join','records':len(records),
        'joined_calls':len(matches),'selected_action_matches':sum(r['selected_action_matches'] for r in matches),
        'policy_fallthrough_calls':sum(r['policy_fallthrough'] for r in matches),
        'unresolved_calls':unresolved,'distinct_decisions_joined':len({r['decision_sequence'] for r in matches}),
        'offer_reason_categories':dict(reasons),'joins':matches,
        'scope':'Diagnostic calculation provenance, not proof of strategic optimality or exhaustive legal candidates.'}


def audit_session(root,complete=False):
    root=Path(root)
    # Capture traces first: a running writer may append a decision afterwards.
    records,p1=read_rows(root/'shop-candidates.jsonl');decisions,p2=read_rows(root/'decisions.jsonl')
    if complete:assert not p1 and not p2, 'Truncated JSONL in completed episode'
    result=audit_rows(records,decisions,complete)
    result['partial_line_observed']=p1 or p2
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',required=True);p.add_argument('--output',required=True);p.add_argument('--complete',action='store_true');a=p.parse_args()
    result=audit_session(a.session,a.complete)
    Path(a.output).write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='joins'}))
