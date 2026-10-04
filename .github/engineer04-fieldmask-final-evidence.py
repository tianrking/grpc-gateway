import hashlib
import json
import pathlib
import subprocess
import sys

out = pathlib.Path('evidence')
out.mkdir(exist_ok=True)
sources = {'original': '3f5cfae0233af91729798db76a89873d14112323', 'fixed': 'c4f83bea97976ca1f7f84469425b37ca6765bfef'}


def git(root, *args):
    return subprocess.check_output(['git', '-C', root, *args], text=True).strip()


def snapshot(label):
    values = {}
    for root, expected in sources.items():
        files = {}
        for name in git(root, 'ls-files').splitlines():
            data = pathlib.Path(root, name).read_bytes()
            files[name] = {'rawSHA256': hashlib.sha256(data).hexdigest(), 'headBlob': git(root, 'rev-parse', f'HEAD:{name}'), 'actualBlob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}
        value = {'head': git(root, 'rev-parse', 'HEAD'), 'status': git(root, 'status', '--porcelain=v1', '--untracked-files=all'), 'files': files}
        values[root] = value
        if value['head'] != expected or value['status'] or any(f['headBlob'] != f['actualBlob'] for f in files.values()):
            (out / f'source-{label}.json').write_text(json.dumps(values, indent=2))
            raise SystemExit(f'{root} source HEAD/clean/raw blob mismatch')
    if values['original']['files']['runtime/fieldmask_empty_object_test.go'] != values['fixed']['files']['runtime/fieldmask_empty_object_test.go']:
        raise SystemExit('Original/fixed regressions are not exactly identical frozen bytes')
    (out / f'source-{label}.json').write_text(json.dumps(values, indent=2))
    if label == 'after' and values != json.loads((out / 'source-before.json').read_text()):
        raise SystemExit('Native verification modified tracked source')
    print(f'{label}: both exact heads/clean states/all tracked hashes/blobs preserved')


def result(name):
    events = [json.loads(line) for line in (out / f'{name}.jsonl').read_text().splitlines()]
    statuses = {(e['Package'], e['Test']): e['Action'] for e in events if 'Test' in e and e['Action'] in ('pass', 'fail', 'skip')}
    leaves = {f'{pkg}/{name}': action for (pkg, name), action in statuses.items() if not any(other_pkg == pkg and other.startswith(name + '/') for other_pkg, other in statuses)}
    return {'exit': int((out / f'{name}.exit').read_text()), 'leaves': leaves, 'leafPass': sum(a == 'pass' for a in leaves.values()), 'leafFail': sum(a == 'fail' for a in leaves.values()), 'leafSkip': sum(a == 'skip' for a in leaves.values()), 'namedPassEvents': sum(a == 'pass' for a in statuses.values()), 'skipNames': [f'{pkg}/{name}' for (pkg, name), action in statuses.items() if action == 'skip'], 'packages': [e for e in events if 'Test' not in e and e['Action'] in ('pass', 'fail', 'skip')]}


if sys.argv[1] in ('before', 'after'):
    snapshot(sys.argv[1])
else:
    names = ['original-focused', 'fixed-focused', 'full-race']
    if (out / 'unix-integration.exit').exists():
        names.append('unix-integration')
    summary = {name: result(name) for name in names}
    summary['checks'] = {name: int((out / f'{name}.exit').read_text()) for name in ('vet', 'format')}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({name: {key: value for key, value in info.items() if key not in ('leaves', 'packages')} if name != 'checks' else info for name, info in summary.items()}, indent=2))
    original, fixed = summary['original-focused'], summary['fixed-focused']
    if (original['exit'], original['leafFail'], original['leafPass'], original['leafSkip']) != (1, 12, 6, 0):
        raise SystemExit('Original regression RED/control outcomes differ; retain raw evidence')
    if (fixed['exit'], fixed['leafFail'], fixed['leafPass'], fixed['leafSkip']) != (0, 0, 18, 0):
        raise SystemExit('Fixed frozen regression did not pass all18 leaves')
    if any(info['exit'] or info['leafFail'] or any(p['Action'] != 'pass' for p in info['packages']) for name, info in summary.items() if name not in ('original-focused', 'checks')) or any(summary['checks'].values()):
        raise SystemExit('Actual full/native check failed; inspect original logs')
