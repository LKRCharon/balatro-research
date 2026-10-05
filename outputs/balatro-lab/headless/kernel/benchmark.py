"""Mechanism-only throughput; never generates full game outcomes or uses study seeds."""
import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import multiprocessing
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
from mechanics import Kernel

def digest(values):
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()

def cases(count):
    rng=random.Random(93920261005)
    suits=['Spades','Hearts','Clubs','Diamonds']
    return [{'cards':[{'rank':v%13+2,'suit':suits[v//13]} for v in rng.sample(range(52),5)],
             'jokers':['Four Fingers'] if i%2 else []} for i in range(count)]

def stream_worker(args):
    source,dll,seed,count=args
    with Kernel(source,dll) as k:
        k.reset(seed)
        return digest([k.pseudoseed('benchmark_stream') for _ in range(count)])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True)
    p.add_argument('--dll',required=True)
    p.add_argument('--count',type=int,default=2000)
    p.add_argument('--output',type=Path,default=Path(__file__).with_name('benchmark.json'))
    args=p.parse_args()
    if args.count<10: p.error('count >= 10 required')
    payload=cases(args.count)
    command=[sys.executable,str(Path(__file__).with_name('mechanics.py')),'--source',args.source,'--dll',args.dll]
    def child(requests):
        started=time.perf_counter()
        result=subprocess.run(command,input=''.join(json.dumps(r)+'\n' for r in requests),text=True,capture_output=True,check=True)
        output=[json.loads(line) for line in result.stdout.splitlines()]
        if len(output)!=len(requests) or any('error' in r for r in output): raise RuntimeError(output)
        return time.perf_counter()-started,[r['result'] for r in output]
    starts=[child([{'method':'reset','params':{'seed':'BENCHMARK_ONLY'}}])[0] for _ in range(5)]
    with Kernel(args.source,args.dll) as k:
        started=time.perf_counter(); expected=[k.classify(**c) for c in payload]
        inproc=time.perf_counter()-started
        k.reset('BENCHMARK_ONLY')
        started=time.perf_counter(); seed_expected=[k.pseudoseed('benchmark_stream') for _ in range(args.count)]
        seed_time=time.perf_counter()-started
        source_hashes=k.hashes
    batched,got=child([{'method':'classify','params':c} for c in payload])
    assert got==expected,'CLI classification differs from in-process'
    seed_cli,seed_got=child([{'method':'reset','params':{'seed':'BENCHMARK_ONLY'}}]+
                         [{'method':'pseudoseed','params':{'key':'benchmark_stream'}}]*args.count)
    assert seed_got[1:]==seed_expected,'CLI seed stream mismatch'
    started=time.perf_counter()
    separate=[child([{'method':'classify','params':c}])[1][0] for c in payload[:10]]
    separate_time=time.perf_counter()-started
    assert separate==expected[:10]
    jobs=[(args.source,args.dll,'MECHANISM_BENCHMARK_'+str(i),args.count) for i in range(4)]
    started=time.perf_counter(); sequential=[stream_worker(j) for j in jobs]; serial=time.perf_counter()-started
    started=time.perf_counter()
    with ProcessPoolExecutor(max_workers=2,mp_context=multiprocessing.get_context('spawn')) as pool:
        parallel=list(pool.map(stream_worker,jobs))
    concurrent=time.perf_counter()-started
    assert parallel==sequential,'Independent process streams are not reproducible'
    result={'scope':'mechanisms only; not game throughput','python':platform.python_version(),
        'source_sha256':source_hashes,'count':args.count,'startup_seconds_samples':starts,
        'startup_seconds_median':statistics.median(starts),
        'classify':{'inprocess_seconds':inproc,'inprocess_per_second':args.count/inproc,
                    'one_process_batched_jsonl_seconds':batched,'batched_per_second':args.count/batched,
                    'ten_separate_processes_seconds':separate_time,'separate_process_per_second':10/separate_time,
                    'result_sha256':digest(expected)},
        'pseudoseed':{'inprocess_seconds':seed_time,'inprocess_per_second':args.count/seed_time,
                      'one_process_batched_jsonl_seconds':seed_cli,'result_sha256':digest(seed_expected),
                      'uses_math_random':False,'full_love_rng_parity_verified':False},
        'process_isolation':{'tasks':4,'workers':2,'sequential_seconds':serial,'parallel_including_spawn_seconds':concurrent,
                             'matching_digests':parallel==sequential},
        'caveat':'Concurrent background training may affect timings; batching avoids process startup but no bulk Lua opcode optimization.'}
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__': main()
