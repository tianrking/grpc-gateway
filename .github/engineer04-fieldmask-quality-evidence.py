import hashlib
import json
import pathlib
import re
import subprocess
import sys

out = pathlib.Path('evidence')
out.mkdir(exist_ok=True)
sources = {'baseline/grpc-gateway': 'c9c2765f7df366c9bd8d95de1568aff59341802b', 'fixed/grpc-gateway': 'c4f83bea97976ca1f7f84469425b37ca6765bfef'}


def git(root, *args):
    return subprocess.check_output(['git', '-C', root, *args], text=True).strip()


def snapshot(label):
    values = {}
    for root, expected in sources.items():
        files = {}
        index_paths = git(root, 'ls-files').splitlines()
        head_paths = git(root, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines()
        for name in sorted(set(index_paths) | set(head_paths)):
            data = pathlib.Path(root, name).read_bytes() if pathlib.Path(root, name).exists() else None
            files[name] = {'rawSHA256': hashlib.sha256(data).hexdigest() if data is not None else None, 'headBlob': git(root, 'rev-parse', f'HEAD:{name}'), 'actualBlob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() if data is not None else None}
        value = {'head': git(root, 'rev-parse', 'HEAD'), 'status': git(root, 'status', '--porcelain=v1', '--untracked-files=all'), 'actualGitLsFiles': index_paths, 'actualHeadTrackedPaths': head_paths, 'files': files}
        values[root] = value
    (out / f'source-{label}.json').write_text(json.dumps(values, indent=2))
    for root, value in values.items():
        if value['head'] != sources[root] or (label == 'before' and value['status']) or any(f['headBlob'] != f['actualBlob'] for f in value['files'].values() if f['actualBlob'] is not None):
            raise SystemExit(f'{root} source changed; actual hashes/status retained for diagnosis')
    if label == 'after':
        before = json.loads((out / 'source-before.json').read_text())
        deletions = {}
        for root, value in values.items():
            changed = [name for name, f in value['files'].items() if f != before[root]['files'].get(name)]
            missing = [name for name, f in value['files'].items() if f['actualBlob'] is None]
            if sorted(changed) != sorted(missing) or any(not re.fullmatch(r'examples/internal/clients/.+/BUILD\.bazel', name) for name in missing):
                raise SystemExit('Generator changed files beyond actual allowed client BUILD deletions')
            delta = git(root, 'diff', '--name-status', 'HEAD').splitlines()
            if sorted(delta) != sorted('D\t' + name for name in missing):
                raise SystemExit('Actual generator diff does not match preserved raw missing file set')
            deletions[root] = missing
        if sorted(deletions['baseline/grpc-gateway']) != sorted(deletions['fixed/grpc-gateway']):
            raise SystemExit('Generator deletion set differs between pristine baseline and fixed source')
        (out / 'actual-generation-deletions.json').write_text(json.dumps(deletions, indent=2))
        print('Actual post-generation source delta preserved without restoration:', json.dumps(deletions))
    else:
        print('Before: exact source heads, clean states, every HEAD/index tracked raw hash and blob preserved')


if sys.argv[1] in ('before', 'after'):
    snapshot(sys.argv[1])
else:
    summary = {root: {p.stem: int(p.read_text()) for p in (out / root).glob('*.exit')} for root in ('baseline', 'fixed')}
    (out / 'quality-results.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    expected = {'generation': {'install', 'clean', 'generate', 'tidy', 'generated-diff', 'final-diff'}}[sys.argv[1]]
    optional = {'final-diff'}
    if any(set(results) != expected or any(code for name, code in results.items() if name not in optional) for results in summary.values()):
        raise SystemExit('Actual native quality incomplete or failed; retained baseline/fixed command exits are authoritative')
    print('Generator commands and upstream allowed-deletion diff check passed; final raw diff retains actual client BUILD deletions, source was never restored')
