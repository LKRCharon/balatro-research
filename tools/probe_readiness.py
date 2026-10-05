"""Administrative mechanics fixture, NOT a policy episode or win-rate result.

Use only a fresh isolated instance and a registered TRAIN seed. Adds two planets
and sets chips/money to isolate synchronization at cash-out and pack boundaries.
"""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'outputs/balatro-lab/headless'))
from transport import RpcClient, RpcError
from isolation import load, verify


def probe(manifest, registry, seed_id, output, *,patched=True):
    if Path(output).exists():raise ValueError('Refusing to overwrite prior mechanism evidence')
    m=load(manifest); verify(m)
    with closing(sqlite3.connect(f'file:{Path(registry).resolve().as_posix()}?mode=ro',uri=True)) as db:
        row=db.execute('SELECT seed, partition, commitment FROM seeds WHERE id=?',(seed_id,)).fetchone()
    if not row or row[1]!='train':raise ValueError('Registered TRAIN seed required')
    report={'kind':'administrative_mechanism_fixture','seed_id':seed_id,
            'seed_commitment':row[2],'patched':patched,'events':[],'passed':False}
    def save():Path(output).write_text(json.dumps(report,indent=2),encoding='utf8')
    with RpcClient(m['port'],timeout=60) as client:
        if client.call('gamestate')['state']!='MENU':raise ValueError('Fresh MENU instance required')
        def call(method,args=None):
            before=time.monotonic()
            try:
                state=client.call(method,args)
                report['events'].append({'method':method,'seconds':time.monotonic()-before,'status':'ok'})
                save();return state
            except RpcError as exc:
                report['events'].append({'method':method,'status':'error','error':str(exc)})
                save();raise
        call('start',{'seed':row[0],'deck':'BLUE','stake':'GOLD'})
        call('select');call('add',{'key':'c_jupiter'})
        call('set',{'chips':1000000,'money':100});call('play',{'cards':[0]})
        state=call('cash_out');level=state['hands']['Flush']['level']
        state=call('use',{'consumable':0}) # Intentionally no intervening poll/sleep.
        assert state['hands']['Flush']['level']==level+1
        assert state['consumables']['count']==0
        report['cashout_planet_exactly_once']=True
        call('add',{'key':'c_saturn'});call('buy',{'pack':0})
        state=call('pack',{'skip':True});level=state['hands']['Straight']['level']
        state=call('use',{'consumable':0}) # Intentionally no intervening poll/sleep.
        assert state['hands']['Straight']['level']==level+1
        assert state['consumables']['count']==0
        report['pack_planet_exactly_once']=True
        if patched:report['readiness']=call('lab_readiness')
        report['passed']=True;save()
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',required=True);p.add_argument('--registry',required=True)
    p.add_argument('--seed-id',type=int,required=True);p.add_argument('--output',required=True)
    p.add_argument('--control',action='store_true');a=p.parse_args()
    print(json.dumps(probe(a.manifest,a.registry,a.seed_id,a.output,patched=not a.control),indent=2))
