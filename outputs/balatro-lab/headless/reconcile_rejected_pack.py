"""Narrow reconciliation of explicit pack target or purchase affordability errors.

Never invokes gameplay RPC. Requires explicit no-target rejection, same isolated
engine and unchanged public state. The known pack target validation returns
before card use; this is not a general unknown-outcome recovery mechanism.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
from contextlib import contextmanager
from environment import canonical_state,sanitize,LAB
from isolation import load,verify
from transport import RpcClient


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


@contextmanager
def lease(port):
    directory=LAB.parents[1]/'work/headless-port-locks';directory.mkdir(parents=True,exist_ok=True)
    stream=(directory/f'{port}.lock').open('a+b')
    if stream.tell()==0:stream.write(b'0');stream.flush()
    stream.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:stream.close()


def validate_rejection(intent,message):
    params=intent.get('params',{})
    if intent.get('event')=='intent' and intent.get('method')=='buy':
        before=intent['before']
        if before.get('state')!='SHOP' or set(params)-{'pack','reason'} or type(params.get('pack')) is not int:
            raise ValueError('Only a pack purchase affordability rejection is supported')
        card=before['packs']['cards'][params['pack']]
        cost=card['cost']['buy'];money=before['money']
        expected=f'Card is not affordable. Cost: {cost}, Available money: {money}'
        if cost<=money or message!=expected:raise ValueError('Explicit affordability rejection does not match recorded cost and balance')
        return
    if intent.get('event')!='intent' or intent.get('method')!='pack' or 'targets' in params or not params.get('cards'):
        raise ValueError('Only pending malformed pack target requests can be reconciled')
    before=intent['before']
    if before.get('state')!='SMODS_BOOSTER_OPENED':raise ValueError('Not a pack selection')
    card=before['pack']['cards'][params['card']]
    expected=f"Card '{card['key']}' requires exactly 1 target card(s). Provided: 0"
    if message!=expected:raise ValueError('Explicit target validation rejection does not match intent')


def reconcile(session,transition_id,rejection):
    root=Path(session).resolve();path=root/'transitions.jsonl'
    config=json.loads((root/'session.json').read_text(encoding='utf8'))
    manifest=load(config['manifest'])
    if hashlib.sha256(Path(config['manifest']).read_bytes()).hexdigest()!=config['manifest_sha256']:
        raise ValueError('Engine manifest changed')
    for name,expected in manifest['input_hashes'].items():
        if hashlib.sha256((Path(manifest['checkout'])/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Engine input changed')
    with lease(manifest['port']):
        initial=path.read_bytes();rows=[json.loads(line) for line in initial.decode('utf8').splitlines()]
        intent=rows[-1]
        if intent.get('id')!=transition_id:raise ValueError('Wrong pending transition')
        validate_rejection(intent,rejection)
        verify(manifest)
        with RpcClient(manifest['port']) as client:
            after=sanitize(client.call('gamestate'),intent['before'])
        before_hash=digest(canonical_state(intent['before']));after_hash=digest(canonical_state(after))
        if before_hash!=after_hash:raise ValueError('Public state changed; no reconciliation allowed')
        if path.read_bytes()!=initial:raise ValueError('Journal changed during read-only verification')
        proof={'event':'rejection_reconciliation','id':transition_id,'at_utc':time.time(),
            'original_intent_sha256':digest(intent),'explicit_rpc_rejection':rejection,
            'error_provenance':'controller reported explicit RPC rejection; server log records matching '+intent['method']+' ERR',
            'before_public_sha256':before_hash,'after_public_sha256':after_hash,
            'engine_manifest_sha256':config['manifest_sha256'],'method_resent':False,
            'outcome':'rejected_no_mutation','accepted':False,'applied':False,
            'scope':'Known pack target-count or buy affordability guard returns before mutation. Public equality alone is not a general proof about hidden RNG.',
            'controller_origin':'controller'}
        with (root/f'rejection-reconciliation-{transition_id}.json').open('x',encoding='utf8') as out:
            json.dump(proof,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
        # Legacy Environment expects result(id,after) to resolve a pending intent.
        # Explicit rejection fields prevent treating this as an accepted mutation.
        resolution={'event':'result','id':transition_id,'after':after,'controller_origin':'controller',
                    'outcome':'rejected_no_mutation','accepted':False,'applied':False,
                    'reconciliation_record':f'rejection-reconciliation-{transition_id}.json'}
        with path.open('a',encoding='utf8') as out:
            for row in (proof,resolution):out.write(json.dumps(row,ensure_ascii=False)+'\n')
            out.flush();os.fsync(out.fileno())
        return {k:v for k,v in proof.items() if k!='scope'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--session',required=True)
    p.add_argument('--transition-id',type=int,required=True);p.add_argument('--rejection',required=True)
    a=p.parse_args();print(json.dumps(reconcile(a.session,a.transition_id,a.rejection),ensure_ascii=False))
