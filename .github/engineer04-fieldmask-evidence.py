import hashlib
import json
import pathlib
import subprocess
import sys

out = pathlib.Path('../evidence')
out.mkdir(exist_ok=True)


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def snapshot(label):
    files = {}
    for name in git('ls-files').splitlines():
        data = pathlib.Path(name).read_bytes()
        files[name] = {
            'rawSHA256': hashlib.sha256(data).hexdigest(),
            'headBlob': git('rev-parse', f'HEAD:{name}'),
            'actualBlob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest(),
        }
    value = {'head': git('rev-parse', 'HEAD'), 'status': git('status', '--porcelain=v1', '--untracked-files=all'), 'files': files}
    (out / f'source-{label}.json').write_text(json.dumps(value, indent=2))
    if value['head'] != '3f5cfae0233af91729798db76a89873d14112323' or value['status']:
        raise SystemExit('Original source HEAD or clean state mismatch')
    if files['runtime/fieldmask.go']['headBlob'] != '12dad6ccbb63510afb6a8697af9823b6a69013ce':
        raise SystemExit('Original production blob mismatch')
    if any(f['headBlob'] != f['actualBlob'] for f in files.values()):
        raise SystemExit('Tracked source raw bytes differ from committed blobs')
    if label == 'after' and value != json.loads((out / 'source-before.json').read_text()):
        raise SystemExit('Source modified by native verification')
    print(f'{label}: {len(files)} tracked files, exact HEAD, clean, raw hashes and blobs preserved')


def result(name):
    events = [json.loads(line) for line in (out / f'{name}.jsonl').read_text().splitlines()]
    statuses = {e['Test']: e['Action'] for e in events if 'Test' in e and e['Action'] in ('pass', 'fail', 'skip')}
    leaves = {name: action for name, action in statuses.items() if not any(other.startswith(name + '/') for other in statuses)}
    return {'exit': int((out / f'{name}.exit').read_text()), 'leaves': leaves, 'passed': sum(a == 'pass' for a in leaves.values()), 'failed': sum(a == 'fail' for a in leaves.values()), 'skipped': sum(a == 'skip' for a in leaves.values()), 'packages': [e for e in events if 'Test' not in e and e['Action'] in ('pass', 'fail', 'skip')]}


if sys.argv[1] in ('before', 'after'):
    snapshot(sys.argv[1])
else:
    focused, controls = result('original-focused'), result('existing-controls')
    summary = {'original': focused, 'existingControls': controls, 'sourceUnchanged': True}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    if (focused['exit'], focused['failed'], focused['passed'], focused['skipped']) != (1, 12, 6, 0):
        raise SystemExit('Actual original outcomes differ from required defect RED and controls; inspect retained raw outputs')
    if controls['exit'] != 0 or controls['failed'] or controls['skipped']:
        raise SystemExit('Existing field mask controls failed or skipped')
