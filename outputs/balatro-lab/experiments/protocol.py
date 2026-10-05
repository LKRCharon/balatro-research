"""Seed-grouped experiment registry. No game launch, policy training, or test-result tuning.

SQLite lives in work/; public manifests contain commitments, not held-out seeds.
All jobs in a campaign share the same seed blocks across frozen policies.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import datetime
import hashlib
import json
from pathlib import Path
import re
import secrets
import sqlite3

LAB = Path(__file__).resolve().parents[1]
WORK = LAB.parents[1] / 'work'
DEFAULT_DB = WORK / 'experiments/registry.sqlite'
ROLES = ('train', 'validation', 'test')


def canonical(seed):
    value = seed.strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{1,8}', value):
        raise ValueError('Seed must already be a valid 1-8 character game seed; no truncation.')
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@contextmanager
def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        with con:
            yield con
    finally:
        con.close()


def initialize(path, known_seeds, sizes):
    path = Path(path)
    if path.exists():
        raise ValueError('Registry already exists. Do not regenerate a split after observing results.')
    if set(sizes) != set(ROLES) or any(type(n) is not int or n < 1 for n in sizes.values()):
        raise ValueError('All three partition sizes must be positive integers.')
    known = sorted({canonical(s) for s in known_seeds if s})
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as con:
        con.executescript('''
        CREATE TABLE seeds (
          id INTEGER PRIMARY KEY, seed TEXT NOT NULL UNIQUE, commitment TEXT NOT NULL UNIQUE,
          partition TEXT NOT NULL CHECK(partition IN ('train','validation','test')),
          already_seen INTEGER NOT NULL CHECK(already_seen IN (0,1)));
        CREATE TABLE policies (
          id TEXT PRIMARY KEY, name TEXT NOT NULL, manifest TEXT NOT NULL,
          created_utc TEXT NOT NULL);
        CREATE TABLE campaigns (
          id TEXT PRIMARY KEY, partition TEXT NOT NULL, policy_ids TEXT NOT NULL,
          seed_ids TEXT NOT NULL, spec TEXT NOT NULL, created_utc TEXT NOT NULL);
        CREATE UNIQUE INDEX only_one_final_test ON campaigns(partition) WHERE partition='test';
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
          seed_id INTEGER NOT NULL REFERENCES seeds(id), policy_id TEXT NOT NULL REFERENCES policies(id),
          status TEXT NOT NULL DEFAULT 'planned', result TEXT,
          UNIQUE(campaign_id,seed_id,policy_id));
        ''')
        for seed in known:
            con.execute('INSERT INTO seeds(seed,commitment,partition,already_seen) VALUES (?,?,?,1)',
                        (seed, digest(seed), 'train'))
        used = set(known)
        for role in ROLES:
            for _ in range(sizes[role]):
                while True:
                    seed = ''.join(secrets.choice('123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(8))
                    if seed not in used:
                        break
                used.add(seed)
                con.execute('INSERT INTO seeds(seed,commitment,partition,already_seen) VALUES (?,?,?,0)',
                            (seed, digest(seed), role))
    return public_summary(path)


def assert_partition(path, seed, declared_partition):
    with connect(path) as con:
        row = con.execute('SELECT partition FROM seeds WHERE seed=?', (canonical(seed),)).fetchone()
    if row is None or row['partition'] != declared_partition:
        raise ValueError('Seed is unregistered or belongs to a different partition.')


def register_policy(path, name, root, config, context_files=()):
    root = Path(root).resolve()
    files = sorted(p for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                   and p.suffix not in {'.pyc', '.tmp'})
    if not files:
        raise ValueError('A frozen policy needs source files.')
    manifest = {'source_root': str(root), 'config': config,
                'files': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                'context': {str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
                            for p in context_files},
                'engine_certified': False}
    ident = digest(json_text(manifest))
    with connect(path) as con:
        con.execute('INSERT OR IGNORE INTO policies VALUES (?,?,?,?)', (ident, name, json_text(manifest), now()))
    return ident


def verify_policy(con, ident):
    row = con.execute('SELECT manifest FROM policies WHERE id=?', (ident,)).fetchone()
    if not row:
        raise ValueError('Policy must be frozen before scheduling.')
    manifest = json.loads(row['manifest'])
    if digest(json_text(manifest)) != ident:
        raise ValueError('Policy manifest changed.')
    root = Path(manifest['source_root'])
    actual_files = {str(p) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts
                    and p.suffix not in {'.pyc', '.tmp'}}
    if actual_files != set(manifest['files']):
        raise ValueError('Policy file set changed; freeze a new version.')
    for filename, expected in {**manifest['files'], **manifest['context']}.items():
        if not Path(filename).is_file() or hashlib.sha256(Path(filename).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen source or engine context changed; execution refused.')
    return manifest


def schedule(path, role, policy_ids, limit, *, final_test=False):
    if role not in ROLES or type(limit) is not int or limit < 1:
        raise ValueError('Invalid partition or seed count.')
    if role == 'test' and not final_test:
        raise ValueError('Final test requires an explicitly frozen campaign, not tuning.')
    policies = sorted(set(policy_ids))
    if not policies:
        raise ValueError('No policies.')
    with connect(path) as con:
        con.execute('BEGIN IMMEDIATE')
        for ident in policies:
            verify_policy(con, ident)
        if role == 'test' and con.execute("SELECT 1 FROM campaigns WHERE partition='test'").fetchone():
            raise ValueError('Final test already allocated. Reusing it to choose a new policy is forbidden.')
        # Legacy seeds are training only. New campaigns prefer unseen training blocks.
        seeds = con.execute('SELECT id FROM seeds WHERE partition=? ORDER BY already_seen,id LIMIT ?',
                            (role, limit)).fetchall()
        if len(seeds) != limit:
            raise ValueError('Insufficient reserved seeds; do not silently shrink the sample.')
        ids = [s['id'] for s in seeds]
        spec = {'deck': 'BLUE', 'stake': 'GOLD', 'win_ante': 8, 'seed_grouped': True,
                'primary_metric': 'wins / all assigned seed-policy jobs',
                'errors': 'retained as errors, not silently excluded',
                'pairing': 'all policies use all selected seeds; compare paired outcomes',
                'test_use': 'one frozen campaign; no model selection using test results'}
        campaign = digest(json_text({'partition': role, 'policies': policies, 'seeds': ids, 'spec': spec}))
        if con.execute('SELECT 1 FROM campaigns WHERE id=?', (campaign,)).fetchone():
            raise ValueError('Campaign already exists; resume its jobs instead of duplicating evidence.')
        con.execute('INSERT INTO campaigns VALUES (?,?,?,?,?,?)',
                    (campaign, role, json_text(policies), json_text(ids), json_text(spec), now()))
        # Rotate policy order across seed blocks without using the game seed as a policy input.
        for block, seed_id in enumerate(ids):
            ordered = policies[block % len(policies):] + policies[:block % len(policies)]
            for policy_id in ordered:
                job = digest(f'{campaign}:{seed_id}:{policy_id}')
                con.execute('INSERT INTO jobs(id,campaign_id,seed_id,policy_id) VALUES (?,?,?,?)',
                            (job, campaign, seed_id, policy_id))
    return campaign


def claim_job(path, job_id, intended_partition):
    """Backend coordinator only. Never pass returned seed to a decision policy."""
    with connect(path) as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('''SELECT j.*,s.seed,s.partition FROM jobs j JOIN seeds s ON s.id=j.seed_id
                             WHERE j.id=?''', (job_id,)).fetchone()
        if row is None or row['partition'] != intended_partition:
            raise ValueError('A worker cannot consume another partition.')
        if row['status'] != 'planned':
            raise ValueError('Job already claimed/completed; do not overwrite an attempt.')
        verify_policy(con, row['policy_id'])
        con.execute("UPDATE jobs SET status='running' WHERE id=?", (job_id,))
        return {'job_id': job_id, 'seed': row['seed'], 'partition': row['partition'], 'policy_id': row['policy_id']}


def record_result(path, job_id, intended_partition, seed, policy_id, result):
    if result.get('status') not in {'win', 'loss', 'error'}:
        raise ValueError('Result must retain win, loss, or technical error explicitly.')
    with connect(path) as con:
        con.execute('BEGIN IMMEDIATE')
        row = con.execute('''SELECT j.*,s.seed,s.partition FROM jobs j JOIN seeds s ON s.id=j.seed_id
                             WHERE j.id=?''', (job_id,)).fetchone()
        if row is None or (row['partition'], row['seed'], row['policy_id']) != (
                intended_partition, canonical(seed), policy_id):
            raise ValueError('Result partition/seed/policy does not match its assigned job.')
        if row['status'] != 'running':
            raise ValueError('Result is not for an outstanding claimed job.')
        # A technical error is still recorded if source changed while a run was in progress.
        if result['status'] != 'error':
            verify_policy(con, policy_id)
        con.execute('UPDATE jobs SET status=?,result=? WHERE id=?',
                    (result['status'], json_text(result), job_id))


def public_summary(path):
    with connect(path) as con:
        seeds = con.execute('SELECT id,commitment,partition,already_seen FROM seeds ORDER BY id').fetchall()
        rows = [dict(r) for r in seeds]
        campaigns = [dict(r) for r in con.execute('SELECT id,partition,policy_ids,seed_ids,spec FROM campaigns')]
        for c in campaigns:
            for key in ('policy_ids', 'seed_ids', 'spec'):
                c[key] = json.loads(c[key])
        jobs = dict(Counter(r[0] for r in con.execute('SELECT status FROM jobs')))
        versions = [dict(r) for r in con.execute('SELECT id,name,created_utc FROM policies')]
    return {'schema_version': 1, 'counts': dict(Counter(r['partition'] for r in rows)),
            'seen_training_seeds': sum(r['already_seen'] for r in rows),
            'seeds': rows, 'assignment_sha256': digest(json_text(rows)),
            'policies': versions, 'campaigns': campaigns, 'job_status_counts': jobs,
            'final_test_campaign_allocated': any(c['partition'] == 'test' for c in campaigns)}


def collect_legacy_seeds():
    known = []
    for path in (LAB / 'results/cli-runs').glob('run-*-outcome.json'):
        seed = json.loads(path.read_text(encoding='utf-8')).get('seed')
        if seed:
            known.append(seed)
    private = WORK / 'private-seeds.json'
    if private.exists():
        known.extend(json.loads(private.read_text(encoding='utf-8')).values())
    return known


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    for role, n in [('train', 128), ('validation', 64), ('test', 256)]:
        init.add_argument('--' + role, type=int, default=n)
    sub.add_parser('status')
    freeze = sub.add_parser('freeze')
    freeze.add_argument('--name', required=True)
    freeze.add_argument('--source', type=Path, required=True)
    freeze.add_argument('--config', type=Path, required=True)
    freeze.add_argument('--context', type=Path, action='append', default=[])
    plan = sub.add_parser('plan')
    plan.add_argument('--split', choices=ROLES, required=True)
    plan.add_argument('--policy', action='append', required=True)
    plan.add_argument('--seeds', type=int, required=True)
    plan.add_argument('--final-test', action='store_true')
    args = p.parse_args()
    if args.command == 'init':
        report = initialize(args.db, collect_legacy_seeds(), {r: getattr(args, r) for r in ROLES})
    else:
        if args.command == 'freeze':
            ident = register_policy(args.db, args.name, args.source,
                                    json.loads(args.config.read_text(encoding='utf-8')), args.context)
            print(json.dumps({'frozen_policy_id': ident}))
        elif args.command == 'plan':
            campaign = schedule(args.db, args.split, args.policy, args.seeds, final_test=args.final_test)
            print(json.dumps({'planned_campaign': campaign}))
        report = public_summary(args.db)
    target = LAB / 'results/experiment-partitions.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'seeds'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
