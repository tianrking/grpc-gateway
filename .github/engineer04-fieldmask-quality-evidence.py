import hashlib
import json
import pathlib
import subprocess
import sys

out = pathlib.Path('evidence')
out.mkdir(exist_ok=True)
sources = {'baseline': 'c9c2765f7df366c9bd8d95de1568aff59341802b', 'fixed': 'c4f83bea97976ca1f7f84469425b37ca6765bfef'}


def git(root, *args):
    return subprocess.check_output(['git', '-C', root, *args], text=True).strip()


def snapshot(label):
    values = {}
    for root, expected in sources.items():
        files = {}
        for name in git(root, 'ls-files').splitlines():
            data = pathlib.Path(root, name).read_bytes() if pathlib.Path(root, name).exists() else None
            files[name] = {'rawSHA256': hashlib.sha256(data).hexdigest() if data is not None else None, 'headBlob': git(root, 'rev-parse', f'HEAD:{name}'), 'actualBlob': hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() if data is not None else None}
        value = {'head': git(root, 'rev-parse', 'HEAD'), 'status': git(root, 'status', '--porcelain=v1', '--untracked-files=all'), 'files': files}
        values[root] = value
    (out / f'source-{label}.json').write_text(json.dumps(values, indent=2))
    for root, value in values.items():
        if value['head'] != sources[root] or value['status'] or any(f['headBlob'] != f['actualBlob'] for f in value['files'].values()):
            raise SystemExit(f'{root} source changed; actual hashes/status retained for diagnosis')
    if label == 'after' and values != json.loads((out / 'source-before.json').read_text()):
        raise SystemExit('Quality/generated/API verification changed source identity')
    print(f'{label}: exact source heads, clean states, all tracked hashes and blobs preserved')


if sys.argv[1] in ('before', 'after'):
    snapshot(sys.argv[1])
else:
    summary = {root: {p.stem: int(p.read_text()) for p in (out / root).glob('*.exit')} for root in sources}
    (out / 'quality-results.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    expected = {'bazel-version', 'install', 'clean', 'generate', 'tidy', 'generated-diff', 'gazelle', 'repositories', 'buildifier', 'bazel-race', 'staticcheck', 'gorelease', 'vet', 'proto-build', 'proto-lint', 'proto-format', 'proto-breaking', 'format', 'final-diff'}
    if any(set(results) != expected or any(results.values()) for results in summary.values()):
        raise SystemExit('Actual native quality incomplete or failed; retained baseline/fixed command exits are authoritative')
