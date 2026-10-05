"""One explicit caller-chosen action per invocation; never selects an action itself.

Read {method, params, expected_score?, note?} from stdin. The underlying audited
client records observations/actions; this file adds manual-controller provenance.
"""
import datetime
import json
import sys
import balatro_cli as cli


def main():
    request = json.load(sys.stdin)
    method = request['method']
    before = cli.read(cli.RUNS / 'current.json', {})
    result = cli.call(method, request.get('params', {}))
    session = cli.read(cli.RUNS / 'session.json')
    run = session['run']
    if method == 'start':
        cli.write(cli.RUNS / f'run-{run:02d}-controller.json', {
            'run': run, 'controller': 'LLM manual turn-by-turn',
            'script_policy': False, 'scope': 'Blue / Gold, stop at Ante 8 victory',
            'sampling': session['sampling'], 'resets': False,
            'hidden_information': 'seed and draw order excluded by balatro_cli',
            'skip_prior': 'Consider development tags on opening small blind; prefer later encounters. Unproven prior.',
        })
    entry = {
        'time': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'run': run, 'controller': 'LLM manual turn-by-turn',
        'method': method, 'params': request.get('params', {}),
        'note': request.get('note'), 'expected_score': request.get('expected_score'),
        'ante': before.get('ante_num'), 'round': before.get('round_num'),
    }
    if method == 'play':
        entry['actual_score'] = result.get('round', {}).get('last_hand', {}).get('total')
    with (cli.RUNS / f'run-{run:02d}-manual.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    cli.show(result)


if __name__ == '__main__':
    main()
