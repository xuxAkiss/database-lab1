"""Generate a source-only handoff inventory; never reads runtime/secrets directories."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
root = Path(__file__).resolve().parents[1]
files = []
allowed_suffixes = {'.py', '.ps1', '.js', '.html', '.css', '.md', '.txt', '.json', '.cfg', '.png'}
for folder in ('backend', 'frontend', 'tests', 'dev', 'docs'):
    for path in (root / folder).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix in allowed_suffixes and path.name != 'baseline-manifest.json':
            files.append(path)
for name in ('README.md', 'requirements.in', 'requirements.txt', '.env.example', '.gitignore', '.gitattributes'):
    files.append(root / name)
rows = [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size,
         'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(files)]
result = {'baseline': 'stage1', 'generated_at': datetime.now(timezone.utc).isoformat(),
          'git': 'See repository history for the uploaded baseline; hashes describe file contents at generation time',
          'excludes': ['.venv', '.local', '.env', 'credentials', '__pycache__', 'database files'],
          'note': 'Manifest excludes itself; deliver listed files plus this manifest.', 'files': rows}
(root / 'docs' / 'baseline-manifest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print('Manifest files:', len(rows))
