"""v5 candidate: fair one-draw discard ranking and conservative hand pacing.
Never reads seeds or actual future order. Uses all roots in a common sample batch;
partial batches are discarded, and search fractions are not win probabilities.
"""
import time
import combat_candidate_v4 as prior
old=prior.old
v1=old.v1
a=old.a


def rank_discards(s,options,cfg):
    roots=old.discard_roots(s,options)
    roots=list(dict.fromkeys(tuple(sorted(r)) for r in roots))
    worlds=v1.static.scenarios(s,min(16,max(8,cfg['samples'])))
    totals=[[] for _ in roots];deadline=time.monotonic()+cfg['time_budget']
    quota=(v1.static.boss(s)['score']-s['round']['chips'])/s['round']['hands_left']
    completed=0
    for world in worlds:
        batch=[]
        for indices in roots:
            # Complete at least one balanced sample batch (soft budget).
            if completed and time.monotonic()>deadline:return summarize(roots,totals,quota)
            try:
                after=old.after_discard(s,indices,world)
                value=a.options(after,optimize_order=True)[0][0]
            except ValueError:value=0
            batch.append(value)
        for values,value in zip(totals,batch):values.append(value)
        completed+=1
    return summarize(roots,totals,quota)


def summarize(roots,totals,quota):
    return [{'cards':list(r),'samples':len(v),'mean':sum(v)/len(v),
             'quota_fraction':sum(x>=quota for x in v)/len(v),
             'minimum':min(v)} for r,v in zip(roots,totals) if v]


def choose(state,config=None):
    cfg=v1.config_values(config);s=old.v2.public_state(state)
    if s.get('state')!='SELECTING_HAND':raise ValueError('Combat state required')
    options=a.options(s,optimize_order=True);best=options[0]
    need=v1.static.boss(s)['score']-s['round']['chips']
    lower=a.conservative_score(s,best[1],best[0])
    if lower is not None and lower>=need:
        return v1.action_for(s,'play',best[1],{'mode':'v5_current_model_clear','optimality_claim':False})
    hidden=any(a.st(c).get('hidden') for c in s['hand']['cards'])
    supported=(not hidden and s.get('_belief',{}).get('unseen') and
        not s.get('_belief',{}).get('hidden_identity_approximation') and
        v1.static.boss(s).get('name') in v1.static.SAFE_BOSSES and
        not a.keys(s)&{'j_castle','j_hit_the_road','j_trading','j_burnt','j_yorick'})
    if s['round']['discards_left']>0 and supported:
        rows=rank_discards(s,options,cfg)
        quota=need/s['round']['hands_left']
        last=s['round']['hands_left']==1
        # No extra confidence from an expectation-only immediate clear.
        under_pressure=best[0]<quota or last and (lower is None or lower<need)
        improving=[r for r in rows if r['mean']>best[0]*(1.05 if under_pressure else 1.35)]
        eligible=improving if improving else rows if last and best[0]<need else []
        if eligible:
            row=max(eligible,key=lambda r:(r['quota_fraction'],r['mean'],r['minimum']))
            return v1.action_for(s,'discard',row['cards'],{
                'mode':'v5_balanced_discard_pacing','optimality_claim':False,
                'no_save_load':True,'future_draw_order_used':False,
                'sample_fraction_is_calibrated_probability':False,
                'remaining_score_per_hand':quota,'current_best_score':best[0],
                'under_pressure':under_pressure,'discard_candidates':rows,
                'one_draw_approximation':True,'soft_budget_complete_first_batch':True})
        # Under pressure, avoid the old whole-round lottery choosing junk-heavy
        # low-score plays; if no strict draw improvement exists use current best.
        if under_pressure:
            return v1.action_for(s,'play',best[1],{'mode':'v5_no_strict_discard_improvement',
                'optimality_claim':False,'discard_candidates':rows})
    return prior.choose(s,config)
