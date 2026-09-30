"""Inventory byte-preserving dataset copies; never deserialize dataset files."""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def inventory(root):
    records, cache = [], {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise RuntimeError('Unexpected symlink: ' + p.relative_to(root).as_posix())
        if not p.is_file():
            continue
        stat = p.stat()
        key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        sha = cache.setdefault(key, None)
        if sha is None:
            sha = cache[key] = digest(p)
        after = p.stat()
        if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError('Source changed while hashing: ' + p.name)
        records.append({'path': p.relative_to(root).as_posix(), 'bytes': stat.st_size, 'sha256': sha})
    return records

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--verify', type=Path)
    args = parser.parse_args()
    records = inventory(args.root.resolve())
    if args.verify:
        reference = json.loads(args.verify.read_text(encoding='utf-8'))['files']
        if records != reference:
            expected = {v['path']: v for v in reference}
            actual = {v['path']: v for v in records}
            raise RuntimeError(json.dumps({'missing': sorted(expected.keys() - actual.keys()),
                'extra': sorted(actual.keys() - expected.keys()),
                'changed': [p for p in expected.keys() & actual.keys() if expected[p] != actual[p]]}))
    extensions = collections.defaultdict(lambda: {'files': 0, 'bytes': 0})
    for r in records:
        ext = Path(r['path']).suffix.lower() or '(none)'
        extensions[ext]['files'] += 1
        extensions[ext]['bytes'] += r['bytes']
    summary = {'files': len(records), 'total_bytes': sum(r['bytes'] for r in records),
               'unique_sha256': len({r['sha256'] for r in records}), 'extensions': dict(extensions)}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'schema_version': 'dataset-manifest/1',
            'dataset': 'XJTU-SPS', 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'hash_algorithm': 'sha256', 'summary': summary, 'files': records}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'verification': 'passed' if args.verify else 'inventory_complete', **summary}, ensure_ascii=False))

if __name__ == '__main__':
    main()
