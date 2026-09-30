"""Validate the frozen repository export without accepting or replacing evidence."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parent.parent
manifest_name = 'release-manifest.json' if (root / 'release-manifest.json').exists() else 'manifest.json'
ignored = {'.git', 'runs', '__pycache__', 'bin', 'obj'}
if manifest_name == 'manifest.json':
    ignored.add('out')
manifest = json.loads((root / manifest_name).read_text(encoding='utf-8'))
actual = {}
for path in root.rglob('*'):
    relative = path.relative_to(root)
    if any(part in ignored for part in relative.parts):
        continue
    if path.is_symlink():
        raise SystemExit(f'symlink refused: {relative}')
    if path.is_file() and relative.as_posix() != manifest_name:
        actual[relative.as_posix()] = path
expected = {row['path']: row for row in manifest['files']}
if len(expected) != len(manifest['files']) or set(actual) != set(expected):
    raise SystemExit('manifest coverage differs from the export')
for name, path in actual.items():
    if '..' in Path(name).parts or Path(name).is_absolute():
        raise SystemExit('nonrelative manifest path')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != expected[name]['sha256'] or path.stat().st_size != expected[name]['bytes']:
        raise SystemExit(f'file identity differs: {name}')
if any((root / name).exists() for name in ['src', 'unreal', 'source', 'Flight.Core', 'Flight.Host']):
    raise SystemExit('excluded simulator source directory present')
if expected['data/published.sf']['sha256'] != 'b83ad5e6eada4626606e1d5358af97e49a25c102a51b5a8364b3b1efdf0efc56':
    raise SystemExit('frozen recording differs')
print(json.dumps({'files_verified': len(expected), 'frozen_recording': 'unchanged', 'scope': 'file integrity; not public-release approval'}))
